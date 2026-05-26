"""``load_scenario`` accepts three input shapes: self-contained JSON,
ZIP archive, and a directory holding one JSON + one WKT. All three
funnel through the same parser so the CLI and the Python API agree.
"""

from __future__ import annotations

import json
import pathlib
import zipfile

import pytest

from jupedsim_scenarios import load_scenario

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "corridor_simple.json"


def test_load_self_contained_json():
    s = load_scenario(str(FIXTURE))
    assert s.walkable_area_wkt.startswith("POLYGON")
    assert s.model_type == "CollisionFreeSpeedModel"
    assert s.seed == 42


def test_load_self_contained_json_without_walkable_area_wkt_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"config": {}}))
    with pytest.raises(ValueError, match="walkable_area_wkt"):
        load_scenario(str(bad))


def test_load_zip_with_split_json_and_wkt(tmp_path):
    data = json.loads(FIXTURE.read_text())
    wkt = data.pop("walkable_area_wkt")
    archive = tmp_path / "scenario.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("scenario.json", json.dumps(data))
        zf.writestr("geometry.wkt", wkt)
    s = load_scenario(str(archive))
    assert s.walkable_area_wkt.startswith("POLYGON")
    assert s.model_type == "CollisionFreeSpeedModel"


def test_load_directory_with_split_json_and_wkt(tmp_path):
    data = json.loads(FIXTURE.read_text())
    wkt = data.pop("walkable_area_wkt")
    (tmp_path / "scenario.json").write_text(json.dumps(data))
    (tmp_path / "geometry.wkt").write_text(wkt)
    s = load_scenario(str(tmp_path))
    assert s.walkable_area_wkt.startswith("POLYGON")


def test_load_directory_missing_wkt_raises(tmp_path):
    (tmp_path / "scenario.json").write_text("{}")
    with pytest.raises(ValueError, match="no \\*\\.wkt file"):
        load_scenario(str(tmp_path))


def test_load_directory_with_multiple_jsons_raises(tmp_path):
    data = json.loads(FIXTURE.read_text())
    wkt = data.pop("walkable_area_wkt")
    (tmp_path / "a.json").write_text(json.dumps(data))
    (tmp_path / "b.json").write_text(json.dumps(data))
    (tmp_path / "geometry.wkt").write_text(wkt)
    with pytest.raises(ValueError, match="expected exactly one"):
        load_scenario(str(tmp_path))


def test_load_zip_with_multiple_wkts_raises(tmp_path):
    data = json.loads(FIXTURE.read_text())
    wkt = data.pop("walkable_area_wkt")
    archive = tmp_path / "scenario.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("scenario.json", json.dumps(data))
        zf.writestr("a.wkt", wkt)
        zf.writestr("b.wkt", wkt)
    with pytest.raises(ValueError, match="expected exactly one"):
        load_scenario(str(archive))


def test_load_corrupt_zip_raises_valueerror(tmp_path):
    bad = tmp_path / "broken.zip"
    bad.write_bytes(b"this is not a zip file")
    with pytest.raises(ValueError, match="not a valid ZIP archive"):
        load_scenario(str(bad))
