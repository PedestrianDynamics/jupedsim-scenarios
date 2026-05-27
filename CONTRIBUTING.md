# Contributing

Thanks for considering a contribution to `jupedsim-scenarios`.

## Development install

```bash
git clone https://github.com/PedestrianDynamics/jupedsim-scenarios.git
cd jupedsim-scenarios
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,viz]"
```

Verify the install:

```bash
python -c "import jupedsim_scenarios; print(jupedsim_scenarios.__version__)"
jps-scenarios --version
```

## Local checks

Before opening a PR, all of the following should pass:

```bash
ruff check .
ruff format --check .
mypy src/jupedsim_scenarios
pytest
```

Notebook examples must also execute cleanly:

```bash
pytest --nbmake examples/
```

## Building the docs

```bash
pip install -r docs/requirements.txt
sphinx-build -b html docs/source docs/build/html
```

The docs build re-executes every notebook (`nb_execution_mode =
"force"` in `docs/source/conf.py`). A failing notebook fails the
build — fix it locally before pushing.

Check for broken links:

```bash
sphinx-build -b linkcheck docs/source docs/build/linkcheck
```

## Code style

- Match the surrounding code. Conventional patterns over creative ones.
- Keep diffs minimal — do not reformat unrelated lines.
- Public API additions must be documented in `docs/source/` and in
  the `__init__.py` re-export list.
- Add or update a how-to notebook whenever you ship a new public
  function or kwarg.

## Pull requests

- One focused change per PR.
- Reference the issue it closes.
- Update `CHANGELOG.md` under the `## Unreleased` heading.
- Confirm in the PR description which local checks you ran.

## Release process

Maintainers cut releases. See `docs/dev/api-design-cleanup.md` for
the pending API cleanups tracked across minor versions.

## Reporting issues

Open an issue at
<https://github.com/PedestrianDynamics/jupedsim-scenarios/issues>.
Include the package version (`jps-scenarios --version`), the
JuPedSim version, your platform, and a minimal reproducer.
