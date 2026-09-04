"""Record the library's own golden-run hashes.

Writes ``tests/golden/library_actual.json`` with one entry per fixture
directory under ``tests/golden/fixtures/`` in the same shape as
``expected.json`` (which the web app's backend produces), so the two
files can be diffed directly::

    python scripts/golden_record.py [--seed 1]

Every fixture runs through the CLI in a fresh process, matching how the
golden test and a user run it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
sys.path.insert(0, str(GOLDEN))

from hash_trajectory import hash_trajectory  # noqa: E402
from run_fixture import run_fixture_cli  # noqa: E402


def _effective_dt(sqlite_path: pathlib.Path) -> float:
    """Recover dt from the writer metadata: fps = 1 / (dt * every_nth_frame)."""
    con = sqlite3.connect(str(sqlite_path))
    try:
        fps = float(con.execute("SELECT value FROM metadata WHERE key = 'fps'").fetchone()[0])
    finally:
        con.close()
    return round(1.0 / (fps * 10), 6)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", default=str(GOLDEN / "library_actual.json"))
    args = parser.parse_args(argv)

    fixtures = sorted(p for p in (GOLDEN / "fixtures").iterdir() if p.is_dir())
    actual: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for fixture in fixtures:
            out = pathlib.Path(tmp) / f"{fixture.name}.sqlite"
            summary = run_fixture_cli(fixture, seed=args.seed, dt=None, output_path=out)
            entry = {
                "seed": args.seed,
                "dt": _effective_dt(out),
                "hash": hash_trajectory(out),
                "time_to_all_arrived": summary["evacuation_time"],
            }
            actual[fixture.name] = entry
            print(
                f"{fixture.name}: dt={entry['dt']} t={entry['time_to_all_arrived']} {entry['hash'][:12]}"
            )
    pathlib.Path(args.out).write_text(json.dumps(actual, indent=2) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
