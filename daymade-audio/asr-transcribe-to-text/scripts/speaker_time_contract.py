"""Canonical millisecond contract shared by speaker-bundle producers."""

from decimal import Decimal, ROUND_HALF_UP


TIME_CONTRACT_ID = "speaker-time-ms-half-up-v1"
MILLISECOND_S = 0.001
_MS_PER_SECOND = Decimal("1000")
_ONE_MS = Decimal("1")


def to_milliseconds(seconds):
    """Convert seconds to integer milliseconds with explicit half-up rounding."""
    return int(
        (Decimal(str(seconds or 0.0)) * _MS_PER_SECOND).quantize(
            _ONE_MS,
            rounding=ROUND_HALF_UP,
        )
    )


def to_seconds(seconds):
    """Return the canonical millisecond-aligned seconds value."""
    return to_milliseconds(seconds) / 1000


def positive_turn_bounds(start, end):
    """Return canonical start/end/duration, enforcing one positive millisecond."""
    start_ms = to_milliseconds(start)
    end_ms = to_milliseconds(end)
    if end_ms <= start_ms:
        end_ms = start_ms + 1
    return start_ms / 1000, end_ms / 1000, (end_ms - start_ms) / 1000


def format_timestamp(seconds):
    """Format canonical milliseconds as total minutes plus seconds."""
    total_ms = to_milliseconds(seconds)
    minutes, remainder_ms = divmod(total_ms, 60_000)
    secs, milliseconds = divmod(remainder_ms, 1_000)
    return f"{minutes:02d}:{secs:02d}.{milliseconds:03d}"
