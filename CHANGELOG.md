# Changelog

All notable changes to `jupedsim-scenarios` are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## [0.7.3] — 2026-09-05

### Added

- **`run_local(scenario, out_dir=..., seeds=..., ...)`.** The library form
  of `jps-scenarios sweep`: loads and optionally scales the scenario, runs
  the seeds, writes `scenario.json` and `sweep.json` next to the trial
  sqlites, fills `sweep.meta` and returns the `SweepResult`. It prints
  nothing; a `progress` callback carries per-trial completion. The CLI
  now calls it, so the output layout that `build_report` reads is
  defined once.

### Changed

- **Live progress in parallel sweeps.** `run_sweep` and
  `run_sweep_from_factory` with `workers > 1` now invoke `progress` as
  each trial completes, in trial order, instead of reporting every trial
  at the end. Results, ordering and on-disk layout are unchanged.

## [0.7.2] — 2026-09-05

### Fixed

- **The CLI no longer prints the library's INFO log lines.** PedPy 1.5
  installs a root logging handler at INFO on import, which turned every
  sweep trial into a per-distribution parameter dump. `jps-scenarios`
  now lowers the library logger to WARNING in the parent and in sweep
  worker processes; `--verbose` restores the old output.

## [0.7.1] — 2026-09-05

### Fixed

- **`Scenario.scale_agents(mode="count")` dry-runs the real placer.** The
  capacity formula is the app's UI estimate and is optimistic against
  `jps.distribute_by_number`: a scaled count could pass the check and then
  fail at placement inside the run. After the formula check, every static
  start area whose count changes is now placed with the same spawn area,
  radius, distances and seed derivation as the run (shared helpers in
  `simulation_init`), and `CapacityError` reports the placeable count
  ("requested 20, fits 17 with this seed"). The check is seed-specific and
  the sweep applies it once for the base seed; a per-seed placement
  failure is still possible and lands as a failed trial.
- **`run_sweep` no longer aborts on a raising trial.** An exception from one
  trial (sequential or `workers>1`) is captured as a failed `Trial` with
  `status="error"` and the exception text in `message`; the sweep completes
  and `sweep.json` is written. `jps-scenarios sweep` exits 1 only when
  every trial failed, and `report` renders the Failures section from such
  a sweep while the other sections degrade gracefully.

## [0.7.0] — 2026-09-04

### Added

- **`Scenario.scale_agents(factor, mode="count" | "flow")`** for the local
  stress-test path. `count` multiplies every start area's `number`,
  `initial_number` and flow-schedule numbers and refuses with
  `CapacityError` when a static start area would overflow the app's
  capacity rule; `flow` keeps the spawn rate and stretches the flow
  window instead. The rule and `PRACTICAL_PACKING_FACTOR` live in the new
  `jupedsim_scenarios.capacity` module, which the web app mirrors.
- **`jps-scenarios sweep`**: seed sweep over an exported zip or directory
  with `--seeds`/`--seed-start`/`--seed-end`, `--scale`, `--scale-mode`,
  `--workers`, `--dt`, `--every-nth-frame` and `--out`. Writes per-trial
  sqlites, a `scenario.json` snapshot and `sweep.json` (with scale, mode,
  seeds and wall clock in `meta`).
- **`jps-scenarios report`**: one self-contained HTML report from a saved
  sweep (time until all arrived, per-exit flow, arrival curve, mean
  Gaussian density, failures). Needs the `viz` extra.
- `run_sweep` accepts `dt` and `every_nth_frame`; `SweepResult` gained a
  persisted `meta` dict with `wall_clock_s`.
- Golden-run tooling: per-model fixtures under `tests/golden/fixtures/`,
  `tests/golden/hash_trajectory.py`, `scripts/golden_record.py` and
  `tests/test_golden_run.py`; `expected.json` is recorded from the web app's production run path (`backend/scripts/golden_record.py` there).

### Changed

- `dt` now falls back to the scenario's `simulationParams.dt` (as the web
  app exports it) when not passed explicitly, so a local run matches the
  in-app run for models with a non-default step (WarpDriverModel: 0.05).

## [0.6.7] — 2026-08-09

### Fixed

- **Waiting-stage targets were sampled from different regions on the first
  hop vs. later hops.** The runtime picker floored target clearance at
  `max(0.05, 0.8 · radius)` while the initial picker also includes
  `reach_penetration` — 0.25 vs 0.16 m at the default radius. On a small
  polygon the two could even take different code branches (eroded-polygon
  sample vs. unbuffered fallback). The runtime picker now includes
  `reach_penetration` too, so every hop samples the same region. (#80)
- **Fallback first-hop targets are picked with the same rule as every
  later hop.** Both fallback spawn sites assigned the first target with a
  raw random interior point while the runtime uses the transit/waiting
  rule (centroid for transit stages), so the same checkpoint was aimed at
  differently depending on its position in the chain. (#76)
- **Unused checkpoints silently rewrote routing for the whole population.**
  A scenario with `checkpoints` but no `journeys_v2` chained *every*
  checkpoint, in JSON insertion order, into the nearest exit — so a stage
  drawn in the editor and never wired into a journey became a mandatory
  waypoint for all agents. The chain now carries only checkpoints that do
  something: `waiting_time > 0`, `speed_factor != 1`, or throttling with a
  positive `max_throughput`. Inert checkpoints fall back to
  straight-to-nearest-exit, and #8's `waiting_time` behavior is unchanged
  and pinned by a regression test. On a 40 × 20 m hall (3 inert 0.49 m
  checkpoints, 2 exits, no journeys) evacuation drops from 227.6 s to
  23.1 s at 40 agents, exactly matching the same scenario authored with no
  checkpoints at all. This is a value test, not a declared intent: a
  checkpoint meant as a pure waypoint is indistinguishable from a forgotten
  one in the current schema and is dropped too — express such a route as a
  `journeys_v2` sequence. (#76)

### Changed

- The fallback chain's ordering semantics are now stated rather than
  inherited: one chain shared by the whole population, in scenario JSON
  insertion order, ending at the exit nearest each agent's spawn point.
  Spawn position deliberately does not reorder the checkpoints, so a given
  JSON always routes the same way. (#76)
- Journey-less distributions on the `journeys_v2` path go straight to the
  nearest exit by design. The checkpoint-chain filter there could never
  match (`_add_stages` stamps no `stage_type`) and has been removed;
  checkpoint chaining is solely the fallback initializer's job. No
  behavior change. (#79)
- The fallback (no `journeys_v2`) path assigns each agent the exit nearest
  its spawn point, once, by straight-line distance. This is now accepted
  as best-effort behavior: scenarios that care about exit choice should
  define journeys. (#77, #81 — closed as won't-fix)

## [0.6.6] — 2026-07-21

### Fixed

- **`CollisionFreeSpeedModelV2` crashed on every run.** The model builder
  passed `strength_neighbor_repulsion` / `range_neighbor_repulsion` to the
  upstream V2 constructor, which takes no arguments in jupedsim 1.4.2 —
  those params are per-agent (`CollisionFreeSpeedModelV2AgentParameters`,
  populated in `simulation_init` from `sim_params`). The builder now
  constructs the bare model; the same knobs still reach agents through
  the per-agent path. A parametrized construct-every-builder test pins
  the registry against upstream signature drift. (#75)

## [0.6.5] — 2026-07-21

> Versioning note: from this release on the project follows strict
> [SemVer](https://semver.org/) — three components, features bump MINOR,
> fixes bump PATCH. The four-part `0.6.4.x` scheme is retired; `0.6.5`
> orders above `0.6.4.5` under both SemVer and PEP 440.

### Fixed

- **`desired_speed` mean and spread silently dropped at spawn.** The
  reduced distribution-parameter views in `simulation_init`
  (`_process_distributions` and the flow-spawn builder) whitelisted only
  legacy `v0`/`v0_std`/`v0_distribution` keys, while the public API
  stores canonical `desired_speed*` names. Scenarios authored via
  `add_distribution` (or loaded from modern JSON) spawned every agent at
  the 1.2 m/s default with no Gaussian spread, on all spawn paths; the
  `set_agent_params` compat mirror masked the bug for sweeps. Canonical
  keys are now read first with legacy fallback. Same fix class as the
  `strict_spawning` drop (#67). (#73, #74)

## [0.6.4.5] — 2026-07-20

### Added

- **WarpDriver model tuning via `sim_params`.** The `WarpDriverModel`
  builder previously discarded `sim_params`, so the model always ran with
  upstream defaults and agent radius was the only lever. The six
  constructor knobs are now forwarded as `wd_`-prefixed keys
  (`wd_time_horizon`, `wd_step_size`, `wd_sigma`, `wd_time_uncertainty`,
  `wd_velocity_uncertainty_x`, `wd_velocity_uncertainty_y`), accepted by
  `set_model_params()` and sweepable via `run_sweep`. Defaults match
  jupedsim 1.4.2, so existing scenarios behave identically. (#72)

### Docs

- **"Coming from vanilla JuPedSim" tutorial.** New how-to notebook
  (`examples/howtos/12_from_vanilla_jupedsim.ipynb`) running the same
  bottleneck study twice — ~45 lines of vanilla `jupedsim` vs ~10 lines
  here on identical geometry — plus a parameters × seeds `run_sweep`
  payoff. Linked from the README and the docs how-to index. (#71)

## [0.6.4.4] — 2026-07-08

### Added

- **Per-agent journey attribution.** `spawning_info` now carries an
  `agent_journeys` map (`agent_id -> original v2 journey id`, or `None` for
  nearest-exit direct-steering agents), recorded at spawn in `_add_agents`.
  The trajectory only stores positions, so the journey each agent was assigned
  by the weighted `journey_weights` draw was previously unrecoverable
  downstream; consumers can now colour dots and count by the actual journey.
  Additive: existing `spawning_info` readers are unaffected. Flow-spawned
  agents (added by the caller mid-run) are not included; the caller records
  those.

### CI

- **Type-check survives numpy 2.5.** numpy 2.5.1's shipped stubs use PEP 695
  `type` statements, which `mypy` rejects under `python_version = 3.11` and
  aborts the whole run on. A mypy override now skips following numpy (stubs
  included), so the unpinned CI upgrade no longer red-lights every PR. No
  runtime or packaging change.

## [0.6.4.3] — 2026-06-06

### Fixed

- **Docs build:** notebooks now call pedpy's jupedsim-sqlite loaders with
  the `trajectory_file=` keyword. pedpy 1.5.0 made
  `load_trajectory_from_jupedsim_sqlite` and
  `load_walkable_area_from_jupedsim_sqlite` keyword-only, so the unpinned
  upgrade broke notebook execution and the Sphinx build during the
  `v0.6.4.2` release. `docs/requirements.txt` now caps `pedpy~=1.5` to keep
  a future breaking release off the tagged build path.

## [0.6.4.2] — 2026-06-04

### Fixed

- **`strict_spawning` opt-in restored.** Both distribution-parameter
  builders (`_initialize_with_fallback` and `_process_distributions`)
  whitelist keys explicitly and silently dropped `strict_spawning`, so the
  flow-spawn deferral always behaved leniently regardless of the setting.
  The key now survives processing, so a blocked placement aborts the run
  when `strict_spawning` is enabled.

## [0.6.4.1] — 2026-05-28

### Fixed

- **Docs build:** added `plotly` to `docs/requirements.txt`. The docs
  workflow installs that file rather than the `viz` extra, so executing
  `02_visualisation.ipynb` (which calls `ScenarioResult.visualise()`)
  raised an `ImportError` and broke the Sphinx build.

### Added

- **README:** visualisation section covering the `viz` extra,
  `Scenario.plot()`, and `ScenarioResult.visualise()`.

## [0.6.4] — 2026-05-28

Visualisation: an interactive run animation and a plan plot that overlays
journeys and agent paths.

### Added

- **`ScenarioResult.visualise()`** — interactive plotly playback of a run
  (agents coloured by speed, with a play button and time slider). Reads
  the run's SQLite directly, subsamples long runs automatically, and
  writes a self-contained file via `save_path="run.html"`.
- **`Scenario.plot()` overlays** — `show_journeys=True` (default) draws
  each journey's route as curved arrows; `trajectories=` overlays the
  agent paths from a `ScenarioResult` (or pedpy `TrajectoryData`) on the
  plan.
- **`examples/howtos/02_visualisation.ipynb`** how-to and a bundled
  `examples/assets/journeys.zip` scenario that exercises both overlays.

### Changed

- **Dependencies:** `plotly` added to the `viz` optional-dependency group.
- **How-tos renumbered** `02`–`10` → `03`–`11` to seat the new
  `02_visualisation` next to `01_inspect_scenario`; doc references updated.
- **Docs:** concepts page now documents the plot overlays and
  `visualise()`.
- **`examples/run_zip.py`:** seed defaults to `None`.

### Fixed

- **`Scenario.plot()` now draws `journeys_v2` routes.** Current web-editor
  exports store routes under `journeys_v2`/`sequence` (which the runtime
  already routes through); the plot only read the legacy
  `journeys`/`stages` shape and silently showed no journeys.

## [0.6.3] — 2026-05-27

Docs and examples polish, plus a friendlier placement-error message.
No public API change.

### Added

- **`examples/run_zip.py`** — a small CLI that loads a scenario ZIP,
  runs it, prints summary metrics (evacuation time, wall-clock time,
  agent counts), and writes `<name>_run.zip` bundling the original
  `config.json` + `geometry.wkt` with the produced
  `trajectory.sqlite`, ready to drop back into the Web-Based JuPedSim
  editor for visualization.

### Changed

- **README:** documented `examples/run_zip.py`; removed the demo GIF
  (the 3-minute intro video covers the same ground).
- **Quickstart notebook:** uses pedpy's `plot_trajectories` and a
  data-driven `vmax` (#62, #63).

### Fixed

- **Placement-failure errors now reference the distribution id, not an
  opaque enumerate index.** The legacy spawn path
  (``_initialize_with_fallback``, used whenever ``journeys_v2`` is
  absent or no distribution carries ``journey_weights``) raised
  ``CRITICAL: Failed to place agents in distribution area 0`` where
  ``0`` was the internal enumerate position of the spawn loop. Users
  of the Web-Based JuPedSim editor (whose start areas are labelled
  "Start 1", "Start 2", …) had no way to map the index back to a
  specific area — both because the index was zero-based against a
  one-based UI and because it ignored the stable
  ``jps-distributions_N`` key. The id is now threaded through every
  log line and error in the legacy path (matching the journey-v2 path
  in ``_add_agents``, which already used ``dist_key``). Regression
  test exercises the legacy path explicitly by stripping
  ``journeys_v2`` from the fixture so the dispatcher routes to
  ``_initialize_with_fallback``. (#64)

## [0.6.2] — 2026-05-27

Documentation pass, quickstart bundle, and an editor-parity bugfix
in agent placement. No public API change.

### Fixed

- **Placement spacing matches the Web-Based JuPedSim editor**
  (#51, #59). `_get_max_agent_radius` previously inflated the
  placement spacing to `mean + 3·std` for Gaussian-radius
  distributions, rejecting packings the editor accepts. The
  spacing now uses the mean radius; sampled radii above the mean
  are handled by the simulator's dynamics phase. Concrete impact:
  scenarios with `radius_std > 0` that failed with
  `AgentNumberError` now place successfully.

### Added

- **Quickstart bundle** (#51, #57). `examples/assets/quickstart.zip`
  plus `examples/howtos/00_quickstart.ipynb` — load, run, plot, and
  clean up in a few cells against a tiny scenario shipped with the
  repo. No web-editor export needed for a first run.
- **`run → pedpy` cookbook** (#54).
  `examples/cookbook/run_to_pedpy.ipynb` walks the full pipeline
  from `run_scenario` to a Gaussian density heatmap using pedpy's
  native SQLite reader and `plot_profiles`.
- **CLI reference auto-generated from the parser** (#56) via
  `sphinx-argparse`. `_build_parser` renamed to `build_parser` so
  the directive can target it.
- **`[viz]` extras** for matplotlib-driven examples and `nbmake` in
  `[dev]` extras (#51).

### Docs

- New Sphinx pages: Concepts (object lifecycle, mutability,
  cleanup), Choosing-an-entrypoint (decision table), Troubleshooting
  (FAQ), CLI reference. Landing page reorganised with intro video,
  animated demo GIF (#55), and a "Where to next" panel pointing at
  the new pages.
- How-tos regrouped by goal in `howtos.rst` (no filename renames so
  external links stay valid).
- README refreshed: intro video link, animated GIF, Citation
  section, Contributing pointer, version bumped in the Roadmap.
- `CONTRIBUTING.md` added (dev install, local checks, docs build).
- Internal `api-design-cleanup.md` moved to `docs/dev/`.

### CI

- Full docs build (>30 min) restricted to tag pushes and manual
  dispatch; Pages now publishes on tagged releases only (#60).
  Every PR and main push runs a fast `notebook-smoke` job that
  executes the quickstart notebook end-to-end.

### Tests

- Regression test pinning the quickstart placement and full
  evacuation at the authored seed (#57).
- Audit + pinning tests for the documented safety multipliers in
  `simulation_init.py` (#58). Documents the rationale on 10
  constants; flags 3 as `(unclear — pending audit)` for follow-up.

### Open follow-ups

- `PedestrianDynamics/jupedsim-web-community#131` — which
  placement code path the editor's Run actually uses.
- `PedestrianDynamics/jupedsim-web-community#132` — editor
  Save-vs-Run geometry-scale mismatch surfaced while bundling the
  quickstart.

## [0.6.1] — 2026-05-27

### Docs

- README refreshed for 0.6: trimmed the Monte Carlo section (the
  workers / pickling / factory-sweeps detail is covered by how-tos
  04 / 09 / 10), removed the broken `set_model_type(v)` call from
  the sweep example (the method was removed in 0.5 — write the
  field directly), and replaced the 0.1 → 0.4 historical roadmap
  with a forward-looking list pointing at `CHANGELOG.md` for shipped
  history.
- Single-run example replaced with the `load_scenario` form (the
  raw `Scenario(raw=data_dict, ...)` snippet referenced a phantom
  `data_dict` variable and didn't run).

No code changes — patch release exists to publish the corrected
README on PyPI.

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
