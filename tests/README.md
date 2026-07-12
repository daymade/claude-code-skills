# Tests

Repository-level regression tests for selected skill scripts.

## Running

Run the suite with pytest in an isolated `uv` environment:

```bash
uv run --with pytest python -m pytest tests/
```

Or use the standard-library `unittest` runner without installing pytest:

```bash
uv run python -m unittest discover tests
```

## Adding Tests

Place new test files in this directory using a descriptive `test_<component>[_<area>].py` name. Import the target script via `importlib` (see the existing tests for examples) so tests remain independent of install location.
