"""Functional tests for Incus instance state functions."""

import pytest

from tests.functional.conftest import check_local_shell
from tests.functional.conftest import check_requirements
from tests.functional.conftest import create_case_parametrize
from tests.functional.conftest import run_cleanup
from tests.functional.conftest import run_local_shell
from tests.functional.conftest import run_setup

pytestmark = pytest.mark.requires_salt_states("incus.instance_present")


def setup_module(module):
    """Pre-fetch images used across instance tests."""
    run_local_shell(
        "incus image copy images:ubuntu/22.04 local: --alias ubuntu/22.04 2>/dev/null || true"
    )
    run_local_shell(
        "incus image copy images:debian/12 local: --alias debian/12 2>/dev/null || true"
    )
    run_local_shell(
        "incus image copy images:ubuntu/jammy local: --alias ubuntu/jammy --vm 2>/dev/null || true"
    )
    run_local_shell(
        "incus image copy images:debian/12 local: --alias debian/12-vm --vm 2>/dev/null || true"
    )


@create_case_parametrize("instances.yml")
def test_instance(case, states):
    check_requirements(case)
    run_setup(case.get("setup"))

    instances = case["pillars"]["incus"]["instances"]

    try:
        for name, opts in instances.items():
            ensure = opts.get("ensure", "present")

            if ensure == "absent":
                ret = states["incus.instance_absent"](name, force=True)
            else:
                ret = states["incus.instance_present"](
                    name,
                    source=opts.get("source"),
                    instance_type=opts.get("instance_type", "container"),
                    config=opts.get("config"),
                    devices=opts.get("devices"),
                    profiles=opts.get("profiles"),
                    ephemeral=opts.get("ephemeral", False),
                )

            assert (
                ret.result is True
            ), f"State incus.instance_{ensure} failed for '{name}': {ret.comment}"
            assert ret.changes, f"Expected changes for '{name}', got none"

        expected = case.get("expected", {})
        if "local_shell" in expected:
            check_local_shell(expected["local_shell"])

    finally:
        run_cleanup(case.get("cleanup", []))
