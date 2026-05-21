# jupedsim-scenarios

Python toolkit for running, sweeping, and analyzing
[JuPedSim](https://www.jupedsim.org/) scenarios authored in the
[Web-Based JuPedSim](https://github.com/PedestrianDynamics/Web-Based-Jupedsim)
editor.

## Status

Alpha (`0.1.0`). Sprint-1 scope: load a scenario JSON and run a single
simulation. Monte Carlo sweeps (`run_sweep`) and a `jps-scenarios` CLI
land in `0.2.0` / `0.3.0`.

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

## Roadmap

| Release | Scope                                                              |
| ------- | ------------------------------------------------------------------ |
| 0.1.0   | Verbatim extraction of `Scenario` + `run_scenario` from web app.   |
| 0.2.0   | `run_sweep(scenario, axes={...}, seeds=...)` Monte Carlo helper.   |
| 0.3.0   | `jps-scenarios` CLI + first community-notebook migration PR.       |
| 0.4.0   | Multiprocess worker pool, restartable sweeps, persisted results.   |

## License

MIT. See [LICENSE](LICENSE).
