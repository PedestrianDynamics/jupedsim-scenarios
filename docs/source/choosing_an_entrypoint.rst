=======================
Choosing an entrypoint
=======================

Pick the smallest tool that fits your goal.

.. list-table::
   :header-rows: 1
   :widths: 45 35 20

   * - You want to…
     - Use
     - Example
   * - Run one scenario exported from the web editor
     - :py:func:`~jupedsim_scenarios.load_scenario` +
       :py:func:`~jupedsim_scenarios.run_scenario`
     - :doc:`notebooks/bottleneck_tutorial`
   * - Sweep one or more numeric parameters
     - :py:func:`~jupedsim_scenarios.run_sweep`
     - :doc:`notebooks/howtos/05_sweep_basics`
   * - Sweep where geometry or journeys change per trial
     - :py:func:`~jupedsim_scenarios.run_sweep_from_factory`
     - :doc:`notebooks/howtos/11_sweep_via_copy`
   * - Save a sweep and re-open it in another session
     - :py:meth:`SweepResult.save <jupedsim_scenarios.SweepResult.save>`
       / :py:meth:`SweepResult.load <jupedsim_scenarios.SweepResult.load>`
     - :doc:`notebooks/howtos/10_sweep_save_load`
   * - Build a scenario in pure Python (no web editor)
     - :py:class:`~jupedsim_scenarios.Scenario` constructor
     - :doc:`notebooks/howtos/09_build_from_scratch`
   * - Drive a single run from a shell or CI pipeline
     - ``jps-scenarios run`` CLI
     - :doc:`cli`

Rules of thumb
==============

- **One scenario, one outcome → ``run_scenario``.**
  Returns metrics and a trajectory you can plot or feed to pedpy.

- **Same scenario, parameter grid → ``run_sweep``.**
  Define ``axes`` (the values to vary) and ``apply`` (the mutator
  per axis). The cartesian product is run with multi-process workers.

- **Per-trial geometry / journey → ``run_sweep_from_factory``.**
  Provide a callable that returns a freshly-built ``Scenario`` for
  each parameter combination. Use this when ``axes + apply`` cannot
  express the variation.

- **Notebook workflow → Python API.**
  **Scripted pipeline → CLI.**
  The CLI prints a one-line JSON summary suitable for shell parsing.

See :doc:`concepts` for the underlying object model.
