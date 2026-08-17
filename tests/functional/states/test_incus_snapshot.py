"""Functional tests for Incus instance snapshot state functions."""

import pytest

from tests.functional.conftest import check_local_shell
from tests.functional.conftest import check_requirements
from tests.functional.conftest import create_case_parametrize
from tests.functional.conftest import run_cleanup
from tests.functional.conftest import run_setup

pytestmark = pytest.mark.requires_salt_states("incus.instance_snapshot_present")


def _managed_name(snap_id, opts):
    """Generate a managed snapshot name with zero-padded index."""
    pattern = opts.get("pattern", "snap-*")
    prefix = pattern.rstrip("*")
    return f"{prefix}001"


@create_case_parametrize("snapshots.yml")
def test_snapshot(case, states):
    check_requirements(case)
    run_setup(case.get("setup"))

    snapshots_cfg = case["pillars"]["incus"]["instance_snapshots"]

    try:
        for snap_id, opts in snapshots_cfg.items():
            instance = opts["instance"]
            ensure = opts.get("ensure", "present")
            managed = opts.get("managed", False)

            if managed:
                # Use instance_snapshots_managed for managed snapshot policies
                snap_name = opts.get("name") or _managed_name(snap_id, opts)
                snapshots_config = {
                    snap_id: {
                        "name": snap_name,
                        "stateful": opts.get("stateful", False),
                        "description": opts.get("description", ""),
                        "pattern": opts.get("pattern"),
                        "keep": opts.get("keep"),
                    }
                }
                if ensure == "absent":
                    # For absent managed: just delete the specific snapshot
                    ret = states["incus.instance_snapshot_absent"](snap_name, instance=instance)
                elif ensure == "restored":
                    ret = states["incus.instance_snapshot_restored"](snap_name, instance=instance)
                else:
                    ret = states["incus.instance_snapshots_managed"](
                        f"{instance}_snapshots",
                        instance=instance,
                        snapshots_config=snapshots_config,
                    )
            else:
                snap_name = opts["name"]
                if ensure == "absent":
                    ret = states["incus.instance_snapshot_absent"](snap_name, instance=instance)
                elif ensure == "restored":
                    ret = states["incus.instance_snapshot_restored"](snap_name, instance=instance)
                else:
                    ret = states["incus.instance_snapshot_present"](
                        snap_name,
                        instance=instance,
                        stateful=opts.get("stateful", False),
                        description=opts.get("description", ""),
                    )

            assert (
                ret.result is True
            ), f"Snapshot state failed for snap_id='{snap_id}': {ret.comment}"

        expected = case.get("expected", {})
        if "local_shell" in expected:
            check_local_shell(expected["local_shell"])

    finally:
        run_cleanup(case.get("cleanup", []))
