"""``Scenario.to_json`` / ``save_scenario`` round-trip (R3.2).

R2.1 let users build scenarios in Python via ``add_*``. R3.2 closes
the loop by providing a documented persistence path — symmetric with
``load_scenario`` and reusing its self-contained-JSON format so a
saved scenario can be round-tripped through every supported reader.
"""

from __future__ import annotations

import json

import pytest

from jupedsim_scenarios import Scenario, load_scenario, save_scenario

SMALL_WKT = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"


def _scenario() -> Scenario:
    return Scenario(
        raw={},
        walkable_area_wkt=SMALL_WKT,
        model_type="CollisionFreeSpeedModel",
        seed=42,
        sim_params={"max_simulation_time": 60},
    )


def test_to_json_string_form_is_valid_self_contained():
    s = _scenario()
    s.add_distribution([(0, 0), (2, 0), (2, 2), (0, 2)], number=15)
    s.add_exit([(8, 0), (10, 0), (10, 10), (8, 10)])
    payload = s.to_json()
    assert isinstance(payload, str)
    data = json.loads(payload)
    assert data["walkable_area_wkt"] == SMALL_WKT
    assert data["config"]["simulation_settings"]["baseSeed"] == 42
    assert "distributions" in data
    assert "exits" in data


def test_to_json_writes_file_and_creates_parent_dir(tmp_path):
    s = _scenario()
    target = tmp_path / "nested" / "scenario.json"
    assert s.to_json(target) is None
    assert target.exists()
    data = json.loads(target.read_text())
    assert data["walkable_area_wkt"] == SMALL_WKT


def test_save_scenario_module_function(tmp_path):
    s = _scenario()
    target = tmp_path / "scenario.json"
    save_scenario(s, target)
    assert target.exists()


def test_roundtrip_preserves_scalar_fields(tmp_path):
    s = _scenario()
    s.seed = 1234
    s.max_simulation_time = 120
    s.sim_params["custom_knob"] = 1.5
    target = tmp_path / "s.json"
    save_scenario(s, target)
    loaded = load_scenario(str(target))
    assert loaded.seed == 1234
    assert loaded.max_simulation_time == 120
    assert loaded.model_type == "CollisionFreeSpeedModel"
    assert loaded.sim_params["custom_knob"] == 1.5


def test_roundtrip_preserves_additive_ops(tmp_path):
    s = _scenario()
    did = s.add_distribution(
        [(0, 0), (2, 0), (2, 2), (0, 2)], number=20, desired_speed=1.4
    )
    eid = s.add_exit([(8, 0), (10, 0), (10, 10), (8, 10)], max_throughput=1.5)
    zid = s.add_zone([(4, 4), (6, 4), (6, 6), (4, 6)], speed_factor=0.5)
    sid = s.add_stage([(5, 5), (6, 5), (6, 6), (5, 6)], waiting_time=3.0)

    target = tmp_path / "s.json"
    save_scenario(s, target)
    loaded = load_scenario(str(target))

    assert did in loaded.distributions
    assert loaded.distributions[did]["parameters"]["number"] == 20
    assert loaded.distributions[did]["parameters"]["desired_speed"] == 1.4
    assert eid in loaded.exits
    assert loaded.exits[eid]["max_throughput"] == 1.5
    assert zid in loaded.zones
    assert loaded.zones[zid]["speed_factor"] == 0.5
    assert sid in loaded.stages
    assert loaded.stages[sid]["waiting_time"] == 3.0


def test_roundtrip_via_to_json_string(tmp_path):
    # Mid-pipeline: serialize to a string, persist somewhere unusual,
    # later re-hydrate via load_scenario.
    s = _scenario()
    s.add_distribution([(0, 0), (1, 0), (1, 1)], number=5)
    payload = s.to_json()
    target = tmp_path / "from_string.json"
    target.write_text(payload, encoding="utf-8")
    loaded = load_scenario(str(target))
    assert loaded.distributions[next(iter(loaded.distributions))][
        "parameters"
    ]["number"] == 5


def test_to_json_raises_on_non_serializable_raw_value():
    # Copilot PR #40 review: to_json must NOT silently stringify
    # unsupported types via default=str. Anything that isn't
    # JSON-serializable should raise TypeError at save time so the
    # mistake surfaces immediately instead of producing a "round-trip"
    # that lies about what survived.
    class _NotJsonable:
        pass

    s = _scenario()
    s.sim_params["bad"] = _NotJsonable()
    with pytest.raises(TypeError):
        s.to_json()


def test_loaded_scenario_runs_after_roundtrip(corridor_scenario, tmp_path):
    # End-to-end: an existing scenario (with journeys etc.) roundtrips
    # through save_scenario + load_scenario and still simulates.
    pytest.importorskip("jupedsim")
    from jupedsim_scenarios import run_scenario

    target = tmp_path / "corridor.json"
    save_scenario(corridor_scenario, target)
    reloaded = load_scenario(str(target))

    result = run_scenario(reloaded, seed=42)
    try:
        assert result.success
        assert result.agents_evacuated > 0
    finally:
        result.cleanup()
