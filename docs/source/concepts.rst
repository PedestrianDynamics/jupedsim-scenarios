========
Concepts
========

Three objects carry state through ``jupedsim-scenarios``. Knowing
which one you are holding — and what mutating it does — prevents
most surprises.

Lifecycle
=========

.. code-block:: text

   zip / json / directory
            │
            ▼  load_scenario(...)
   ┌──────────────────┐
   │     Scenario     │  mutable; .copy() to branch
   └──────────────────┘
            │
            ▼  run_scenario(scenario, seed=...)
   ┌──────────────────┐
   │  ScenarioResult  │  owns a temp sqlite; call .cleanup()
   └──────────────────┘
            │
            ▼  .trajectory_dataframe()  /  .sqlite_file
        pandas / pedpy analysis

   For parameter studies:

       base : Scenario  ──►  run_sweep(base, axes=..., apply=..., seeds=...)
                                       │
                                       ▼
                                 ┌──────────────┐
                                 │ SweepResult  │  .save(...) / load(...)
                                 └──────────────┘

Scenario — the mutable plan
===========================

A :py:class:`~jupedsim_scenarios.Scenario` is the in-memory
representation of one simulation setup: geometry, agents, journeys,
solver settings, seed, and time limits.

It is **mutable**. Every ``add_*`` / ``remove_*`` / ``set_*`` call,
and every direct attribute assignment, changes the instance in place:

.. code-block:: python

    base = load_scenario("bottleneck.zip")
    base.seed = 99             # base is now permanently at seed=99

If you want to keep the original intact — and you almost always do
once you start sweeping or comparing variants — call ``.copy()``
first and edit the clone:

.. code-block:: python

    trial = base.copy()
    trial.seed = 99
    trial.max_simulation_time = 60
    # base is untouched

:py:func:`~jupedsim_scenarios.run_sweep` does this for you per
trial. The copy-first discipline only matters when you assemble
variants by hand. See
:doc:`notebooks/howtos/11_sweep_via_copy` for the worked pattern.

Inspecting the plan
===================

``scenario.plot()`` draws the walkable area with labelled
distributions, exits, zones, and checkpoints. Two arguments turn it
into a before/after view of a run:

- ``show_journeys=True`` (the default) overlays each journey's route
  as curved arrows in stage order. Both schema versions are read,
  so current web-editor exports (``journeys_v2``) show routes too.
- ``trajectories=`` takes a ``ScenarioResult`` (or a pedpy
  ``TrajectoryData``) and draws the agent paths from a completed run
  on top of the plan. Use ``show_trajectories=False`` to force it off.

.. code-block:: python

    result = run_scenario(scenario, seed=42)
    scenario.plot(show_journeys=True, trajectories=result)

See :doc:`notebooks/howtos/02_visualisation` for the full tour.

ScenarioResult — the run output
================================

:py:func:`~jupedsim_scenarios.run_scenario` returns a
:py:class:`~jupedsim_scenarios.ScenarioResult`. It carries
summary metrics (``evacuation_time``, ``agents_evacuated``,
``frame_rate``, …) and owns a **temporary SQLite trajectory file**
written by the simulator.

Two things to remember:

- ``trajectory_dataframe()`` materializes the trajectory as a
  pandas DataFrame compatible with :doc:`pedpy <pedpy:index>`.
- ``visualise()`` returns an interactive plotly animation of the run
  — agents coloured by speed, with a play button and time slider.
  Pass ``save_path="run.html"`` to write a self-contained file.
- ``cleanup()`` deletes the temp sqlite. Call it when you are done,
  or wrap your run in a ``try / finally`` block. The file does not
  vanish on garbage collection.

.. code-block:: python

    result = run_scenario(scenario, seed=42)
    try:
        df = result.trajectory_dataframe()
        # ...analysis...
    finally:
        result.cleanup()

SweepResult — the persisted study
=================================

:py:func:`~jupedsim_scenarios.run_sweep` and
:py:func:`~jupedsim_scenarios.run_sweep_from_factory` return a
:py:class:`~jupedsim_scenarios.SweepResult`. It is the artifact
you save, re-load, and analyze across sessions.

- ``to_dataframe()`` returns one row per trial: parameter values,
  metrics, sqlite path.
- ``save(path)`` / ``SweepResult.load(path)`` round-trip a sweep,
  including the per-trial trajectory databases. Useful for long
  studies that you want to analyze separately.
- ``cleanup()`` removes all per-trial temp files.

See :doc:`notebooks/howtos/10_sweep_save_load` for the
save/reload pattern.

Where each object lives
=======================

+--------------------+----------------------+----------------------------+
| Object             | Lives in             | Disk footprint             |
+====================+======================+============================+
| ``Scenario``       | Python memory only   | None until you ``save``    |
+--------------------+----------------------+----------------------------+
| ``ScenarioResult`` | Python + temp sqlite | One trajectory db          |
+--------------------+----------------------+----------------------------+
| ``SweepResult``    | Python + temp dir    | One sqlite per trial       |
+--------------------+----------------------+----------------------------+

Next
====

- :doc:`choosing_an_entrypoint` — pick the right function for the job.
- :doc:`troubleshooting` — common pitfalls and their fixes.
