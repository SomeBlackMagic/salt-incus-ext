"""Functional tests for Incus server settings state functions."""

import pytest

from tests.functional.conftest import check_local_shell
from tests.functional.conftest import create_case_parametrize
from tests.functional.conftest import run_cleanup
from tests.functional.conftest import run_setup

pytestmark = pytest.mark.requires_salt_states("incus.settings_present")


@create_case_parametrize("settings.yml")
def test_settings(case, states):
    run_setup(case.get("setup"))

    server_settings = case["pillars"]["incus"]["server_settings"]
    config = server_settings["config"]

    try:
        ret = states["incus.settings_present"]("server_settings", config=config)

        assert ret.result is True, f"State incus.settings_present failed: {ret.comment}"

        expected = case.get("expected", {})
        if "local_shell" in expected:
            check_local_shell(expected["local_shell"])

    finally:
        run_cleanup(case.get("cleanup", []))
