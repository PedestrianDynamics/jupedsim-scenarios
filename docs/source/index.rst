===================
jupedsim-scenarios
===================

.. toctree::
   :maxdepth: 1
   :hidden:

   Getting started <notebooks/bottleneck_tutorial>
   How-tos <howtos>
   Cookbook <cookbook>
   API reference <api/jupedsim_scenarios/index>


**Useful links**:
`Python Package <https://pypi.org/project/jupedsim-scenarios/>`__ |
`Source Repository <https://github.com/PedestrianDynamics/jupedsim-scenarios>`__ |
`Issues <https://github.com/PedestrianDynamics/jupedsim-scenarios/issues>`__ |
`JuPedSim <https://www.jupedsim.org/>`__

What is jupedsim-scenarios
==========================

``jupedsim-scenarios`` is a Python toolkit for running, sweeping, and
analyzing `JuPedSim <https://www.jupedsim.org/>`_ scenarios authored in
the `Web-Based JuPedSim <https://github.com/PedestrianDynamics/jupedsim-web-community>`_
editor.

Where the main :doc:`jupedsim package <jupedsim:index>` exposes the
simulation primitives (geometry, agents, models, journeys),
``jupedsim-scenarios`` operates one level up: it consumes a scenario
**as exported from the web editor** — a JSON config plus a WKT geometry,
packaged as a zip — and gives you three things:

- :py:func:`~jupedsim_scenarios.run_scenario` — run one scenario, get
  back a :py:class:`~jupedsim_scenarios.ScenarioResult` with metrics
  and a trajectory database compatible with
  :doc:`pedpy <pedpy:index>`.
- :py:func:`~jupedsim_scenarios.run_sweep` — Monte Carlo parameter
  sweeps over any axes the :py:class:`~jupedsim_scenarios.Scenario`
  mutators expose, with multi-process workers.
- :py:func:`~jupedsim_scenarios.run_sweep_from_factory` — factory-style
  sweeps for studies where the geometry itself depends on the trial
  parameters.

Install
=======

.. code:: bash

    pip install jupedsim-scenarios

Quick start
===========

.. code:: python

    from jupedsim_scenarios import load_scenario, run_scenario

    scenario = load_scenario("bottleneck.zip")
    result = run_scenario(scenario, seed=42)

    print(result.evacuation_time)        # seconds
    print(result.agents_evacuated, "/", result.total_agents)
    df = result.trajectory_dataframe()   # pandas DataFrame
    result.cleanup()

For a guided tour with sweeps, model comparison, and a 2-D
``model × bottleneck width`` study, see the
:doc:`bottleneck tutorial <notebooks/bottleneck_tutorial>`.

Status
======

Alpha. Single-run, Monte Carlo sweeps (multi-process), and a
``jps-scenarios`` CLI are shipped. Restartable / resumable sweeps land
in 0.4.0.
