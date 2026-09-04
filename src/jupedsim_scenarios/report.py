"""Self-contained HTML report for a saved sweep.

``build_report`` reads the ``sweep.json`` written by ``jps-scenarios sweep``
(plus the per-trial SQLite trajectories next to it) and writes one HTML
file with matplotlib PNGs embedded as data URIs. It needs the ``viz``
extra::

    pip install 'jupedsim-scenarios[viz]'

Sections, in order: header, time until all arrived, per-exit flow,
arrival curve, density, failures.
"""

from __future__ import annotations

import base64
import html
import io
import math
import pathlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from shapely import wkt
from shapely.geometry import Polygon

from .runner import Scenario, load_scenario
from .sweep import SweepResult, Trial

SWEEP_FILE = "sweep.json"
SCENARIO_SNAPSHOT = "scenario.json"

# Headings, in document order. The CLI smoke test asserts on these.
SECTION_TIME = "Time until all arrived"
SECTION_EXITS = "Per-exit flow"
SECTION_ARRIVAL = "Arrival curve"
SECTION_DENSITY = "Density"
SECTION_FAILURES = "Failures"

# Same Gaussian FWHM and grid the app's heatmap uses.
DENSITY_GAUSSIAN_WIDTH = 0.5
DENSITY_GRID_SIZE = 0.4
# Frames sampled per trial for the density profile; keeps the report
# build bounded on long runs.
DENSITY_MAX_FRAMES = 200


def _require_matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError(
            "jps-scenarios report needs matplotlib. Install the viz extra: "
            "pip install 'jupedsim-scenarios[viz]'"
        ) from exc
    return plt


def _fig_to_data_uri(plt, fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@dataclass
class _TrialData:
    """Per-trial arrival data derived from one SQLite trajectory."""

    trial: Trial
    frame_rate: float
    arrival_times: np.ndarray
    arrival_xy: np.ndarray
    total_agents: int
    df: Any = field(default=None, repr=False)


def _load_trial_data(trial: Trial) -> _TrialData | None:
    result = trial.result
    if not result.sqlite_file or not pathlib.Path(result.sqlite_file).exists():
        return None
    df = result.trajectory_dataframe()
    if df.empty:
        return None
    frame_rate = float(result.metrics.get("frame_rate") or 0.0)
    if frame_rate <= 0:
        return None
    last = df.sort_values("frame").groupby("id").tail(1)
    final_frame = int(df["frame"].max())
    total = int(last.shape[0])
    if not result.success:
        # Agents still present in the final frame never arrived.
        last = last[last["frame"] < final_frame]
    times = (last["frame"].to_numpy(dtype=float) + 1.0) / frame_rate
    xy = last[["x", "y"]].to_numpy(dtype=float)
    return _TrialData(trial, frame_rate, times, xy, total, df)


def _exit_polygons(scenario: Scenario | None) -> dict[str, Polygon]:
    if scenario is None:
        return {}
    polygons = {}
    for exit_id, spec in scenario.exits.items():
        coords = spec.get("coordinates") or []
        if len(coords) < 3:
            continue
        polygons[exit_id] = Polygon(coords)
    return polygons


def _assign_exits(xy: np.ndarray, exits: dict[str, Polygon]) -> list[str]:
    from shapely.geometry import Point

    ids = list(exits)
    labels = []
    for x, y in xy:
        point = Point(x, y)
        distances = [exits[e].distance(point) for e in ids]
        labels.append(ids[int(np.argmin(distances))])
    return labels


def _mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return math.nan, math.nan
    arr = np.asarray(values, dtype=float)
    std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    return float(arr.mean()), std


def _walkable_polygon(scenario: Scenario | None, sweep: SweepResult):
    if scenario is not None:
        return scenario.walkable_polygon
    for trial in sweep.trials:
        raw = trial.result.metrics.get("walkable_polygon")
        if isinstance(raw, str) and raw.startswith(("POLYGON", "MULTIPOLYGON")):
            return wkt.loads(raw)
    return None


def _resolve_scenario(results_dir: pathlib.Path, sweep: SweepResult) -> Scenario | None:
    name = sweep.meta.get("scenario_json") or SCENARIO_SNAPSHOT
    path = results_dir / name
    if not path.exists():
        return None
    return load_scenario(str(path))


def _versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    out = {}
    for name in ("jupedsim-scenarios", "jupedsim", "pedpy"):
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = "unknown"
    return out


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _render_header(sweep: SweepResult, scenario: Scenario | None, results_dir: pathlib.Path) -> str:
    meta = sweep.meta
    seeds = [s for s in sweep.seeds if s is not None]
    seed_range = f"{min(seeds)} to {max(seeds)} ({len(seeds)} seeds)" if seeds else "scenario seed"
    rows = [
        ("Results", str(results_dir)),
        ("Trials", f"{len(sweep.trials)}"),
        ("Scale factor", f"{meta.get('scale', 1.0)} (mode: {meta.get('scale_mode', 'count')})"),
        ("Seeds", seed_range),
        ("Wall clock", f"{meta.get('wall_clock_s', 'n/a')} s"),
    ]
    rows += [(f"Version {k}", v) for k, v in _versions().items()]
    table = "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in rows
    )
    summary = (
        html.escape(scenario.summary()) if scenario is not None else "(scenario snapshot not found)"
    )
    return f"<table class='kv'>{table}</table><pre>{summary}</pre>"


def _render_time_section(plt, sweep: SweepResult) -> str:
    times = [t.result.evacuation_time for t in sweep.trials if t.result.success]
    if not times:
        return "<p>No trial completed, so there is no time-until-all-arrived statistic.</p>"
    mean, std = _mean_std(times)
    half_ci = 1.96 * std / math.sqrt(len(times)) if len(times) > 1 else 0.0
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.hist(times, bins=min(20, max(3, len(times) // 2 + 1)), color="#2563eb", alpha=0.85)
    ax.axvline(mean, color="#111", linestyle="--", linewidth=1)
    ax.set_xlabel("time until all arrived [s]")
    ax.set_ylabel("seeds")
    uri = _fig_to_data_uri(plt, fig)
    stats = [
        ("Mean", f"{mean:.2f} s"),
        ("Std", f"{std:.2f} s"),
        ("95% CI", f"{mean - half_ci:.2f} to {mean + half_ci:.2f} s"),
        ("Min", f"{min(times):.2f} s"),
        ("Max", f"{max(times):.2f} s"),
        ("Completed trials", f"{len(times)} / {len(sweep.trials)}"),
    ]
    table = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in stats)
    return f"<p class='headline'>{mean:.1f} s (mean over {len(times)} seeds)</p><table class='kv'>{table}</table><img src='{uri}' alt='histogram'>"


def _render_exit_section(trial_data: list[_TrialData], exits: dict[str, Polygon]) -> str:
    if not exits:
        return "<p>No exit polygons available (scenario snapshot missing).</p>"
    if not trial_data:
        return "<p>No trajectories available.</p>"
    per_exit_counts: dict[str, list[float]] = {e: [] for e in exits}
    per_exit_flow: dict[str, list[float]] = {e: [] for e in exits}
    for data in trial_data:
        if data.arrival_times.size == 0:
            for e in exits:
                per_exit_counts[e].append(0.0)
            continue
        labels = np.asarray(_assign_exits(data.arrival_xy, exits))
        for e in exits:
            mask = labels == e
            n = int(mask.sum())
            per_exit_counts[e].append(float(n))
            if n < 2:
                continue
            span = float(data.arrival_times[mask].max() - data.arrival_times[mask].min())
            if span > 0:
                per_exit_flow[e].append(n / span)
    rows = []
    for e in exits:
        c_mean, c_std = _mean_std(per_exit_counts[e])
        f_mean, f_std = _mean_std(per_exit_flow[e])
        rows.append(
            f"<tr><td>{html.escape(e)}</td><td>{c_mean:.1f} &plusmn; {c_std:.1f}</td>"
            f"<td>{f_mean:.2f} &plusmn; {f_std:.2f}</td></tr>"
        )
    return (
        "<table class='grid'><tr><th>Exit</th><th>Agents (mean &plusmn; std)</th>"
        "<th>Mean flow [1/s] (first to last arrival, mean &plusmn; std)</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _render_arrival_section(plt, trial_data: list[_TrialData]) -> str:
    curves = [d for d in trial_data if d.total_agents > 0]
    if not curves:
        return "<p>No trajectories available.</p>"
    t_max = max(float(d.arrival_times.max()) if d.arrival_times.size else 0.0 for d in curves)
    if t_max <= 0:
        return "<p>No agent arrived in any trial.</p>"
    grid = np.linspace(0.0, t_max, 300)
    fig, ax = plt.subplots(figsize=(6, 3.6))
    stack = []
    for d in curves:
        sorted_t = np.sort(d.arrival_times)
        frac = np.searchsorted(sorted_t, grid, side="right") / d.total_agents
        stack.append(frac)
        ax.plot(grid, frac, color="#2563eb", alpha=0.15, linewidth=1)
    ax.plot(grid, np.mean(stack, axis=0), color="#111", linewidth=2, label="mean")
    ax.set_xlabel("time [s]")
    ax.set_ylabel("fraction arrived")
    ax.set_ylim(0, 1.02)
    ax.legend(loc="lower right")
    return f"<img src='{_fig_to_data_uri(plt, fig)}' alt='arrival curve'>"


def _trial_density_profile(data: _TrialData, walkable_area) -> np.ndarray | None:
    from pedpy import DensityMethod, compute_density_profile

    frames = np.sort(data.df["frame"].unique())
    stride = max(1, len(frames) // DENSITY_MAX_FRAMES)
    subset = data.df[data.df["frame"].isin(frames[::stride])][["id", "frame", "x", "y"]]
    if subset.empty:
        return None
    profiles = compute_density_profile(
        data=subset,
        walkable_area=walkable_area,
        grid_size=DENSITY_GRID_SIZE,
        density_method=DensityMethod.GAUSSIAN,
        gaussian_width=DENSITY_GAUSSIAN_WIDTH,
    )
    if not profiles:
        return None
    return np.mean([np.asarray(p) for p in profiles], axis=0)


def _render_density_section(plt, trial_data: list[_TrialData], walkable_polygon) -> str:
    if walkable_polygon is None or not trial_data:
        return "<p>No geometry or trajectories available for a density profile.</p>"
    from pedpy import WalkableArea, plot_profiles

    walkable_area = WalkableArea(walkable_polygon)
    profiles = [
        p for p in (_trial_density_profile(d, walkable_area) for d in trial_data) if p is not None
    ]
    if not profiles:
        return "<p>Density profile could not be computed.</p>"
    fig, ax = plt.subplots(figsize=(7, 5))
    plot_profiles(
        walkable_area=walkable_area,
        profiles=profiles,
        axes=ax,
        title=f"Mean Gaussian density (FWHM {DENSITY_GAUSSIAN_WIDTH} m)",
    )
    return (
        f"<img src='{_fig_to_data_uri(plt, fig)}' alt='density'>"
        f"<p class='note'>Mean over {len(profiles)} trials, up to {DENSITY_MAX_FRAMES} frames each, "
        f"grid {DENSITY_GRID_SIZE} m.</p>"
    )


def _render_failures_section(sweep: SweepResult) -> str:
    failed = [t for t in sweep.trials if not t.result.success]
    if not failed:
        return "<p>All trials completed.</p>"
    rows = "".join(
        f"<tr><td>{t.index}</td><td>{t.seed}</td><td>{html.escape(str(t.result.metrics.get('status', '')))}</td>"
        f"<td>{html.escape(str(t.result.metrics.get('message', '')))}</td></tr>"
        for t in failed
    )
    return f"<table class='grid'><tr><th>Trial</th><th>Seed</th><th>Status</th><th>Message</th></tr>{rows}</table>"


def _render_playback(sweep: SweepResult, results_dir: pathlib.Path, out_path: pathlib.Path) -> str:
    links = []
    for t in sweep.trials:
        if not t.result.sqlite_file or not pathlib.Path(t.result.sqlite_file).exists():
            continue
        target = results_dir / f"playback_trial_{t.index:05d}.html"
        t.result.visualise(save_path=target)
        try:
            href = target.relative_to(out_path.parent)
        except ValueError:
            href = target
        links.append(
            f"<li><a href='{html.escape(str(href))}'>trial {t.index} (seed {t.seed})</a></li>"
        )
    if not links:
        return ""
    return f"<h2>Playback</h2><ul>{''.join(links)}</ul>"


_STYLE = """
body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#111}
h1{font-size:1.6rem}h2{margin-top:2.5rem;border-bottom:1px solid #ddd;padding-bottom:.3rem}
table.kv th{text-align:left;padding-right:1rem;font-weight:600}
table.grid{border-collapse:collapse}table.grid th,table.grid td{border:1px solid #ccc;padding:.3rem .6rem}
pre{background:#f6f6f6;padding:.8rem;overflow-x:auto}img{max-width:100%}
.headline{font-size:1.8rem;font-weight:700;margin:.4rem 0}.note{color:#555;font-size:.9rem}
"""


def build_report(
    results_dir: str | pathlib.Path,
    out_path: str | pathlib.Path | None = None,
    *,
    playback: bool = False,
) -> pathlib.Path:
    """Write the HTML report for the sweep saved under ``results_dir``.

    Returns the path of the written file. Raises ``ImportError`` when
    matplotlib is not installed and ``FileNotFoundError`` when
    ``results_dir`` holds no ``sweep.json``.
    """
    plt = _require_matplotlib()
    results = pathlib.Path(results_dir)
    sweep_file = results if results.is_file() else results / SWEEP_FILE
    results = sweep_file.parent
    if not sweep_file.exists():
        raise FileNotFoundError(
            f"{results}: no {SWEEP_FILE} found (run `jps-scenarios sweep` first)"
        )
    out = pathlib.Path(out_path) if out_path is not None else results / "report.html"

    sweep = SweepResult.load(sweep_file)
    scenario = _resolve_scenario(results, sweep)
    trial_data = [d for d in (_load_trial_data(t) for t in sweep.trials) if d is not None]
    exits = _exit_polygons(scenario)
    walkable = _walkable_polygon(scenario, sweep)

    sections = [
        (SECTION_TIME, _render_time_section(plt, sweep)),
        (SECTION_EXITS, _render_exit_section(trial_data, exits)),
        (SECTION_ARRIVAL, _render_arrival_section(plt, trial_data)),
        (SECTION_DENSITY, _render_density_section(plt, trial_data, walkable)),
        (SECTION_FAILURES, _render_failures_section(sweep)),
    ]
    body = "".join(f"<h2>{html.escape(title)}</h2>{content}" for title, content in sections)
    playback_html = ""
    if playback:
        try:
            playback_html = _render_playback(sweep, results, out)
        except ImportError as exc:
            print(f"note: playback skipped ({exc})")

    document = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>jupedsim-scenarios sweep report</title>"
        f"<style>{_STYLE}</style></head><body>"
        "<h1>Sweep report</h1>"
        f"{_render_header(sweep, scenario, results)}{body}{playback_html}"
        "</body></html>"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document, encoding="utf-8")
    return out
