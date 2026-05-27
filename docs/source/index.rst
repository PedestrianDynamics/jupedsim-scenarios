===================
jupedsim-scenarios
===================

.. toctree::
   :maxdepth: 1
   :hidden:

   Getting started <notebooks/bottleneck_tutorial>
   Concepts <concepts>
   Choosing an entrypoint <choosing_an_entrypoint>
   How-tos <howtos>
   Cookbook <cookbook>
   CLI reference <cli>
   Troubleshooting <troubleshooting>
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

.. image:: _static/jupedsim-scenarios-demo.gif
   :alt: Demo — a few lines of Python to load and run a scenario
   :align: center
   :width: 720px

.. raw:: html

   <p style="text-align: center; margin-top: 1em;">
     <a href="https://youtu.be/GqVUDMuoSmc?si=qWKOeAVCzjG1vg60">
       <img src="https://img.youtube.com/vi/GqVUDMuoSmc/0.jpg"
            alt="jupedsim-scenarios intro video"
            style="max-width: 480px; width: 100%;">
     </a>
     <br>
     <em>Intro video (3 min) — overview of the load → run → sweep flow.</em>
   </p>

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

In a hurry? The :doc:`5-minute quickstart <notebooks/howtos/00_quickstart>`
uses a tiny scenario shipped with the repo — no web-editor export
needed. For a guided tour with sweeps, model comparison, and a 2-D
``model × bottleneck width`` study, see the
:doc:`bottleneck tutorial <notebooks/bottleneck_tutorial>`.

Where to next
=============

- :doc:`concepts` — the object model: ``Scenario`` (mutable),
  ``ScenarioResult`` (owns a temp sqlite), ``SweepResult``
  (savable artifact).
- :doc:`choosing_an_entrypoint` — decision table mapping goals to
  API calls.
- :doc:`troubleshooting` — common pitfalls and their fixes.
- :doc:`cli` — ``jps-scenarios`` command-line reference.

Citation
========

If ``jupedsim-scenarios`` supports work you publish, please cite the
upstream `JuPedSim <https://www.jupedsim.org/stable/citing.html>`_
project and link to this repository
(`<https://github.com/PedestrianDynamics/jupedsim-scenarios>`_). A
dedicated DOI for this toolkit will be added once a Zenodo deposit
is in place.

Status
======

Single-run, Monte Carlo sweeps (multi-process), save/resume of
sweeps, and a ``jps-scenarios`` CLI are shipped. See the
`CHANGELOG <https://github.com/PedestrianDynamics/jupedsim-scenarios/blob/main/CHANGELOG.md>`_
for the full release history.
