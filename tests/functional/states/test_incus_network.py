"""Functional tests for Incus network state functions."""

import pytest

from tests.functional.conftest import check_local_shell
from tests.functional.conftest import check_requirements
from tests.functional.conftest import create_case_parametrize
from tests.functional.conftest import run_cleanup
from tests.functional.conftest import run_setup

pytestmark = pytest.mark.requires_salt_states("incus.network_present")


@create_case_parametrize("network.yml")
def test_network(case, states):
    check_requirements(case)
    run_setup(case.get("setup"))

    networks = case["pillars"]["incus"]["networks"]

    try:
        for name, opts in (networks or {}).items():
            ensure = opts.get("ensure", "present")

            if ensure == "absent":
                ret = states["incus.network_absent"](name)
            else:
                ret = states["incus.network_present"](
                    name,
                    network_type=opts.get("network_type", "bridge"),
                    config=opts.get("config"),
                    description=opts.get("description", ""),
                )

            assert (
                ret.result is True
            ), f"State incus.network_{ensure} failed for '{name}': {ret.comment}"

        expected = case.get("expected", {})
        if "local_shell" in expected:
            check_local_shell(expected["local_shell"])

    finally:
        run_cleanup(case.get("cleanup", []))
