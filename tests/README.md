# Tests

Regression tests for safety-critical skill scripts.

## Running

```bash
python -m pytest tests/
```

Or with the standard `unittest` runner:

```bash
python -m unittest discover tests
```

## Coverage

| Test file | What it covers |
|-----------|----------------|
| `test_macos_cleaner_safety.py` | `macos-cleaner` safety guards — verifies that `safe_delete` blocks high-risk system paths and credentials, and that `find_app_remnants` correctly identifies orphaned app support files without false positives. |

## Adding Tests

Place new test files in this directory following the `test_<skill_name>_<area>.py` naming convention. Each file should import the target script via `importlib` (see the existing test for an example) so tests remain independent of install location.
