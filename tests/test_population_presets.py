import importlib.util
import json
from importlib import resources
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "population_presets"


def _load_derive():
    spec = importlib.util.spec_from_file_location("derive_presets", SCRIPTS / "derive_presets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


derive = _load_derive()


def _packaged():
    path = resources.files("jupedsim_scenarios") / "assets" / "population_presets.json"
    return json.loads(path.read_text())


def test_derive_moments_constant_curve():
    table = {a: (1.0, 0.2) for a in range(10, 20)}
    result = derive.derive_moments(table, list(range(10, 20)), [1.0] * 10)
    assert result == pytest.approx((1.0, 0.2))


def test_derive_moments_adds_between_age_variance():
    table = {10: (1.0, 0.0), 11: (2.0, 0.0)}
    assert derive.derive_moments(table, [10, 11], [1, 1]) == pytest.approx((1.5, 0.5))


def test_shipped_presets_match_derivation():
    assert _packaged() == derive.build_presets(SCRIPTS / "rimea4_abb3.csv")


def test_presets_shape():
    data = _packaged()
    assert set(data["profiles"]) == {
        "general_population",
        "children",
        "young_people",
        "adults",
        "older_adults",
    }
    for pid, p in data["profiles"].items():
        assert p["preset"] == f"rimea4/{pid}@1"
        assert p["radius"] == {"mean": 0.2, "std": None, "distribution": "constant"}
        assert set(p["provenance"]) == {"desired_speed", "age_range", "radius", "distribution"}
        assert p["desired_speed"]["std"] > 0
        assert p["desired_speed"]["distribution"] == "gaussian"
