# Changelog

All notable changes to `jupedsim-scenarios` are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] — 2026-05-27

Round-3 nice-to-haves on top of the 0.5 redesign — same five design
rules (simplicity, consistency, sensible defaults, mental models,
discoverability), smaller scope. See `docs/api-design-cleanup.md` for
the R3 rationale per item.

### Added

- **`Scenario.to_json()` + `save_scenario(scenario, path)`** (R3.2) —
  serialize a scenario as self-contained JSON so the
  build-mutate-run-persist loop closes. `to_json()` returns a string;
  `save_scenario` writes to disk (mirrors `load_scenario`,
  parallels `json.dumps`/`json.dump`).
- **`SweepResult.save(path)` + `SweepResult.load(path)`** (R3.1) —
  persist a sweep's axes, seeds, per-trial metrics and sqlite paths
  as JSON; reload metadata later without re-running. Trajectory
  sqlites stay where `output_dir` put them.
- **`SweepResult.__getitem__`** (R3.9) — `sweep[0]` / `sweep[-1]` /
  `sweep[a:b]` work consistently with `len(sweep)` and
  `for t in sweep`. Typed via `@overload`.
- **`remove_exit` accepts an int index** (R3.4) — parity with
  `remove_distribution` / `remove_zone` / `remove_stage`. The four
  resolvers now share one `_resolve_key` helper, so error messages
  stay uniform.
- **CLI passthrough** (R3.5) — `jps-scenarios run` forwards `--dt`,
  `--every-nth-frame`, and `--output-path` to the runner.
- **Four new how-to notebooks** under `examples/howtos/`:
  - `07_interactive_runner` — chunked `ScenarioRunner` with
    mid-run inspection and partial trajectory via pedpy.
  - `08_build_from_scratch` — author a `Scenario` in pure Python
    with `add_*` + `save_scenario`.
  - `09_sweep_save_load` — sweep persistence round-trip + slicing
    + the metrics-survive-cleanup behaviour.
  - `10_sweep_via_copy` — `Scenario.copy()` + `run_sweep_from_factory`
    for trial-shape variation that `axes`/`apply` can't express.

### Breaking changes

- **`add_*` / `remove_*` kwarg `id` renamed to `key`** (R3.12). The
  `id` name shadowed the builtin and read inconsistently across the
  add/remove pair. Callers passing `id=` by keyword must migrate:
  ```python
  # Before
  scenario.add_distribution(poly, id="src-A", number=20)
  scenario.remove_exit(id="exit-A")

  # After
  scenario.add_distribution(poly, key="src-A", number=20)
  scenario.remove_exit(key="exit-A")
  ```
  Positional calls (`scenario.remove_exit("exit-A")`) are unaffected.
- **`Trial.success` removed** (R3.6) — it was the only proxied
  result field; mixed shorthand. Read `trial.result.success` (and
  `trial.result.evacuation_time`, etc.) for a single canonical path.
- **`Scenario.copy(**overrides)` no longer accepts overrides** (R3.11).
  `copy()` only returns a deep clone now; copy-then-assign for
  field changes:
  ```python
  clone = base.copy()
  clone.seed = 99
  clone.max_simulation_time = 60
  ```
  Background: the previous `hasattr`-based override loop accepted
  methods and properties — `copy(plot=lambda: ...)` silently replaced
  the method. The new shape is harder to misuse.

### Deprecations

- The `v0` / `v0_std` / `v0_distribution` kwargs on
  `add_distribution` / `set_agent_params` remain accepted, still
  emit `DeprecationWarning`, and continue to map to
  `desired_speed` / `desired_speed_std` / `desired_speed_distribution`.
  The 0.5.0 changelog promised removal in 0.6 — that was premature;
  removal is deferred to a future release, matching the "future
  release" wording already in `runner.py`.

### Refactored (no public-API change)

- `set_agent_count` is now a thin fold over `set_agent_params` that
  also forces `distribution_mode="by_number"` (R3.3). Docstring
  leads with the side effect; for count-only changes call
  `set_agent_params(id, number=n)` directly.
- `_resolve_key`'s `kind` parameter is typed
  `Literal["Distribution", "Exit", "Zone", "Stage"]` so typos at the
  four call sites surface in Pyright.
- Package docstring rewritten (R3.8) — old text referenced the
  retired `backend/core/` mirror and a never-shipped
  `jupedsim.internal.scenarios` migration.

### Docs

- README: new "Mutating a scenario — copy first, then assign"
  subsection right after Single-run usage. Scenario is mutable in
  place; users want explicit guidance on when to `copy()`.
- `01_inspect_scenario` how-to: parallel callout before the
  log-verbosity section, so the footgun is seen before any setter
  is reached for.

## [0.5.0] — 2026-05-26

A scientist/power-user pass framed against five design rules
(simplicity, consistency, sensible defaults, mental models,
discoverability). See `docs/api-design-cleanup.md` for the full
per-item rationale.

### Added

- **`ScenarioRunner`** — interactive driver matching the imperative
  shape of `jupedsim.Simulation`. Step / inspect / mutate / continue.
  Context-manager friendly; `run_scenario` is now a thin wrapper.
  ```python
  with ScenarioRunner(scenario, seed=42) as runner:
      runner.run_until(10.0)
      print(runner.elapsed_time, runner.agent_count)
      runner.run_until()           # to completion
      result = runner.result()
  ```
- **Additive ops on loaded scenarios** — extend a scenario in pure
  Python without touching `raw`:
  ```python
  did = scenario.add_distribution(poly, number=20, desired_speed=1.4)
  eid = scenario.add_exit([(8, 0), (10, 0), (10, 10), (8, 10)])
  zid = scenario.add_zone(zone_poly, speed_factor=0.5)
  sid = scenario.add_stage(wait_poly, waiting_time=3.0)
  scenario.remove_distribution(did)
  ```
  Coordinates accept shapely `Polygon` or any iterable of `(x, y)`;
  polygons auto-close. IDs are auto-generated as
  `jps-{collection}_{n}` so round-trips with web exports stay clean.
- **`ScenarioResult.as_pedpy_trajectory()`** — adapter to
  `pedpy.TrajectoryData`, so analysis no longer requires rebuilding
  the dataframe + looking up the frame rate manually.
- **Configurable simulation params** on `run_scenario`:
  `dt`, `every_nth_frame`, `output_path` (the trajectory writer
  stride, simulation step, and output location are no longer
  hardcoded).
- **Useful `__repr__` + `_repr_html_`** on `Scenario` — one-line
  debug repr and a notebook-rendered table:
  ```
  Scenario(model='CollisionFreeSpeedModel', seed=42, agents≈25,
           exits=2, distributions=2, stages=1, zones=3)
  ```
- **`Scenario.max_simulation_time`** is now settable
  (`scenario.max_simulation_time = 60`), with positive-number
  validation.

### Breaking changes

- `Scenario.set_seed`, `Scenario.set_max_time`, `Scenario.set_model_type`
  are removed. Write the fields directly:
  ```python
  scenario.seed = 42
  scenario.max_simulation_time = 60
  scenario.model_type = "CollisionFreeSpeedModel"
  ```
- `set_agent_params` and `set_model_params` raise `TypeError` for
  unknown kwargs, with a difflib suggestion:
  ```
  set_agent_params() received unknown keyword arguments:
  'radius_dist' (did you mean 'radius_std'?). Accepted: [...]
  ```
- `run_until(target_time)` clamps `target_time` to
  `scenario.max_simulation_time`; callers can no longer drive the
  simulation past the configured horizon by accident.
- `ScenarioRunner.step` / `.run_until` / `.result` raise
  `RuntimeError` after `close()` instead of silently using a closed
  writer.

### Deprecation removals (none in 0.5)

The `v0` / `v0_std` / `v0_distribution` kwargs deprecated in 0.4 are
still accepted with `DeprecationWarning`. They'll be removed in 0.6.

### Migration

Replace:
```python
scenario.set_seed(42)
scenario.set_max_time(60)
scenario.set_model_type("SocialForceModel")
```
with direct attribute assignment:
```python
scenario.seed = 42
scenario.max_simulation_time = 60
scenario.model_type = "SocialForceModel"
```

For interactive simulations:
```python
# 0.4: one-shot only
result = run_scenario(scenario, seed=42)

# 0.5: also one-shot, plus the interactive option
with ScenarioRunner(scenario, seed=42) as runner:
    runner.run_until(10.0)
    # inspect / mutate ...
    runner.run_until()
    result = runner.result()
```

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
