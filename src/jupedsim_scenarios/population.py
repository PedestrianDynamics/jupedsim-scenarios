"""Population mixes: validation and resolution of per-area profile shares.

A spawn area may carry ``parameters.population_mix``, a list of
``{"profile": id, "share": int}`` entries referencing the top-level
``population_profiles`` map. Resolved groups are attached to each area's
parameters under :data:`GROUPS_KEY`, which is derived state and is rebuilt
on every initialisation.
"""

from __future__ import annotations

import json
import math
from importlib import resources

from .agent_parameters import _area_label, _area_params, _is_number

MIX_KEY = "population_mix"
GROUPS_KEY = "_population_groups"
SUPPORTED_DISTRIBUTIONS = ("constant", "gaussian")
_PROFILE_FIELDS = ("radius", "desired_speed")


class PopulationMixError(ValueError):
    """A population mix or a referenced profile is invalid; the run does not start."""


def load_population_presets() -> dict:
    """The packaged population presets."""
    text = (
        resources.files("jupedsim_scenarios")
        .joinpath("assets/population_presets.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def allocate_counts(shares: list[int], n: int) -> list[int]:
    """Split ``n`` agents by percentage shares using the largest remainder."""
    counts = [n * s // 100 for s in shares]
    remainders = [n * s - 100 * c for s, c in zip(shares, counts, strict=True)]
    order = sorted(range(len(shares)), key=lambda i: (-remainders[i], i))
    for i in order[: n - sum(counts)]:
        counts[i] += 1
    return counts


def _is_whole_share(share) -> bool:
    return isinstance(share, int) and not isinstance(share, bool)


def _finite(value) -> bool:
    return _is_number(value) and math.isfinite(value)


def _check_profile_field(profile_id: str, profile: dict, field: str) -> None:
    prefix = f"population profile '{profile_id}': "
    spec = profile.get(field)
    if not isinstance(spec, dict):
        raise PopulationMixError(f"{prefix}{field} is missing")
    if "mean" not in spec or spec["mean"] is None:
        raise PopulationMixError(f"{prefix}{field}.mean is missing")
    if not spec.get("distribution"):
        raise PopulationMixError(f"{prefix}{field}.distribution is missing")
    name = spec["distribution"]
    if name not in SUPPORTED_DISTRIBUTIONS:
        raise PopulationMixError(
            f"{prefix}{field} distribution '{name}' is not supported (constant, gaussian)"
        )
    if not _finite(spec["mean"]) or spec["mean"] <= 0:
        raise PopulationMixError(f"{prefix}{field}.mean must be a finite number above 0")
    std = spec.get("std")
    if name == "gaussian" and std is not None and (not _finite(std) or std < 0):
        raise PopulationMixError(f"{prefix}{field}.std must be a finite number of at least 0")


def _check_profile(profile_id: str, profile) -> None:
    if not isinstance(profile, dict):
        raise PopulationMixError(f"population profile '{profile_id}': radius is missing")
    for field in _PROFILE_FIELDS:
        _check_profile_field(profile_id, profile, field)


def _check_mix(label: str, mix, profiles: dict) -> None:
    if not isinstance(mix, list) or not mix:
        raise PopulationMixError(
            f"{label}: population_mix is empty; remove it to use the area's own radius and speed"
        )
    seen: set = set()
    total = 0
    for item in mix:
        item = item if isinstance(item, dict) else {}
        profile_id, share = item.get("profile"), item.get("share")
        if not _is_whole_share(share) or share < 1:
            raise PopulationMixError(
                f"{label}: share for '{profile_id}' is {share}; "
                "each share must be a whole number of at least 1"
            )
        if profile_id not in profiles:
            raise PopulationMixError(f"{label}: unknown population profile '{profile_id}'")
        if profile_id in seen:
            raise PopulationMixError(
                f"{label}: population profile '{profile_id}' is listed more than once"
            )
        seen.add(profile_id)
        total += share
    if total != 100:
        raise PopulationMixError(f"{label}: population shares total {total} %, must be 100 %")


def _mixes(data: dict):
    for key, entry in (data.get("distributions") or {}).items():
        mix = _area_params(entry).get(MIX_KEY)
        if mix is not None:
            yield _area_label(key, entry), mix


def validate_population(data: dict) -> None:
    """Reject invalid mixes and the profiles they reference before placement."""
    profiles = data.get("population_profiles") or {}
    checked: set = set()
    for label, mix in _mixes(data):
        _check_mix(label, mix, profiles)
        for item in mix:
            if item["profile"] in checked:
                continue
            _check_profile(item["profile"], profiles[item["profile"]])
            checked.add(item["profile"])


def _std(spec: dict):
    std = spec.get("std")
    return None if std is None else float(std)


def _group(item: dict, profile: dict) -> dict:
    radius, speed = profile["radius"], profile["desired_speed"]
    return {
        "profile": item["profile"],
        "share": item["share"],
        "radius": float(radius["mean"]),
        "radius_distribution": radius["distribution"],
        "radius_std": _std(radius),
        "v0": float(speed["mean"]),
        "v0_distribution": speed["distribution"],
        "v0_std": _std(speed),
    }


def _store_params(entry: dict, params: dict) -> None:
    if isinstance(entry.get("parameters"), str):
        entry["parameters"] = params


def attach_population_groups(data: dict) -> None:
    """Rebuild :data:`GROUPS_KEY` on every area from its current mix."""
    profiles = data.get("population_profiles") or {}
    for entry in (data.get("distributions") or {}).values():
        params = _area_params(entry)
        had_stale = params.pop(GROUPS_KEY, None) is not None
        mix = params.get(MIX_KEY)
        if mix:
            params[GROUPS_KEY] = [_group(item, profiles[item["profile"]]) for item in mix]
        if had_stale or mix:
            _store_params(entry, params)
