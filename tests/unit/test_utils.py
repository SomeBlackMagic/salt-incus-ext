from unittest.mock import Mock

import pytest

from incus.utils import compute_backoff_interval
from incus.utils import resolve_polling_settings
from incus.utils import validate_timeout


def test_compute_backoff_first_interval_has_no_jitter():
    uniform = Mock()

    result = compute_backoff_interval(0, 0.5, 1.5, 30, 0.2, uniform=uniform)

    assert result == 0.5
    uniform.assert_not_called()


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(0, 0.5), (1, 0.75), (2, 1.125), (7, 8.54296875), (11, 30.0)],
)
def test_compute_backoff_grows_and_caps_without_jitter(attempt, expected):
    assert compute_backoff_interval(attempt, 0.5, 1.5, 30, 0) == expected


def test_compute_backoff_applies_jitter_after_capping_base():
    uniform = Mock(return_value=1.2)

    result = compute_backoff_interval(20, 0.5, 1.5, 30, 0.2, uniform=uniform)

    assert result == 36
    uniform.assert_called_once_with(0.8, 1.2)


def test_compute_backoff_allows_max_below_first_interval():
    assert compute_backoff_interval(0, 2, 1.5, 1, 0) == 2
    assert compute_backoff_interval(1, 2, 1.5, 1, 0) == 1


@pytest.mark.parametrize(
    "arguments",
    [
        (-1, 1, 1.5, 30, 0.2),
        (True, 1, 1.5, 30, 0.2),
        (0, 0, 1.5, 30, 0.2),
        (0, 1, 0.9, 30, 0.2),
        (0, 1, 1.5, 0, 0.2),
        (0, 1, 1.5, 30, -0.1),
        (0, 1, 1.5, 30, 1.1),
        (0, float("inf"), 1.5, 30, 0.2),
    ],
)
def test_compute_backoff_rejects_invalid_values(arguments):
    with pytest.raises(ValueError):
        compute_backoff_interval(*arguments)


@pytest.mark.parametrize("timeout", [-1, True, float("nan")])
def test_validate_timeout_rejects_invalid_values(timeout):
    with pytest.raises(ValueError, match="timeout"):
        validate_timeout(timeout)


def test_resolve_polling_settings_rejects_both_interval_names():
    defaults = {
        "initial_interval": 1,
        "backoff_enabled": False,
        "backoff_factor": 1.5,
        "max_interval": 30,
        "jitter": 0.2,
    }

    with pytest.raises(ValueError, match="mutually exclusive"):
        resolve_polling_settings({}, defaults, interval=1, initial_interval=2)


def test_resolve_polling_settings_prefers_explicit_values():
    defaults = {
        "initial_interval": 1,
        "backoff_enabled": False,
        "backoff_factor": 1.5,
        "max_interval": 30,
        "jitter": 0.2,
    }
    configured = {**defaults, "initial_interval": 4, "backoff_enabled": True}

    settings = resolve_polling_settings(
        configured,
        defaults,
        initial_interval=2,
        backoff_factor=2,
        jitter=0,
    )

    assert settings.initial_interval == 2
    assert settings.delay(0) == 2
    assert settings.delay(1) == 4
