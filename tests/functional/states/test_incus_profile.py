"""Functional tests for Incus profile state functions."""

import pytest

from tests.functional.conftest import check_local_shell
from tests.functional.conftest import create_case_parametrize
from tests.functional.conftest import run_cleanup
from tests.functional.conftest import run_setup

pytestmark = pytest.mark.requires_salt_states("incus.profile_present")


@create_case_parametrize("profiles.yml")
def test_profile(case, states):
    run_setup(case.get("setup"))

    profiles = case["pillars"]["incus"]["profiles"]

    try:
        for name, opts in (profiles or {}).items():
            ensure = opts.get("ensure", "present")

            if ensure == "absent":
                ret = states["incus.profile_absent"](name)
            else:
                ret = states["incus.profile_present"](
                    name,
                    config=opts.get("config"),
                    devices=opts.get("devices"),
                    description=opts.get("description", ""),
                )

            assert (
                ret.result is True
            ), f"State incus.profile_{ensure} failed for '{name}': {ret.comment}"

        expected = case.get("expected", {})
        if "local_shell" in expected:
            check_local_shell(expected["local_shell"])

    finally:
        run_cleanup(case.get("cleanup", []))
