"""Functional tests for Incus storage pool state functions."""

import pytest

from tests.functional.conftest import check_local_shell
from tests.functional.conftest import check_requirements
from tests.functional.conftest import create_case_parametrize
from tests.functional.conftest import run_cleanup
from tests.functional.conftest import run_setup

pytestmark = pytest.mark.requires_salt_states("incus.storage_pool_present")


@create_case_parametrize("storage.yml")
def test_storage_pool(case, states):
    check_requirements(case)
    run_setup(case.get("setup"))

    pools = case["pillars"]["incus"]["storage_pools"]

    try:
        for name, opts in pools.items():
            ensure = opts.get("ensure", "present")

            if ensure == "absent":
                ret = states["incus.storage_pool_absent"](name)
                # Absent on non-existing pool is not a failure
                assert (
                    ret.result is True
                ), f"State incus.storage_pool_absent failed for '{name}': {ret.comment}"
            else:
                ret = states["incus.storage_pool_present"](
                    name,
                    driver=opts["driver"],
                    config=opts.get("config"),
                    description=opts.get("description", ""),
                )
                assert (
                    ret.result is True
                ), f"State incus.storage_pool_present failed for '{name}': {ret.comment}"

        expected = case.get("expected", {})
        if "local_shell" in expected:
            check_local_shell(expected["local_shell"])

    finally:
        run_cleanup(case.get("cleanup", []))
