# Repository Guidelines

## Project Structure & Module Organization

`vase_stress/` contains the local Python backend. Keep text parsing in `config.py`, color interpolation in `colors.py`, finite element assembly in `solver.py`, geometry and file conversion in `pipeline.py`, and command handling in `cli.py`. Tests live in `tests/`; editable input examples live in `examples/`. Generated VTU, GLB, and summary files belong under ignored `outputs/` directories.

## Build, Test, and Development Commands

- `python -m venv .venv`: create an isolated environment.
- `python -m pip install -e .`: install the backend and numerical dependencies using the environment's Python.
- `python -m unittest discover -s tests -v`: run validation, numerical, and conversion tests. Dependency-related skips do not establish solver correctness.
- `python -m vase_stress.cli run --model vase.glb --settings examples/settings.txt --output outputs/run-001`: generate VTU first, then its stress-colored GLB.

See `README.md` for Windows environment commands and every input setting.

## Coding Style & Naming Conventions

Use four spaces, descriptive `snake_case` names, and small functions with explicit units in field names. Keep core configuration and color utilities dependency-free. No formatter or linter is configured. Reject malformed inputs with actionable errors; preserve existing output files.

## Testing Guidelines

Use standard-library `unittest` and name tests `test_*.py`. Generate geometry fixtures in temporary directories. Numerical changes require analytical element checks or force-equilibrium checks, plus relevant file round trips. No coverage threshold is configured. CI runs on Windows and Linux.

## Commit & Pull Request Guidelines

No existing Git history establishes message conventions. Use concise imperative subjects, such as `Add gravity equilibrium test`. Describe behavior, assumptions, validation results, and dependency changes in pull requests. Link related issues and include stress previews when visualization changes.

## Configuration & Numerical Integrity

Keep model files, results, and API keys out of commits. Preserve editable physical inputs, SI units, documented approximation limits, and the white-yellow-orange-red stress scale. Never replace computed stress with AI-generated values.
