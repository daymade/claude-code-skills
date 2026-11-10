"""Request composition shared by the native HTTP and WebSocket surfaces."""
from __future__ import annotations

import copy
import json
from collections.abc import Mapping

UNSET = object()


def merge_request(request=None, *, typed=None, extra=None, defaults=None):
    """Preserve native fields; conflicting explicit values are an error."""
    body = {}
    for name, values in (("request", request), ("typed", typed), ("extra", extra)):
        if values is None:
            continue
        if not isinstance(values, Mapping):
            raise TypeError(f"{name} must be a mapping")
        for key, value in values.items():
            if value is UNSET:
                continue
            if key in body and json.dumps(body[key], sort_keys=True, allow_nan=False) != json.dumps(
                value, sort_keys=True, allow_nan=False
            ):
                raise ValueError(f"Conflicting explicit values for {key!r}; use one request channel")
            body[key] = copy.deepcopy(value)
    for key, value in (defaults or {}).items():
        body.setdefault(key, value)
    json.dumps(body, allow_nan=False)
    return body


def require_strings(body, *names):
    for name in names:
        if not isinstance(body.get(name), str) or not body[name].strip():
            raise ValueError(f"An explicit non-empty {name} is required")


def require_key(api_key):
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("An explicit API key is required; no credential fallback")
    return api_key
