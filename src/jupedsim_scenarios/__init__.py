"""Scenario layer — high-level Scenario / run_scenario API.

Wraps the simulation primitives in `utils.simulation_init` and
`shared.direct_steering_runtime` into a load-and-run API used by the
trajectory regression test and the `scripts/run_scenario.py` CLI. The
web runtime itself goes through `services.simulation_service`.

This package replaced the former `backend/core/` mirror. Once
`jupedsim.internal.scenarios` lands upstream (jupedsim PR #1565), this
module's contents will migrate to thin wrappers around the upstream API.
"""

from .runner import Scenario, ScenarioResult, load_scenario, run_scenario
from .sweep import SweepResult, Trial, run_sweep

__all__ = [
    "Scenario",
    "ScenarioResult",
    "SweepResult",
    "Trial",
    "load_scenario",
    "run_scenario",
    "run_sweep",
]
