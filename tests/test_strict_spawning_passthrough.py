"""strict_spawning must survive distribution-parameter processing.

The flow-spawn deferral consumer (Web-Based-Jupedsim's flow_spawner) reads
``flow_dist["params"]["strict_spawning"]`` to decide whether a blocked spawn
aborts the run (strict) or defers (lenient). The param builders here whitelist
keys explicitly, and ``strict_spawning`` was omitted — so the opt-in was
silently dropped and every run behaved leniently regardless of the setting.
This pins the key through ``_process_distributions``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("jupedsim")

from jupedsim_scenarios.simulation_init import _process_distributions


def _data(strict):
    params = {"number": 5, "use_flow_spawning": True}
    if strict is not None:
        params["strict_spawning"] = strict
    return {
        "distributions": {
            "jps-distributions_0": {
                "coordinates": [[0, 0], [4, 0], [4, 4], [0, 4]],
                "parameters": params,
            }
        }
    }


def test_strict_spawning_passed_through_when_true():
    _geom, params = _process_distributions(_data(True))
    assert params["jps-distributions_0"]["strict_spawning"] is True


def test_strict_spawning_defaults_false_when_absent():
    _geom, params = _process_distributions(_data(None))
    assert params["jps-distributions_0"]["strict_spawning"] is False
