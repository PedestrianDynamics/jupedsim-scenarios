"""Load a scenario ZIP, run it, and print summary metrics."""

import sys
import time
from pathlib import Path

from jupedsim_scenarios import load_scenario, run_scenario


def main(path: str, seed: int = 42, output: str | None = None) -> None:
    scenario = load_scenario(path)
    if output is None:
        output = str(Path(path).with_suffix(".sqlite"))
    t0 = time.perf_counter()
    result = run_scenario(scenario, seed=seed, output_path=output)
    wall_time = time.perf_counter() - t0

    print(f"scenario:        {path}")
    print(f"seed:            {result.seed}")
    print(f"success:         {result.success}")
    print(f"evacuation time: {result.evacuation_time:.2f} s")
    print(f"wall-clock time: {wall_time:.2f} s")
    print(f"total agents:    {result.total_agents}")
    print(f"evacuated:       {result.agents_evacuated}")
    print(f"remaining:       {result.agents_remaining}")
    print(f"trajectory:      {result.sqlite_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python run_zip.py <scenario.zip> [seed]")
        sys.exit(1)
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    main(sys.argv[1], seed)
