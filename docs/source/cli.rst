==============
CLI reference
==============

``jps-scenarios`` is a thin command-line wrapper around
:py:func:`~jupedsim_scenarios.run_scenario`. It is intended for CI
smoke tests and scripted pipelines. Interactive and notebook
workflows should stay on the Python API.

The CLI installs as a console script with the package:

.. code:: bash

    pip install jupedsim-scenarios
    jps-scenarios --version

Command-line interface
======================

The full parser is generated from
:py:func:`jupedsim_scenarios.cli.build_parser`, so this reference is
always in sync with the installed CLI.

.. argparse::
   :module: jupedsim_scenarios.cli
   :func: build_parser
   :prog: jps-scenarios

Input shapes for ``SCENARIO``
=============================

``jps-scenarios run`` routes through
:py:func:`~jupedsim_scenarios.load_scenario` and accepts any of:

- A self-contained JSON file with ``walkable_area_wkt`` embedded.
- A ZIP archive exported from the web editor.
- A directory holding one ``<name>.json`` + one ``<name>.wkt``.

Output schema
=============

On success ``run`` prints a single line of JSON to stdout:

.. code:: json

    {
      "scenario": "/abs/path/to/scenario.zip",
      "seed": 42,
      "model_type": "collision_free_speed",
      "evacuation_time": 28.41,
      "total_agents": 50,
      "agents_evacuated": 50,
      "agents_remaining": 0,
      "sqlite_file": "/abs/path/to/out.sqlite"
    }

``sqlite_file`` is ``null`` when ``--out`` was not given. The temp
trajectory is written during the run, then removed in a ``finally``
block immediately after the summary is printed — by the time the
process exits, no trajectory file remains on disk.

Exit codes
==========

+------+----------------------------------------------------------+
| Code | Meaning                                                  |
+======+==========================================================+
| 0    | Run finished, scenario fully evacuated or time-limited.  |
+------+----------------------------------------------------------+
| 1    | Simulation reported a failure (message on stderr).       |
+------+----------------------------------------------------------+
| 2    | Bad input — scenario not found, invalid args, IO error.  |
+------+----------------------------------------------------------+

Examples
========

Smoke test in CI (discard trajectory, keep summary):

.. code:: bash

    jps-scenarios run scenarios/bottleneck.zip --seed 0

Persist the trajectory for downstream pedpy analysis:

.. code:: bash

    jps-scenarios run scenarios/bottleneck.zip \
        --seed 0 --out runs/bottleneck.sqlite

Higher-resolution trajectory (every iteration recorded):

.. code:: bash

    jps-scenarios run scenarios/bottleneck.zip \
        --every-nth-frame 1 --out runs/dense.sqlite
