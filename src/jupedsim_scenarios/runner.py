"""High-level helpers for loading and running JuPedSim web-UI scenario JSON files.

A thin scenario layer on top of the simulation primitives in
`utils.simulation_init` and `shared.direct_steering_runtime`. Used by the
trajectory regression test and the `scripts/run_scenario.py` CLI; the
web runtime itself goes through `services.simulation_service`.

This module replaced the previous `backend/core/scenario.py` mirror — see
the chore/drop-core-mirror PR. The longer-term plan is to migrate to
`jupedsim.internal.scenarios` (jupedsim PR #1565) once it lands upstream.

Usage::

    from scenarios import load_scenario, run_scenario

    scenario = load_scenario("scenario.zip")
    print(scenario.summary())

    result = run_scenario(scenario)
    print(result.metrics)

    df = result.trajectory_dataframe()
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import sqlite3
import tempfile
import warnings
import zlib
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from types import MappingProxyType, SimpleNamespace
from typing import Any

import jupedsim as jps
import numpy as np
from shapely import wkt

from .direct_steering_runtime import (
    advance_path_target,
    assign_agent_target,
    check_stage_reached,
    ensure_agent_speed_state,
    extract_agent_xy,
    sample_wait_time,
    set_agent_desired_speed,
    update_checkpoint_speed,
)
from .simulation_init import (
    _find_nearest_exit,
    _random_point_in_polygon,
    _sample_agent_values,
    build_agent_path_state,
    create_agent_parameters,
    initialize_simulation_from_json,
)

# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------

_MODEL_BUILDERS = {
    "CollisionFreeSpeedModel": lambda p: jps.CollisionFreeSpeedModel(
        strength_neighbor_repulsion=p.get("strength_neighbor_repulsion", 2.6),
        range_neighbor_repulsion=p.get("range_neighbor_repulsion", 0.1),
    ),
    "CollisionFreeSpeedModelV2": lambda p: jps.CollisionFreeSpeedModelV2(
        strength_neighbor_repulsion=p.get("strength_neighbor_repulsion", 2.6),
        range_neighbor_repulsion=p.get("range_neighbor_repulsion", 0.1),
    ),
    "CollisionFreeSpeedModelV3": lambda _: jps.CollisionFreeSpeedModelV3(),
    "WarpDriverModel": lambda _: jps.WarpDriverModel(),
      "AnticipationVelocityModel": lambda _: jps.AnticipationVelocityModel(
        #strength_neighbor_repulsion=p.get("strength_neighbor_repulsion", 2.6),
        #range_neighbor_repulsion=p.get("range_neighbor_repulsion", 0.1),
        #anticipation_time=p.get("anticipation_time", 1.0)
    ),
    "GeneralizedCentrifugalForceModel": lambda p: jps.GeneralizedCentrifugalForceModel(
        strength_neighbor_repulsion=p.get("gcfm_strength_neighbor_repulsion", 0.3),
        strength_geometry_repulsion=p.get("gcfm_strength_geometry_repulsion", 0.2),
        max_neighbor_interaction_distance=p.get("gcfm_max_neighbor_interaction_distance", 2.0),
        max_geometry_interaction_distance=p.get("gcfm_max_geometry_interaction_distance", 2.0),
        max_neighbor_repulsion_force=p.get("gcfm_max_neighbor_repulsion_force", 9.0),
        max_geometry_repulsion_force=p.get("gcfm_max_geometry_repulsion_force", 3.0),
    ),
    "SocialForceModel": lambda p: jps.SocialForceModel(
        body_force=p.get("sfm_body_force", 120000),
        friction=p.get("sfm_friction", 240000),
    ),

}

def _build_model(model_type: str, sim_params: dict):
    builder = _MODEL_BUILDERS.get(model_type)
    if builder is None:
        raise ValueError(f"Unknown model type: {model_type}. Available: {list(_MODEL_BUILDERS)}")
    return builder(sim_params)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _stable_flow_rng_offset(flow_dist: dict, fallback_index: int) -> int:
    """Stable per-source seed offset for flow-spawn parameter sampling.

    The offset is derived from the distribution's stable identity
    (``dist_key`` or ``dist_index``) so reordering or adding sources does
    not shift seeds for unrelated sources sharing the same scenario seed.
    """
    dist_key = flow_dist.get("dist_key")
    if dist_key:
        return zlib.crc32(str(dist_key).encode()) % (2**31)
    dist_index = flow_dist.get("dist_index")
    if dist_index is not None:
        return int(dist_index) + 1
    return fallback_index + 1


def _normalize_flow_schedule_entry(entry: dict) -> dict:
    start_time = entry.get("flow_start_time", entry.get("start_time_s"))
    end_time = entry.get("flow_end_time", entry.get("end_time_s"))
    number = entry.get("number", entry.get("sim_count"))

    if start_time is None or end_time is None or number is None:
        raise ValueError(
            "Each flow schedule entry must define start/end time and number. "
            "Accepted keys: flow_start_time|start_time_s, flow_end_time|end_time_s, number|sim_count."
        )

    start_time = float(start_time)
    end_time = float(end_time)
    number = int(number)

    if start_time < 0 or end_time <= start_time:
        raise ValueError(
            f"Invalid flow window [{start_time}, {end_time}] - end_time must be greater than start_time."
        )
    if number <= 0:
        raise ValueError(f"Flow schedule numbers must be positive integers, got {number!r}")

    return {
        "flow_start_time": start_time,
        "flow_end_time": end_time,
        "number": number,
    }


def _normalized_flow_schedule(params: dict) -> list[dict]:
    raw_schedule = params.get("flow_schedule", [])
    if not raw_schedule:
        return []
    normalized = [_normalize_flow_schedule_entry(entry) for entry in raw_schedule]
    normalized.sort(key=lambda entry: (entry["flow_start_time"], entry["flow_end_time"]))
    return normalized


def _distribution_agent_budget(dist: dict) -> int:
    params = dist.get("parameters", {})
    schedule = _normalized_flow_schedule(params)
    if schedule:
        initial_number = int(params.get("initial_number", 0) or 0)
        return initial_number + sum(entry["number"] for entry in schedule)
    return int(params.get("number", 0) or 0)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
# Shared by Scenario setters so each one stays a thin "validate + assign".
# Bounds documented alongside the helper that enforces them — e.g. radius
# is capped at 1.0 m because jupedsim's agent representation breaks down
# beyond that, and desired_speed at 5.0 m/s because typical pedestrian
# free-flow speeds top out around 1.5 m/s and 5 m/s is already well into
# "scenario-author typo" territory.


def _ensure_positive_int(name: str, value: Any) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    return value


def _ensure_positive_number(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be a positive number, got {value!r}")
    return float(value)


def _ensure_non_negative_number(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} must be a non-negative number, got {value!r}")
    return float(value)


def _ensure_in_half_open_range(
    name: str, value: Any, *, lo: float, hi: float, unit: str = ""
) -> float:
    """Validate ``lo < value <= hi``. Used for physical caps (radius, speed)."""
    suffix = f" {unit}" if unit else ""
    if (
        not isinstance(value, (int, float))
        or value <= lo
        or value > hi
    ):
        raise ValueError(
            f"{name} must be in ({lo}, {hi}]{suffix}, got {value!r}"
        )
    return float(value)


def _normalize_polygon_coords(coordinates) -> list[list[float]]:
    """Coerce ``coordinates`` to the closed list-of-[x, y] the schema uses.

    Accepts a shapely ``Polygon`` (in which case the exterior ring is
    used and interiors are dropped — additive ops don't support holes
    on element polygons), or any iterable of length-2 (x, y) pairs.
    The ring is closed automatically if the caller forgot the duplicate
    end point.
    """
    from shapely.geometry import Polygon

    if isinstance(coordinates, Polygon):
        points = list(coordinates.exterior.coords)
    else:
        points = [tuple(p) for p in coordinates]

    if len(points) < 3:
        raise ValueError(
            f"Polygon needs at least 3 distinct points, got {len(points)}."
        )

    for i, pt in enumerate(points):
        if len(pt) != 2:
            raise ValueError(
                f"Polygon coordinate at index {i} must be (x, y), got {pt!r}."
            )

    if points[0] != points[-1]:
        points = points + [points[0]]

    return [[float(x), float(y)] for x, y in points]


def _ensure_choice(name: str, value: Any, choices: set[str]) -> str:
    if value not in choices:
        raise ValueError(
            f"{name} must be one of {sorted(choices)}, got {value!r}"
        )
    return value


def _reject_unknown_kwargs(
    name: str,
    kwargs: dict[str, Any],
    allowed: AbstractSet[str],
) -> None:
    """Raise ``TypeError`` for kwargs outside ``allowed``, suggesting matches.

    A silently-ignored typo (``radius_dist`` instead of
    ``radius_distribution``) used to write a dead key and run a
    scenario with default parameters; this surface it as a build-time
    error with a difflib suggestion.
    """
    import difflib

    unknown = sorted(set(kwargs) - allowed)
    if not unknown:
        return
    hints = []
    for key in unknown:
        suggestion = difflib.get_close_matches(key, allowed, n=1, cutoff=0.6)
        hints.append(
            f"{key!r} (did you mean {suggestion[0]!r}?)"
            if suggestion
            else repr(key)
        )
    raise TypeError(
        f"{name}() received unknown keyword arguments: {', '.join(hints)}. "
        f"Accepted: {sorted(allowed)}"
    )


# Public allow-lists for the kwarg guards on ``set_agent_params`` and
# ``set_model_params``. The agent set is the documented surface plus
# the three deprecated v0* aliases (which warn separately). The model
# set is the union of parameters consumed by any model in
# ``_MODEL_BUILDERS``; cross-model keys are allowed so callers can set
# params before choosing the model.
_AGENT_PARAM_KEYS = frozenset({
    "radius", "radius_distribution", "radius_std",
    "desired_speed", "desired_speed_std", "desired_speed_distribution",
    "v0", "v0_std", "v0_distribution",
    "use_flow_spawning", "flow_start_time", "flow_end_time",
    "distribution_mode", "number",
})
_MODEL_PARAM_KEYS = frozenset({
    "strength_neighbor_repulsion", "range_neighbor_repulsion",
    "gcfm_strength_neighbor_repulsion", "gcfm_strength_geometry_repulsion",
    "gcfm_max_neighbor_interaction_distance",
    "gcfm_max_geometry_interaction_distance",
    "gcfm_max_neighbor_repulsion_force", "gcfm_max_geometry_repulsion_force",
    "sfm_body_force", "sfm_friction",
    "anticipation_time",
})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(repr=False)
class Scenario:
    """A loaded scenario ready for inspection and execution."""

    raw: dict[str, Any]
    walkable_area_wkt: str
    model_type: str
    seed: int
    sim_params: dict[str, Any]
    source_path: str | None = None

    _walkable_polygon: Any = field(default=None, init=False, repr=False)
    _walkable_polygon_key: str | None = field(default=None, init=False, repr=False)

    @property
    def walkable_polygon(self):
        # Re-parse whenever walkable_area_wkt has changed since the last
        # access — keyed on the string itself rather than a __setattr__
        # hook, so direct assignment, .copy() overrides, and setters all
        # invalidate the cache automatically.
        if self._walkable_polygon_key != self.walkable_area_wkt:
            self._walkable_polygon = wkt.loads(self.walkable_area_wkt)
            self._walkable_polygon_key = self.walkable_area_wkt
        return self._walkable_polygon

    @property
    def max_simulation_time(self) -> float:
        return self.sim_params.get("max_simulation_time", 300)

    @max_simulation_time.setter
    def max_simulation_time(self, seconds: float) -> None:
        _ensure_positive_number("max_simulation_time", seconds)
        self.sim_params["max_simulation_time"] = seconds

    # The four properties below expose read-only views over the
    # corresponding sections of ``raw``. The view itself can't be
    # mutated (``s.exits["new"] = {...}`` raises ``TypeError``), so
    # callers can't accidentally bypass the setters' invariants.
    # The nested dicts the view yields are still live and mutable —
    # ``s.distributions[did]["parameters"]["number"] = 5`` still works
    # and is how the setters themselves edit per-element fields.

    @property
    def exits(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(self.raw.get("exits", {}))

    @property
    def distributions(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(self.raw.get("distributions", {}))

    @property
    def stages(self) -> MappingProxyType[str, Any]:
        # The JSON schema (web UI export) calls these "checkpoints";
        # jupedsim's runtime calls them "stages". We surface the runtime
        # vocabulary on the Python API and keep the JSON key as-is so
        # existing exports load unchanged.
        return MappingProxyType(self.raw.get("checkpoints", {}))

    @property
    def zones(self) -> MappingProxyType[str, Any]:
        return MappingProxyType(self.raw.get("zones", {}))

    @property
    def journeys(self) -> list[dict[str, Any]]:
        return self.raw.get("journeys", [])

    def _simulation_settings(self) -> dict[str, Any]:
        config = self.raw.setdefault("config", {})
        return config.setdefault("simulation_settings", {})

    def _simulation_params(self) -> dict[str, Any]:
        settings = self._simulation_settings()
        return settings.setdefault("simulationParams", {})

    def _synced_raw(self) -> dict[str, Any]:
        """Return ``raw`` with seed / model_type / sim_params mirrored in.

        Called immediately before serialization (see ``run_scenario``) so
        the denormalized copy under ``raw["config"]["simulation_settings"]``
        always reflects the current dataclass field values, regardless of
        how they were updated (setters, attribute assignment, dict mutation).
        Mutates ``raw`` in place and returns it for convenience.
        """
        settings = self._simulation_settings()
        settings["baseSeed"] = self.seed
        params = self._simulation_params()
        params.update(self.sim_params)
        params["model_type"] = self.model_type
        return self.raw

    def to_json(self) -> str:
        """Serialize the scenario as self-contained JSON.

        Returns the JSON string. To write to disk, use
        :func:`save_scenario` (mirrors :func:`load_scenario`).

        The output embeds ``walkable_area_wkt`` at the top level so
        :func:`load_scenario` can read it back via the
        self-contained-JSON branch — completing the build → run →
        persist loop introduced by R2.1's ``add_*`` methods.

        Round-trip is value-preserving for everything the public API
        touches (geometry, seed, model_type, sim_params, exits,
        distributions, stages, zones, journeys) provided every value
        is JSON-serializable. The default :func:`json.dumps` encoder
        is used with no fallback, so an unsupported type stuffed into
        ``scenario.raw`` (or ``sim_params``) raises ``TypeError`` at
        save time rather than silently stringifying — surfacing the
        mistake before the round-trip lies about what was preserved.
        """
        data = dict(self._synced_raw())
        data["walkable_area_wkt"] = self.walkable_area_wkt
        return json.dumps(data, indent=2)

    def _total_agents(self) -> int:
        return sum(
            _distribution_agent_budget(d) for d in self.distributions.values()
        )

    def __repr__(self) -> str:
        # One-line, autocomplete-friendly debug repr. The default
        # dataclass repr dumps `raw` (often a multi-kilobyte JSON dict)
        # which is unreadable in a notebook cell or a stack trace.
        return (
            f"Scenario(model={self.model_type!r}, seed={self.seed}, "
            f"agents≈{self._total_agents()}, exits={len(self.exits)}, "
            f"distributions={len(self.distributions)}, "
            f"stages={len(self.stages)}, zones={len(self.zones)})"
        )

    def _repr_html_(self) -> str:
        """Notebook-friendly summary table (Jupyter calls this automatically)."""
        rows = [
            ("Source", self.source_path or "(in-memory)"),
            ("Model", self.model_type),
            ("Seed", self.seed),
            ("Max time", f"{self.max_simulation_time}s"),
            ("Exits", len(self.exits)),
            ("Distributions", len(self.distributions)),
            ("Stages", len(self.stages)),
            ("Zones", len(self.zones)),
            ("Journeys", len(self.journeys)),
            ("Agents", f"~{self._total_agents()}"),
        ]
        body = "".join(
            f"<tr><th style='text-align:left;padding-right:1em'>{k}</th>"
            f"<td>{v}</td></tr>"
            for k, v in rows
        )
        return (
            "<table style='border-collapse:collapse'>"
            "<caption style='text-align:left;font-weight:bold'>Scenario</caption>"
            f"{body}</table>"
        )

    def summary(self) -> str:
        total_agents = self._total_agents()
        journey_sequence = []
        journeys = self.raw.get("journeys", [])
        if journeys:
            journey_sequence = list(journeys[0].get("stages", []))
        lines = [
            f"Scenario: {self.source_path or '(in-memory)'}",
            f"  Model:         {self.model_type}",
            f"  Seed:          {self.seed}",
            f"  Max time:      {self.max_simulation_time}s",
            f"  Exits:         {len(self.exits)}",
            f"  Distributions: {len(self.distributions)}",
            f"  Stages:        {len(self.stages)}",
            f"  Zones:         {len(self.zones)}",
            f"  Journeys:      {len(self.journeys)}",
            f"  Agents:        ~{total_agents}",
        ]
        if journey_sequence:
            checkpoint_count = sum(
                stage.startswith("jps-checkpoints_") for stage in journey_sequence
            )
            exit_count = sum(stage.startswith("jps-exits_") for stage in journey_sequence)
            distribution_count = sum(
                stage.startswith("jps-distributions_") for stage in journey_sequence
            )
            lines.append(f"  Journey elems: {len(journey_sequence)}")
            lines.append(
                "  Route:         "
                f"{distribution_count} distribution, "
                f"{checkpoint_count} checkpoint, "
                f"{exit_count} exit"
            )
            lines.append(f"  Sequence:      {' -> '.join(journey_sequence)}")
        for dist_id, dist in self.distributions.items():
            params = dist.get("parameters", {})
            flow = params.get("use_flow_spawning", False)
            n = params.get("number", "?")
            tag = f" (flow: {params.get('flow_start_time', 0)}-{params.get('flow_end_time', 10)}s)" if flow else ""
            lines.append(f"    {dist_id}: {n} agents{tag}")
        return "\n".join(lines)

    def plot(self, ax=None):
        """Plot the scenario geometry with labeled distributions, exits, zones, and checkpoints.

        Returns the matplotlib Axes so callers can further customise the figure.
        """
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPolygon

        if ax is None:
            _, ax = plt.subplots(figsize=(12, 7), constrained_layout=True)

        # Walkable area (exterior + interior holes as walls)
        from matplotlib.patches import PathPatch
        from matplotlib.path import Path as MplPath

        exterior_coords = list(self.walkable_polygon.exterior.coords)
        codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(exterior_coords) - 2) + [MplPath.CLOSEPOLY]
        verts = list(exterior_coords)

        for interior in self.walkable_polygon.interiors:
            hole_coords = list(interior.coords)
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(hole_coords) - 2) + [MplPath.CLOSEPOLY]
            verts += list(hole_coords)

        path = MplPath(verts, codes)
        patch = PathPatch(path, facecolor="#f0f0ec", edgecolor="#3a3a3a",
                          linewidth=1.5, alpha=0.5, zorder=0)
        ax.add_patch(patch)

        # Draw wall outlines explicitly
        wx, wy = self.walkable_polygon.exterior.xy
        ax.plot(wx, wy, color="#3a3a3a", linewidth=1.5, zorder=1)
        for interior in self.walkable_polygon.interiors:
            ix, iy = interior.xy
            ax.plot(ix, iy, color="#3a3a3a", linewidth=1.5, zorder=1)

        palette = {
            "distribution": "#2563EB",
            "exit": "#DC2626",
            "zone": "#059669",
            "checkpoint": "#D97706",
        }

        def _plot_element(coords, color, label, alpha=0.35):
            poly = MplPolygon(coords[:-1], closed=True, facecolor=color,
                              edgecolor=color, alpha=alpha, linewidth=1.5, zorder=2)
            ax.add_patch(poly)
            cx = sum(c[0] for c in coords[:-1]) / max(len(coords) - 1, 1)
            cy = sum(c[1] for c in coords[:-1]) / max(len(coords) - 1, 1)
            ax.text(cx, cy, label, ha="center", va="center",
                    fontsize=8, fontweight="bold", color=color, zorder=3)

        for i, d in enumerate(self.distributions.values()):
            n = _distribution_agent_budget(d)
            _plot_element(d["coordinates"], palette["distribution"],
                          f"D{i}\n({n} ag)")

        for i, e in enumerate(self.exits.values()):
            _plot_element(e["coordinates"], palette["exit"], f"E{i}", alpha=0.5)

        for i, z in enumerate(self.zones.values()):
            sf = z.get("speed_factor", 1.0)
            _plot_element(z["coordinates"], palette["zone"],
                          f"Z{i}\n(sf={sf})", alpha=0.25)

        for i, s in enumerate(self.stages.values()):
            wt = s.get("waiting_time", 0.0)
            _plot_element(s["coordinates"], palette["checkpoint"],
                          f"C{i}\n(w={wt}s)", alpha=0.3)

        # Legend
        from matplotlib.patches import Patch
        handles = []
        if self.distributions:
            handles.append(Patch(facecolor=palette["distribution"], alpha=0.35, label="Distribution"))
        if self.exits:
            handles.append(Patch(facecolor=palette["exit"], alpha=0.5, label="Exit"))
        if self.zones:
            handles.append(Patch(facecolor=palette["zone"], alpha=0.25, label="Zone"))
        if self.stages:
            handles.append(Patch(facecolor=palette["checkpoint"], alpha=0.3, label="Checkpoint"))
        if handles:
            ax.legend(handles=handles, loc="best", frameon=False, fontsize=9)

        ax.set_aspect("equal")
        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
        ax.set_title(f"Scenario: {self.source_path or '(in-memory)'}", pad=10)
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        return ax

    # -- resolver helpers (private) -----------------------------------------

    @staticmethod
    def _resolve_key(
        kind: str, bucket: MappingProxyType[str, Any] | dict[str, Any],
        id_or_index: int | str,
    ) -> str:
        """Shared int-or-string resolver for the collection lookups.

        ``kind`` is used only for error messages
        (``"Distribution"`` / ``"Exit"`` / ``"Zone"`` / ``"Stage"``).
        """
        if isinstance(id_or_index, int):
            keys = list(bucket.keys())
            if id_or_index < 0 or id_or_index >= len(keys):
                raise IndexError(
                    f"{kind} index {id_or_index} out of range. "
                    f"Available indices: 0..{len(keys) - 1}"
                )
            return keys[id_or_index]
        if id_or_index not in bucket:
            raise KeyError(
                f"{kind} {id_or_index!r} not found. "
                f"Available: {list(bucket.keys())}"
            )
        return id_or_index

    def _resolve_distribution_id(self, id_or_index: int | str) -> str:
        return self._resolve_key("Distribution", self.distributions, id_or_index)

    def _resolve_exit_id(self, id_or_index: int | str) -> str:
        return self._resolve_key("Exit", self.exits, id_or_index)

    def _resolve_zone_id(self, id_or_index: int | str) -> str:
        return self._resolve_key("Zone", self.zones, id_or_index)

    def _resolve_stage_id(self, id_or_index: int | str) -> str:
        return self._resolve_key("Stage", self.stages, id_or_index)

    # -- additive ops --------------------------------------------------------
    # Mirror the web-UI JSON schema under the hood so loaded scenarios can
    # be extended without cracking open `raw`. Each ``add_*`` returns the
    # assigned id; each ``remove_*`` pops by id. IDs are auto-generated
    # along the schema's ``jps-{collection}_{n}`` convention if not given.

    def add_distribution(
        self,
        coordinates,
        *,
        key: str | None = None,
        number: int = 10,
        **agent_params,
    ) -> str:
        """Add a spawn distribution. Returns its id.

        ``coordinates`` accepts a shapely ``Polygon`` or any iterable of
        ``(x, y)`` pairs. The polygon is automatically closed.
        ``key`` picks a specific id; ``None`` auto-generates one
        as ``jps-distributions_{n}``. Extra keyword arguments are
        validated through the same allow-list as ``set_agent_params``
        so typos surface immediately.
        """
        coords = _normalize_polygon_coords(coordinates)
        _ensure_positive_int("number", number)
        # Reuse the agent-params allow-list + speed-alias migration so
        # add_distribution behaves consistently with set_agent_params.
        _reject_unknown_kwargs("add_distribution", agent_params, _AGENT_PARAM_KEYS)
        agent_params = self._migrate_speed_aliases(agent_params)
        dist_id = self._allocate_id("distributions", key)
        params = {"number": number, "distribution_mode": "by_number"}
        params.update(agent_params)
        self.raw.setdefault("distributions", {})[dist_id] = {
            "type": "polygon",
            "coordinates": coords,
            "parameters": params,
            "journey_weights": [],
        }
        return dist_id

    def add_exit(
        self,
        coordinates,
        *,
        key: str | None = None,
        max_throughput: float = 0.0,
    ) -> str:
        """Add an exit polygon. Returns its id."""
        coords = _normalize_polygon_coords(coordinates)
        _ensure_non_negative_number("max_throughput", max_throughput)
        exit_id = self._allocate_id("exits", key)
        self.raw.setdefault("exits", {})[exit_id] = {
            "type": "polygon",
            "coordinates": coords,
            "enable_throughput_throttling": max_throughput > 0,
            "max_throughput": max_throughput,
        }
        return exit_id

    def add_zone(
        self,
        coordinates,
        *,
        key: str | None = None,
        speed_factor: float = 1.0,
    ) -> str:
        """Add a speed-modifier zone. Returns its id."""
        coords = _normalize_polygon_coords(coordinates)
        _ensure_non_negative_number("speed_factor", speed_factor)
        zone_id = self._allocate_id("zones", key)
        self.raw.setdefault("zones", {})[zone_id] = {
            "type": "polygon",
            "coordinates": coords,
            "speed_factor": speed_factor,
        }
        return zone_id

    def add_stage(
        self,
        coordinates,
        *,
        key: str | None = None,
        waiting_time: float = 0.0,
    ) -> str:
        """Add a waypoint / checkpoint stage. Returns its id.

        The web-UI JSON calls these "checkpoints"; the Python API uses
        "stage" to match jupedsim's runtime vocabulary. ``raw`` keeps
        the JSON name, so existing web exports load unchanged.
        """
        coords = _normalize_polygon_coords(coordinates)
        _ensure_non_negative_number("waiting_time", waiting_time)
        stage_id = self._allocate_id("checkpoints", key)
        self.raw.setdefault("checkpoints", {})[stage_id] = {
            "type": "polygon",
            "coordinates": coords,
            "waiting_time": waiting_time,
        }
        return stage_id

    def remove_distribution(self, key: int | str) -> None:
        key = self._resolve_distribution_id(key)
        self.raw["distributions"].pop(key)

    def remove_exit(self, key: int | str) -> None:
        key = self._resolve_exit_id(key)
        self.raw["exits"].pop(key)

    def remove_zone(self, key: int | str) -> None:
        key = self._resolve_zone_id(key)
        self.raw["zones"].pop(key)

    def remove_stage(self, key: int | str) -> None:
        key = self._resolve_stage_id(key)
        self.raw["checkpoints"].pop(key)

    _RAW_KEY_BY_COLLECTION = {
        "distributions": "distributions",
        "exits": "exits",
        "zones": "zones",
        "checkpoints": "checkpoints",
    }

    def _allocate_id(self, collection: str, requested: str | None) -> str:
        """Return a free id for ``collection`` (e.g. 'distributions')."""
        bucket = self.raw.setdefault(self._RAW_KEY_BY_COLLECTION[collection], {})
        if requested is not None:
            if requested in bucket:
                raise ValueError(
                    f"id {requested!r} already exists in {collection!r}; "
                    "remove it first or pick another id."
                )
            return requested
        # Match the web UI's naming so round-trips look natural.
        prefix = f"jps-{collection}_"
        used_indices: list[int] = []
        for key in bucket:
            if key.startswith(prefix):
                tail = key[len(prefix):]
                if tail.isdigit():
                    used_indices.append(int(tail))
        next_index = (max(used_indices) + 1) if used_indices else 0
        return f"{prefix}{next_index}"

    # -- discovery methods ---------------------------------------------------

    def list_distributions(self) -> list[dict]:
        """Return a list of ``{"index", "id", "agents", "flow"}`` dicts."""
        result = []
        for i, (did, d) in enumerate(self.distributions.items()):
            params = d.get("parameters", {})
            result.append({
                "index": i,
                "id": did,
                "agents": _distribution_agent_budget(d),
                "flow": params.get("use_flow_spawning", False) or bool(params.get("flow_schedule")),
            })
        return result

    def list_zones(self) -> list[dict]:
        """Return a list of ``{"index", "id", "speed_factor"}`` dicts."""
        result = []
        for i, (zid, z) in enumerate(self.zones.items()):
            result.append({
                "index": i,
                "id": zid,
                "speed_factor": z.get("speed_factor", 1.0),
            })
        return result

    def list_stages(self) -> list[dict]:
        """Return a list of ``{"index", "id", "waiting_time"}`` dicts."""
        result = []
        for i, (sid, s) in enumerate(self.stages.items()):
            result.append({
                "index": i,
                "id": sid,
                "waiting_time": s.get("waiting_time", 0.0),
            })
        return result

    # -- copy ----------------------------------------------------------------

    def copy(self) -> Scenario:
        """Return an independent deep copy of this scenario.

        The clone shares no mutable state with the original — mutating
        the clone (adding distributions, changing the seed, etc.) does
        not affect the source. Used internally by ``run_sweep`` to
        isolate per-trial scenarios.

        For a copy with one or two fields changed, copy first then
        assign::

            clone = base.copy()
            clone.seed = 99
            clone.max_simulation_time = 60
        """
        import copy

        return copy.deepcopy(self)

    # -- setters -------------------------------------------------------------

    def set_agent_count(self, distribution_id: int | str, count: int):
        """Switch a distribution to by-number spawning with ``count`` agents.

        Sets ``number=count`` AND unconditionally forces
        ``distribution_mode="by_number"`` — so a distribution previously
        configured as ``by_density`` will be flipped. If you want to
        update the count without changing the spawning mode, call
        ``set_agent_params(id, number=count)`` directly.
        """
        self.set_agent_params(distribution_id, number=count)
        # Force distribution_mode regardless of what set_agent_params would
        # have done — this setter's contract is "use by-number spawning".
        did = self._resolve_distribution_id(distribution_id)
        self.distributions[did]["parameters"]["distribution_mode"] = "by_number"

    # set_seed / set_max_time / set_model_type were removed in 0.5 —
    # write the fields directly. ``raw`` is mirrored lazily via
    # ``_synced_raw()`` at serialization time, so the previous eager
    # mirror in those setters became dead weight.
    #
    #   scenario.seed = 42
    #   scenario.max_simulation_time = 60        # validates positive
    #   scenario.model_type = "CollisionFreeSpeedModel"

    def set_model_params(self, **kwargs):
        """Set model-specific parameters (e.g. strength_neighbor_repulsion, range_neighbor_repulsion)."""
        _reject_unknown_kwargs("set_model_params", kwargs, _MODEL_PARAM_KEYS)
        for key, value in kwargs.items():
            if isinstance(value, (int, float)):
                _ensure_non_negative_number(f"model parameter {key!r}", value)
        self.sim_params.update(kwargs)
        self._simulation_params().update(kwargs)

    def set_agent_params(self, distribution_id: int | str, **kwargs):
        """Set agent parameters for a distribution.

        Supported keys: ``radius``, ``desired_speed``, ``radius_distribution``,
        ``radius_std``, ``desired_speed_distribution``, ``desired_speed_std``,
        ``use_flow_spawning``, ``flow_start_time``, ``flow_end_time``,
        ``distribution_mode``, ``number``.

        ``v0``, ``v0_std``, and ``v0_distribution`` are accepted as
        deprecated aliases for the ``desired_speed*`` keys and emit a
        ``DeprecationWarning``. They will be removed in a future release.
        """
        distribution_id = self._resolve_distribution_id(distribution_id)
        _reject_unknown_kwargs("set_agent_params", kwargs, _AGENT_PARAM_KEYS)
        kwargs = self._migrate_speed_aliases(kwargs)
        speed_value = kwargs.get("desired_speed")
        speed_std_value = kwargs.get("desired_speed_std")
        speed_dist_value = kwargs.get("desired_speed_distribution")
        if "radius" in kwargs:
            _ensure_in_half_open_range(
                "radius", kwargs["radius"], lo=0, hi=1.0, unit="m"
            )
        if speed_value is not None:
            _ensure_in_half_open_range(
                "desired_speed", speed_value, lo=0, hi=5.0, unit="m/s"
            )
        if speed_std_value is not None:
            _ensure_non_negative_number("desired_speed_std", speed_std_value)
        if speed_dist_value is not None:
            _ensure_choice(
                "desired_speed_distribution",
                speed_dist_value,
                {"constant", "gaussian"},
            )
        if "number" in kwargs:
            _ensure_positive_int("number", kwargs["number"])
        dist = self.distributions[distribution_id]
        params = dist.setdefault("parameters", {})
        params.update(kwargs)
        # Mirror the canonical desired_speed* values into the legacy v0*
        # keys for one release so the downstream consumers in
        # simulation_init (and any third-party tooling that still reads
        # raw JSON exports) keep working. The mirror itself goes away
        # together with the deprecated kwargs.
        if speed_value is not None:
            params["v0"] = speed_value
        if speed_std_value is not None:
            params["v0_std"] = speed_std_value
        if speed_dist_value is not None:
            params["v0_distribution"] = speed_dist_value

    @staticmethod
    def _migrate_speed_aliases(kwargs: dict[str, Any]) -> dict[str, Any]:
        """Translate deprecated ``v0*`` kwargs onto their ``desired_speed*`` keys.

        Returns a new dict so the caller's kwargs aren't mutated. Raises
        ``TypeError`` if the user passes both spellings with different
        values — silent precedence would lose data.
        """
        aliases = {
            "v0": "desired_speed",
            "v0_std": "desired_speed_std",
            "v0_distribution": "desired_speed_distribution",
        }
        migrated = dict(kwargs)
        for old, new in aliases.items():
            if old not in migrated:
                continue
            warnings.warn(
                f"{old!r} is deprecated; use {new!r} instead.",
                DeprecationWarning,
                stacklevel=3,
            )
            value = migrated.pop(old)
            if new in migrated and migrated[new] != value:
                raise TypeError(
                    f"Got conflicting values for {new!r} (={migrated[new]!r}) "
                    f"and deprecated alias {old!r} (={value!r}); pass only {new!r}."
                )
            migrated.setdefault(new, value)
        return migrated

    def set_flow_schedule(
        self,
        distribution_id: int | str,
        schedule: list[dict],
        *,
        keep_initial_agents: bool = False,
    ):
        """Attach a time-windowed inflow schedule to one source distribution."""
        distribution_id = self._resolve_distribution_id(distribution_id)
        if not isinstance(schedule, list) or not schedule:
            raise ValueError("schedule must be a non-empty list of flow schedule entries")

        normalized_schedule = [_normalize_flow_schedule_entry(entry) for entry in schedule]
        normalized_schedule.sort(key=lambda entry: (entry["flow_start_time"], entry["flow_end_time"]))

        dist = self.distributions[distribution_id]
        params = dist.setdefault("parameters", {})

        if keep_initial_agents:
            params["initial_number"] = int(params.get("number", 0) or 0)
        else:
            params.pop("initial_number", None)

        params["flow_schedule"] = normalized_schedule
        params["use_flow_spawning"] = True
        params["distribution_mode"] = "by_number"
        params["number"] = sum(entry["number"] for entry in normalized_schedule)
        params["flow_start_time"] = normalized_schedule[0]["flow_start_time"]
        params["flow_end_time"] = normalized_schedule[-1]["flow_end_time"]

    def set_zone_speed_factor(self, zone_id: int | str, factor: float):
        """Set the speed factor for a zone."""
        zone_id = self._resolve_zone_id(zone_id)
        _ensure_non_negative_number("factor", factor)
        self.zones[zone_id]["speed_factor"] = factor

    def set_checkpoint_waiting_time(self, checkpoint_id: int | str, waiting_time: float):
        """Set the waiting time for a checkpoint/stage."""
        checkpoint_id = self._resolve_stage_id(checkpoint_id)
        _ensure_non_negative_number("waiting_time", waiting_time)
        self.stages[checkpoint_id]["waiting_time"] = waiting_time


@dataclass
class ScenarioResult:
    """Results from running a scenario."""

    metrics: dict[str, Any]
    sqlite_file: str | None = None

    @property
    def success(self) -> bool:
        return self.metrics.get("success", False)

    @property
    def evacuation_time(self) -> float:
        return self.metrics.get("evacuation_time", 0.0)

    @property
    def total_agents(self) -> int:
        return self.metrics.get("total_agents", 0)

    @property
    def agents_evacuated(self) -> int:
        return self.metrics.get("agents_evacuated", 0)

    @property
    def agents_remaining(self) -> int:
        return self.metrics.get("agents_remaining", 0)

    @property
    def frame_rate(self) -> float:
        """Trajectory frame rate (Hz), computed from the writer stride and dt
        at simulation time. KeyError if the metrics dict doesn't have it —
        that's a runner bug, not something to paper over with a default.
        """
        return self.metrics["frame_rate"]

    @property
    def dt(self) -> float:
        """Simulation timestep in seconds, as reported by jupedsim."""
        return self.metrics["dt"]

    @property
    def seed(self) -> int:
        """Random seed used for this run."""
        return self.metrics.get("seed", 0)

    @property
    def walkable_polygon(self):
        """Walkable area as a Shapely Polygon (for pedpy analysis)."""
        return self.metrics.get("walkable_polygon")

    def trajectory_dataframe(self):
        """Load trajectory data into a pandas DataFrame.

        Columns: frame, id, x, y, ori_x, ori_y
        """
        import pandas as pd

        if not self.sqlite_file or not os.path.exists(self.sqlite_file):
            raise FileNotFoundError("No trajectory SQLite file available")

        con = sqlite3.connect(self.sqlite_file)
        try:
            df = pd.read_sql_query(
                "SELECT frame, id, pos_x AS x, pos_y AS y, ori_x, ori_y FROM trajectory_data",
                con,
            )
        finally:
            con.close()
        return df

    def as_pedpy_trajectory(self):
        """Return the trajectory as a ``pedpy.TrajectoryData``.

        Thin adapter so scientists doing pedpy analysis don't have to
        rebuild the dataframe and look up the frame rate themselves::

            result = run_scenario(scenario, seed=42)
            traj = result.as_pedpy_trajectory()
            pedpy.compute_classic_density(traj=traj, ...)

        pedpy is already a hard dependency of this package (used
        internally for ``WalkableArea`` etc.) so the import is direct.
        """
        import pedpy

        df = self.trajectory_dataframe()
        # pedpy only needs id, frame, x, y. The orientation columns
        # would be silently ignored, but slicing keeps the contract
        # tight and avoids surprises if pedpy ever tightens its schema.
        return pedpy.TrajectoryData(
            data=df[["id", "frame", "x", "y"]],
            frame_rate=self.frame_rate,
        )

    def cleanup(self) -> int:
        """Delete the temporary SQLite trajectory file.

        Returns the number of files removed (0 or 1) so callers and
        ``SweepResult.cleanup`` can report totals without re-checking.
        """
        if self.sqlite_file and os.path.exists(self.sqlite_file):
            os.unlink(self.sqlite_file)
            self.sqlite_file = None
            return 1
        return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_scenario(path: str) -> Scenario:
    """Load a scenario from a ZIP archive, a directory, or a self-contained JSON file.

    Three input shapes are supported:

    * **Directory** — contains one ``*.json`` and one ``*.wkt`` file.
    * **ZIP archive** — same two files packed together.
    * **Self-contained JSON** — a single ``.json`` file whose top-level
      object embeds the walkable geometry as ``"walkable_area_wkt"``.
      This is what the CLI consumes.
    """
    resolved = pathlib.Path(path).resolve()

    if resolved.is_dir():
        data, walkable_wkt = _load_scenario_from_dir(resolved)
    elif resolved.suffix.lower() == ".json":
        data, walkable_wkt = _load_scenario_from_self_contained_json(resolved)
    else:
        data, walkable_wkt = _load_scenario_from_zip(resolved)

    sim_settings = data.get("config", {}).get("simulation_settings", {})
    sim_params = sim_settings.get("simulationParams", {})
    model_type = sim_params.get("model_type", data.get("model_type", "CollisionFreeSpeedModel"))
    seed = data.get("seed", sim_settings.get("baseSeed", 42))

    sim_params.setdefault("max_simulation_time", 300)

    return Scenario(
        raw=data,
        walkable_area_wkt=walkable_wkt,
        model_type=model_type,
        seed=seed,
        sim_params=sim_params,
        source_path=str(resolved),
    )


def save_scenario(scenario: Scenario, path: str | pathlib.Path) -> None:
    """Write ``scenario`` to ``path`` as self-contained JSON.

    Side-effecting counterpart to :meth:`Scenario.to_json` (which
    returns the JSON as a string), mirroring :func:`load_scenario`.
    Parent directories are created if missing.
    """
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(scenario.to_json(), encoding="utf-8")


def _exactly_one(candidates: list, *, kind: str, where: str) -> Any:
    """Pick the sole candidate from ``candidates`` or raise on 0 / >1.

    Refuses to silently choose between multiple matches — a scenario
    folder or archive that holds more than one ``*.json`` / ``*.wkt``
    is ambiguous, and picking the first sorted entry hides the user's
    actual intent.
    """
    if not candidates:
        raise ValueError(f"{where}: no {kind} found.")
    if len(candidates) > 1:
        raise ValueError(
            f"{where}: expected exactly one {kind}, found {len(candidates)}: "
            f"{[str(c) for c in candidates]}. Trim the extras or load the "
            "intended file directly."
        )
    return candidates[0]


def _load_scenario_from_dir(resolved: pathlib.Path) -> tuple[dict, str]:
    json_files = sorted(resolved.glob("*.json"))
    wkt_files = sorted(resolved.glob("*.wkt"))
    json_path = _exactly_one(json_files, kind="*.json file", where=str(resolved))
    wkt_path = _exactly_one(wkt_files, kind="*.wkt file", where=str(resolved))
    data = json.loads(json_path.read_text(encoding="utf-8"))
    walkable_wkt = wkt_path.read_text(encoding="utf-8").strip()
    return data, walkable_wkt


def _load_scenario_from_zip(resolved: pathlib.Path) -> tuple[dict, str]:
    import zipfile

    try:
        zf_ctx = zipfile.ZipFile(resolved)
    except zipfile.BadZipFile as exc:
        # Surface as ValueError so the CLI's existing handler converts
        # it to a friendly exit-2 instead of a Python traceback.
        raise ValueError(f"{resolved}: not a valid ZIP archive ({exc}).") from exc

    with zf_ctx as zf:
        names = zf.namelist()
        json_names = [n for n in names if n.endswith(".json")]
        wkt_names = [n for n in names if n.endswith(".wkt")]
        json_name = _exactly_one(json_names, kind="*.json entry", where=str(resolved))
        wkt_name = _exactly_one(wkt_names, kind="*.wkt entry", where=str(resolved))
        data = json.loads(zf.read(json_name))
        walkable_wkt = zf.read(wkt_name).decode("utf-8").strip()
    return data, walkable_wkt


def _load_scenario_from_self_contained_json(resolved: pathlib.Path) -> tuple[dict, str]:
    data = json.loads(resolved.read_text(encoding="utf-8"))
    walkable_wkt = data.get("walkable_area_wkt")
    if not walkable_wkt:
        raise ValueError(
            f"{resolved}: self-contained scenario JSON must embed "
            "'walkable_area_wkt'. For two-file exports (separate .json + "
            ".wkt), pass the parent directory or a ZIP instead."
        )
    return data, walkable_wkt.strip()


# ---------------------------------------------------------------------------
# Per-tick loop helpers
# ---------------------------------------------------------------------------
# Each helper owns one slice of what the main loop in ``run_scenario``
# does on every tick. They mutate the dicts/lists passed in (agent
# counters, wait-state, throughput trackers) in place and return
# nothing — keep that contract when adding new ones, otherwise the
# behavioral parity with the upstream loop is easy to break.


def _select_journey_variant(distribution_journeys, rng):
    """Weighted pick over a distribution's journey variants."""
    total_weight = sum(
        v["variant_data"]["percentage"] for v in distribution_journeys
    )
    rand_val = rng.random() * total_weight
    cumulative = 0.0
    for variant_info in distribution_journeys:
        cumulative += variant_info["variant_data"]["percentage"]
        if rand_val <= cumulative:
            return variant_info
    return distribution_journeys[0]


def _resolve_variant_stage(selected_variant, spawning_info, direct_steering_info):
    """Pick entry stage + (optionally) override with the global DS stage."""
    selected_stage_id = None
    for stage in selected_variant.get("entry_stages", []):
        if (
            stage in spawning_info["stage_map"]
            and spawning_info["stage_map"][stage] != -1
        ):
            selected_stage_id = spawning_info["stage_map"][stage]
            break
    if selected_stage_id is None:
        raise ValueError(
            "No valid entry stage for variant "
            f"{selected_variant.get('variant_name', selected_variant.get('id'))}"
        )
    journey_id = selected_variant["id"]
    uses_direct_steering = any(
        stage in direct_steering_info
        for stage in selected_variant.get("actual_stages", [])
    )
    global_ds_journey_id = spawning_info.get("global_ds_journey_id")
    global_ds_stage_id = spawning_info.get("global_ds_stage_id")
    if (
        uses_direct_steering
        and global_ds_journey_id is not None
        and global_ds_stage_id is not None
    ):
        return global_ds_journey_id, global_ds_stage_id
    return journey_id, selected_stage_id


def _exit_wait_info(
    *, exit_id, exit_info, direct_steering_info, agent_id, seed
) -> dict[str, Any]:
    """Build the path-state record for an agent steered straight to an exit."""
    base_seed = seed + agent_id * 9973
    target = _random_point_in_polygon(
        exit_info["polygon"], random.Random(base_seed)
    )
    stage_configs = {
        sk: {
            "polygon": info.get("polygon"),
            "stage_type": info.get("stage_type", "exit"),
            "waiting_time": float(info.get("waiting_time", 0.0)),
            "waiting_time_distribution": info.get(
                "waiting_time_distribution", "constant"
            ),
            "waiting_time_std": float(info.get("waiting_time_std", 1.0)),
            "enable_throughput_throttling": bool(
                info.get("enable_throughput_throttling", False)
            ),
            "max_throughput": float(info.get("max_throughput", 1.0)),
            "speed_factor": float(info.get("speed_factor", 1.0)),
        }
        for sk, info in direct_steering_info.items()
    }
    return {
        "mode": "path",
        "path_choices": {},
        "stage_configs": stage_configs,
        "current_origin": exit_id,
        "current_target_stage": exit_id,
        "target": target,
        "target_assigned": False,
        "state": "to_target",
        "wait_until": None,
        "inside_since": None,
        "reach_penetration": 0.25,
        "reach_dwell_seconds": 0.2,
        "step_index": 0,
        "base_seed": base_seed,
    }


def _spawn_flow_agents(
    *,
    simulation,
    current_time: float,
    seed: int,
    spawning_info: dict,
    direct_steering_info: dict,
    agent_wait_info: dict | None,
    agent_radii: dict,
    flow_variant_rng,
    flow_param_rngs: dict,
    pending_flow_samples: dict,
) -> None:
    """Spawn any flow-source agents whose scheduled time has arrived."""
    spawning_freqs_and_numbers = spawning_info["spawning_freqs_and_numbers"]
    flow_distributions = spawning_info["flow_distributions"]
    num_agents_per_source = spawning_info["num_agents_per_source"]
    agent_counter_per_source = spawning_info["agent_counter_per_source"]

    for source_id in range(len(spawning_freqs_and_numbers)):
        if source_id >= len(flow_distributions):
            continue

        flow_dist = flow_distributions[source_id]
        spawn_frequency = spawning_freqs_and_numbers[source_id][0]
        next_spawn_time = flow_dist["start_time"] + (
            agent_counter_per_source[source_id] * spawn_frequency
        )

        if agent_counter_per_source[source_id] >= num_agents_per_source[source_id]:
            continue
        if current_time < flow_dist["start_time"] or current_time > flow_dist["end_time"]:
            continue
        if current_time < next_spawn_time:
            continue

        for _ in range(spawning_freqs_and_numbers[source_id][1]):
            # Sample radius / v0 ONCE per logical agent and cache it
            # across ticks: an agent that fails all candidate positions
            # reuses the same draw on the next attempt rather than being
            # redrawn (which biases the realized distribution against
            # values that are harder to place).
            base_flow_params = flow_dist["params"]
            if source_id not in pending_flow_samples:
                sampled_radii, sampled_v0s = _sample_agent_values(
                    base_flow_params, 1, flow_param_rngs[source_id]
                )
                pending_flow_samples[source_id] = (
                    float(sampled_radii[0]),
                    float(sampled_v0s[0]),
                )
            pending_radius, pending_v0 = pending_flow_samples[source_id]
            flow_params = {
                **base_flow_params,
                "radius": pending_radius,
                "v0": pending_v0,
            }

            spawned = _try_spawn_one_flow_agent(
                simulation=simulation,
                seed=seed,
                source_id=source_id,
                flow_dist=flow_dist,
                flow_params=flow_params,
                spawning_info=spawning_info,
                direct_steering_info=direct_steering_info,
                agent_wait_info=agent_wait_info,
                agent_radii=agent_radii,
                flow_variant_rng=flow_variant_rng,
            )
            if not spawned:
                break
            agent_counter_per_source[source_id] += 1
            pending_flow_samples.pop(source_id, None)


def _try_spawn_one_flow_agent(
    *,
    simulation,
    seed,
    source_id,
    flow_dist,
    flow_params,
    spawning_info,
    direct_steering_info,
    agent_wait_info,
    agent_radii,
    flow_variant_rng,
) -> bool:
    """Try every starting position for this source until one accepts.

    Returns True on a successful spawn, False if every position failed
    (in which case the outer loop stops trying this source for this
    tick — matches the original control flow).
    """
    starting_positions = spawning_info["starting_pos_per_source"][source_id]
    agent_counter_per_source = spawning_info["agent_counter_per_source"]
    selected_variant = None
    selected_variant_info = None

    for j in range(len(starting_positions)):
        pos_index = (agent_counter_per_source[source_id] + j) % len(starting_positions)
        position = starting_positions[pos_index]

        try:
            agent_parameters = create_agent_parameters(
                model_type=spawning_info["model_type"],
                position=position,
                params=flow_params,
                global_params=spawning_info["global_parameters"],
                journey_id=None,
                stage_id=None,
            )

            if flow_dist.get("journey_info"):
                selected_variant_info = _select_journey_variant(
                    flow_dist["journey_info"], flow_variant_rng
                )
                selected_variant = selected_variant_info["variant_data"]
                journey_id, stage_id = _resolve_variant_stage(
                    selected_variant, spawning_info, direct_steering_info
                )
                agent_parameters.journey_id = journey_id
                agent_parameters.stage_id = stage_id
            else:
                nearest_exit_stage_id = _find_nearest_exit(
                    position,
                    stage_map=spawning_info.get("stage_map"),
                    exits=spawning_info.get("exits"),
                    exit_geometries=spawning_info.get("exit_geometries"),
                )
                nearest_journey_id = spawning_info.get(
                    "exit_to_journey", {}
                ).get(nearest_exit_stage_id)
                if nearest_journey_id is None:
                    raise ValueError(
                        f"Missing exit journey mapping for stage {nearest_exit_stage_id}"
                    )
                agent_parameters.journey_id = nearest_journey_id
                agent_parameters.stage_id = nearest_exit_stage_id

            agent_id = simulation.add_agent(agent_parameters)
            agent_radii[agent_id] = flow_params.get("radius", 0.2)

            if (
                selected_variant
                and agent_wait_info is not None
                and direct_steering_info
            ):
                path_state = build_agent_path_state(
                    variant_data=selected_variant,
                    journey_key=(
                        selected_variant_info.get("original_journey_id")
                        if selected_variant_info
                        else None
                    ),
                    transitions=spawning_info.get("transitions", []),
                    direct_steering_info=direct_steering_info,
                    waypoint_routing=spawning_info.get("waypoint_routing", {}),
                    seed=seed,
                    agent_id=agent_id,
                    agent_radius=float(flow_params.get("radius", 0.2)),
                )
                if path_state:
                    agent_wait_info[agent_id] = path_state
            elif (
                not selected_variant
                and agent_wait_info is not None
                and direct_steering_info
            ):
                stage_id_to_exit = {
                    v: k for k, v in spawning_info.get("stage_map", {}).items()
                }
                exit_id = stage_id_to_exit.get(agent_parameters.stage_id)
                if exit_id and exit_id in direct_steering_info:
                    agent_wait_info[agent_id] = _exit_wait_info(
                        exit_id=exit_id,
                        exit_info=direct_steering_info[exit_id],
                        direct_steering_info=direct_steering_info,
                        agent_id=agent_id,
                        seed=seed,
                    )

            return True
        except Exception:
            continue

    return False


def _apply_premovement(
    *,
    simulation,
    current_time: float,
    premovement_times: dict,
    agent_speed_state: dict,
) -> None:
    """Release agents whose premovement timer has elapsed."""
    for agent in simulation.agents():
        agent_id = agent.id
        entry = premovement_times.get(agent_id)
        if entry is None or entry["activated"]:
            continue
        if current_time < entry["premovement_time"]:
            continue
        desired_speed = entry["desired_speed"]
        set_agent_desired_speed(agent, desired_speed)
        speed_state = ensure_agent_speed_state(
            agent_speed_state, agent_id, agent
        )
        speed_state["original_speed"] = float(desired_speed)
        speed_state["active_checkpoint"] = None
        entry["activated"] = True


def _advance_direct_steering(
    *,
    simulation,
    agent_speed_state: dict,
    direct_steering_info: dict,
) -> None:
    """Apply per-tick checkpoint-speed updates and prune dead agents."""
    live_agent_ids: set[int] = set()
    for agent in simulation.agents():
        agent_id = int(agent.id)
        live_agent_ids.add(agent_id)
        x, y = extract_agent_xy(agent)
        if x is None or y is None:
            continue
        update_checkpoint_speed(
            agent_speed_state, direct_steering_info,
            agent_id, agent, None, None, x, y,
        )
    for tracked_agent_id in list(agent_speed_state.keys()):
        if tracked_agent_id not in live_agent_ids:
            agent_speed_state.pop(tracked_agent_id, None)


def _advance_path_following(
    *,
    simulation,
    current_time: float,
    agent_wait_info: dict,
    agent_speed_state: dict,
    direct_steering_info: dict,
    checkpoint_throughput_tracker: dict,
) -> None:
    """Drive each path-mode agent through its to_target / waiting / done states."""
    agents_by_id = {agent.id: agent for agent in simulation.agents()}
    for agent_id, wait_info in list(agent_wait_info.items()):
        if wait_info.get("mode") != "path":
            continue
        agent = agents_by_id.get(agent_id)
        if agent is None:
            continue
        x, y = extract_agent_xy(agent)
        if x is None or y is None:
            continue
        wait_info["current_position"] = (x, y)
        _step_path_agent(
            simulation=simulation,
            current_time=current_time,
            agent=agent,
            agent_id=agent_id,
            wait_info=wait_info,
            x=x,
            y=y,
            agent_speed_state=agent_speed_state,
            direct_steering_info=direct_steering_info,
            checkpoint_throughput_tracker=checkpoint_throughput_tracker,
        )


def _step_path_agent(
    *,
    simulation,
    current_time,
    agent,
    agent_id,
    wait_info,
    x,
    y,
    agent_speed_state,
    direct_steering_info,
    checkpoint_throughput_tracker,
) -> None:
    state = wait_info.get("state", "to_target")
    current_target_stage = wait_info.get("current_target_stage")
    stage_cfg = wait_info.get("stage_configs", {}).get(current_target_stage, {})
    target = wait_info.get("target")

    if state == "done":
        update_checkpoint_speed(
            agent_speed_state, direct_steering_info,
            agent_id, agent, None, None, x, y,
        )
        return

    if state == "to_target":
        update_checkpoint_speed(
            agent_speed_state, direct_steering_info,
            agent_id, agent, current_target_stage, stage_cfg, x, y,
        )
        if not wait_info.get("target_assigned", False):
            assign_agent_target(agent, target)
            wait_info["target_assigned"] = True

        reached_target = check_stage_reached(
            wait_info, stage_cfg, x, y, current_time, target,
        )
        if not reached_target:
            return

        # Throttled checkpoints can defer the transition; if the gate
        # rejects us, leave state machine unchanged and try again next tick.
        if not _accept_throughput(
            checkpoint_throughput_tracker, current_target_stage, stage_cfg, current_time
        ):
            return

        if stage_cfg.get("stage_type") == "exit":
            try:
                simulation.mark_agent_for_removal(agent_id)
            except Exception:
                pass
            wait_info["state"] = "done"
            return

        wait_time = sample_wait_time(
            stage_cfg,
            wait_info.get("base_seed", 0),
            wait_info.get("step_index", 0),
        )
        if wait_time > 0:
            wait_info["state"] = "waiting"
            wait_info["wait_until"] = current_time + wait_time
        else:
            advance_path_target(wait_info)
        return

    if state == "waiting":
        update_checkpoint_speed(
            agent_speed_state, direct_steering_info,
            agent_id, agent, current_target_stage, stage_cfg, x, y,
        )
        if current_time >= float(wait_info.get("wait_until", current_time)):
            advance_path_target(wait_info)


def _accept_throughput(
    tracker: dict, wp_key, stage_cfg: dict, current_time: float
) -> bool:
    """Throughput gate for a checkpoint transition. Records the exit time on accept."""
    if not stage_cfg.get("enable_throughput_throttling", False):
        return True
    max_throughput = float(stage_cfg.get("max_throughput", 1.0))
    if not wp_key or max_throughput <= 0:
        return True
    min_interval = 1.0 / max_throughput
    last = tracker.get(wp_key, {"last_exit_time": -9999}).get("last_exit_time", -9999)
    if current_time - last < min_interval:
        return False
    tracker[wp_key] = {"last_exit_time": current_time}
    return True


class ScenarioRunner:
    """Drive a scenario tick-by-tick with inspection between steps.

    Matches the imperative shape of ``jupedsim.Simulation`` so users
    familiar with the lower-level API feel at home::

        with ScenarioRunner(scenario, seed=42) as runner:
            runner.run_until(10.0)
            print(runner.elapsed_time, runner.agent_count)
            # mutate the simulation or scenario here, then continue:
            runner.run_until(20.0)
            result = runner.result()

    To run all the way to ``scenario.max_simulation_time``, call
    ``run_until()`` with no argument (the loop also stops early once
    every agent has evacuated)::

        with ScenarioRunner(scenario, seed=42) as runner:
            runner.run_until()
            result = runner.result()

    Outside a context manager you can call ``close()`` directly; the
    sqlite trajectory file survives ``close()`` so the returned
    ``ScenarioResult`` keeps working.
    """

    def __init__(
        self,
        scenario: Scenario,
        *,
        seed: int | None = None,
        dt: float | None = None,
        every_nth_frame: int = 10,
        output_path: str | pathlib.Path | None = None,
    ):
        _ensure_positive_int("every_nth_frame", every_nth_frame)
        if dt is not None:
            _ensure_positive_number("dt", dt)
        self._scenario = scenario
        self._seed = seed if seed is not None else scenario.seed
        self._every_nth_frame = every_nth_frame
        self._closed = False

        model = _build_model(scenario.model_type, scenario.sim_params)

        if output_path is None:
            sqlite_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
            self._output_file: str = sqlite_tmp.name
            sqlite_tmp.close()
            self._owns_output = True
        else:
            self._output_file = str(pathlib.Path(output_path).resolve())
            pathlib.Path(self._output_file).parent.mkdir(parents=True, exist_ok=True)
            self._owns_output = False

        # Everything below this point can fail; on failure we tear down
        # the writer, the config tempfile, and the runner-owned
        # trajectory tempfile so __init__ never leaks resources.
        try:
            self._writer = jps.SqliteTrajectoryWriter(
                output_file=pathlib.Path(self._output_file),
                every_nth_frame=every_nth_frame,
            )
            sim_kwargs: dict[str, Any] = dict(
                model=model,
                geometry=scenario.walkable_polygon,
                trajectory_writer=self._writer,
            )
            if dt is not None:
                sim_kwargs["dt"] = dt
            self._simulation = jps.Simulation(**sim_kwargs)

            config_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
            self._config_tmp_path: str = config_tmp.name
            json.dump(scenario._synced_raw(), config_tmp, indent=2)
            config_tmp.close()

            walkable_area = SimpleNamespace(polygon=scenario.walkable_polygon)
            global_parameters = SimpleNamespace(**scenario.sim_params)
            _, _, agent_radii, spawning_info = initialize_simulation_from_json(
                self._config_tmp_path,
                self._simulation,
                walkable_area,
                seed=self._seed,
                model_type=scenario.model_type,
                global_parameters=global_parameters,
            )
        except Exception:
            self._close_partial_init()
            raise

        self._agent_radii = agent_radii
        self._spawning_info = spawning_info
        self._initial_agent_count = int(self._simulation.agent_count())

        # Per-tick mutable state, hoisted from the previous monolithic
        # run_scenario into instance attributes so step() can mutate
        # them across calls.
        self._has_flow_spawning: bool = spawning_info.get("has_flow_spawning", False)
        self._num_agents_per_source: list[int] = spawning_info.get(
            "num_agents_per_source", []
        )
        self._agent_counter_per_source: list[int] = spawning_info.get(
            "agent_counter_per_source", []
        )
        self._flow_distributions: list[dict] = spawning_info.get("flow_distributions", [])
        self._has_premovement: bool = spawning_info.get("has_premovement", False)
        self._premovement_times: dict = spawning_info.get("premovement_times", {})
        self._direct_steering_info: dict = spawning_info.get("direct_steering_info", {})
        self._agent_wait_info: dict = spawning_info.get("agent_wait_info", {})
        self._checkpoint_throughput_tracker: dict[Any, dict[str, float]] = {}
        self._agent_speed_state: dict[int, dict[str, Any]] = {}
        self._flow_variant_rng = random.Random(self._seed)
        # Per-source RNGs for flow-spawn agent parameter sampling. Seed
        # from a stable distribution identity (dist_key/dist_index) and
        # use np.random.RandomState to match services/simulation_service.py
        # — given the same seed, both runners must produce the same
        # sampled sequence.
        self._flow_param_rngs = {
            i: np.random.RandomState(self._seed + _stable_flow_rng_offset(d, i))
            for i, d in enumerate(self._flow_distributions)
        }
        # Cache one (radius, v0) per source while a spawn is pending so
        # that an agent that fails all candidate positions reuses the
        # same draw on the next attempt instead of being redrawn (which
        # biases the realized distribution).
        self._pending_flow_samples: dict[int, tuple[float, float]] = {}

    # -- introspection ------------------------------------------------

    @property
    def elapsed_time(self) -> float:
        return float(self._simulation.elapsed_time())

    @property
    def agent_count(self) -> int:
        return int(self._simulation.agent_count())

    @property
    def seed(self) -> int:
        return self._seed

    def agents(self):
        """Iterate over live agents (delegates to ``jupedsim.Simulation.agents``)."""
        return self._simulation.agents()

    @property
    def simulation(self):
        """The underlying ``jupedsim.Simulation``. Use this when the higher-level
        API doesn't cover what you need; mutate at your own risk."""
        return self._simulation

    def _should_continue(self) -> bool:
        if self.agent_count > 0:
            return True
        if not self._has_flow_spawning:
            return False
        return sum(self._agent_counter_per_source) < sum(self._num_agents_per_source)

    def _check_open(self) -> None:
        """Reject step/run_until/result after close()."""
        if self._closed:
            raise RuntimeError(
                "ScenarioRunner is closed: the trajectory writer has been "
                "released and the config tempfile removed. Create a new "
                "ScenarioRunner to run again."
            )

    # -- stepping -----------------------------------------------------

    def step(self) -> None:
        """Advance one iteration tick (all per-tick helpers + simulation.iterate)."""
        self._check_open()
        current_time = self._simulation.elapsed_time()
        if self._has_flow_spawning:
            _spawn_flow_agents(
                simulation=self._simulation,
                current_time=current_time,
                seed=self._seed,
                spawning_info=self._spawning_info,
                direct_steering_info=self._direct_steering_info,
                agent_wait_info=self._agent_wait_info,
                agent_radii=self._agent_radii,
                flow_variant_rng=self._flow_variant_rng,
                flow_param_rngs=self._flow_param_rngs,
                pending_flow_samples=self._pending_flow_samples,
            )
        if self._has_premovement:
            _apply_premovement(
                simulation=self._simulation,
                current_time=current_time,
                premovement_times=self._premovement_times,
                agent_speed_state=self._agent_speed_state,
            )
        if self._direct_steering_info:
            _advance_direct_steering(
                simulation=self._simulation,
                agent_speed_state=self._agent_speed_state,
                direct_steering_info=self._direct_steering_info,
            )
        if self._direct_steering_info and self._agent_wait_info:
            _advance_path_following(
                simulation=self._simulation,
                current_time=current_time,
                agent_wait_info=self._agent_wait_info,
                agent_speed_state=self._agent_speed_state,
                direct_steering_info=self._direct_steering_info,
                checkpoint_throughput_tracker=self._checkpoint_throughput_tracker,
            )
        self._simulation.iterate()

    def run_until(self, target_time: float | None = None) -> None:
        """Run forward until ``elapsed_time >= target_time``.

        ``target_time=None`` (default) means ``scenario.max_simulation_time``
        — i.e. "run to completion". Stops early once every agent has
        evacuated (and any flow spawning has emptied its budget).

        ``target_time`` is clamped to ``scenario.max_simulation_time``
        so callers can't drive the simulation past the scenario's
        configured horizon by accident. ``target_time=0`` is accepted
        and is a no-op at ``t=0``.
        """
        self._check_open()
        if target_time is None:
            target_time = self._scenario.max_simulation_time
        _ensure_non_negative_number("target_time", target_time)
        target_time = min(target_time, self._scenario.max_simulation_time)
        while self.elapsed_time < target_time and self._should_continue():
            self.step()

    # -- result + teardown -------------------------------------------

    def result(self) -> ScenarioResult:
        """Build a ``ScenarioResult`` reflecting the runner's current state.

        Safe to call multiple times — each invocation snapshots the
        live metrics. The runner does NOT close the writer when
        ``result()`` is called, so subsequent ``step()`` / ``run_until``
        calls keep appending to the same sqlite file.
        """
        self._check_open()
        evacuation_time = float(self._simulation.elapsed_time())
        remaining = int(self._simulation.agent_count())
        total_agents = self._initial_agent_count
        if self._has_flow_spawning:
            total_agents += sum(self._agent_counter_per_source)
        max_time = self._scenario.max_simulation_time

        all_evacuated = remaining == 0
        timed_out = evacuation_time >= max_time and not all_evacuated
        if all_evacuated:
            status = "completed"
            message = "All agents evacuated before reaching the maximum simulation time."
        elif timed_out:
            status = "timeout"
            message = "Simulation reached max_simulation_time with remaining agents."
        else:
            status = "incomplete"
            message = (
                "Simulation stopped before all agents evacuated and before "
                "max_simulation_time."
            )

        dt = float(self._simulation.delta_time())
        frame_rate = 1.0 / (dt * self._every_nth_frame) if dt > 0 else 0.0
        metrics = {
            "success": all_evacuated,
            "status": status,
            "message": message,
            "evacuation_time": round(evacuation_time, 2),
            "total_agents": total_agents,
            "agents_evacuated": total_agents - remaining,
            "agents_remaining": remaining,
            "all_evacuated": all_evacuated,
            "frame_rate": frame_rate,
            "dt": dt,
            "seed": self._seed,
            "walkable_polygon": self._scenario.walkable_polygon,
        }
        return ScenarioResult(metrics=metrics, sqlite_file=self._output_file)

    def _close_partial_init(self) -> None:
        """Best-effort cleanup for __init__ failure paths.

        Closes whatever was constructed so far and removes the
        runner-owned trajectory tempfile so a failed __init__ doesn't
        leak. Safe to call multiple times.
        """
        writer = getattr(self, "_writer", None)
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
        config_path = getattr(self, "_config_tmp_path", None)
        if config_path is not None:
            try:
                os.unlink(config_path)
            except OSError:
                pass
        if self._owns_output:
            try:
                os.unlink(self._output_file)
            except OSError:
                pass
        self._closed = True

    def close(self) -> None:
        """Close the trajectory writer and clean up the config tempfile.

        Idempotent. Does NOT remove the sqlite trajectory file — call
        ``ScenarioResult.cleanup()`` for that, or just keep the file.
        """
        if self._closed:
            return
        try:
            self._writer.close()
        except Exception:
            pass
        try:
            os.unlink(self._config_tmp_path)
        except Exception:
            pass
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, tb
        try:
            self.close()
        finally:
            # On exception inside the with block, remove the runner-owned
            # trajectory tempfile so failed runs don't leak. Matches the
            # previous run_scenario behaviour.
            if exc is not None and self._owns_output:
                try:
                    os.unlink(self._output_file)
                except OSError:
                    pass
        return False


def run_scenario(
    scenario: Scenario,
    *,
    seed: int | None = None,
    dt: float | None = None,
    every_nth_frame: int = 10,
    output_path: str | pathlib.Path | None = None,
) -> ScenarioResult:
    """Run a scenario to completion. Thin wrapper around ``ScenarioRunner``."""
    with ScenarioRunner(
        scenario,
        seed=seed,
        dt=dt,
        every_nth_frame=every_nth_frame,
        output_path=output_path,
    ) as runner:
        runner.run_until()
        return runner.result()
