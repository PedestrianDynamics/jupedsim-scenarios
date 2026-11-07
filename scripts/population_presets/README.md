# Population presets from RiMEA 4.0.0 Abb. 3

Source: RiMEA 4.0.0, https://rimea.de/wp-content/uploads/2023/01/rimea-4.0.0.pdf
(SHA-256 `a27724f60f84dc2ae0138887b2ea8c7cf23aae3489e10c423820f7f837110685`).
Figure Abb. 3 (walking speed over age, section 3.2.2.2; after Weidmann 1992) is on
page 10. The PDF is not stored in this repository.

## Method

1. `digitise_abb3.py <pdf>` reads the vector paths of the three curves (mean,
   mean + sigma, mean - sigma) with PyMuPDF, maps PDF coordinates to
   (age, speed) with the axis tick marks (x 0-90 years, y 0-2 m/s) and
   interpolates each curve at integer ages 3-80 into `rimea4_abb3.csv`.
   PyMuPDF is not a project dependency: run it with `uv run --with pymupdf`.
2. `derive_presets.py` takes sigma = (v_plus - v_minus) / 2 per age and
   combines the ages of each band into one Gaussian: weighted mean, and a std
   made of the within-age variance plus the between-age variance of the means.
   Ages 81-85 reuse the age-80 values. Results are rounded to 0.01 and written
   to `src/jupedsim_scenarios/assets/population_presets.json`.
   With `--pdf` it also renders `abb3_overlay.png` (needs `pdftoppm`).

Read from the figure: the three curves only. Everything else is an app choice:
the age bands (except `general_population`, which uses the RiMEA standard
population of section 3.2.4, approximated by weights `exp(-(a-50)^2/800)` over
ages 10-85), the Gaussian shape, and the constant radius of 0.2 m.

`abb3_overlay.png` embeds a crop of the axes region only.

Review status: pending maintainer review
