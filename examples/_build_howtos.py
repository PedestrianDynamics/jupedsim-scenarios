"""Generate the small how-to notebooks under ``examples/howtos/``.

Each how-to answers ONE focused question a newcomer would ask after the
bottleneck tutorial. Run once; commit the ``.ipynb`` files.

To add a new how-to: define a ``build_<slug>()`` function below that
returns ``(filename, cells)`` and append it to ``HOWTOS``.
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf


def md(cells: list, src: str) -> None:
    cell = nbf.v4.new_markdown_cell(src.strip("\n"))
    cell["id"] = f"cell-{len(cells):02d}"
    cells.append(cell)


def code(cells: list, src: str) -> None:
    cell = nbf.v4.new_code_cell(src.strip("\n"))
    cell["id"] = f"cell-{len(cells):02d}"
    cells.append(cell)


ASSET = '"../assets/bottleneck.zip"'


def build_01_inspect() -> tuple[str, list]:
    cells: list = []
    md(cells, """
# How do I see what's inside a scenario?

A scenario bundles **distributions** (agent sources), **zones**
(speed-modifier regions), **stages** (waypoints / exits / queues), and
the simulation **config**. Every mutator you'll use later
(`set_agent_count`, `set_agent_params`, `set_zone_speed_factor`, ...)
needs the **id** of the thing you want to change.

Use `list_distributions()` / `list_zones()` / `list_stages()` to
discover those ids.
""")
    code(cells, f"""
from jupedsim_scenarios import load_scenario

scenario = load_scenario({ASSET})
""")
    md(cells, "**Distributions** — agent sources. Each has a string `id` and an `index`. Setters accept either.")
    code(cells, "scenario.list_distributions()")
    md(cells, "**Zones** — regions that modify agent speed (e.g. stairs, slow areas).")
    code(cells, "scenario.list_zones()")
    md(cells, "**Stages** — waypoints, exits, queues. Used in journeys.")
    code(cells, "scenario.list_stages()")
    md(cells, """
## Why this matters

Every mutator below takes a `distribution_id`, `zone_id`, or
`stage_id`. Pass either the **string id** (`"jps-distributions_0"`) or
the **integer index** (`0`). The index form is handy when you don't
care about the exact name:

```python
scenario.set_agent_count(0, 50)              # by index
scenario.set_agent_count("jps-distributions_0", 50)  # by string id
```
""")
    return "01_inspect_scenario.ipynb", cells


def build_02_agent_count() -> tuple[str, list]:
    cells: list = []
    md(cells, """
# How do I change the number of agents?

`set_agent_count(distribution_id, n)` rewrites the source so it spawns
`n` agents instead of whatever the scenario JSON specified.
""")
    code(cells, f"""
from jupedsim_scenarios import load_scenario, run_scenario

scenario = load_scenario({ASSET})
scenario.set_agent_count(0, 30)   # 30 agents from the first distribution

result = run_scenario(scenario, seed=42)
print("agents:", result.total_agents)
print("evacuation time:", result.evacuation_time, "s")
result.cleanup()
""")
    md(cells, "Both forms work — by **index** or **string id**:")
    code(cells, """
scenario.set_agent_count(0, 30)                       # index
scenario.set_agent_count("jps-distributions_0", 30)   # string id
""")
    md(cells, """
## Inspecting the raw scenario

The `Scenario` object exposes the parsed JSON as plain dicts. Use
`json.dumps(..., indent=2)` to pretty-print any sub-section.
""")
    code(cells, f"""
import json
from jupedsim_scenarios import load_scenario

scenario = load_scenario({ASSET})

print(json.dumps(scenario.distributions, indent=2, default=str))
""")
    md(cells, "Other dicts you can print the same way: `scenario.zones`, `scenario.stages`, `scenario.config`.")
    md(cells, """
## Capacity check — why a "small" number can still be rejected

jupedsim-scenarios estimates how many agents fit in a distribution
area using a conservative packing approximation:

```
max_capacity ≈ floor( area / (π · r²) · 0.5 )
```

With the default radius of `0.2 m`, that's roughly **3 agents per
1 m²**. If `set_agent_count(i, n)` raises *"requested N agents but
area can hold at most ~M"*, either:

- reduce `n`, or
- enlarge the distribution polygon in the web editor, or
- shrink agent radius via `set_agent_params(i, radius=0.15)`.

You can compute a safe target from the current count instead of
hard-coding:
""")
    code(cells, f"""
scenario = load_scenario({ASSET})
current = scenario.distributions["jps-distributions_0"]["parameters"]["number"]
print("current count:", current)

scenario.set_agent_count(0, current // 2)   # always within capacity
""")
    return "02_change_agent_count.ipynb", cells


def build_03_agent_speed() -> tuple[str, list]:
    cells: list = []
    md(cells, """
# How do I change the agents' walking speed?

`set_agent_params(distribution_id, **kwargs)` updates parameters on a
distribution — radius, speed, distribution shape, flow timing, etc.

For walking speed, use `desired_speed=` (canonical) or `v0=`
(backwards-compatible alias). Both write the same value.
""")
    code(cells, f"""
from jupedsim_scenarios import load_scenario, run_scenario

scenario = load_scenario({ASSET})
scenario.set_agent_params(0, desired_speed=1.5)   # m/s

result = run_scenario(scenario, seed=42)
print("evacuation time:", result.evacuation_time, "s")
result.cleanup()
""")
    md(cells, """
## Other useful keys

Supported on `set_agent_params`:

- `desired_speed` (or `v0`)
- `desired_speed_std` (or `v0_std`)
- `desired_speed_distribution` (or `v0_distribution`) — `"constant"` or `"gaussian"`
- `radius`, `radius_distribution`, `radius_std`
- `number`, `distribution_mode`
- `use_flow_spawning`, `flow_start_time`, `flow_end_time`

Example with a gaussian speed distribution:

```python
scenario.set_agent_params(
    0,
    desired_speed=1.34,
    desired_speed_std=0.20,
    desired_speed_distribution="gaussian",
)
```
""")
    return "03_change_agent_speed.ipynb", cells


def build_04_sweep_basics() -> tuple[str, list]:
    cells: list = []
    md(cells, """
# Why does `run_sweep` need both `axes` and `apply`?

`run_sweep` lets you run many trials varying one or more parameters.
You write two things:

- **`axes`** — *what* varies. A mapping from a label to a list of
  values. Labels are arbitrary; they show up in the result table.
- **`apply`** — *how* to inject each value into the scenario. A mapping
  from the same label to a function `(scenario, value) -> None`.

The split exists because the library can't guess what your label means.
`"num_agents": 30` is meaningful to you, not to the sweeper — you tell
it `set_agent_count("...", 30)`.
""")
    code(cells, f"""
from jupedsim_scenarios import load_scenario, run_sweep

base = load_scenario({ASSET})

sweep = run_sweep(
    base,
    axes={{"num_agents": [30, 40, 50]}},
    apply={{"num_agents": lambda s, n: s.set_agent_count(0, n)}},
    seeds=range(100, 105),   # 5 seeds per condition
    workers=2,
)

df = sweep.to_dataframe()
df[["num_agents", "seed", "evacuation_time"]].head()
""")
    md(cells, """
## Two axes

`axes` with multiple entries produces the **Cartesian product** of all
value lists. Here that's 3 × 3 = 9 conditions × 5 seeds = 45 trials.
""")
    code(cells, """
sweep = run_sweep(
    base,
    axes={
        "num_agents":    [30, 40, 50],
        "desired_speed": [1.0, 1.2, 1.4],
    },
    apply={
        "num_agents":    lambda s, n: s.set_agent_count(0, n),
        "desired_speed": lambda s, v: s.set_agent_params(0, desired_speed=v),
    },
    seeds=range(100, 105),
    workers=4,
)
sweep.to_dataframe().head()
""")
    md(cells, """
## Paired (zipped) conditions

To pair values instead of crossing them — e.g. only the three
combinations `(30, 1.0)`, `(40, 1.2)`, `(50, 1.4)` — collapse them into
a single composite axis:

```python
axes={"cond": [(30, 1.0), (40, 1.2), (50, 1.4)]},
apply={"cond": lambda s, c: (
    s.set_agent_count(0, c[0]),
    s.set_agent_params(0, desired_speed=c[1]),
)},
```
""")
    return "04_sweep_basics.ipynb", cells


HOWTOS = [
    build_01_inspect,
    build_02_agent_count,
    build_03_agent_speed,
    build_04_sweep_basics,
]


def main() -> None:
    out_dir = Path(__file__).parent / "howtos"
    out_dir.mkdir(exist_ok=True)
    for builder in HOWTOS:
        name, cells = builder()
        nb = nbf.v4.new_notebook()
        nb["cells"] = cells
        nb["metadata"] = {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        }
        path = out_dir / name
        nbf.write(nb, path)
        print(f"wrote {path.relative_to(Path(__file__).parent.parent)}")


if __name__ == "__main__":
    main()
