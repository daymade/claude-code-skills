#!/usr/bin/env python3
"""Compatibility entry; implementation is generated from the standalone I/O owner."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_spec = spec_from_file_location(
    __name__ + "._owner", Path(__file__).resolve().parent / "_bounded_io" / "capture.py")
_owner = module_from_spec(_spec)
_spec.loader.exec_module(_owner)

# Keep the established programmatic API as well as both CLI entry forms.
globals().update({name: value for name, value in vars(_owner).items()
                  if not name.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(main())
