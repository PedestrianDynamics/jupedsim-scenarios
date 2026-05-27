================
Troubleshooting
================

Common pitfalls and their fixes. If your issue is not here, please
open an `issue <https://github.com/PedestrianDynamics/jupedsim-scenarios/issues>`_.

My second sweep trial sees modified values from the first
=========================================================

``Scenario`` is mutable. If you edit ``base`` inside a loop, every
later trial inherits the edits.

.. code-block:: python

    # Wrong — mutates base in place
    for v in [0.8, 1.2, 1.6]:
        base.set_agent_params(0, desired_speed=v)
        run_scenario(base)

    # Right — branch from base each iteration
    for v in [0.8, 1.2, 1.6]:
        trial = base.copy()
        trial.set_agent_params(0, desired_speed=v)
        run_scenario(trial)

:py:func:`~jupedsim_scenarios.run_sweep` does the ``.copy()`` for
you. See :doc:`concepts` for the full mutability story.

``result.frame_rate`` is ``None``
=================================

The result genuinely has no recorded frame rate — typically because
metrics were not written, not because the run failed. Read the
actual writer stride from the simulation settings used for the run,
or re-run with metric capture enabled.

What does ``workers=0`` mean in ``run_sweep``?
==============================================

One worker **per CPU**. Set ``workers=1`` to force serial execution
(easier to debug), or pick an integer ≥ 1 to cap parallelism.

Where is the trajectory SQLite file? When is it deleted?
========================================================

Each run writes its trajectory to a temp directory managed by the
result object:

- ``result.sqlite_file`` — absolute path to the file.
- ``result.cleanup()`` — deletes it.

The file is **not** deleted on garbage collection. If you forget
``cleanup()`` the OS will reclaim it on next reboot, but long-running
notebooks can accumulate gigabytes of trajectories.

Wrap runs in ``try / finally`` for safety:

.. code-block:: python

    result = run_scenario(scenario)
    try:
        df = result.trajectory_dataframe()
    finally:
        result.cleanup()

Can I resume a sweep that was interrupted?
==========================================

Yes — sweeps can be saved and re-loaded. See
:doc:`notebooks/howtos/09_sweep_save_load`. The save format
includes per-trial trajectories so analysis works offline.

``DeprecationWarning: v0 / v0_std / v0_distribution``
=====================================================

Use ``desired_speed`` / ``desired_speed_std`` /
``desired_speed_distribution`` instead. The ``v0`` family was
renamed to match upstream JuPedSim. Old names still work for now;
they will be removed in a future release.

.. code-block:: python

    # Old
    scenario.set_agent_params(0, v0=1.2)
    # New
    scenario.set_agent_params(0, desired_speed=1.2)

``load_scenario`` fails on my file
==================================

``load_scenario`` accepts three input shapes:

- A ZIP archive exported from the web editor.
- A directory containing ``<name>.json`` plus ``<name>.wkt``.
- A single self-contained JSON file with ``walkable_area_wkt``
  embedded as a string.

If you have a bare ``.json`` without an embedded WKT geometry, the
loader cannot reconstruct the geometry — point it at the directory
or zip that holds the matching ``.wkt`` file.

The CLI only accepts the bare-JSON form for the ``run`` subcommand.
For zips, use the Python API or unzip first.

Sphinx docs build fails on notebook execution
=============================================

The published docs re-run every notebook on each build
(``nb_execution_mode = "force"`` in ``docs/source/conf.py``). If a
notebook errors, the build fails on purpose. Install the docs
extras and run the offending notebook locally first:

.. code-block:: bash

    pip install -r docs/requirements.txt
    jupyter execute examples/howtos/04_sweep_basics.ipynb
