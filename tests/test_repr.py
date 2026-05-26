"""``Scenario`` __repr__ and _repr_html_ contracts.

The default dataclass repr would dump the entire ``raw`` JSON dict —
useless in a Jupyter cell and noisy in stack traces. The custom repr
keeps it to one autocomplete-friendly line; ``_repr_html_`` powers the
nicer table view in notebooks.
"""

from __future__ import annotations

from jupedsim_scenarios import Scenario

SMALL_WKT = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"


def _scenario() -> Scenario:
    return Scenario(
        raw={
            "exits": {"e0": {}, "e1": {}},
            "distributions": {
                "d0": {"parameters": {"number": 20}},
                "d1": {"parameters": {"number": 5}},
            },
            "checkpoints": {"c0": {}},
            "zones": {"z0": {}, "z1": {}, "z2": {}},
        },
        walkable_area_wkt=SMALL_WKT,
        model_type="CollisionFreeSpeedModel",
        seed=42,
        sim_params={"max_simulation_time": 60},
    )


def test_repr_is_one_line_and_contains_key_facts():
    r = repr(_scenario())
    assert "\n" not in r
    assert "CollisionFreeSpeedModel" in r
    assert "seed=42" in r
    assert "agents≈25" in r
    assert "exits=2" in r
    assert "distributions=2" in r
    assert "stages=1" in r
    assert "zones=3" in r


def test_repr_does_not_dump_raw_dict():
    # The original dataclass repr would inline ``raw`` — make sure ours
    # doesn't accidentally regress into that.
    r = repr(_scenario())
    assert "{" not in r
    assert "raw=" not in r


def test_repr_html_is_valid_table_markup():
    html = _scenario()._repr_html_()
    assert html.startswith("<table")
    assert html.endswith("</table>")
    assert html.count("<tr>") == html.count("</tr>")
    for field in ("Model", "Seed", "Exits", "Distributions", "Stages", "Zones"):
        assert f">{field}<" in html


def test_repr_html_reflects_field_values():
    html = _scenario()._repr_html_()
    assert "CollisionFreeSpeedModel" in html
    assert ">42<" in html
    assert ">~25<" in html
