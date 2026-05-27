# jupedsim-scenarios

[![CI](https://github.com/PedestrianDynamics/jupedsim-scenarios/actions/workflows/ci.yml/badge.svg)](https://github.com/PedestrianDynamics/jupedsim-scenarios/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/jupedsim-scenarios.svg)](https://pypi.org/project/jupedsim-scenarios/)
[![Python versions](https://img.shields.io/pypi/pyversions/jupedsim-scenarios.svg)](https://pypi.org/project/jupedsim-scenarios/)
[![Downloads](https://static.pepy.tech/badge/jupedsim-scenarios/month)](https://pepy.tech/project/jupedsim-scenarios)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Python toolkit for running, sweeping, and analyzing
[JuPedSim](https://www.jupedsim.org/) scenarios authored in the
[Web-Based JuPedSim](https://github.com/PedestrianDynamics/jupedsim-web-community)
editor.

![Demo: a few lines of Python](https://raw.githubusercontent.com/PedestrianDynamics/jupedsim-scenarios/main/docs/source/_static/jupedsim-scenarios-demo.gif)

> **Intro video (3 min):**
> [![Watch the intro](https://img.youtube.com/vi/GqVUDMuoSmc/0.jpg)](https://youtu.be/GqVUDMuoSmc?si=qWKOeAVCzjG1vg60)

## Install

```bash
pip install jupedsim-scenarios
```

For development from a clone:

```bash
pip install -e ".[dev]"
```

## Single-run usage

```python
from jupedsim_scenarios import load_scenario, run_scenario

scenario = load_scenario("my_scenario.zip")
result = run_scenario(scenario, seed=42)
print(result.evacuation_time)
df = result.trajectory_dataframe()
result.cleanup()
```

`load_scenario` accepts a ZIP archive, a directory containing
`<name>.json` + `<name>.wkt`, or a single self-contained JSON file
(geometry embedded as `walkable_area_wkt`).

To build a `Scenario` in pure Python — without going through a
web-app export — see
[`examples/howtos/08_build_from_scratch.ipynb`](examples/howtos/08_build_from_scratch.ipynb).

### Quick CLI: run a ZIP and bundle the trajectory

[`examples/run_zip.py`](examples/run_zip.py) loads a scenario ZIP,
runs it, prints summary metrics (evacuation time, wall-clock time,
agent counts), and writes `<name>_run.zip` containing the original
`config.json` + `geometry.wkt` plus `trajectory.sqlite` — ready to
drop back into the web app for visualization.

```bash
python examples/run_zip.py my_scenario.zip [seed]
```

### Mutating a scenario — copy first, then assign

`Scenario` is a mutable object. Direct assignments and `add_*` /
`remove_*` / `set_*` calls all change the instance **in place**:

```python
base = load_scenario(...)
base.seed = 99            # this mutates `base` — every later use sees seed=99
```

That's fine when you only want one variant. For sweeps or any time
you want to keep the original intact, call `.copy()` first and edit
the clone:

```python
trial = base.copy()
trial.seed = 99
trial.max_simulation_time = 60
# base is untouched
```

`run_sweep` does this for you per trial. The pattern only matters
when you build variants manually (see
`examples/howtos/10_sweep_via_copy.ipynb`).

## Monte Carlo sweep

```python
from jupedsim_scenarios import load_scenario, run_sweep

base = load_scenario("faster_is_slower.zip")

sweep = run_sweep(
    base,
    axes={"v0": [0.8, 1.2, 1.6, 1.8]},
    apply={"v0": lambda s, v: s.set_agent_params(0, desired_speed=v)},
    seeds=range(40, 50),
    workers=4,
)

df = sweep.to_dataframe()
print(df.groupby("v0")["evacuation_time"].agg(["mean", "std"]))
sweep.cleanup()
```

`run_sweep` walks the cartesian product of `axes`, applies each axis's
mutator to an isolated `.copy()` of the base, and runs the trials.
`workers=0` uses one worker per CPU. For sweeps that need a different
scenario *shape* per trial — geometry that depends on the parameters,
journeys that vary — use `run_sweep_from_factory` instead.

For deeper coverage see the how-to notebooks:

- [`04_sweep_basics`](examples/howtos/04_sweep_basics.ipynb) — axes / apply / paired conditions
- [`09_sweep_save_load`](examples/howtos/09_sweep_save_load.ipynb) — `SweepResult.save` / `load`
- [`10_sweep_via_copy`](examples/howtos/10_sweep_via_copy.ipynb) — factory sweeps and `Scenario.copy()`

## Command line

```
jps-scenarios run scenario.json --seed 42 --out trajectory.sqlite
```

Runs a single scenario and prints a one-line JSON summary
(`evacuation_time`, agent counts, `sqlite_file`) to stdout. Useful in CI
or scripted pipelines; notebook workflows should stay on the Python API.

## Documentation

API reference, bottleneck tutorial, and how-tos are built with Sphinx
and deployed on every push to `main` via GitHub Pages.

To build locally:

```bash
pip install -e .
pip install -r docs/requirements.txt
sphinx-build -b html docs/source docs/build/html
```

## Roadmap

Shipped: see [CHANGELOG.md](CHANGELOG.md). Current release: **0.6.2**.

On the table for future releases:

- Greenfield `Scenario()` constructor — a builder shape that doesn't
  require pre-loading a JSON template (R3.7 in
  [`docs/dev/api-design-cleanup.md`](docs/dev/api-design-cleanup.md)).
- Typed `Zone` / `Stage` view classes with property setters,
  replacing the `set_zone_speed_factor` / `set_checkpoint_waiting_time`
  wrappers (R3.10).
- Removal of the `v0` / `v0_std` / `v0_distribution` deprecated kwargs
  (currently still accepted with `DeprecationWarning`).

Concrete proposals are tracked under
[issues](https://github.com/PedestrianDynamics/jupedsim-scenarios/issues).

## Citation

If `jupedsim-scenarios` supports work you publish, please cite the
upstream [JuPedSim](https://www.jupedsim.org/stable/citing.html)
project and link to this repository. A dedicated DOI for this
toolkit will be added once a Zenodo deposit is in place.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the dev install, local
checks, and PR conventions.

## License

MIT. See [LICENSE](LICENSE).
