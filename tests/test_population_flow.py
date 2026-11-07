"""Flow arrivals draw a population profile once per arrival."""

from __future__ import annotations

import copy
import pathlib

import numpy as np
import pytest

pytest.importorskip("jupedsim")

from jupedsim_scenarios import ScenarioRunner, load_scenario
from jupedsim_scenarios import runner as runner_module
from jupedsim_scenarios.population import GROUPS_KEY
from jupedsim_scenarios.simulation_init import (
    _sample_agent_values,
    sample_flow_arrival,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

LEGACY = {
    "radius": 0.2,
    "radius_distribution": "gaussian",
    "radius_std": 0.03,
    "v0": 1.3,
    "v0_distribution": "gaussian",
    "v0_std": 0.2,
}


def _group(share, v0, radius=0.2):
    return {
        "share": share,
        "radius": radius,
        "radius_distribution": "constant",
        "radius_std": None,
        "v0": v0,
        "v0_distribution": "constant",
        "v0_std": None,
    }


def _stream(params, rng, n=20):
    return [sample_flow_arrival(params, rng) for _ in range(n)]


def _legacy_stream(params, rng, n=20):
    out = []
    for _ in range(n):
        r, v = _sample_agent_values(params, 1, rng)
        out.append((float(r[0]), float(v[0])))
    return out


def test_legacy_flow_arrival_matches_0_9_1_stream():
    seq_a = _stream(LEGACY, np.random.RandomState(3))
    seq_b = _legacy_stream(LEGACY, np.random.RandomState(3))
    assert seq_a == seq_b


def test_single_group_flow_makes_no_profile_draw():
    params = {**LEGACY, GROUPS_KEY: [_group(100, 0.9)]}
    rng_a, rng_b = np.random.RandomState(3), np.random.RandomState(3)
    seq_a = _stream(params, rng_a)
    seq_b = _legacy_stream(params, rng_b)
    assert seq_a == seq_b
    assert rng_a.random_sample() == rng_b.random_sample()


def test_flow_shares_hold_on_average():
    params = {GROUPS_KEY: [_group(70, 0.8), _group(30, 1.6)]}
    rng = np.random.RandomState(0)
    n = 10_000
    slow = sum(sample_flow_arrival(params, rng)[1] == 0.8 for _ in range(n))
    assert abs(slow / n - 0.70) < 4 * np.sqrt(0.21 / n)


def test_blocked_spawn_keeps_arrival(monkeypatch):
    params = {GROUPS_KEY: [_group(50, 0.8), _group(50, 1.6)]}
    rng = np.random.RandomState(11)
    calls = []
    real = runner_module.sample_flow_arrival

    def spy(p, r):
        calls.append(1)
        return real(p, r)

    attempts = []

    def fake_spawn(*, flow_params, **_):
        attempts.append((flow_params["radius"], flow_params["v0"]))
        return len(attempts) > 5

    monkeypatch.setattr(runner_module, "sample_flow_arrival", spy)
    monkeypatch.setattr(runner_module, "_try_spawn_one_flow_agent", fake_spawn)
    spawning_info = {
        "spawning_freqs_and_numbers": [(0.0, 1)],
        "flow_distributions": [{"start_time": 0, "end_time": 100, "params": params}],
        "num_agents_per_source": [1],
        "agent_counter_per_source": [0],
    }
    pending: dict = {}
    for tick in range(6):
        runner_module._spawn_flow_agents(
            simulation=None,
            current_time=float(tick),
            seed=0,
            spawning_info=spawning_info,
            direct_steering_info={},
            agent_wait_info=None,
            agent_radii={},
            flow_variant_rng=None,
            flow_param_rngs={0: rng},
            pending_flow_samples=pending,
        )
    assert len(calls) == 1
    assert len(attempts) == 6 and len(set(attempts)) == 1
    expected = np.random.RandomState(11)
    sample_flow_arrival(params, expected)
    assert rng.random_sample() == expected.random_sample()


def _mix_profile(v0):
    return {
        "desired_speed": {"mean": v0, "std": None, "distribution": "constant"},
        "radius": {"mean": 0.2, "std": None, "distribution": "constant"},
    }


def test_flow_mix_reaches_runner_end_to_end():
    scenario = load_scenario(str(FIXTURES / "corridor_simple.json"))
    scenario.max_simulation_time = 60
    dist = scenario.raw["distributions"]["jps-distributions_0"]
    dist["parameters"] = {
        **copy.deepcopy(dist["parameters"]),
        "number": 40,
        "v0": 1.3,
        "use_flow_spawning": True,
        "flow_start_time": 0,
        "flow_end_time": 20,
        "population_mix": [
            {"profile": "slow", "share": 70},
            {"profile": "fast", "share": 30},
        ],
    }
    scenario.raw["population_profiles"] = {
        "slow": _mix_profile(0.8),
        "fast": _mix_profile(1.6),
    }
    speeds = set()
    with ScenarioRunner(scenario, seed=5) as runner:
        total = 0
        for _ in range(2000):
            runner.step()
            for agent in runner.simulation.agents():
                speeds.add(round(runner.simulation.agent(agent.id).model.desired_speed, 6))
            total = sum(runner._agent_counter_per_source)
            if total >= 40:
                break
    assert total == 40
    assert speeds == {0.8, 1.6}
