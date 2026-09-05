"""Keep the CLI's terminal output to its own lines.

Some dependencies (PedPy 1.5 for one) install a root logging handler at
INFO level on import, which turns this library's diagnostic ``logger.info``
calls into a wall of text for every trial. The CLI therefore lowers the
library logger to WARNING unless ``--verbose`` is given. Sweep workers are
separate processes, so the choice travels through an environment variable
that ``_run_trial`` reads on the worker side.
"""

from __future__ import annotations

import logging
import os

QUIET_ENV = "JPS_SCENARIOS_QUIET"
_LIBRARY_LOGGER = "jupedsim_scenarios"


def quiet_library_logging() -> None:
    logging.getLogger(_LIBRARY_LOGGER).setLevel(logging.WARNING)


def request_quiet(quiet: bool) -> None:
    """Called once by the CLI: apply in this process and mark it for workers."""
    if not quiet:
        os.environ.pop(QUIET_ENV, None)
        return
    os.environ[QUIET_ENV] = "1"
    quiet_library_logging()


def apply_quiet_from_env() -> None:
    """Called at the start of each trial, which may run in a worker process."""
    if os.environ.get(QUIET_ENV) == "1":
        quiet_library_logging()
