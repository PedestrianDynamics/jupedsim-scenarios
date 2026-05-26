# Changelog

All notable changes to `jupedsim-scenarios` are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] — 2026-05-26

A focused API-ergonomics pass. See `docs/api-design-cleanup.md` for the
full per-item rationale.

### Breaking changes

- `Scenario.copy(sim_params={...})` now raises `TypeError` if the
  replacement dict drops keys present in the original. Pass every
  original key (or mutate `clone.sim_params` after `copy()`) to keep
  the previous behavior.
- `Scenario.exits`, `.distributions`, `.stages`, `.zones` now return
  read-only views (`types.MappingProxyType`). Top-level assignment such
  as `scenario.exits["new"] = …` raises `TypeError`. Nested per-element
  edits and all setters are unaffected.
- `set_agent_params(..., v0=X, desired_speed=Y)` with `X != Y` now
  raises `TypeError`. Previously the conflict was resolved silently in
  favor of `desired_speed`.
- `ScenarioResult.frame_rate` and `.dt` raise `KeyError` when the
  underlying metrics dict is empty instead of silently returning
  hardcoded defaults (`10.0` / `0.01`). The default `run_scenario`
  output always populates them, so most callers see no change.

### Deprecated

- `set_agent_params` keyword arguments `v0`, `v0_std`, and
  `v0_distribution` emit `DeprecationWarning` and will be removed in a
  future release. Use the canonical `desired_speed`,
  `desired_speed_std`, and `desired_speed_distribution`. The
  distribution-params dict still mirrors `desired_speed*` onto the
  legacy `v0*` keys for one release so downstream consumers that read
  raw JSON exports keep working.

### Behavior changes

- `ScenarioResult.frame_rate` and `.dt` are now computed from
  `simulation.delta_time()` and the writer's `every_nth_frame`, not
  hardcoded. Today's defaults still resolve to `10.0` / `0.01`, but any
  future change to either input is reflected immediately.
- `load_scenario` now accepts a third input shape: a single
  self-contained JSON file (with `walkable_area_wkt` embedded). The
  CLI routes through it, so `jps-scenarios run` accepts JSON, ZIP, or
  directory paths uniformly.
- `load_scenario` rejects ambiguous scenario folders / archives (more
  than one `*.json` or `*.wkt`) instead of silently picking the first
  sorted match.
- Corrupt ZIP archives surface as `ValueError` (and exit-2 from the
  CLI) instead of an unhandled `zipfile.BadZipFile` traceback.
- `Scenario.copy(sim_params=...)` documents replacement-not-merge
  semantics explicitly in the docstring.

### Added

- `SweepResult.cleanup()` and `ScenarioResult.cleanup()` return the
  number of files actually removed (`int`).
- Internal helper `Scenario._synced_raw()` produces a mirrored `raw`
  dict on demand for serialization; the cached `walkable_polygon` is
  now wkt-keyed and self-invalidates on any update path.

### Refactored (no public-API change)

- `run_scenario`'s 470-line main loop is decomposed into per-tick
  helpers (`_spawn_flow_agents`, `_apply_premovement`,
  `_advance_direct_steering`, `_advance_path_following`) plus small
  companions. The loop body is now ~50 lines and the helpers are
  unit-testable. Trajectory output is byte-identical to 0.3.7.
- Setter validation extracted into shared helpers
  (`_ensure_positive_int`, `_ensure_in_half_open_range`,
  `_ensure_choice`, …). Error messages now include units (m, m/s).

### Migration

Replace:

```python
scenario.set_agent_params(
    0,
    v0=1.3,
    v0_std=0.2,
    v0_distribution="gaussian",
)
```

with:

```python
scenario.set_agent_params(
    0,
    desired_speed=1.3,
    desired_speed_std=0.2,
    desired_speed_distribution="gaussian",
)
```

For partial sim-param updates, mutate after `copy()` instead of
passing `sim_params=` to `copy()`:

```python
clone = base.copy()
clone.sim_params["max_simulation_time"] = 60
```

To detect ambiguous scenario folders early, ensure each scenario
directory or ZIP archive holds exactly one `*.json` and one `*.wkt`.

## [0.3.7] — prior

Previous releases are tracked in the git history.
