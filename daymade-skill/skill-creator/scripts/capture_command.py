#!/usr/bin/env python3
"""Compatibility entry; implementation is generated from the standalone I/O owner."""
try:
    from ._bounded_io import capture as _owner
except ImportError:
    from _bounded_io import capture as _owner

# Keep the established programmatic API as well as both CLI entry forms.
globals().update({name: value for name, value in vars(_owner).items()
                  if not name.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(main())
