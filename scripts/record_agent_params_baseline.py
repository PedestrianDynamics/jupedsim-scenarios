"""Record the resolved agent parameters for the baseline cases.

Run on a known-good library revision to (re)generate
tests/fixtures/agent_params_baseline_0_7_4.json.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from test_agent_params_baseline import AREA_PARAMS, BASELINE_CASES, FIXTURE  # noqa: E402

from jupedsim_scenarios.simulation_init import create_agent_parameters  # noqa: E402

_DROPPED = {"position", "journey_id", "stage_id"}


def resolve(model_type: str, global_params: dict | None) -> dict:
    namespace = SimpleNamespace(**global_params) if global_params else None
    built = create_agent_parameters(model_type, (0.0, 0.0), dict(AREA_PARAMS), namespace)
    fields = dataclasses.asdict(built)
    return {
        k: list(v) if isinstance(v, tuple) else v for k, v in fields.items() if k not in _DROPPED
    }


def main() -> None:
    recorded = {case_id: resolve(model, g) for case_id, model, g in BASELINE_CASES}
    FIXTURE.write_text(json.dumps(recorded, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(recorded)} cases to {FIXTURE}")


if __name__ == "__main__":
    main()
