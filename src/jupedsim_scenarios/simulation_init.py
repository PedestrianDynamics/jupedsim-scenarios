import importlib.util
import json
import logging
import math
import random
import subprocess
import sys
import zlib
from collections import defaultdict
from typing import Any

import jupedsim as jps
import numpy as np
import pedpy
import shapely
from shapely.geometry import Point, Polygon

logger = logging.getLogger(__name__)

required_packages = [
    ("jupedsim", "jupedsim"),
    ("shapely", "shapely"),
    ("numpy", "numpy"),
    ("matplotlib", "matplotlib"),
    ("pedpy", "pedpy"),
    ("ezdxf", "ezdxf"),
    ("plotly", "plotly"),
    ("geopandas", "geopandas"),
    ("typer", "typer"),
    ("nbformat", "nbformat"),
]


def is_package_installed(import_name: str) -> bool:
    """Check if packages is installed."""
    return importlib.util.find_spec(import_name) is not None


def install_if_missing(pip_name: str, import_name: str | None = None):
    """Pip install missing packages."""
    import_name = import_name or pip_name
    if not is_package_installed(import_name):
        logger.info(f"Installing {pip_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
    else:
        logger.info(f"{pip_name} already installed.")
def create_agent_parameters(
    model_type: str,
    position: tuple,
    params: dict,
    global_params=None,
    journey_id=None,
    stage_id=None,
):
    """Create appropriate agent parameters based on the model type"""

    base_params = {
        "position": position,
        "radius": params.get("radius", 0.2),
    }

    # Add journey and stage if provided
    if journey_id is not None:
        base_params["journey_id"] = journey_id
    if stage_id is not None:
        base_params["stage_id"] = stage_id

    if model_type == "CollisionFreeSpeedModel":
        base_params["desired_speed"] = params.get("v0", 1.2)
        return jps.CollisionFreeSpeedModelAgentParameters(**base_params)

    elif model_type == "CollisionFreeSpeedModelV2":
        v2_params = base_params.copy()
        v2_params["desired_speed"] = params.get("v0", 1.2)
        v2_params["time_gap"] = 1.0
        if global_params:
            v2_params["strength_neighbor_repulsion"] = getattr(
                global_params, "strength_neighbor_repulsion", 2.6
            )
            v2_params["range_neighbor_repulsion"] = getattr(
                global_params, "range_neighbor_repulsion", 0.1
            )
        return jps.CollisionFreeSpeedModelV2AgentParameters(**v2_params)

    elif model_type == "CollisionFreeSpeedModelV3":
        v3_params = base_params.copy()
        v3_params["desired_speed"] = params.get("v0", 1.2)
        return jps.CollisionFreeSpeedModelV3AgentParameters(**v3_params)

    elif model_type == "WarpDriverModel":
        wd_params = base_params.copy()
        wd_params["desired_speed"] = params.get("v0", 1.2)
        return jps.WarpDriverModelAgentParameters(**wd_params)

    elif model_type == "GeneralizedCentrifugalForceModel":
        gcfm_params = {
            "position": position,
            "desired_speed": params.get("v0", 1.2),
            "mass": getattr(global_params, "mass", 80.0) if global_params else 80.0,
            "tau": getattr(global_params, "tau", 0.5) if global_params else 0.5,
            "a_v": getattr(global_params, "a_v", 1.0) if global_params else 1.0,
            "a_min": getattr(global_params, "a_min", 0.2) if global_params else 0.2,
            "b_min": getattr(global_params, "b_min", 0.2) if global_params else 0.2,
            "b_max": getattr(global_params, "b_max", 0.4) if global_params else 0.4,
        }
        if journey_id is not None:
            gcfm_params["journey_id"] = journey_id
        if stage_id is not None:
            gcfm_params["stage_id"] = stage_id
        try:
            return jps.GeneralizedCentrifugalForceModelAgentParameters(**gcfm_params)
        except TypeError as error:
            if "unexpected keyword argument" not in str(error):
                raise
            for param_name in ("a_v", "a_min", "b_min", "b_max"):
                gcfm_params.pop(param_name, None)
            return jps.GeneralizedCentrifugalForceModelAgentParameters(**gcfm_params)

    elif model_type == "SocialForceModel":
        sfm_params = base_params.copy()
        sfm_params["desired_speed"] = params.get("v0", 0.8)
        sfm_params["reaction_time"] = (
            getattr(global_params, "relaxation_time", 0.5) if global_params else 0.5
        )
        sfm_params["agent_scale"] = (
            getattr(global_params, "agent_strength", 2000) if global_params else 2000
        )
        sfm_params["force_distance"] = (
            getattr(global_params, "agent_range", 0.08) if global_params else 0.08
        )
        sfm_params["mass"] = (
            getattr(global_params, "mass", 80.0) if global_params else 80.0
        )
        sfm_params["obstacle_scale"] = (
            getattr(global_params, "sfm_obstacle_scale", 2000)
            if global_params
            else 2000
        )
        return jps.SocialForceModelAgentParameters(**sfm_params)

    elif model_type == "AnticipationVelocityModel":
        avm_params = base_params.copy()
        avm_params["desired_speed"] = params.get("v0", 1.2)
        avm_params["time_gap"] = 1.06  # Default value
        if global_params:
            avm_params["anticipation_time"] = (
                global_params.T if hasattr(global_params, "T") else 1.0
            )
            avm_params["reaction_time"] = (
                global_params.s0 if hasattr(global_params, "s0") else 0.3
            )
        else:
            avm_params["anticipation_time"] = 1.0
            avm_params["reaction_time"] = 0.3
        return jps.AnticipationVelocityModelAgentParameters(**avm_params)

    else:
        # Fallback to CollisionFreeSpeedModel
        base_params["v0"] = params.get("v0", 1.2)
        return jps.CollisionFreeSpeedModelAgentParameters(**base_params)


def _estimate_max_capacity(polygon, max_radius):
    """Estimate how many agents fit in a polygon using packing approximation."""
    effective_radius = max(max_radius, 0.1)
    theoretical = polygon.area / (math.pi * effective_radius * effective_radius)
    return max(1, math.floor(theoretical * 0.5))


def _get_max_agent_radius(params):
    """Get the radius used for placement spacing.

    Returns the mean radius for both constant and Gaussian distributions,
    matching the placement behavior of the Web-Based JuPedSim editor. A
    previous implementation used mean + 3*std as a safety margin for the
    Gaussian case; that turned out to be too conservative and rejected
    packings the editor accepts. Initial micro-overlaps from sampled
    radii above the mean are handled by the simulator's dynamics phase.
    """
    return params.get("radius", 0.2)


def _get_distribution_mode_and_count(params):
    """Get distribution mode and agent count based on distribution_mode parameter.

    Returns:
        tuple: (distribution_mode, number_of_agents)
            - distribution_mode: 'by_number' or 'by_percentage'
            - number_of_agents: 0 for percentage mode, actual count for by_number
    """
    mode = params.get("distribution_mode", "by_number")
    if mode == "by_number":
        number = int(params.get("number", 0))
        return mode, max(0, number)
    elif mode in {"by_percentage", "fill_area", "until_full"}:
        return "by_percentage", 0
    else:
        number = int(params.get("number", 0))
        return "by_number", max(0, number)


def _get_distribution_percentage(params):
    """Return clamped distribution density percentage for by_percentage mode."""
    mode = params.get("distribution_mode", "by_number")
    default_percentage = 100 if mode in {"fill_area", "until_full"} else 50
    raw_percentage = params.get("percentage", default_percentage)
    try:
        percentage = int(float(raw_percentage))
    except (TypeError, ValueError):
        percentage = default_percentage
    return max(1, min(100, percentage))


def _sample_agent_values(params, n_agents, rng):
    """Sample per-agent radius and desired-speed values.

    For Gaussian distributions the *mean* is clamped to a safe range
    BEFORE sampling and the samples themselves are then clipped — without
    the mean clamp, a mis-configured mean (e.g. radius=2.0) collapses the
    distribution onto the clip ceiling and destroys variance. Clamping
    the mean first preserves variance while staying inside JuPedSim's
    accepted range. Constant (non-Gaussian) values pass through
    unchanged so any radius or speed JuPedSim accepts is honored.

    Accepts ``desired_speed`` as an alias for ``v0`` (and
    ``desired_speed_distribution`` / ``desired_speed_std`` for the
    distribution variants) so the public Scenario API and the legacy
    flow-spawn config can share this function.
    """
    raw_radius = params.get("radius", 0.2)
    raw_v0 = params.get("desired_speed", params.get("v0", 1.2))

    if params.get("radius_distribution") == "gaussian" and params.get("radius_std"):
        mean_radius = max(0.1, min(1.0, raw_radius))
        radii = rng.normal(mean_radius, params["radius_std"], n_agents).clip(0.1, 1.0)
    else:
        radii = np.full(n_agents, raw_radius)

    v0_dist = params.get("desired_speed_distribution", params.get("v0_distribution"))
    v0_std = params.get("desired_speed_std", params.get("v0_std"))
    if v0_dist == "gaussian" and v0_std:
        mean_v0 = max(0.1, min(5.0, raw_v0))
        v0s = rng.normal(mean_v0, v0_std, n_agents).clip(0.1, 5.0)
    else:
        v0s = np.full(n_agents, raw_v0)

    return radii, v0s


def _normalize_speed_factor(value: Any) -> float:
    """Normalize checkpoint speed factor to the supported interval [0, 3]."""
    try:
        speed_factor = float(value)
    except (TypeError, ValueError):
        return 1.0
    if not np.isfinite(speed_factor) or speed_factor < 0.0:
        return 1.0
    return min(speed_factor, 3.0)


def _normalize_bool(value: Any) -> bool:
    """Normalize booleans from JSON-like payloads."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


def _normalize_checkpoint_mode(
    waiting_time: Any,
    enable_throughput_throttling: Any,
    speed_factor: Any,
) -> tuple[float, bool, float]:
    """Enforce mutually exclusive checkpoint behavior modes."""
    try:
        normalized_waiting_time = float(waiting_time)
    except (TypeError, ValueError):
        normalized_waiting_time = 0.0
    if not np.isfinite(normalized_waiting_time) or normalized_waiting_time < 0.0:
        normalized_waiting_time = 0.0

    normalized_throughput = _normalize_bool(enable_throughput_throttling)
    normalized_speed_factor = _normalize_speed_factor(speed_factor)

    if normalized_waiting_time > 0.0:
        normalized_throughput = False
        normalized_speed_factor = 1.0
    elif normalized_throughput:
        normalized_waiting_time = 0.0
        normalized_speed_factor = 1.0
    elif abs(normalized_speed_factor - 1.0) > 1e-9:
        normalized_waiting_time = 0.0
        normalized_throughput = False

    return normalized_waiting_time, normalized_throughput, normalized_speed_factor


def _normalize_variant_weights(
    distribution_journeys: list[dict[str, Any]],
) -> tuple[list[float], float]:
    """Return non-negative variant weights and a strictly positive total."""
    weights: list[float] = []
    for variant_info in distribution_journeys:
        raw_percentage = variant_info.get("variant_data", {}).get("percentage", 0.0)
        try:
            weight = float(raw_percentage)
        except (TypeError, ValueError):
            weight = 0.0
        if not np.isfinite(weight) or weight < 0.0:
            weight = 0.0
        weights.append(weight)

    total_weight = float(sum(weights))
    if total_weight <= 0.0 and weights:
        # If all configured weights are zero/invalid, spread agents uniformly.
        weights = [1.0] * len(weights)
        total_weight = float(len(weights))
    return weights, total_weight


def _spawn_area_polygons(geometry):
    """Flatten a spawn geometry into its polygon components."""
    if geometry is None or geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type == "MultiPolygon":
        return [poly for poly in getattr(geometry, "geoms", []) if not poly.is_empty]
    if geometry.geom_type == "GeometryCollection":
        polygons = []
        for geom in getattr(geometry, "geoms", []):
            polygons.extend(_spawn_area_polygons(geom))
        return polygons
    return []


def _distribute_positions_until_filled(
    spawn_area, distance_to_agents, distance_to_polygon, seed
):
    """Return shuffled candidate positions across all connected spawn polygons."""
    polygons = _spawn_area_polygons(spawn_area)
    if not polygons:
        return []

    if len(polygons) == 1:
        positions = list(
            jps.distribute_until_filled(
                polygon=polygons[0],
                distance_to_agents=distance_to_agents,
                distance_to_polygon=distance_to_polygon,
                seed=seed,
            )
        )
    else:
        positions = []
        for index, polygon in enumerate(polygons):
            positions.extend(
                jps.distribute_until_filled(
                    polygon=polygon,
                    distance_to_agents=distance_to_agents,
                    distance_to_polygon=distance_to_polygon,
                    seed=seed + index,
                )
            )

    shuffle_rng = random.Random(seed)
    shuffle_rng.shuffle(positions)
    return positions


def _distribute_positions_by_number(
    spawn_area, number_of_agents, distance_to_agents, distance_to_polygon, seed
):
    """Place a fixed number of agents across all connected spawn polygons."""
    polygons = _spawn_area_polygons(spawn_area)
    if not polygons or number_of_agents <= 0:
        return []

    if len(polygons) == 1:
        return jps.distribute_by_number(
            polygon=polygons[0],
            number_of_agents=number_of_agents,
            distance_to_agents=distance_to_agents,
            distance_to_polygon=distance_to_polygon,
            seed=seed,
        )

    candidate_positions = _distribute_positions_until_filled(
        spawn_area=spawn_area,
        distance_to_agents=distance_to_agents,
        distance_to_polygon=distance_to_polygon,
        seed=seed,
    )
    if number_of_agents > len(candidate_positions):
        raise ValueError(
            f"Requested {number_of_agents} agents but only {len(candidate_positions)} positions fit in the connected spawn regions."
        )
    return candidate_positions[:number_of_agents]


def _pick_initial_stage_target(
    stage_cfg: dict[str, Any],
    rng,
    agent_radius: float,
    reach_penetration: float = 0.25,
):
    """Pick a target point inside the stage polygon.

    Transit stages use the centroid so agents approach head-on.
    Waiting stages use a random interior point to distribute agents.
    """
    cfg = stage_cfg or {}
    polygon = cfg.get("polygon")
    if polygon is None:
        return None

    is_transit = (
        float(cfg.get("waiting_time", 0.0)) <= 0.0
        and cfg.get("stage_type") != "exit"
    )
    if is_transit:
        try:
            centroid = polygon.centroid
            return (centroid.x, centroid.y)
        except AttributeError:
            pass

    target_clearance = max(0.05, float(agent_radius) * 0.8, float(reach_penetration))
    return _random_point_in_polygon(polygon, rng, min_clearance=target_clearance)


def build_agent_path_state(
    variant_data: dict[str, Any],
    journey_key: str | None,
    transitions: list[dict[str, Any]],
    direct_steering_info: dict[str, dict[str, Any]],
    waypoint_routing: dict[str, Any] | None,
    seed: int,
    agent_id: int,
    agent_radius: float = 0.2,
) -> dict[str, Any] | None:
    """Build DS routing state as origin->weighted-next mapping."""
    if not direct_steering_info:
        return None

    outgoing: dict[str, list[str]] = {}

    def _append_edge(origin: str, target: str) -> None:
        targets = outgoing.setdefault(origin, [])
        if target not in targets:
            targets.append(target)

    # Build outgoing edges from the variant's resolved stages first.
    full_stages = variant_data.get("stages", []) or variant_data.get(
        "actual_stages", []
    )
    variant_edges: set = set()
    for idx in range(len(full_stages) - 1):
        from_stage = full_stages[idx]
        to_stage = full_stages[idx + 1]
        if isinstance(from_stage, str) and isinstance(to_stage, str):
            _append_edge(from_stage, to_stage)
            variant_edges.add(from_stage)

    # Add journey transitions only for stages NOT already covered by the variant.
    # This preserves cyclic edges and continuity while preventing re-randomization
    # at routing split points where the variant has already resolved the choice.
    if journey_key:
        for transition in transitions:
            if transition.get("journey_id") != journey_key:
                continue
            from_stage = transition.get("from")
            to_stage = transition.get("to")
            if isinstance(from_stage, str) and isinstance(to_stage, str):
                if from_stage not in variant_edges:
                    _append_edge(from_stage, to_stage)

    # Invariant: variant-resolved edges are authoritative inside the variant's
    # sampled path; global routing only applies to routing-split nodes the
    # variant never explored. A stage present in variant_edges has already been
    # pre-sampled at variant generation time — leaving it alone preserves the
    # agent's assigned branch. Stages outside the variant's path (e.g. a shared
    # waypoint a short variant ends at) would otherwise dead-end at runtime, so
    # we seed path_choices with their global outgoing transitions here.
    for transition in transitions:
        from_stage = transition.get("from")
        to_stage = transition.get("to")
        if not isinstance(from_stage, str) or not isinstance(to_stage, str):
            continue
        if from_stage in variant_edges:
            continue
        if not _is_routing_split_node(from_stage):
            continue
        _append_edge(from_stage, to_stage)

    if not outgoing:
        return None

    path_choices: dict[str, list[tuple[str, float]]] = {}
    routing_for_journey = waypoint_routing if isinstance(waypoint_routing, dict) else {}
    for origin, targets in outgoing.items():
        configured = routing_for_journey.get(origin, {}).get("destinations", [])

        choices: list[tuple[str, float]] = []
        if configured:
            for dest in configured:
                target = dest.get("target")
                pct = float(dest.get("percentage", 0.0))
                if (
                    isinstance(target, str)
                    and target in targets
                    and target in direct_steering_info
                    and pct > 0
                ):
                    choices.append((target, pct))
        if not choices:
            ds_targets = [
                target for target in targets if target in direct_steering_info
            ]
            if len(ds_targets) == 1:
                choices = [(ds_targets[0], 100.0)]
            elif len(ds_targets) > 1:
                uniform_pct = 100.0 / len(ds_targets)
                choices = [(target, uniform_pct) for target in ds_targets]

        if choices:
            path_choices[origin] = choices

    if not path_choices:
        return None

    distribution_stages = [
        stage
        for stage in full_stages
        if isinstance(stage, str) and stage.startswith("jps-distributions_")
    ]
    start_origin = next(
        (stage for stage in distribution_stages if stage in path_choices), None
    )
    if start_origin is None:
        start_origin = next(
            (
                stage
                for stage in variant_data.get("actual_stages", [])
                if isinstance(stage, str) and stage in path_choices
            ),
            None,
        )
    if start_origin is None:
        return None

    start_choices = path_choices.get(start_origin, [])
    if not start_choices:
        return None
    chooser_rng = random.Random(int(seed) + int(agent_id) * 9973)
    total = sum(max(0.0, float(weight)) for _, weight in start_choices)
    if total <= 0:
        current_target_stage = start_choices[0][0]
    else:
        pick = chooser_rng.random() * total
        running = 0.0
        current_target_stage = start_choices[-1][0]
        for stage_key, weight in start_choices:
            running += max(0.0, float(weight))
            if pick <= running:
                current_target_stage = stage_key
                break

    stage_configs: dict[str, dict[str, Any]] = {}
    for stage_key, info in direct_steering_info.items():
        stage_configs[stage_key] = {
            "polygon": info.get("polygon"),
            "stage_type": info.get("stage_type", "checkpoint"),
            "waiting_time": float(info.get("waiting_time", 0.0)),
            "waiting_time_distribution": info.get(
                "waiting_time_distribution", "constant"
            ),
            "waiting_time_std": float(info.get("waiting_time_std", 1.0)),
            "enable_throughput_throttling": bool(
                info.get("enable_throughput_throttling", False)
            ),
            "max_throughput": float(info.get("max_throughput", 1.0)),
            "speed_factor": _normalize_speed_factor(info.get("speed_factor", 1.0)),
        }

    base_seed = int(seed) + int(agent_id) * 9973
    target_rng = np.random.RandomState(base_seed)
    target = _pick_initial_stage_target(
        stage_configs.get(current_target_stage, {}),
        target_rng,
        float(agent_radius),
        0.25,
    )

    return {
        "mode": "path",
        "path_choices": path_choices,
        "stage_configs": stage_configs,
        "current_origin": start_origin,
        "current_target_stage": current_target_stage,
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


def initialize_simulation_from_json(
    json_path: str,
    simulation: jps.Simulation,
    walkable_area: pedpy.WalkableArea,
    seed: int = 42,
    model_type: str = "CollisionFreeSpeedModel",
    global_parameters=None,
) -> tuple[dict[str, Any], list[tuple[float, float]], dict[int, float], dict[str, Any]]:
    """
    Initialize a JuPedSim simulation from a JSON configuration with fallback logic.
    """
    try:
        with open(json_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        raise ValueError(f"Error loading JSON configuration: {e}")

    # Only require exits - everything else can be fallback
    if "exits" not in data or not data["exits"]:
        raise ValueError("At least one exit is required in JSON configuration")

    # Check what's missing and use fallback logic
    needs_fallback = False
    fallback_reasons = []

    if "distributions" not in data or not data["distributions"]:
        needs_fallback = True
        fallback_reasons.append("No distributions defined")

    # Journey Definition v2 (issue #376) is now the only journey path.
    # The fallback runs only when no journey is defined at all.
    has_v2_journeys = bool(data.get("journeys_v2")) and any(
        (d.get("journey_weights") or [])
        for d in (data.get("distributions") or {}).values()
    )
    if not has_v2_journeys:
        needs_fallback = True
        fallback_reasons.append("No journeys defined")

    if "checkpoints" not in data and "waiting_polygons" not in data:
        data["checkpoints"] = {}

    if needs_fallback:
        logger.info(f"Using fallback logic: {', '.join(fallback_reasons)}")

        result_data, positions, agent_radii, spawning_info = _initialize_with_fallback(
            simulation, data, walkable_area, seed, model_type, global_parameters
        )
        # Return empty spawning_info for fallback
        return result_data, positions, agent_radii, spawning_info
    else:
        # Use original logic for complete configurations
        result_data, positions, agent_radii, spawning_info = (
            _initialize_complete_config(
                simulation, data, walkable_area, seed, model_type, global_parameters
            )
        )
        return result_data, positions, agent_radii, spawning_info


def _initialize_complete_config(
    simulation: jps.Simulation,
    data: dict[str, Any],
    walkable_area: pedpy.WalkableArea,
    seed: int,
    model_type: str,
    global_parameters=None,
) -> tuple[dict[str, Any], list[tuple[float, float]], dict[int, float], dict[str, Any]]:
    """Original initialization logic for complete configurations"""
    stage_map, direct_steering_info = _add_stages(simulation, data, walkable_area)
    dist_geom, dist_params = _process_distributions(data)
    # Journey Definition v2 (issue #376) is now the only journey path.
    # The legacy waypoint-routing builder was removed in phase 5d.
    journey_data = _create_journeys_v2(simulation, data, stage_map)
    global_ds_stage_id = None
    global_ds_journey_id = None
    if direct_steering_info:
        global_ds_stage_id = simulation.add_direct_steering_stage()
        global_ds_journey = jps.JourneyDescription([global_ds_stage_id])
        global_ds_journey_id = simulation.add_journey(global_ds_journey)

    positions, agent_radii, spawning_info = _add_agents(
        simulation=simulation,
        data=data,
        stage_map=stage_map,
        dist_geom=dist_geom,
        dist_params=dist_params,
        journey_data=journey_data,
        walkable_area=walkable_area,
        seed=seed,
        model_type=model_type,
        global_parameters=global_parameters,
        direct_steering_info=direct_steering_info,
        global_ds_journey_id=global_ds_journey_id,
        global_ds_stage_id=global_ds_stage_id,
    )

    # Inject direct steering info into spawning_info
    spawning_info["direct_steering_info"] = direct_steering_info
    spawning_info["global_ds_journey_id"] = global_ds_journey_id
    spawning_info["global_ds_stage_id"] = global_ds_stage_id

    return (
        {
            "stage_map": stage_map,
            "journey_ids": journey_data["journey_ids"],
        },
        positions,
        agent_radii,
        spawning_info,
    )


def _build_fallback_checkpoint_chain(
    ordered_checkpoint_ids: list[str], nearest_exit_id: str
) -> tuple[dict[str, list[tuple[str, float]]], str]:
    """Build a path_choices map that chains a list of checkpoints into the nearest exit.

    Used by the fallback (no `journeys_v2`) path to honor checkpoint
    `waiting_time` and `speed_factor` settings instead of sending every agent
    straight to the closest exit (the regression that caused
    jupedsim-scenarios#8). The chain is deterministic — scenario JSON
    insertion order — so agents in the same distribution take the same
    route.

    Returns
    -------
    (path_choices, first_target_stage)
        ``path_choices`` keys are origin stages, values are
        ``[(next_stage, 100.0)]``. ``first_target_stage`` is the first
        checkpoint (or ``nearest_exit_id`` when there are no checkpoints).
    """
    if not ordered_checkpoint_ids:
        return {}, nearest_exit_id
    chain = list(ordered_checkpoint_ids) + [nearest_exit_id]
    path_choices: dict[str, list[tuple[str, float]]] = {}
    for i in range(len(chain) - 1):
        path_choices[chain[i]] = [(chain[i + 1], 100.0)]
    return path_choices, chain[0]


def _initialize_with_fallback(
    simulation: jps.Simulation,
    data: dict[str, Any],
    walkable_area: pedpy.WalkableArea,
    seed: int,
    model_type: str,
    global_parameters=None,
) -> tuple[dict[str, Any], list[tuple[float, float]], dict[int, float], dict[str, Any]]:
    """Fallback initialization logic"""
    import numpy as np
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    # print("Data:", data)

    # Extract default parameters from distributions if available
    default_agent_radius = 0.2
    default_v0 = 1.2
    default_n_agents = 100

    # Try to get parameters from the first distribution with valid parameters
    if "distributions" in data and data["distributions"]:
        for dist_id, dist_data in data["distributions"].items():
            if "parameters" in dist_data:
                params = dist_data["parameters"]
                logger.info(f"Processing with parameters: {params}")
                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except Exception:
                        continue

                if isinstance(params, dict):
                    default_agent_radius = params.get("radius", default_agent_radius)
                    default_v0 = params.get("v0", default_v0)
                    default_n_agents = params.get("number", default_n_agents)
                    break

    # # Default parameters
    # default_agent_radius = 0.2
    # default_v0 = 1.2
    # default_n_agents = 100

    # Override defaults with global parameters if provided
    if global_parameters:
        default_v0 = getattr(global_parameters, "v0", default_v0)
        default_agent_radius = getattr(
            global_parameters, "radius", default_agent_radius
        )
        default_n_agents = getattr(global_parameters, "number", default_n_agents)

    logger.info(
        f"Using default parameters: v0={default_v0}, radius={default_agent_radius}, n_agents={default_n_agents}"
    )
    # Step 1: Add exits to simulation
    stage_map = {}
    exits = []
    exit_geometries = {}
    direct_steering_info = {}

    for exit_id, exit_data in data.get("exits", {}).items():
        if "coordinates" in exit_data:
            coords = exit_data["coordinates"]
            if isinstance(coords, list) and len(coords) >= 3:
                exit_polygon = Polygon(coords)
                exits.append(exit_polygon)

                enable_throttling = _normalize_bool(
                    exit_data.get("enable_throughput_throttling", False)
                )
                ds_stage = simulation.add_direct_steering_stage()
                stage_map[exit_id] = ds_stage
                exit_geometries[exit_id] = exit_polygon

                # Direct-steering targets are sampled inside this polygon and
                # passed to JuPedSim via agent.target. Exits that extend past
                # the walkable boundary (open-street pattern) would yield
                # targets outside the accessible area; clip to the absorbing
                # area (exit intersected with walkable) so samples stay inside.
                steering_polygon = _clip_exit_to_walkable(
                    exit_polygon, walkable_area.polygon
                )

                direct_steering_info[exit_id] = {
                    "polygon": steering_polygon,
                    "waiting_time": 0.0,
                    "waiting_time_distribution": "constant",
                    "waiting_time_std": 0.0,
                    "speed_factor": 1.0,
                    "ds_stage_id": ds_stage,
                    "enable_throughput_throttling": enable_throttling,
                    "max_throughput": float(exit_data.get("max_throughput", 0.0)),
                    "stage_type": "exit",
                }

    if not exits:
        raise ValueError("No valid exits found in configuration")

    # Preserve checkpoint direct-steering metadata even in fallback mode so
    # runtime zone speed factors can still be applied without explicit journeys.
    checkpoint_data = data.get("checkpoints", {}) or data.get("waiting_polygons", {})
    for cp_id, cp_data in checkpoint_data.items():
        coordinates = cp_data.get("coordinates", [])
        if not coordinates:
            continue
        try:
            checkpoint_polygon = Polygon(coordinates)
        except Exception:
            continue
        waiting_time, enable_throttling, speed_factor = _normalize_checkpoint_mode(
            cp_data.get("waiting_time", 0),
            cp_data.get("enable_throughput_throttling", False),
            cp_data.get("speed_factor", 1.0),
        )
        direct_steering_info[cp_id] = {
            "polygon": checkpoint_polygon,
            "waiting_time": waiting_time,
            "waiting_time_distribution": cp_data.get(
                "waiting_time_distribution", "constant"
            ),
            "waiting_time_std": cp_data.get("waiting_time_std", 1.0),
            "speed_factor": speed_factor,
            "enable_throughput_throttling": enable_throttling,
            "max_throughput": cp_data.get("max_throughput", 1.0),
            "stage_type": "checkpoint",
        }

    # Geometry-only speed zones are applied at runtime and are not journey stages.
    for zone_id, zone_data in data.get("zones", {}).items():
        coordinates = zone_data.get("coordinates", [])
        if not coordinates:
            continue
        try:
            zone_polygon = Polygon(coordinates)
        except Exception:
            continue
        direct_steering_info[zone_id] = {
            "polygon": zone_polygon,
            "waiting_time": 0.0,
            "waiting_time_distribution": "constant",
            "waiting_time_std": 0.0,
            "speed_factor": _normalize_speed_factor(zone_data.get("speed_factor", 1.0)),
            "enable_throughput_throttling": False,
            "max_throughput": 0.0,
            "stage_type": "zone",
        }

    # Step 2: Handle distributions (use walkable area if none provided)
    distributions = []
    distribution_params = []  # Store parameters for each distribution
    total_agents = 0

    if "distributions" in data and data["distributions"]:
        # Use provided distributions
        for dist_id, dist_data in data["distributions"].items():
            if "coordinates" in dist_data:
                coords = dist_data["coordinates"]
                if isinstance(coords, list) and len(coords) >= 3:
                    dist_polygon = Polygon(coords)
                    distributions.append(dist_polygon)

                    # Get parameters for this specific distribution
                    params = dist_data.get("parameters", {})
                    if isinstance(params, str):
                        try:
                            params = json.loads(params)
                        except Exception:
                            params = {}

                    # Use distribution-specific parameters or fall back to defaults
                    dist_params = {
                        "number": params.get("number", default_n_agents),
                        "radius": params.get("radius", default_agent_radius),
                        "v0": params.get("v0", default_v0),
                        "distribution_mode": params.get(
                            "distribution_mode", "by_number"
                        ),
                        "percentage": params.get("percentage", None),
                        "use_flow_spawning": params.get("use_flow_spawning", False),
                        "flow_start_time": params.get("flow_start_time", 0),
                        "flow_end_time": params.get("flow_end_time", 10),
                        "use_premovement": params.get("use_premovement", False),
                        "premovement_distribution": params.get(
                            "premovement_distribution", "gamma"
                        ),
                        "premovement_param_a": params.get("premovement_param_a", None),
                        "premovement_param_b": params.get("premovement_param_b", None),
                        "premovement_seed": params.get("premovement_seed", None),
                        "radius_distribution": params.get(
                            "radius_distribution", "constant"
                        ),
                        "radius_std": params.get("radius_std", None),
                        "v0_distribution": params.get("v0_distribution", "constant"),
                        "v0_std": params.get("v0_std", None),
                    }

                    distribution_params.append(dist_params)
                    total_agents += int(dist_params["number"])

                    logger.info(f"Distribution {dist_id}: {dist_params}")
    # Fallback: use walkable area if no valid distributions
    if not distributions:
        logger.info("No valid distributions found; using walkable area as fallback")
        distributions = [walkable_area.polygon]
        distribution_params = [
            {
                "number": default_n_agents,
                "radius": default_agent_radius,
                "v0": default_v0,
                "distribution_mode": "by_number",
                "percentage": None,
                "use_flow_spawning": False,
                "flow_start_time": 0,
                "flow_end_time": 10,
                "use_premovement": False,
                "premovement_distribution": "gamma",
                "premovement_param_a": None,
                "premovement_param_b": None,
                "premovement_seed": None,
            }
        ]
        total_agents = default_n_agents

    # Step 3: Create a single global DS journey for all fallback agents
    global_ds_stage_id = simulation.add_direct_steering_stage()
    global_ds_journey = jps.JourneyDescription([global_ds_stage_id])
    global_ds_journey_id = simulation.add_journey(global_ds_journey)

    # Step 4: Handle obstacles (holes in walkable area)
    holes = [Polygon(interior) for interior in walkable_area.polygon.interiors]
    obstacles_union = unary_union(holes) if holes else None

    # Step 5: Handle flow spawning vs immediate spawning
    spawning_freqs_and_numbers = []
    starting_pos_per_source = []
    num_agents_per_source = []
    flow_distributions: list[dict[str, Any]] = []
    has_flow_spawning = False

    all_positions = []
    agent_radii = {}
    agent_counter = 0
    fallback_agent_wait_info = {}

    immediate_spawn_distributions = []

    np.random.seed(seed)

    # Separate flow spawning from immediate spawning
    for i, (dist_area, dist_params) in enumerate(
        zip(distributions, distribution_params, strict=False)
    ):
        use_flow_spawning = dist_params.get("use_flow_spawning", False)
        dist_mode, requested_n_agents = _get_distribution_mode_and_count(dist_params)

        if dist_mode == "by_number" and requested_n_agents <= 0:
            continue

        # Remove obstacles from distribution area
        if obstacles_union and not obstacles_union.is_empty:
            clean_dist_area = dist_area.difference(obstacles_union)
        else:
            clean_dist_area = dist_area

        # Ensure distribution area is within walkable area
        clean_dist_area = shapely.intersection(clean_dist_area, walkable_area.polygon)

        if clean_dist_area.is_empty:
            logger.warning(f"Distribution area {i} is outside walkable area")
            continue

        if use_flow_spawning:
            has_flow_spawning = True

            max_radius = _get_max_agent_radius(dist_params)
            max_capacity = _estimate_max_capacity(clean_dist_area, max_radius)

            # Flow spawning: agents spawn over time so the full requested
            # count is valid even if it exceeds simultaneous capacity.
            if dist_mode == "by_number":
                n_agents = requested_n_agents
            else:  # by_percentage
                percentage = _get_distribution_percentage(dist_params)
                n_agents = max(1, int(max_capacity * percentage / 100))

            if n_agents <= 0:
                logger.warning(f"No agents fit in distribution {i}")
                continue

            # Get flow parameters
            flow_start_time = max(0, dist_params.get("flow_start_time", 0))
            flow_end_time = max(
                flow_start_time + 0.1, dist_params.get("flow_end_time", 10)
            )
            flow_duration = flow_end_time - flow_start_time

            # Validate flow rate does not exceed area capacity
            flow_rate = n_agents / flow_duration
            if flow_rate > max_capacity:
                raise ValueError(
                    f"Distribution {i}: flow rate of {flow_rate:.1f} agents/s "
                    f"exceeds area capacity of {max_capacity} agents. "
                    f"Reduce the number of agents ({n_agents}) or increase "
                    f"the flow duration ({flow_duration:.1f}s)."
                )

            dist_params["number"] = n_agents

            # Calculate frequency (seconds between spawns)
            frequency = flow_duration / n_agents
            agents_per_spawn = 1  # spawn 1 agent at a time for smooth flow

            spawning_freqs_and_numbers.append([frequency, agents_per_spawn])
            num_agents_per_source.append(n_agents)

            positions = _distribute_positions_until_filled(
                spawn_area=clean_dist_area,
                distance_to_agents=2 * max_radius,
                distance_to_polygon=max_radius,
                seed=seed + i,
            )
            starting_pos_per_source.append(positions)

            # Store flow distribution info
            flow_distributions.append(
                {
                    "dist_index": i,
                    "params": dist_params,
                    "start_time": flow_start_time,
                    "end_time": flow_end_time,
                    "area": clean_dist_area,
                }
            )

            logger.info(
                f"Flow spawning: Distribution {i} - {n_agents} agents over {flow_duration}s"
            )
        else:
            # Store for immediate spawning
            immediate_spawn_distributions.append(
                {"area": clean_dist_area, "params": dist_params, "index": i}
            )

    # Handle immediate spawning (with optional premovement)
    premovement_times = {}  # Dictionary mapping agent_id -> (premovement_time, position)
    has_premovement = False

    for spawn_data in immediate_spawn_distributions:
        try:
            max_radius = _get_max_agent_radius(spawn_data["params"])
            max_capacity = _estimate_max_capacity(spawn_data["area"], max_radius)
            dist_mode, requested_count = _get_distribution_mode_and_count(
                spawn_data["params"]
            )
            if dist_mode == "by_percentage":
                percentage = _get_distribution_percentage(spawn_data["params"])
                requested_count = max(1, int(max_capacity * percentage / 100))
            if requested_count > max_capacity:
                raise ValueError(
                    f"Distribution {spawn_data['index']}: requested {requested_count} agents "
                    f"but area can hold at most ~{max_capacity}. "
                    f"Reduce the number of agents or enlarge the distribution area."
                )
            positions = _distribute_positions_by_number(
                spawn_area=spawn_data["area"],
                number_of_agents=requested_count,
                distance_to_agents=2 * max_radius,
                distance_to_polygon=max_radius,
                seed=seed + spawn_data["index"],
            )
        except Exception as e:
            error_msg = (
                f"CRITICAL: Failed to place agents in distribution area {spawn_data['index']}. "
                f"Error: {str(e)}. This usually means the spawn area is too small or crowded. "
                f"Consider: 1) Making the distribution area larger, 2) Reducing the number of agents, "
                f"3) Increasing distance between agents, or 4) Checking for obstacles in the area."
            )
            logger.error(f"{error_msg}")
            raise Exception(error_msg)

        # Check if this distribution uses premovement
        use_premovement = spawn_data["params"].get("use_premovement", False)

        # Generate premovement times if enabled
        agent_premovement_times = None
        if use_premovement:
            has_premovement = True
            # Premovement support lives in an external utils package not vendored
            # here; importing lazily keeps the default path dependency-free.
            from utils.premovement_distributions import (  # type: ignore[import-not-found]
                PREMOVEMENT_PRESETS,
                create_premovement_distribution,
            )

            dist_type = spawn_data["params"].get("premovement_distribution", "gamma")
            param_a = spawn_data["params"].get("premovement_param_a")
            param_b = spawn_data["params"].get("premovement_param_b")
            premovement_seed = spawn_data["params"].get("premovement_seed")

            # Use custom parameters if provided, otherwise use presets
            if param_a is not None and param_b is not None:
                dist_params = {"a": param_a, "b": param_b}
            else:
                dist_params = PREMOVEMENT_PRESETS.get(
                    dist_type, PREMOVEMENT_PRESETS["gamma"]
                )

            # Use distribution-specific seed or global seed
            if premovement_seed is None:
                premovement_seed = seed + spawn_data["index"] + 1000

            logger.info(
                f"Generating premovement times: {dist_type} with params {dist_params}, seed={premovement_seed}"
            )
            distribution = create_premovement_distribution(
                dist_type, dist_params, premovement_seed
            )
            agent_premovement_times = distribution.sample(len(positions))

            logger.info(
                f"Premovement times stats - Min: {agent_premovement_times.min():.2f}s, "
                f"Max: {agent_premovement_times.max():.2f}s, "
                f"Mean: {agent_premovement_times.mean():.2f}s"
            )
        # Sample per-agent radius and v0
        rng = np.random.RandomState(seed + spawn_data["index"])
        sampled_radii, sampled_v0s = _sample_agent_values(
            spawn_data["params"], len(positions), rng
        )

        # Build stage configs for DS navigation (only needed if throttled exits exist)
        stage_configs = {}
        if direct_steering_info:
            for sk, info in direct_steering_info.items():
                stage_configs[sk] = {
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
                    "speed_factor": _normalize_speed_factor(
                        info.get("speed_factor", 1.0)
                    ),
                }

        # Checkpoints declared in the scenario but no journey to chain them
        # into — route through them in JSON-insertion order before the
        # nearest exit (jupedsim-scenarios#8). Empty list → straight-to-exit
        # behavior, preserved.
        ordered_checkpoint_ids = [
            cp_id
            for cp_id, info in direct_steering_info.items()
            if info.get("stage_type") == "checkpoint"
        ]

        # Add agents with nearest exit assignment — all on global DS journey
        for idx, pos in enumerate(positions):
            nearest_exit_id = _find_nearest_exit(pos, exit_geometries=exit_geometries)
            path_choices, first_target_stage = _build_fallback_checkpoint_chain(
                ordered_checkpoint_ids, nearest_exit_id
            )

            agent_radius = float(sampled_radii[idx])
            agent_v0 = float(sampled_v0s[idx])

            # Modify agent parameters based on premovement
            agent_params_dict = {
                "radius": agent_radius,
                "v0": 0.0 if use_premovement else agent_v0,
            }

            agent_params = create_agent_parameters(
                model_type=model_type,
                position=pos,
                params=agent_params_dict,
                global_params=global_parameters,
                journey_id=global_ds_journey_id,
                stage_id=global_ds_stage_id,
            )

            agent_id = simulation.add_agent(agent_params)
            all_positions.append(pos)
            agent_radii[agent_id] = agent_radius

            # Build DS wait info — chain through checkpoints (if any) then exit.
            base_seed = seed + idx * 9973
            target_rng = np.random.RandomState(base_seed)
            first_polygon = direct_steering_info[first_target_stage]["polygon"]
            target = _random_point_in_polygon(first_polygon, target_rng)
            fallback_agent_wait_info[agent_id] = {
                "mode": "path",
                "path_choices": path_choices,
                "stage_configs": stage_configs,
                "current_origin": nearest_exit_id,
                "current_target_stage": first_target_stage,
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

            # Store premovement time and desired speed for this agent
            if use_premovement and agent_premovement_times is not None:
                premovement_times[agent_id] = {
                    "premovement_time": float(agent_premovement_times[idx]),
                    "position": pos,
                    "desired_speed": agent_v0,
                    "activated": False,
                }

            agent_counter += 1

    # Prepare spawning info for flow spawning and premovement
    agent_counter_per_source = [0] * len(flow_distributions)

    spawning_info = {
        "has_flow_spawning": has_flow_spawning,
        "spawning_freqs_and_numbers": spawning_freqs_and_numbers,
        "starting_pos_per_source": starting_pos_per_source,
        "num_agents_per_source": num_agents_per_source,
        "agent_counter_per_source": agent_counter_per_source,
        "flow_distributions": flow_distributions,
        "model_type": model_type,
        "global_parameters": global_parameters,
        "stage_map": stage_map,
        "exit_geometries": exit_geometries,
        "exits": exits,
        "has_premovement": has_premovement,
        "premovement_times": premovement_times,
        "agent_wait_info": fallback_agent_wait_info,
        "direct_steering_info": direct_steering_info,
        "global_ds_journey_id": global_ds_journey_id,
        "global_ds_stage_id": global_ds_stage_id,
    }

    logger.info(
        f"Added {len(all_positions)} agents using fallback logic (immediate), prepared {len(flow_distributions)} flow sources"
    )
    return (
        {
            "stage_map": stage_map,
            "journey_ids": {},
        },
        all_positions,
        agent_radii,
        spawning_info,
    )


def _find_nearest_exit(
    position: tuple,
    stage_map: dict | None = None,
    exits: list | None = None,
    exit_geometries: dict | None = None,
):
    """Find the key of the nearest exit to the given position."""

    point = Point(position)
    min_distance = float("inf")
    nearest_stage_id = None

    if exit_geometries:
        for stage_id, exit_geom in exit_geometries.items():
            distance = point.distance(exit_geom)
            if distance < min_distance:
                min_distance = distance
                nearest_stage_id = stage_id
        if nearest_stage_id is not None:
            return nearest_stage_id

    if stage_map and exits:
        preferred_stage_ids = [
            stage_id
            for stage_key, stage_id in stage_map.items()
            if isinstance(stage_key, str) and stage_key.startswith("jps-exits_")
        ]
        if not preferred_stage_ids:
            preferred_stage_ids = [
                stage_id
                for stage_key, stage_id in stage_map.items()
                if isinstance(stage_key, str) and "exit" in stage_key.lower()
            ]
        if not preferred_stage_ids and len(stage_map) == len(exits):
            preferred_stage_ids = list(stage_map.values())
        if not preferred_stage_ids:
            preferred_stage_ids = list(stage_map.values())[: len(exits)]

        for stage_id, exit_geom in zip(preferred_stage_ids, exits, strict=False):
            if stage_id == -1:
                continue
            distance = point.distance(exit_geom)

            if distance < min_distance:
                min_distance = distance
                nearest_stage_id = stage_id
        if nearest_stage_id is not None:
            return nearest_stage_id

    raise ValueError("No exits available for nearest-exit assignment")


def _clip_exit_to_walkable(exit_polygon, walkable_polygon):
    """Return exit ∩ walkable as a Polygon — the absorbing region.

    Direct-steering targets are sampled inside the exit polygon and assigned
    via agent.target. JuPedSim rejects targets outside the walkable area
    with "Point ... is outside of accessible area" on iterate(0). Clipping
    to the walkable area keeps samples inside while preserving the
    open-street pattern of drawing exits past the boundary. Falls back to
    raising rather than returning the raw polygon — silent fallback would
    just reintroduce the bug.
    """
    try:
        clipped = exit_polygon.intersection(walkable_polygon)
    except Exception as exc:
        raise ValueError(
            f"Failed to clip exit polygon to walkable area: {exc}"
        ) from exc

    if clipped.is_empty:
        raise ValueError("Exit polygon does not overlap the walkable area")

    geom_type = clipped.geom_type
    if geom_type in ("Polygon", "MultiPolygon"):
        polygon_like = clipped
    elif geom_type == "GeometryCollection":
        polys = [g for g in clipped.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            raise ValueError(
                "Exit polygon overlaps the walkable area only along an edge "
                "(zero-area absorbing region)"
            )
        polygon_like = polys[0] if len(polys) == 1 else max(polys, key=lambda g: g.area)
    else:
        raise ValueError(f"Unexpected clipped geometry type: {geom_type}")

    if polygon_like.area <= 0:
        raise ValueError(
            "Exit polygon overlaps the walkable area with zero area"
        )
    return polygon_like


def _random_point_in_polygon(polygon, rng, min_clearance: float = 0.2):
    """Generate a random point inside a polygon, preferring interior clearance."""

    candidate_polygon = polygon
    if min_clearance > 0:
        try:
            inner_polygon = polygon.buffer(-float(min_clearance))
            if not inner_polygon.is_empty:
                if hasattr(inner_polygon, "geoms"):
                    candidate_polygon = max(
                        inner_polygon.geoms, key=lambda geom: geom.area
                    )
                else:
                    candidate_polygon = inner_polygon
        except Exception:
            candidate_polygon = polygon

    minx, miny, maxx, maxy = candidate_polygon.bounds
    for _ in range(1000):
        x = rng.uniform(minx, maxx)
        y = rng.uniform(miny, maxy)
        if candidate_polygon.contains(Point(x, y)):
            return (x, y)

    # Fallback to the original polygon when inner buffering was too restrictive.
    if candidate_polygon is not polygon:
        minx, miny, maxx, maxy = polygon.bounds
        for _ in range(1000):
            x = rng.uniform(minx, maxx)
            y = rng.uniform(miny, maxy)
            if polygon.contains(Point(x, y)):
                return (x, y)

    c = candidate_polygon.representative_point()
    return (c.x, c.y)


def _add_stages(
    simulation: jps.Simulation, data: dict[str, Any], walkable_area=None
) -> tuple[dict[str, int], dict[str, dict]]:
    """Add checkpoints and exits. Returns (stage_map, direct_steering_info)."""
    stage_map = {}
    direct_steering_info = {}

    # Parse checkpoints (with backward compat for waiting_polygons key)
    checkpoint_data = data.get("checkpoints", {}) or data.get("waiting_polygons", {})
    for cp_id, cp_data in checkpoint_data.items():
        coordinates = cp_data.get("coordinates", [])
        if not coordinates:
            continue
        waiting_time, enable_throttling, speed_factor = _normalize_checkpoint_mode(
            cp_data.get("waiting_time", 0),
            cp_data.get("enable_throughput_throttling", False),
            cp_data.get("speed_factor", 1.0),
        )
        from shapely.geometry import Polygon as ShapelyPolygon

        polygon = ShapelyPolygon(coordinates)
        ds_stage = simulation.add_direct_steering_stage()
        direct_steering_info[cp_id] = {
            "polygon": polygon,
            "waiting_time": waiting_time,
            "waiting_time_distribution": cp_data.get(
                "waiting_time_distribution", "constant"
            ),
            "waiting_time_std": cp_data.get("waiting_time_std", 1.0),
            "speed_factor": speed_factor,
            "ds_stage_id": ds_stage,
            "enable_throughput_throttling": enable_throttling,
            "max_throughput": cp_data.get("max_throughput", 1.0),
        }
        stage_map[cp_id] = ds_stage
        logger.info(
            f"Added DirectSteeringStage for checkpoint {cp_id}: time={cp_data.get('waiting_time', 0)}s"
        )
    # Zones are geometry modifiers and intentionally omitted from stage_map.
    for zone_id, zone_data in data.get("zones", {}).items():
        coordinates = zone_data.get("coordinates", [])
        if not coordinates:
            continue
        from shapely.geometry import Polygon as ShapelyPolygon

        polygon = ShapelyPolygon(coordinates)
        direct_steering_info[zone_id] = {
            "polygon": polygon,
            "waiting_time": 0.0,
            "waiting_time_distribution": "constant",
            "waiting_time_std": 0.0,
            "speed_factor": _normalize_speed_factor(zone_data.get("speed_factor", 1.0)),
            "enable_throughput_throttling": False,
            "max_throughput": 0.0,
            "stage_type": "zone",
        }

    for exit_id, exit_data in data.get("exits", {}).items():
        coordinates = exit_data.get("coordinates", [])
        if not coordinates:
            continue
        from shapely.geometry import Polygon as ShapelyPolygon

        exit_polygon = ShapelyPolygon(coordinates)
        enable_throttling = _normalize_bool(
            exit_data.get("enable_throughput_throttling", False)
        )

        ds_stage = simulation.add_direct_steering_stage()
        stage_map[exit_id] = ds_stage

        # Direct-steering targets are sampled inside this polygon and assigned
        # to agents via agent.target. Exits crossing the walkable boundary
        # (open-street pattern) would yield targets outside the accessible
        # area; clip to exit ∩ walkable so samples stay inside.
        steering_polygon = (
            _clip_exit_to_walkable(exit_polygon, walkable_area.polygon)
            if walkable_area is not None
            else exit_polygon
        )

        # Always include exits in direct_steering_info so DS-routed agents
        # (e.g. coming from a checkpoint) can navigate to and be removed at exits.
        direct_steering_info[exit_id] = {
            "polygon": steering_polygon,
            "waiting_time": 0.0,
            "waiting_time_distribution": "constant",
            "waiting_time_std": 0.0,
            "speed_factor": 1.0,
            "ds_stage_id": ds_stage,
            "enable_throughput_throttling": enable_throttling,
            "max_throughput": float(exit_data.get("max_throughput", 0.0)),
            "stage_type": "exit",
        }

    for dist_id in data.get("distributions", {}):
        # Distributions don't need to be added as stages in JuPedSim,
        # but we need them in stage_map for journey creation
        stage_map[dist_id] = -1

    return stage_map, direct_steering_info


def _process_distributions(
    data: dict[str, Any],
) -> tuple[dict[str, list[list[float]]], dict[str, dict[str, Any]]]:
    """Process distribution geometries from JSON."""
    dist_geom = {}
    dist_params = {}

    for dist_id, dist_data in data.get("distributions", {}).items():
        dist_geom[dist_id] = dist_data["coordinates"]

        params = dist_data.get("parameters", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {"number": 10, "radius": 0.2, "v0": 1.2}
        elif not isinstance(params, dict):
            params = {"number": 10, "radius": 0.2, "v0": 1.2}

        dist_params[dist_id] = {
            "number": params.get("number", 10),
            "radius": params.get("radius", 0.2),
            "v0": params.get("v0", 1.2),
            "use_flow_spawning": params.get("use_flow_spawning", False),
            "flow_start_time": params.get("flow_start_time", 0),
            "flow_end_time": params.get("flow_end_time", 10),
            "use_premovement": params.get("use_premovement", False),
            "premovement_distribution": params.get("premovement_distribution", "gamma"),
            "premovement_param_a": params.get("premovement_param_a", None),
            "premovement_param_b": params.get("premovement_param_b", None),
            "premovement_seed": params.get("premovement_seed", None),
            "radius_distribution": params.get("radius_distribution", "constant"),
            "radius_std": params.get("radius_std", None),
            "v0_distribution": params.get("v0_distribution", "constant"),
            "v0_std": params.get("v0_std", None),
            "distribution_mode": params.get("distribution_mode", "by_number"),
            "percentage": params.get("percentage", None),
        }

        logger.debug(f"Distribution {dist_id} RAW params from JSON: {params}")
        logger.debug(f"Distribution {dist_id} processed params: {dist_params[dist_id]}")
    return dist_geom, dist_params


def _is_routing_split_node(stage_key: Any) -> bool:
    """Routing split nodes are checkpoints (with backward compat for waypoints/waiting_polygons)."""
    return isinstance(stage_key, str) and (
        stage_key.startswith("jps-checkpoints_")
        or stage_key.startswith("jps-waypoints_")
        or stage_key.startswith("jps-waiting_polygons_")
    )



def _create_journeys_v2(
    simulation: jps.Simulation,
    data: dict[str, Any],
    stage_map: dict[str, int],
) -> dict[str, Any]:
    """Build JuPedSim journeys from the Journey Definition v2 model (#376).

    Each entry in ``data["journeys_v2"]`` becomes exactly one JuPedSim
    journey whose stages are the entries in ``sequence`` (refs to
    checkpoint / exit ids that already exist in ``stage_map``). Per-start-
    area weights live on each distribution's ``journey_weights`` array;
    we copy the journey's variant descriptor into ``journeys_per_distribution``
    once per (distribution × journey) pair, with the normalised percentage.

    This returns the same shape as ``_create_journeys_with_percentages`` so
    the downstream agent spawner (``_add_agents``) is unchanged.
    """
    journeys_v2 = data.get("journeys_v2") or []
    variants_by_v2_id: dict[str, dict[str, Any]] = {}

    # In this codebase every checkpoint and exit is registered as a
    # JuPedSim DirectSteeringStage (see _add_stages). JuPedSim rejects any
    # JourneyDescription that mixes a DS stage with other stages, so each
    # journey is registered with ONE stage only — the entry stage — and
    # the rest of the sequence drives the agent via direct steering at
    # runtime (build_agent_path_state walks variant_data["stages"]).
    for j in journeys_v2:
        seq = [k for k in (j.get("sequence") or []) if k in stage_map]
        if not seq:
            continue
        entry_stage_id = stage_map[seq[0]]
        jd = jps.JourneyDescription([entry_stage_id])
        jps_journey_id = simulation.add_journey(jd)
        variants_by_v2_id[j["id"]] = {
            "id": jps_journey_id,
            # Full sequence — build_agent_path_state reads this to chain
            # the DS waypoints/exits in order at runtime.
            "stages": list(seq),
            "actual_stages": list(seq),
            "entry_stages": [seq[0]],
            "percentage": 0.0,
            "variant_name": f"v2_{j['id']}",
        }

    journeys_per_distribution: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for dist_key, dist_data in (data.get("distributions") or {}).items():
        weights = dist_data.get("journey_weights") or []
        total = sum(float(w.get("weight", 0)) for w in weights)
        if total <= 0:
            continue
        for w in weights:
            base = variants_by_v2_id.get(w.get("journey_id"))
            if not base:
                continue
            # build_agent_path_state expects variant.stages to start with the
            # distribution key — it uses that as the start_origin and the
            # NEXT element becomes the agent's first runtime target. Without
            # the prefix the first stage of the sequence becomes the origin
            # and the agent skips straight to the second element. Prepend
            # dist_key per-copy so each (dist × journey) pair routes
            # through the journey's first stage instead of skipping it.
            variant_copy = dict(base)
            variant_copy["stages"] = [dist_key] + list(base["actual_stages"])
            variant_copy["percentage"] = (float(w.get("weight", 0)) / total) * 100.0
            journeys_per_distribution[dist_key].append(
                {
                    "original_journey_id": w.get("journey_id"),
                    "variant_data": variant_copy,
                }
            )

    journey_ids = {jid: v["id"] for jid, v in variants_by_v2_id.items()}
    journey_variants = {jid: [v] for jid, v in variants_by_v2_id.items()}

    return {
        "journey_ids": journey_ids,
        "journey_variants": journey_variants,
        "journey_endpoints": {},
        "journeys_per_distribution": journeys_per_distribution,
        "waypoint_routing": {},
    }


def _add_agents(
    simulation: jps.Simulation,
    data: dict[str, Any],
    stage_map: dict[str, int],
    dist_geom: dict[str, list[list[float]]],
    dist_params: dict[str, dict[str, Any]],
    journey_data: dict[str, Any],
    walkable_area: pedpy.WalkableArea,
    seed: int,
    model_type: str = "CollisionFreeSpeedModel",
    global_parameters=None,
    direct_steering_info=None,
    global_ds_journey_id=None,
    global_ds_stage_id=None,
) -> tuple[list[tuple[float, float]], dict[int, float], dict[str, Any]]:
    """Add agents to the simulation based on distributions and journeys."""
    journeys_per_distribution = journey_data["journeys_per_distribution"]

    np.random.seed(seed)
    all_positions = []
    agent_radii = {}
    current_agent_id = 0
    agent_wait_info = {}

    # Build exit_geometries keyed by exit_id for nearest-exit lookup
    exit_geometries = {}
    for exit_id, exit_data in data.get("exits", {}).items():
        if "coordinates" in exit_data:
            exit_geometries[exit_id] = Polygon(exit_data["coordinates"])

    spawning_freqs_and_numbers = []
    starting_pos_per_source = []
    num_agents_per_source = []
    flow_distributions: list[dict[str, Any]] = []
    has_flow_spawning = False

    # Process distributions to separate flow vs immediate spawning
    immediate_spawn_distributions = {}
    journeys_per_distribution = journey_data["journeys_per_distribution"]

    for dist_key, polygon in dist_geom.items():
        logger.debug(f"Processing distribution with dist_key = '{dist_key}'")
        logger.debug(
            f"Available journeys_per_distribution keys = {list(journeys_per_distribution.keys())}"
        )
        params = dist_params[dist_key]
        dist_mode, requested_n_agents = _get_distribution_mode_and_count(params)
        use_flow_spawning = params.get("use_flow_spawning", False)

        if dist_mode == "by_number" and requested_n_agents <= 0:
            continue

        try:
            polygon_obj = Polygon(polygon)
            dist_area = shapely.intersection(polygon_obj, walkable_area.polygon)

            if dist_area.is_empty:
                logger.warning(f"Distribution {dist_key} is outside walkable area")
                continue

            # dist_key already matches journey mapping keys (e.g. jps-distributions_0).
            distribution_journeys = journeys_per_distribution.get(dist_key, [])
            logger.debug(
                f"dist_key = '{dist_key}', found {len(distribution_journeys)} distribution_journeys"
            )
            if use_flow_spawning:
                has_flow_spawning = True

                max_radius = _get_max_agent_radius(params)
                max_capacity = _estimate_max_capacity(dist_area, max_radius)

                # Flow spawning: agents spawn over time so the full requested
                # count is valid even if it exceeds simultaneous capacity.
                if dist_mode == "by_number":
                    n_agents = requested_n_agents
                else:  # by_percentage
                    percentage = _get_distribution_percentage(params)
                    n_agents = max(1, int(max_capacity * percentage / 100))

                if n_agents <= 0:
                    logger.warning(f"No agents fit in distribution {dist_key}")
                    continue

                # Get flow parameters
                flow_start_time = max(0, params.get("flow_start_time", 0))
                flow_end_time = max(
                    flow_start_time + 0.1, params.get("flow_end_time", 10)
                )
                flow_duration = flow_end_time - flow_start_time

                # Validate flow rate does not exceed area capacity
                flow_rate = n_agents / flow_duration
                if flow_rate > max_capacity:
                    raise ValueError(
                        f"Distribution '{dist_key}': flow rate of {flow_rate:.1f} agents/s "
                        f"exceeds area capacity of {max_capacity} agents. "
                        f"Reduce the number of agents ({n_agents}) or increase "
                        f"the flow duration ({flow_duration:.1f}s)."
                    )

                params["number"] = n_agents

                frequency = flow_duration / n_agents  # seconds between spawns
                agents_per_spawn = 1  # spawn 1 agent at a time for smooth flow

                spawning_freqs_and_numbers.append([frequency, agents_per_spawn])
                num_agents_per_source.append(n_agents)

                positions = _distribute_positions_until_filled(
                    spawn_area=dist_area,
                    distance_to_agents=2 * max_radius,
                    distance_to_polygon=max_radius,
                    seed=seed + zlib.crc32(dist_key.encode()),
                )
                starting_pos_per_source.append(positions)

                # Store distribution info for flow spawning
                flow_distributions.append(
                    {
                        "dist_key": dist_key,
                        "source_id": len(flow_distributions),
                        "params": params,
                        "start_time": flow_start_time,
                        "end_time": flow_end_time,
                        "journey_info": distribution_journeys,
                    }
                )

                logger.info(
                    f"Flow spawning: {dist_key} - {n_agents} agents over {flow_duration}s (freq: {frequency:.2f}s, rate: {1 / frequency:.2f} agents/s)"
                )
            else:
                # Store for immediate spawning
                immediate_spawn_distributions[dist_key] = {
                    "polygon": polygon,
                    "params": params,
                    "area": dist_area,
                    "distribution_journeys": distribution_journeys,
                }

        except Exception as e:
            logger.warning(f"Error processing distribution {dist_key}: {e}")
            continue

    agent_counter_per_source = [0] * len(flow_distributions)

    # Initialize premovement tracking
    premovement_times = {}
    has_premovement = False

    # Handle immediate spawning distributions (existing logic)
    for dist_key, spawn_data in immediate_spawn_distributions.items():
        try:
            params = spawn_data["params"]
            max_radius = _get_max_agent_radius(spawn_data["params"])
            max_capacity = _estimate_max_capacity(spawn_data["area"], max_radius)
            dist_mode, requested_count = _get_distribution_mode_and_count(
                spawn_data["params"]
            )
            if dist_mode == "by_percentage":
                percentage = _get_distribution_percentage(spawn_data["params"])
                requested_count = max(1, int(max_capacity * percentage / 100))
            if requested_count > max_capacity:
                raise ValueError(
                    f"Distribution '{dist_key}': requested {requested_count} agents "
                    f"but area can hold at most ~{max_capacity}. "
                    f"Reduce the number of agents or enlarge the distribution area."
                )
            positions = _distribute_positions_by_number(
                spawn_area=spawn_data["area"],
                number_of_agents=requested_count,
                distance_to_agents=2 * max_radius,
                distance_to_polygon=max_radius,
                # Preserve legacy deterministic placement for single-region start areas.
                seed=seed,
            )

            all_positions.extend(positions)

            distribution_journeys = spawn_data["distribution_journeys"]

            # Check if this distribution uses premovement
            use_premovement = params.get("use_premovement", False)

            # Generate premovement times if enabled
            agent_premovement_times = None
            if use_premovement:
                has_premovement = True
                from utils.premovement_distributions import (  # type: ignore[import-not-found]
                    PREMOVEMENT_PRESETS,
                    create_premovement_distribution,
                )

                dist_type = params.get("premovement_distribution", "gamma")
                param_a = params.get("premovement_param_a")
                param_b = params.get("premovement_param_b")
                premovement_seed = params.get("premovement_seed")

                # Use custom parameters if provided, otherwise use presets
                if param_a is not None and param_b is not None:
                    dist_params = {"a": param_a, "b": param_b}
                else:
                    dist_params = PREMOVEMENT_PRESETS.get(
                        dist_type, PREMOVEMENT_PRESETS["gamma"]
                    )

                # Use distribution-specific seed or global seed
                if premovement_seed is None:
                    premovement_seed = seed + 1000

                logger.info(
                    f"Generating premovement times for {dist_key}: {dist_type} with params {dist_params}, seed={premovement_seed}"
                )
                distribution = create_premovement_distribution(
                    dist_type, dist_params, premovement_seed
                )
                agent_premovement_times = distribution.sample(len(positions))

                logger.info(
                    f"Premovement times stats - Min: {agent_premovement_times.min():.2f}s, "
                    f"Max: {agent_premovement_times.max():.2f}s, "
                    f"Mean: {agent_premovement_times.mean():.2f}s"
                )
            # Sample per-agent radius and v0
            rng = np.random.RandomState(seed + zlib.crc32(dist_key.encode()) % (2**31))
            sampled_radii, sampled_v0s = _sample_agent_values(
                params, len(positions), rng
            )

            if distribution_journeys:
                logger.info(
                    f"Distribution {dist_key} has {len(distribution_journeys)} journey variants"
                )
                variant_weights, total_weight = _normalize_variant_weights(
                    distribution_journeys
                )

                # Calculate agent distribution using proportional allocation
                agent_assignments = []
                remaining_agents = len(positions)

                for i, variant_info in enumerate(distribution_journeys):
                    variant_data = variant_info["variant_data"]
                    variant_weight = (
                        variant_weights[i] if i < len(variant_weights) else 0.0
                    )

                    if i == len(distribution_journeys) - 1:
                        # Last variant gets all remaining agents to ensure exact total
                        variant_agents = remaining_agents
                    else:
                        # Calculate proportional assignment (rounded)
                        variant_agents = round(
                            (len(positions) * variant_weight) / total_weight
                        )
                        # Ensure we don't exceed remaining agents
                        variant_agents = min(variant_agents, remaining_agents)

                    if variant_agents > 0:
                        agent_assignments.append((variant_info, variant_agents))
                        remaining_agents -= variant_agents

                    logger.info(
                        f"Variant {variant_data['variant_name']}: {variant_agents} agents "
                        f"(weight={variant_weight}, total={total_weight})"
                    )
                # Verify we're using all agents
                total_assigned = sum(assignment[1] for assignment in agent_assignments)
                logger.info(f"Total agents assigned: {total_assigned}/{len(positions)}")

                agent_index = 0
                for variant_info, variant_agents in agent_assignments:
                    variant_data = variant_info["variant_data"]
                    journey_key = variant_info.get("original_journey_id")
                    uses_direct_steering = bool(
                        direct_steering_info
                        and any(
                            stage in direct_steering_info
                            for stage in variant_data.get("actual_stages", [])
                        )
                    )

                    # Entry stage comes from the pre-segmented journey (never mixed DS + regular stages).
                    entry_stages = variant_data.get("entry_stages", [])
                    start_stage_key = next(
                        (
                            stage
                            for stage in entry_stages
                            if stage in stage_map and stage_map[stage] != -1
                        ),
                        None,
                    )

                    if start_stage_key:
                        for _ in range(variant_agents):
                            if agent_index < len(positions):
                                pos = positions[agent_index]
                                agent_radius = float(sampled_radii[agent_index])
                                agent_v0 = float(sampled_v0s[agent_index])

                                # Use v0=0 if premovement is enabled, otherwise use sampled v0
                                actual_v0 = 0.0 if use_premovement else agent_v0
                                agent_journey_id = variant_data["id"]
                                agent_stage_id = stage_map[start_stage_key]
                                if (
                                    uses_direct_steering
                                    and global_ds_journey_id is not None
                                    and global_ds_stage_id is not None
                                ):
                                    agent_journey_id = global_ds_journey_id
                                    agent_stage_id = global_ds_stage_id

                                agent_params = create_agent_parameters(
                                    model_type=model_type,
                                    position=pos,
                                    params={"v0": actual_v0, "radius": agent_radius},
                                    global_params=global_parameters,
                                    journey_id=agent_journey_id,
                                    stage_id=agent_stage_id,
                                )

                                agent_id = simulation.add_agent(agent_params)
                                agent_radii[agent_id] = agent_radius

                                # Store premovement time if enabled
                                if (
                                    use_premovement
                                    and agent_premovement_times is not None
                                ):
                                    premovement_times[agent_id] = {
                                        "premovement_time": float(
                                            agent_premovement_times[agent_index]
                                        ),
                                        "position": pos,
                                        "desired_speed": agent_v0,
                                        "activated": False,
                                    }

                                # Record path-based direct steering state.
                                # Use agent_index (not JuPedSim agent_id) for seeding
                                # to ensure determinism across runs in the same process.
                                if direct_steering_info:
                                    path_state = build_agent_path_state(
                                        variant_data=variant_data,
                                        journey_key=journey_key,
                                        transitions=[],
                                        direct_steering_info=direct_steering_info,
                                        waypoint_routing={},
                                        seed=seed,
                                        agent_id=agent_index,
                                        agent_radius=agent_radius,
                                    )
                                    if path_state:
                                        agent_wait_info[agent_id] = path_state

                                agent_index += 1
                                current_agent_id += 1
            else:
                # No journey variants — spawn on global DS journey, build DS wait info
                logger.info(
                    f"Distribution {dist_key} has no journey variants - using DS nearest exit"
                )
                # Build stage configs for DS navigation
                ds_info = direct_steering_info or {}
                stage_configs = {}
                for sk, info in ds_info.items():
                    sf = float(info.get("speed_factor", 1.0))
                    stage_configs[sk] = {
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
                        "speed_factor": max(0.0, min(sf, 1.0)),
                    }

                # Same fallback-checkpoint chain logic as the immediate
                # spawn path above — keep flow-spawned agents in sync.
                ordered_checkpoint_ids = [
                    cp_id
                    for cp_id, info in ds_info.items()
                    if info.get("stage_type") == "checkpoint"
                ]

                for idx, pos in enumerate(positions):
                    nearest_exit_id = _find_nearest_exit(
                        pos, exit_geometries=exit_geometries
                    )
                    path_choices, first_target_stage = _build_fallback_checkpoint_chain(
                        ordered_checkpoint_ids, nearest_exit_id
                    )

                    agent_radius = float(sampled_radii[idx])
                    agent_v0 = float(sampled_v0s[idx])

                    agent_params_dict = {
                        "radius": agent_radius,
                        "v0": 0.0 if use_premovement else agent_v0,
                    }

                    agent_params = create_agent_parameters(
                        model_type=model_type,
                        position=pos,
                        params=agent_params_dict,
                        global_params=global_parameters,
                        journey_id=global_ds_journey_id,
                        stage_id=global_ds_stage_id,
                    )

                    agent_id = simulation.add_agent(agent_params)
                    agent_radii[agent_id] = agent_radius

                    # Build DS wait info — chain through checkpoints (if any) then exit.
                    base_seed = seed + current_agent_id * 9973
                    target_rng = np.random.RandomState(base_seed)
                    first_polygon = ds_info[first_target_stage]["polygon"]
                    target = _random_point_in_polygon(first_polygon, target_rng)
                    agent_wait_info[agent_id] = {
                        "mode": "path",
                        "path_choices": path_choices,
                        "stage_configs": stage_configs,
                        "current_origin": nearest_exit_id,
                        "current_target_stage": first_target_stage,
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

                    # Store premovement time if enabled
                    if use_premovement and agent_premovement_times is not None:
                        premovement_times[agent_id] = {
                            "premovement_time": float(agent_premovement_times[idx]),
                            "position": pos,
                            "desired_speed": agent_v0,
                            "activated": False,
                        }
                    current_agent_id += 1

        except Exception as e:
            error_msg = (
                f"CRITICAL: Failed to place agents in distribution '{dist_key}'. "
                f"Error: {str(e)}. This usually means the spawn area is too small or crowded. "
                f"Consider: 1) Making the distribution area larger, 2) Reducing the number of agents, "
                f"3) Increasing distance between agents, or 4) Checking for obstacles in the area."
            )
            logger.error(f"{error_msg}")
            raise Exception(error_msg)

    spawning_info = {
        "has_flow_spawning": has_flow_spawning,
        "spawning_freqs_and_numbers": spawning_freqs_and_numbers,
        "starting_pos_per_source": starting_pos_per_source,
        "num_agents_per_source": num_agents_per_source,
        "agent_counter_per_source": agent_counter_per_source,
        "flow_distributions": flow_distributions,
        "model_type": model_type,
        "global_parameters": global_parameters,
        "stage_map": stage_map,
        "exit_geometries": exit_geometries,
        "has_premovement": has_premovement,
        "premovement_times": premovement_times,
        "agent_wait_info": agent_wait_info,
        "transitions": [],
        "waypoint_routing": {},
        "global_ds_journey_id": global_ds_journey_id,
        "global_ds_stage_id": global_ds_stage_id,
    }

    return all_positions, agent_radii, spawning_info


# ---------------------------------------------------------------------------
# Public aliases
# ---------------------------------------------------------------------------
# These helpers were defined with a leading underscore back when this code
# lived inside the web app and the underscore meant "module-private". After
# the extraction (jupedsim-scenarios#3) the same helpers are imported across
# a package boundary by `Web-Based-Jupedsim/backend/services/simulation_service.py`
# and several of its tests. The underscored names stay (so internal callers
# don't churn) but these aliases give consumers a stable, conventionally
# public surface. See jupedsim-scenarios#4.
random_point_in_polygon = _random_point_in_polygon
find_nearest_exit = _find_nearest_exit
sample_agent_values = _sample_agent_values
clip_exit_to_walkable = _clip_exit_to_walkable
