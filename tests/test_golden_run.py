"""Golden-run matrix: the library reproduces the app's trajectories.

``tests/golden/expected.json`` is produced by the web app's backend
(one entry per fixture directory under ``tests/golden/fixtures/``):

    {"<fixture name>": {"seed": 1, "dt": null, "hash": "...", "time_to_all_arrived": 16.7}}

An entry may carry ``"xfail": "<reason>"`` for a fixture that is known not
to match yet (upstream nondeterminism, or a documented divergence between
the two spawner implementations). Such a fixture still runs, so a fix is
noticed as an unexpected pass.

Each fixture is skipped when the file has no entry for it; the whole
module is skipped when the file is missing. Fixtures run through the
CLI in a fresh process each (see ``tests/golden/run_fixture.py``).
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

GOLDEN = pathlib.Path(__file__).parent / "golden"
FIXTURES = GOLDEN / "fixtures"
EXPECTED_FILE = GOLDEN / "expected.json"

sys.path.insert(0, str(GOLDEN))
from hash_trajectory import hash_trajectory  # noqa: E402
from run_fixture import run_fixture_cli  # noqa: E402

if not EXPECTED_FILE.exists():
    pytest.skip("tests/golden/expected.json not present", allow_module_level=True)

EXPECTED = json.loads(EXPECTED_FILE.read_text())
FIXTURE_NAMES = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_golden_run_matches_app(name, tmp_path):
    pytest.importorskip("jupedsim")

    expected = EXPECTED.get(name)
    if expected is None:
        pytest.skip(f"no expected entry for {name}")

    out = tmp_path / f"{name}.sqlite"
    summary = run_fixture_cli(
        FIXTURES / name, seed=int(expected["seed"]), dt=expected.get("dt"), output_path=out
    )
    matches = hash_trajectory(out) == expected["hash"] and summary["evacuation_time"] == pytest.approx(
        expected["time_to_all_arrived"], abs=1e-6
    )
    if expected.get("xfail") and not matches:
        pytest.xfail(expected["xfail"])
    assert hash_trajectory(out) == expected["hash"]
    assert summary["evacuation_time"] == pytest.approx(expected["time_to_all_arrived"], abs=1e-6)
