"""Shared utility helpers for the Incus extension."""

import logging
import math
import random
from dataclasses import dataclass
from functools import wraps
from numbers import Real

_SENSITIVE_FIELD_MARKERS = (
    "certificate",
    "cloud-init",
    "key",
    "password",
    "secret",
    "token",
    "user-data",
)


def redact_sensitive_data(value):
    """Return a copy with values of sensitive mapping fields redacted."""
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if any(marker in str(key).lower() for marker in _SENSITIVE_FIELD_MARKERS)
                else redact_sensitive_data(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    return value


def log_state_changes(func):
    """Log the changes reported by a successful Salt state function."""
    logger = logging.getLogger(func.__module__)

    @wraps(func)
    def wrapped(*args, **kwargs):
        result = func(*args, **kwargs)
        if isinstance(result, dict) and result.get("result") is not False:
            name = result.get("name", args[0] if args else kwargs.get("name", ""))
            changes = result.get("changes") or {}
            if changes:
                logger.debug(
                    "State '%s': applying changes %s", name, redact_sensitive_data(changes)
                )
            else:
                logger.debug("State '%s': no changes needed", name)
        return result

    return wrapped


def _validate_real(name, value, *, minimum, inclusive):
    """Validate a finite real number against a lower bound."""
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if inclusive and value < minimum:
        raise ValueError(f"{name} must be greater than or equal to {minimum}")
    if not inclusive and value <= minimum:
        raise ValueError(f"{name} must be greater than {minimum}")


def validate_timeout(timeout):
    """Validate a polling timeout."""
    _validate_real("timeout", timeout, minimum=0, inclusive=True)


def compute_backoff_interval(
    attempt,
    initial_interval,
    backoff_factor,
    max_interval,
    jitter,
    uniform=None,
):
    """Return the polling delay for a zero-based attempt number."""
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        raise ValueError("attempt must be an integer greater than or equal to 0")
    _validate_real("initial_interval", initial_interval, minimum=0, inclusive=False)
    _validate_real("backoff_factor", backoff_factor, minimum=1, inclusive=True)
    _validate_real("max_interval", max_interval, minimum=0, inclusive=False)
    _validate_real("jitter", jitter, minimum=0, inclusive=True)
    if jitter > 1:
        raise ValueError("jitter must be less than or equal to 1")

    if attempt == 0:
        return float(initial_interval)

    try:
        base = initial_interval * (backoff_factor**attempt)
    except OverflowError:
        base = max_interval
    base = float(min(base, max_interval))

    if jitter == 0:
        return base

    uniform = uniform or random.uniform
    return base * uniform(1.0 - jitter, 1.0 + jitter)


@dataclass(frozen=True)
class PollingSettings:
    """Validated settings for a polling loop."""

    initial_interval: float
    backoff_enabled: bool
    backoff_factor: float
    max_interval: float
    jitter: float

    def delay(self, attempt):
        """Return the delay for an attempt according to the selected mode."""
        if not self.backoff_enabled:
            return self.initial_interval
        return compute_backoff_interval(
            attempt,
            self.initial_interval,
            self.backoff_factor,
            self.max_interval,
            self.jitter,
        )


def resolve_polling_settings(
    configured,
    defaults,
    *,
    interval=None,
    initial_interval=None,
    backoff_enabled=None,
    backoff_factor=None,
    max_interval=None,
    jitter=None,
):
    """Merge explicit polling options with configuration and defaults."""
    if interval is not None and initial_interval is not None:
        raise ValueError("interval and initial_interval are mutually exclusive")

    def resolve(name, explicit):
        if explicit is not None:
            return explicit
        return configured.get(name, defaults[name])

    resolved = PollingSettings(
        initial_interval=(
            initial_interval
            if initial_interval is not None
            else interval if interval is not None else resolve("initial_interval", None)
        ),
        backoff_enabled=resolve("backoff_enabled", backoff_enabled),
        backoff_factor=resolve("backoff_factor", backoff_factor),
        max_interval=resolve("max_interval", max_interval),
        jitter=resolve("jitter", jitter),
    )
    if not isinstance(resolved.backoff_enabled, bool):
        raise ValueError("backoff_enabled must be a boolean")
    compute_backoff_interval(
        0,
        resolved.initial_interval,
        resolved.backoff_factor,
        resolved.max_interval,
        resolved.jitter,
    )
    return resolved
