"""Load a scenario ZIP, run it, print metrics, and bundle results into a ZIP."""

import sys
import time
import zipfile
from pathlib import Path

from jupedsim_scenarios import load_scenario, run_scenario


def main(path: str, seed: int = 42) -> None:
    src = Path(path)
    sqlite_path = src.with_name(f"{src.stem}_run.sqlite")
    bundle_path = src.with_name(f"{src.stem}_run.zip")

    scenario = load_scenario(path)
    t0 = time.perf_counter()
    result = run_scenario(scenario, seed=seed, output_path=str(sqlite_path))
    wall_time = time.perf_counter() - t0

    print(f"scenario:        {path}")
    print(f"seed:            {result.seed}")
    print(f"success:         {result.success}")
    print(f"evacuation time: {result.evacuation_time:.2f} s")
    print(f"wall-clock time: {wall_time:.2f} s")
    print(f"total agents:    {result.total_agents}")
    print(f"evacuated:       {result.agents_evacuated}")
    print(f"remaining:       {result.agents_remaining}")

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as out:
        with zipfile.ZipFile(src) as inp:
            for name in inp.namelist():
                out.writestr(name, inp.read(name))
        out.write(sqlite_path, arcname="trajectory.sqlite")

    print(f"bundle:          {bundle_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python run_zip.py <scenario.zip> [seed]")
        sys.exit(1)
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    main(sys.argv[1], seed)
