# API Design Cleanup

Tracking doc for the API ergonomics pass on `jupedsim_scenarios`.
Each item ships in this branch; we cut a release with consolidated notes
once everything below is checked off.

Public surface under review: `Scenario`, `ScenarioResult`, `load_scenario`,
`run_scenario`, `run_sweep`, `run_sweep_from_factory`, `SweepResult`, `Trial`.

## High impact

- [x] **1. Drop `Scenario.__setattr__` magic** — `src/jupedsim_scenarios/runner.py:191-208`
  - Problem: dict-level mutation (`s.sim_params["x"] = 5`) silently bypasses
    the sync hook while attribute reassignment triggers it. Asymmetric and
    fragile; the docstring already calls it out.
  - Fix: replace eager mirroring with lazy serialization. Compute
    `raw["config"]["simulation_settings"]` on demand (e.g. `to_json()` /
    inside `run_scenario`) instead of on every write. Delete the
    `__setattr__` override and `_sync_runtime_to_raw`.
  - Acceptance: setters still work; round-tripping a Scenario through JSON
    reflects the latest field values; tests pass without the sync hook.

- [x] **2. Extract validation helpers** — `runner.py:501-625`
  - Problem: every setter re-implements isinstance + range checks. Magic
    ceilings (`radius <= 1.0`, `desired_speed <= 5.0`) appear without
    rationale in the error message.
  - Fix: small private helpers — `_positive_int(name, v)`,
    `_in_range(name, v, lo, hi)`, `_non_negative_number(name, v)`. Use them
    in every setter. Surface units in messages where ceilings come from a
    physical constraint.
  - Acceptance: setter bodies shrink to validation calls + assignment;
    error messages remain at least as informative.

- [x] **3. Deprecate `v0` / `desired_speed` duality** — `runner.py:536-581`
  - Problem: `set_agent_params` accepts both names and writes both into
    params. The underlying JSON schema institutionalizes the duplication.
  - Fix: pick `desired_speed` as canonical (matches jupedsim upstream).
    Emit `DeprecationWarning` when `v0` / `v0_std` / `v0_distribution` are
    passed. Keep the dual write on the params dict for one release so
    downstream consumers don't break; remove in the release after.
  - Acceptance: passing `v0=` warns; passing `desired_speed=` is silent;
    downstream sim still receives the value.

## Medium impact

- [x] **4. Decompose `run_scenario`** — `runner.py:760-1236`
  - Problem: 470-line orchestration function with no extension points.
    Blocks any future `on_tick=` callback, step API, or custom controllers.
  - Fix: extract `_spawn_flow_agents(...)`, `_apply_premovement(...)`,
    `_advance_direct_steering(...)`, `_advance_path_following(...)`. Keep
    `run_scenario` as a thin loop calling them. No public API change in
    this PR — this is groundwork.
  - Acceptance: `run_scenario` body fits on a screen; helper functions are
    unit-testable; trajectory regression tests unchanged.

- [x] **5. Fix `ScenarioResult.frame_rate` fallback + hardcoded metric**
  - `runner.py:656-663` and `runner.py:1214-1215`
  - Problem: property silently returns `10.0` when metrics are absent.
    Worse: `run_scenario` hardcodes `"frame_rate": 10.0` and `"dt": 0.01`
    into the metrics dict regardless of the actual `every_nth_frame` /
    `dt` used.
  - Fix: compute the true frame rate from `writer.every_nth_frame` and
    the simulation `dt`. Drop the silent fallback — raise or return
    `None` if metrics genuinely lack it.
  - Acceptance: result reflects the actual writer stride; changing
    `every_nth_frame` is visible in `result.frame_rate`.

- [x] **6. `Scenario.copy(**overrides)` partial-update footgun** — `runner.py:487-497`
  - Problem: `clone.copy(sim_params={"x": 1})` replaces the entire dict
    silently — easy to drop keys.
  - Fix: keep current behavior for top-level fields, but for dict-valued
    fields (`sim_params`, `raw`) require explicit replacement via a
    separate kwarg or method. Simplest: document the replacement
    semantics in the docstring + raise `TypeError` if someone passes a
    dict-valued override that's missing keys present in the original.
  - Acceptance: docstring explicit; accidental partial dict overrides
    fail loudly.

- [x] **7. Reconcile `load_scenario` vs CLI input formats**
  - `runner.py:712` (dir or zip), `cli.py:27` (bare JSON only)
  - Problem: three input formats across two entry points, with the CLI
    refusing what the Python API accepts.
  - Fix: route the CLI through `load_scenario`. Teach `load_scenario`
    about the bare-JSON case (detect by suffix / content) so all three
    formats go through one function.
  - Acceptance: CLI accepts `.json`, `.zip`, and dir paths;
    `load_scenario` is the single entry point.

## Low impact

- [x] **8. `SweepResult.cleanup()` returns removed-file count** — `sweep.py:114-117`
  - Change signature to `cleanup() -> int`. Cheap, useful for scripts.

- [x] **9. Read-only views for `Scenario.exits/distributions/stages/zones`**
  - `runner.py:223-240`
  - Wrap with `types.MappingProxyType` when accessed via property, OR
    add a docstring line stating "treat as read-only; use setters to
    mutate." Prefer the proxy.

- [x] **10. Rename `stages` property OR `raw["checkpoints"]`** — `runner.py:231`
  - Problem: `s.stages` returns `raw["checkpoints"]`. Mismatch is a
    papercut when reading `raw` directly.
  - Fix: pick one term project-wide. If the JSON schema is fixed
    upstream, add a one-line comment on the property explaining the
    mapping rather than renaming.

- [ ] **11. (Deferred) Lazy plan generation in `run_sweep`** — `sweep.py:248`
  - Already documented in the source. Not in this PR — track separately
    when memory pressure becomes real.

## Release checklist

- [ ] All items above checked off (or explicitly deferred with a note).
- [ ] `CHANGELOG` entry covering: breaking changes (#1, #3 deprecation,
      #5 metric correction), behavioral changes (#6, #7), additions
      (#8, #9).
- [ ] Version bump: minor (new deprecations + behavioral fixes, no hard
      removals yet).
- [ ] Migration note for `v0` → `desired_speed`.
- [ ] Smoke run of `examples/cookbook/*.ipynb` against the new API.
