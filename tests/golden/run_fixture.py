"""Run one golden fixture through the CLI in a fresh process.

A fresh process per fixture keeps the run independent of jupedsim's
process-global agent-id counter, which seeds part of the flow-spawn and
direct-steering randomness. This is also how a user runs the exported
zip, so it is the path the golden comparison should exercise.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys


def run_fixture_cli(
    fixture_dir: pathlib.Path,
    *,
    seed: int,
    dt: float | None,
    output_path: pathlib.Path,
) -> dict:
    """Run ``jps-scenarios run`` on ``fixture_dir`` and return the summary JSON."""
    cmd = [
        sys.executable,
        "-m",
        "jupedsim_scenarios.cli",
        "run",
        str(fixture_dir),
        "--seed",
        str(seed),
        "--every-nth-frame",
        "10",
        "--out",
        str(output_path),
    ]
    if dt is not None:
        cmd += ["--dt", str(dt)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{fixture_dir.name}: exit {proc.returncode}\n{proc.stderr}")
    summary_line = next(line for line in reversed(proc.stdout.splitlines()) if line.startswith("{"))
    return json.loads(summary_line)
