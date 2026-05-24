# Sphinx configuration for jupedsim-scenarios.
# Style and stack mirror the main jupedsim docs:
# sphinx-book-theme + sphinx-autoapi + myst-nb.

import datetime
import shutil
from pathlib import Path

import jupedsim_scenarios

# ---------------------------------------------------------------------------
# Project information
# ---------------------------------------------------------------------------

project = "jupedsim-scenarios"
author = "The JuPedSim Development Team"
copyright = (
    f"{datetime.datetime.today().year}, Forschungszentrum Jülich GmbH, IAS-7"
)

version = getattr(jupedsim_scenarios, "__version__", "")
release = version

# ---------------------------------------------------------------------------
# Mirror the bottleneck tutorial notebook into source/notebooks/.
# Single source of truth lives at ../../examples/bottleneck_tutorial.ipynb.
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_EXAMPLE_NB = _HERE.parent.parent / "examples" / "bottleneck_tutorial.ipynb"
_NB_DEST = _HERE / "notebooks" / "bottleneck_tutorial.ipynb"
if _EXAMPLE_NB.exists():
    _NB_DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_EXAMPLE_NB, _NB_DEST)

# ---------------------------------------------------------------------------
# General configuration
# ---------------------------------------------------------------------------

extensions = [
    "sphinx.ext.mathjax",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx_copybutton",
    "sphinx_favicon",
    "notfound.extension",
    "autoapi.extension",
    "myst_nb",
]

templates_path = ["_templates"]
exclude_patterns = []

# Cross-project linking — match jupedsim's intersphinx targets so symbols
# resolve when we reference jupedsim / shapely / pedpy types.
intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "shapely": ("https://shapely.readthedocs.io/en/stable/", None),
    "jupedsim": ("https://www.jupedsim.org/stable/", None),
    "pedpy": ("https://pedpy.readthedocs.io/stable/", None),
}

# ---------------------------------------------------------------------------
# autoapi — static API reference generated from the source tree.
# ---------------------------------------------------------------------------

autoapi_dirs = ["../../src/jupedsim_scenarios"]
autoapi_root = "api"
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
    "imported-members",
]
autoapi_ignore = [
    "**/tests/**",
]
autoapi_add_toctree_entry = False
autoapi_python_class_content = "class"
autoapi_member_order = "groupwise"

add_module_names = False




# ---------------------------------------------------------------------------
# myst-nb — execute notebooks at build time so figures stay fresh.
# ---------------------------------------------------------------------------

# The tutorial notebook ships pre-executed (see examples/_build_notebook.py +
# `jupyter nbconvert --execute --inplace`). Re-executing on every docs build
# would add ~5 minutes and pull in jupedsim's full runtime; trust the
# committed outputs instead.
nb_execution_mode = "off"
nb_execution_raise_on_error = True
myst_enable_extensions = [
    "amsmath",
    "colon_fence",
    "deflist",
    "dollarmath",
    "html_image",
]

# ---------------------------------------------------------------------------
# HTML output — sphinx-book-theme, same chrome as jupedsim.org.
# ---------------------------------------------------------------------------

html_theme = "sphinx_book_theme"
html_static_path = ["_static"]
html_css_files = ["css/custom.css"]
html_context = {"default_mode": "light"}

html_theme_options = {
    "home_page_in_toc": False,
    "use_fullscreen_button": False,
    "use_issues_button": False,
    "use_download_button": False,
    "article_header_end": ["search-button", "toggle-secondary-sidebar"],
    "show_toc_level": 2,
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/PedestrianDynamics/jupedsim-scenarios",
            "icon": "fa-brands fa-github",
        },
        {
            "name": "PyPI",
            "url": "https://pypi.org/project/jupedsim-scenarios/",
            "icon": "https://img.shields.io/pypi/v/jupedsim-scenarios",
            "type": "url",
        },
    ],
}

html_sidebars = {
    "**": ["navbar-logo", "icon-links", "search-field", "sbt-sidebar-nav.html"]
}
