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

## Status

Alpha (`0.3.3`). Single-run (`run_scenario`), Monte Carlo sweeps
(`run_sweep` — now multiprocess), and a `jps-scenarios` CLI are shipped.
Restartable / resumable sweeps land in 0.4.0.

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
from jupedsim_scenarios import Scenario, run_scenario

scenario = Scenario(
    raw=data_dict,                          # the JSON exported by the web app
    walkable_area_wkt=data_dict["walkable_area_wkt"],
    model_type="CollisionFreeSpeedModel",
    seed=42,
    sim_params=data_dict["config"]["simulation_settings"]["simulationParams"],
    source_path="my_scenario.json",
)
result = run_scenario(scenario, seed=42)
print(result.metrics["evacuation_time"])
df = result.trajectory_dataframe()
result.cleanup()
```

A higher-level `load_scenario(path)` is available for zipped exports
(JSON + WKT file in the same archive or directory).

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
    axes={
        "v0":    [0.8, 1.2, 1.6, 1.8],
        "model": ["CollisionFreeSpeedModel", "AnticipationVelocityModel"],
    },
    apply={
        "v0":    lambda s, v: s.set_agent_params(0, desired_speed=v),
        "model": lambda s, v: s.set_model_type(v),
    },
    seeds=range(40, 50),
    output_dir="runs/",
)

df = sweep.to_dataframe()       # one row per (v0, model, seed) trial
print(df.groupby(["v0", "model"])["evacuation_time"].agg(["mean", "std"]))
sweep.cleanup()                 # delete the per-trial sqlite files
```

The library walks the cartesian product of the named axes, calls each
axis's `apply` function on an isolated `.copy()` of the base scenario,
runs the simulation, and tabulates the results. Anything the
`Scenario.set_*` mutators can change is fair game for sweeping.

Pass ``workers=N`` (or ``workers=0`` for one worker per CPU) to run
trials in parallel:

```python
sweep = run_sweep(base, axes=..., apply=..., seeds=range(40, 50), workers=4)
```

Mutations are applied in the calling process — only the resulting
mutated `Scenario` crosses the process boundary, so user `apply`
lambdas don't need to be picklable.

### Factory-style sweeps

If the scenario can't be expressed as one base mutated by axis values
— typically because the geometry itself depends on the trial parameters
— use `run_sweep_from_factory` instead. Each trial parameter dict is
handed to your factory; the factory builds a fresh `Scenario` and
optionally returns a payload that rides along on `Trial.extras`:

```python
from jupedsim_scenarios import run_sweep_from_factory

def build_loop(params):
    scenario, geometry = build_loop_scenario(
        num_agents=params["num_agents"],
        spacing=TRACK_LENGTH / params["num_agents"],
    )
    return scenario, geometry  # extras travel with the trial

sweep = run_sweep_from_factory(
    build_loop,
    trials=[{"num_agents": n} for n in (50, 100, 200, 400)],
    seeds=[42],
    workers=4,
)
df = sweep.to_dataframe()           # one row per trial; "num_agents" is a column
for t in sweep.trials:
    geometry = t.extras             # whatever the factory returned alongside
```

## Command line

```
jps-scenarios run scenario.json --seed 42 --out trajectory.sqlite
```

Runs a single scenario and prints a one-line JSON summary
(`evacuation_time`, agent counts, `sqlite_file`) to stdout. Useful in CI
or scripted pipelines; notebook workflows should stay on the Python API.

## Documentation

The full API reference and the bottleneck tutorial are built with Sphinx
(stack mirrors [jupedsim.org](https://www.jupedsim.org/): `sphinx-book-theme`
+ `sphinx-autoapi` + `myst-nb`). Every push to `main` rebuilds and deploys
the site via the `.github/workflows/docs.yml` GitHub Pages workflow.

To build locally:

```bash
pip install -e .
pip install -r docs/requirements.txt
sphinx-build -b html docs/source docs/build/html
open docs/build/html/index.html        # macOS; use xdg-open on Linux
```

`conf.py` mirrors `examples/bottleneck_tutorial.ipynb` into the docs tree at
build time, so there's no committed duplicate. If you edit the notebook,
regenerate it first with `python examples/_build_notebook.py` and re-execute
with `jupyter nbconvert --to notebook --execute --inplace
examples/bottleneck_tutorial.ipynb` before building the docs.

## Roadmap

| Release | Scope                                                              |
| ------- | ------------------------------------------------------------------ |
| 0.1.0   | Verbatim extraction of `Scenario` + `run_scenario` from web app.   |
| 0.2.0   | `run_sweep(scenario, axes={...}, seeds=...)`.                      |
| 0.3.0   | Multiprocess worker pool + `jps-scenarios` CLI.                    |
| 0.3.1   | Public aliases for helpers shared with Web-Based-Jupedsim.         |
| 0.3.2   | First PyPI release.                                                |
| 0.3.3   | Fix: checkpoints honored without journeys (#8).                    |
| 0.3.4   | `run_sweep_from_factory` for factory-style sweeps (this release, #11). |
| 0.4.0   | Restartable / resumable sweeps, persisted results.                 |

## License

MIT. See [LICENSE](LICENSE).
