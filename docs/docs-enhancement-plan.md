# Documentation Enhancement Plan

Target release: **0.7.0 — documentation pass**.
Goal: convert "library that works" into "library that is adopted" by
JuPedSim users. No public API changes; docs and small packaging
extras only.

## Assets

- Intro video: <https://youtu.be/GqVUDMuoSmc?si=qWKOeAVCzjG1vg60>
  - Embed on README (after the badge row, before "Install").
  - Embed on Sphinx landing page (`docs/source/index.rst`) above
    "What is jupedsim-scenarios", using the `youtube` directive from
    `sphinxcontrib-youtube` (add to `docs/requirements.txt`).
  - Add a still thumbnail + link variant for PyPI README (PyPI does
    not render iframes).

## Scope summary

Three buckets, ordered by ROI:

1. **High-impact structural** — new pages users currently lack.
2. **Quality of life** — stale text, grouping, CI guardrails.
3. **Polish** — visuals, citation, contributing.

---

## Todos

### Bucket 1 — High-impact structural

- [ ] **Add `docs/source/concepts.rst`** — object model and lifecycle.
  - Cover: `Scenario` (mutable, copy-first), `ScenarioResult`
    (owns temp sqlite, `cleanup()`), `SweepResult` (savable artifact).
  - Include lifecycle diagram (mermaid or graphviz) showing
    `zip/json → load_scenario → Scenario → run_scenario →
    ScenarioResult → DataFrame → pedpy`.
  - Link from `index.rst` toctree as second entry after Getting Started.

- [ ] **Add `docs/source/choosing_an_entrypoint.rst`** — decision table.
  - Table mapping user goal → API call
    (`run_scenario`, `run_sweep`, `run_sweep_from_factory`,
    `Scenario()` constructor, `jps-scenarios` CLI).
  - Link from `index.rst` near top.

- [ ] **Add `docs/source/troubleshooting.rst`** — FAQ.
  - Mutability footgun (copy-first).
  - `frame_rate` `None` semantics.
  - `workers=0` = one per CPU.
  - sqlite temp-dir location and cleanup.
  - Resuming sweeps (`SweepResult.save` / `load`).
  - `v0` / `desired_speed` deprecation.
  - Link from `index.rst`.

- [ ] **Add 5-minute quickstart notebook**
  `examples/howtos/00_quickstart.ipynb`.
  - Single bundled tiny scenario in `examples/scenario_files/`.
  - Loads, runs, prints evac time, plots one trajectory frame.
  - Wire into `index.rst` as the first "try it" link, above the
    long bottleneck tutorial.

- [ ] **Add `examples/cookbook/run_to_pedpy.ipynb`**
  - End-to-end: `run_scenario` → `trajectory_dataframe()` → pedpy
    density / fundamental diagram.
  - Add to `cookbook.rst` toctree.

- [ ] **Add `docs/source/cli.rst`** — CLI reference.
  - Use `sphinx-argparse` (add to `docs/requirements.txt`) targeting
    `jupedsim_scenarios.cli:build_parser` (extract a `build_parser()`
    in `cli.py` if needed — internal-only, no behavior change).
  - Document subcommands, flags, JSON output schema, exit codes.

### Bucket 2 — Quality of life

- [ ] **Fix stale Status block** in `docs/source/index.rst:55-60`.
  - Currently says "0.4.0 lands soon"; current release is 0.6.1.
  - Replace with link to CHANGELOG.

- [ ] **Update README roadmap version** to 0.6.1 (currently 0.6.0).

- [ ] **Regroup how-tos by goal** in `docs/source/howtos.rst`.
  - Sections: Inspecting / Changing agents / Routing & zones /
    Sweeping / Authoring from scratch / Interactive.
  - Do **not** rename notebook files in this PR (avoid breaking
    external links). Filename rename deferred to 0.8.

- [ ] **Add `nbmake` to CI** — execute notebooks on every push.
  - Add `pytest --nbmake examples/` step to `.github/workflows/ci.yml`.
  - Add `nbmake` to `[dev]` extras.

- [ ] **Add Sphinx linkcheck to CI**.
  - `sphinx-build -b linkcheck docs/source docs/build/linkcheck`.
  - Allow warnings; fail only on broken local refs.

- [ ] **Move `docs/api-design-cleanup.md` to `docs/dev/`**.
  - Internal tracking doc shouldn't sit beside the published site.
  - Update any inbound references (README mentions it once).

### Bucket 3 — Polish

- [ ] **Embed intro video**
  (<https://youtu.be/GqVUDMuoSmc?si=qWKOeAVCzjG1vg60>).
  - README: HTML `<a>` wrapping the YouTube thumbnail (PyPI-safe).
  - Sphinx: `.. youtube::` directive on `index.rst`.

- [ ] **Add an animated trajectory GIF** to README top and
  `index.rst`. Source from `run_to_pedpy.ipynb` output or pedpy
  animator. Keep < 2 MB.

- [ ] **Add `[viz]` extras** in `pyproject.toml`
  (`pedpy`, `matplotlib`). Lets the quickstart show a plot in one
  paragraph without a second `pip install`.

- [ ] **Add "Citing this work" section** to README and `index.rst`.
  - Zenodo DOI badge + BibTeX block.
  - Coordinate with maintainers on Zenodo deposit if not yet done.

- [ ] **Add `CONTRIBUTING.md`** at repo root.
  - Dev install (`pip install -e ".[dev]"`).
  - Ruff / mypy / pytest commands.
  - Notebook policy (must execute clean under `nbmake`).
  - Link from README and Sphinx footer.

---

## Out of scope (defer to 0.8+)

- Renaming `01_…10_` how-to filenames (link breakage).
- Public API changes (already tracked in
  `docs/api-design-cleanup.md`).
- Translating docs.
- Tutorial videos beyond the existing intro.

## Acceptance

- `sphinx-build -b html` clean (no new warnings).
- `sphinx-build -b linkcheck` no broken local refs.
- `pytest --nbmake examples/` green.
- README renders correctly on PyPI (no iframe; thumbnail-link only).
- Landing page surfaces the video, quickstart, concepts, and
  troubleshooting within one scroll.
