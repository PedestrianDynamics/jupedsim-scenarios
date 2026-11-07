"""Digitise RiMEA 4.0.0 Abb. 3 (walking speed over age) from the vector PDF.

Usage: uv run --with pymupdf python scripts/population_presets/digitise_abb3.py <rimea-4.0.0.pdf>
"""

import csv
import sys
from pathlib import Path

import numpy as np

PAGE_INDEX = 9  # page 10, 0-based
AGES = range(3, 81)
AXES_X = (0.0, 90.0)
AXES_Y = (0.0, 2.0)
MEAN_STROKE_WIDTH = 3.0
OUT_CSV = Path(__file__).with_name("rimea4_abb3.csv")


def _bezier(p0, p1, p2, p3, n=200):
    t = np.linspace(0.0, 1.0, n)[:, None]
    p0, p1, p2, p3 = (np.array([p.x, p.y]) for p in (p0, p1, p2, p3))
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t**2 * p2 + t**3 * p3


def path_points(drawing):
    """Densely sampled polyline (PDF coordinates) of a stroked path."""
    pts = []
    for item in drawing["items"]:
        if item[0] == "c":
            pts.append(_bezier(*item[1:5]))
        elif item[0] == "l":
            pts.append(np.array([[item[1].x, item[1].y], [item[2].x, item[2].y]]))
    return np.vstack(pts)


def axis_calibration(drawings):
    """Pixel-free calibration from the axis tick marks: (x0, x90, y0, y2) in PDF points."""
    ticks_x, ticks_y = [], []
    for d in drawings:
        for item in d["items"]:
            if item[0] != "l":
                continue
            a, b = item[1], item[2]
            if a.x == b.x and abs(b.y - a.y - 3.0) < 0.01 and a.y > 200:
                ticks_x.append(a.x)
            if a.y == b.y and abs(b.x - a.x - 3.0) < 0.01 and a.x < 120:
                ticks_y.append(a.y)
    if len(ticks_x) < 10 or len(ticks_y) < 11:
        raise SystemExit("could not find axis tick marks")
    return min(ticks_x), max(ticks_x), max(ticks_y), min(ticks_y)


def find_curves(drawings, axes_rect):
    """Return (mean, upper, lower) polylines: the three black curves inside the axes box."""
    cands = [
        d
        for d in drawings
        if d.get("color") == (0.0, 0.0, 0.0)
        and any(it[0] == "c" for it in d["items"])
        and axes_rect.contains(d["rect"])
    ]
    if len(cands) != 3:
        raise SystemExit(f"expected 3 curve paths in the axes box, found {len(cands)}")
    mean = [d for d in cands if abs(d["width"] - MEAN_STROKE_WIDTH) < 0.01]
    others = [d for d in cands if d not in mean]
    if len(mean) != 1:
        raise SystemExit("could not identify the mean curve by stroke width")
    others.sort(key=lambda d: d["rect"].y0)  # smaller y = higher speed
    return mean[0], others[0], others[1]


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    import pymupdf

    page = pymupdf.open(argv[1])[PAGE_INDEX]
    drawings = page.get_drawings()
    if not drawings or page.get_images():
        raise SystemExit("raster figure: digitise by hand and record the method in README.md")
    x0, x90, y0, y2 = axis_calibration(drawings)
    axes_rect = pymupdf.Rect(x0 - 1, y2 - 1, x90 + 1, y0 + 1)
    curves = find_curves(drawings, axes_rect)

    def to_data(p):
        age = AXES_X[0] + (p[:, 0] - x0) / (x90 - x0) * (AXES_X[1] - AXES_X[0])
        speed = AXES_Y[0] + (y0 - p[:, 1]) / (y0 - y2) * (AXES_Y[1] - AXES_Y[0])
        return np.column_stack([age, speed])

    ages = np.array(list(AGES), dtype=float)
    sampled, rms = [], []
    for name, d in zip(("mean", "plus", "minus"), curves, strict=True):
        raw = to_data(path_points(d))
        raw = raw[np.argsort(raw[:, 0])]
        v = np.interp(ages, raw[:, 0], raw[:, 1])
        pts = np.column_stack([ages, v])
        dist = np.sqrt(((pts[:, None, :] - raw[None, :, :]) ** 2).sum(-1)).min(axis=1)
        rms.append(float(np.sqrt((dist**2).mean())))
        sampled.append(v)
        print(f"{name}: age span {raw[0, 0]:.2f}-{raw[-1, 0]:.2f}, RMS to raw path {rms[-1]:.5f}")

    with OUT_CSV.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["age", "v_mean", "v_plus_sigma", "v_minus_sigma"])
        for i, a in enumerate(AGES):
            w.writerow([a, *(f"{s[i]:.4f}" for s in sampled)])
    print(f"wrote {OUT_CSV} ({len(AGES)} rows)")
    print(
        f"v_mean(20)={sampled[0][17]:.3f} v_mean(40)={sampled[0][37]:.3f} "
        f"v_mean(60)={sampled[0][57]:.3f} v_mean(80)={sampled[0][77]:.3f}"
    )


if __name__ == "__main__":
    main(sys.argv)
