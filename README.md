# jupedsim-scenarios

Python toolkit for running, sweeping, and analyzing
[JuPedSim](https://www.jupedsim.org/) scenarios authored in the
[Web-Based JuPedSim](https://github.com/PedestrianDynamics/jupedsim-web-community)
editor.

## Status

Alpha (`0.2.0`). Sprint-1 shipped single-run (`run_scenario`); Sprint-2
ships Monte Carlo sweeps (`run_sweep`). Multiprocess workers and the
`jps-scenarios` CLI land in later releases.

## Install

```bash
pip install -e .         # from a clone
# or:
pip install git+https://github.com/PedestrianDynamics/jupedsim-scenarios.git
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

Today `run_sweep` runs trials sequentially. The `workers=` parameter is
reserved for the multiprocess implementation that lands in the next
release.

## Roadmap

| Release | Scope                                                              |
| ------- | ------------------------------------------------------------------ |
| 0.1.0   | Verbatim extraction of `Scenario` + `run_scenario` from web app.   |
| 0.2.0   | `run_sweep(scenario, axes={...}, seeds=...)` (this release).       |
| 0.3.0   | Multiprocess worker pool + `jps-scenarios` CLI.                    |
| 0.4.0   | Restartable / resumable sweeps, persisted results.                 |

## License

MIT. See [LICENSE](LICENSE).
