"""Unknown kwargs on `set_agent_params` / `set_model_params` raise loudly.

Previously a typo (`radius_dist=` for `radius_distribution=`,
`stength_neighbor_repulsion=` for `strength_...`) silently wrote a
dead key and ran the simulation with default parameters. R2.3
catches the typo at the setter call site with a difflib suggestion.
"""

from __future__ import annotations

import pytest

from jupedsim_scenarios import Scenario

SMALL_WKT = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"


def _scenario() -> Scenario:
    return Scenario(
        raw={"distributions": {"d0": {"parameters": {}}}},
        walkable_area_wkt=SMALL_WKT,
        model_type="CollisionFreeSpeedModel",
        seed=42,
        sim_params={"max_simulation_time": 60},
    )


def test_set_agent_params_typo_raises_with_suggestion():
    s = _scenario()
    with pytest.raises(TypeError, match="radius_distribution"):
        s.set_agent_params("d0", radius_dist="gaussian")


def test_set_agent_params_unknown_with_no_close_match_raises():
    s = _scenario()
    with pytest.raises(TypeError, match="totally_made_up_key"):
        s.set_agent_params("d0", totally_made_up_key=1)


def test_set_agent_params_accepts_known_kwargs():
    s = _scenario()
    s.set_agent_params("d0", radius=0.3, desired_speed=1.4, number=10)
    params = s.distributions["d0"]["parameters"]
    assert params["radius"] == 0.3
    assert params["desired_speed"] == 1.4
    assert params["number"] == 10


def test_set_agent_params_deprecated_aliases_still_pass_guard():
    # v0* keys are deprecated (DeprecationWarning) but must still be in
    # the allow-list during the deprecation window.
    s = _scenario()
    with pytest.warns(DeprecationWarning):
        s.set_agent_params("d0", v0=1.3)
    assert s.distributions["d0"]["parameters"]["desired_speed"] == 1.3


def test_set_model_params_typo_raises_with_suggestion():
    s = _scenario()
    with pytest.raises(TypeError, match="strength_neighbor_repulsion"):
        s.set_model_params(stength_neighbor_repulsion=2.6)


def test_set_model_params_accepts_known_kwargs_across_models():
    # Cross-model keys are allowed (set params, then switch model). A
    # GCFM-only key on a CFSM scenario must NOT raise.
    s = _scenario()
    s.set_model_params(strength_neighbor_repulsion=2.6)
    s.set_model_params(gcfm_max_neighbor_repulsion_force=9.0)
    s.set_model_params(sfm_body_force=120000)


def test_set_model_params_unknown_raises():
    s = _scenario()
    with pytest.raises(TypeError, match="received unknown keyword arguments"):
        s.set_model_params(definitely_not_a_param=0.1)


def test_set_agent_count_routes_through_set_agent_params():
    # R3.3: set_agent_count is now a thin wrapper over set_agent_params,
    # so it inherits the same positive-int validation and forces
    # distribution_mode = "by_number".
    s = _scenario()
    s.set_agent_count("d0", 7)
    params = s.distributions["d0"]["parameters"]
    assert params["number"] == 7
    assert params["distribution_mode"] == "by_number"

    with pytest.raises(ValueError, match="positive integer"):
        s.set_agent_count("d0", 0)
