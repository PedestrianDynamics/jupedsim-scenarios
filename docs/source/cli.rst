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

Subcommands
===========

``run``
-------

Execute a single scenario and emit a one-line JSON summary on
stdout.

.. code:: bash

    jps-scenarios run SCENARIO [--seed N] [--out PATH]
                                [--dt SECONDS] [--every-nth-frame N]

Positional argument
^^^^^^^^^^^^^^^^^^^

``SCENARIO``
    Scenario source. Accepts any of:

    - A self-contained JSON file with ``walkable_area_wkt`` embedded.
    - A ZIP archive exported from the web editor.
    - A directory holding one ``<name>.json`` + one ``<name>.wkt``.

Options
^^^^^^^

``--seed N``
    Override the scenario's seed. Default: the value in the JSON.

``--out PATH``
    Where to write the trajectory SQLite. If omitted the file lives
    in a tempdir and is deleted on exit. Metrics still print.

``--dt SECONDS``
    Iteration step in seconds. Default: JuPedSim's built-in
    (currently ``0.01``).

``--every-nth-frame N``
    Trajectory writer stride. Default ``10`` (≈ 10 fps at
    ``dt=0.01``). Set to ``1`` to record every iteration.

Output schema
^^^^^^^^^^^^^

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

``sqlite_file`` is ``null`` when ``--out`` was not given (the temp
file has already been removed by the time the line is printed).

Exit codes
^^^^^^^^^^

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
^^^^^^^^

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
