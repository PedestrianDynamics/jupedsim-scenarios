"""Derive population presets from the digitised RiMEA 4.0.0 Abb. 3 table.

Usage: uv run --extra viz python scripts/population_presets/derive_presets.py [--pdf rimea-4.0.0.pdf]

Always writes src/jupedsim_scenarios/assets/population_presets.json. With --pdf, also renders
abb3_overlay.png (needs pdftoppm and matplotlib).
"""

import argparse
import csv
import json
import math
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "rimea4_abb3.csv"
JSON_PATH = HERE.parents[1] / "src" / "jupedsim_scenarios" / "assets" / "population_presets.json"
OVERLAY_PATH = HERE / "abb3_overlay.png"

LAST_DIGITISED_AGE = 80
RADIUS = {"mean": 0.2, "std": None, "distribution": "constant"}
SOURCE = {
    "document": "RiMEA 4.0.0",
    "figure": "Abb. 3",
    "section": "3.2.2.2",
    "population_section": "3.2.4",
    "underlying": "Weidmann 1992",
}
# id -> (age_min, age_max, age_weighting, age_range provenance)
BANDS = {
    "general_population": (10, 85, "rimea_standard_population", "rimea4_s324"),
    "children": (5, 12, "uniform", "app_choice_band"),
    "young_people": (13, 29, "uniform", "app_choice_band"),
    "adults": (30, 59, "uniform", "app_choice_band"),
    "older_adults": (60, 80, "uniform", "app_choice_band"),
}


def read_table(csv_path):
    """age -> (v_mean, sigma) with sigma = (v_plus - v_minus) / 2; ages above 80 hold age 80."""
    table = {}
    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            mean = float(row["v_mean"])
            sigma = (float(row["v_plus_sigma"]) - float(row["v_minus_sigma"])) / 2
            table[int(row["age"])] = (mean, sigma)
    return table


def derive_moments(table, ages, weights):
    """Mixture mean and std: within-age variance plus between-age variance."""
    total = sum(weights)
    mean = sum(w * table[a][0] for a, w in zip(ages, weights, strict=True)) / total
    within = sum(w * table[a][1] ** 2 for a, w in zip(ages, weights, strict=True)) / total
    between = sum(w * (table[a][0] - mean) ** 2 for a, w in zip(ages, weights, strict=True)) / total
    return mean, math.sqrt(within + between)


def _weights(kind, ages):
    if kind == "uniform":
        return [1.0] * len(ages)
    return [math.exp(-((a - 50) ** 2) / 800) for a in ages]


def build_presets(csv_path):
    table = read_table(csv_path)
    for age in range(LAST_DIGITISED_AGE + 1, 86):
        table[age] = table[LAST_DIGITISED_AGE]
    profiles = {}
    for pid, (lo, hi, weighting, age_prov) in BANDS.items():
        ages = list(range(lo, hi + 1))
        mean, std = derive_moments(table, ages, _weights(weighting, ages))
        profiles[pid] = {
            "preset": f"rimea4/{pid}@1",
            "age_min": lo,
            "age_max": hi,
            "age_weighting": weighting,
            "desired_speed": {
                "mean": round(mean, 2),
                "std": round(std, 2),
                "distribution": "gaussian",
            },
            "radius": dict(RADIUS),
            "provenance": {
                "desired_speed": "rimea4_abb3_derived",
                "age_range": age_prov,
                "radius": "app_default_radius",
                "distribution": "app_choice_gaussian",
            },
        }
    return {"version": 1, "source": dict(SOURCE), "profiles": profiles}


def render_overlay(presets, pdf_path, out_path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    # Axes box of Abb. 3 in PDF points (see digitise_abb3.py): x 0-90 years, y 0-2 m/s.
    left, right, top, bottom = 117.72, 383.28, 66.12, 251.40
    dpi = 200
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["pdftoppm", "-f", "10", "-l", "10", "-r", str(dpi), "-png", str(pdf_path), f"{tmp}/p"],
            check=True,
        )
        page = mpimg.imread(next(Path(tmp).glob("p*.png")))
    s = dpi / 72
    crop = page[int(top * s) : int(bottom * s), int(left * s) : int(right * s)]

    table = read_table(CSV_PATH)
    ages = sorted(table)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax in (ax1, ax2):
        ax.imshow(crop, extent=(0, 90, 0, 2), aspect="auto")
        ax.set_xlabel("Age (years)")
        ax.set_xlim(0, 90)
        ax.set_ylim(0, 2)
    ax1.set_ylabel("Walking speed (m/s)")
    ax1.set_title("Digitised curves over Abb. 3 (crop)")
    ax1.plot(ages, [table[a][0] for a in ages], color="tab:red", lw=1, label="mean")
    ax1.plot(
        ages,
        [table[a][0] + table[a][1] for a in ages],
        color="tab:blue",
        lw=1,
        ls="--",
        label="mean + sigma",
    )
    ax1.plot(
        ages,
        [table[a][0] - table[a][1] for a in ages],
        color="tab:blue",
        lw=1,
        ls="--",
        label="mean - sigma",
    )
    ax1.legend(loc="upper right", fontsize=8)
    ax2.set_title("Derived presets: mean ± std over age band")
    for i, (pid, p) in enumerate(presets["profiles"].items()):
        mean, std = p["desired_speed"]["mean"], p["desired_speed"]["std"]
        lo, hi = p["age_min"], p["age_max"]
        ax2.errorbar(
            (lo + hi) / 2,
            mean,
            xerr=(hi - lo) / 2,
            yerr=std,
            color=f"C{i}",
            capsize=3,
            lw=1.5,
            label=f"{pid} ({mean:.2f} ± {std:.2f})",
        )
    ax2.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", type=Path, help="RiMEA 4.0.0 PDF; enables the overlay figure")
    args = parser.parse_args()
    presets = build_presets(CSV_PATH)
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(presets, indent=2) + "\n")
    print(f"wrote {JSON_PATH}")
    for pid, p in presets["profiles"].items():
        ds = p["desired_speed"]
        print(f"{pid}: ages {p['age_min']}-{p['age_max']} mean {ds['mean']} std {ds['std']}")
    if args.pdf:
        render_overlay(presets, args.pdf, OVERLAY_PATH)
        print(f"wrote {OVERLAY_PATH}")


if __name__ == "__main__":
    main()
