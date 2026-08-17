from unittest.mock import Mock

import pytest

from incus.states import incus_instance_snapshot_mod


@pytest.fixture
def state_runtime(monkeypatch):
    function_names = [
        "incus.instance_get",
        "incus.instance_snapshot_list",
        "incus.instance_snapshot_create",
        "incus.instance_snapshot_delete",
        "incus.instance_snapshot_restore",
        "incus.instance_snapshot_update",
    ]
    salt_funcs = {name: Mock() for name in function_names}
    opts = {"test": False}
    monkeypatch.setattr(incus_instance_snapshot_mod, "__salt__", salt_funcs, raising=False)
    monkeypatch.setattr(incus_instance_snapshot_mod, "__opts__", opts, raising=False)
    return salt_funcs, opts


def _existing_instance(salt_funcs, status="Stopped", **extra):
    instance = {"status": status, **extra}
    salt_funcs["incus.instance_get"].return_value = {
        "success": True,
        "instance": instance,
    }
    return instance


def _snapshots(salt_funcs, *snapshots):
    salt_funcs["incus.instance_snapshot_list"].return_value = {
        "success": True,
        "snapshots": list(snapshots),
    }


def test_virtual_loads_only_with_snapshot_execution_functions(monkeypatch):
    monkeypatch.setattr(
        incus_instance_snapshot_mod,
        "__salt__",
        {"incus.instance_snapshot_list": Mock()},
        raising=False,
    )
    assert incus_instance_snapshot_mod.__virtual__() == "incus"

    monkeypatch.setattr(incus_instance_snapshot_mod, "__salt__", {}, raising=False)
    assert incus_instance_snapshot_mod.__virtual__() == (
        False,
        "incus snapshot execution functions are not available",
    )


@pytest.mark.parametrize(
    "function",
    [
        incus_instance_snapshot_mod.instance_snapshot_present,
        incus_instance_snapshot_mod.instance_snapshot_absent,
        incus_instance_snapshot_mod.instance_snapshot_restored,
    ],
)
def test_snapshot_states_require_existing_instance(state_runtime, function):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.instance_get"].return_value = {"success": False}

    result = function("vm1", "snap1")

    assert result["result"] is False
    assert result["comment"] == "Instance vm1 does not exist"
    salt_funcs["incus.instance_snapshot_list"].assert_not_called()


@pytest.mark.parametrize(
    "function",
    [
        incus_instance_snapshot_mod.instance_snapshot_present,
        incus_instance_snapshot_mod.instance_snapshot_absent,
        incus_instance_snapshot_mod.instance_snapshot_restored,
    ],
)
def test_snapshot_states_report_list_errors(state_runtime, function):
    salt_funcs, _ = state_runtime
    _existing_instance(salt_funcs)
    salt_funcs["incus.instance_snapshot_list"].return_value = {
        "success": False,
        "error": "list failed",
    }

    result = function("vm1", "snap1")

    assert result["result"] is False
    assert result["comment"] == "Failed to list snapshots: list failed"
    salt_funcs["incus.instance_snapshot_list"].assert_called_once_with("vm1", recursion=1)


@pytest.mark.parametrize(
    ("exists", "test_mode", "create_result", "expected_result", "comment"),
    [
        (True, False, None, True, "Snapshot snap1 already exists for instance vm1"),
        (False, True, None, None, "Snapshot snap1 would be created for instance vm1"),
        (False, False, {"success": True}, True, "Snapshot snap1 created for instance vm1"),
        (
            False,
            False,
            {"success": False, "error": "create failed"},
            False,
            "Failed to create snapshot snap1: create failed",
        ),
    ],
)
def test_instance_snapshot_present(
    state_runtime,
    exists,
    test_mode,
    create_result,
    expected_result,
    comment,
):
    salt_funcs, opts = state_runtime
    opts["test"] = test_mode
    _existing_instance(salt_funcs)
    _snapshots(salt_funcs, *([{"name": "snap1"}] if exists else []))
    if create_result is not None:
        salt_funcs["incus.instance_snapshot_create"].return_value = create_result

    result = incus_instance_snapshot_mod.instance_snapshot_present(
        "vm1", "snap1", stateful=True, description="before update"
    )

    assert result["result"] is expected_result
    assert result["comment"] == comment
    if create_result is not None:
        salt_funcs["incus.instance_snapshot_create"].assert_called_once_with(
            "vm1", "snap1", stateful=True, description="before update"
        )


@pytest.mark.parametrize(
    ("exists", "test_mode", "delete_result", "expected_result", "comment"),
    [
        (False, False, None, True, "Snapshot snap1 already absent from instance vm1"),
        (True, True, None, None, "Snapshot snap1 would be deleted from instance vm1"),
        (True, False, {"success": True}, True, "Snapshot snap1 deleted from instance vm1"),
        (
            True,
            False,
            {"success": False, "error": "delete failed"},
            False,
            "Failed to delete snapshot snap1: delete failed",
        ),
    ],
)
def test_instance_snapshot_absent(
    state_runtime,
    exists,
    test_mode,
    delete_result,
    expected_result,
    comment,
):
    salt_funcs, opts = state_runtime
    opts["test"] = test_mode
    _existing_instance(salt_funcs)
    _snapshots(salt_funcs, *([{"name": "snap1"}] if exists else []))
    if delete_result is not None:
        salt_funcs["incus.instance_snapshot_delete"].return_value = delete_result

    result = incus_instance_snapshot_mod.instance_snapshot_absent("vm1", "snap1")

    assert result["result"] is expected_result
    assert result["comment"] == comment
    if delete_result is not None:
        salt_funcs["incus.instance_snapshot_delete"].assert_called_once_with("vm1", "snap1")


@pytest.mark.parametrize(
    ("exists", "test_mode", "restore_result", "expected_result", "comment"),
    [
        (False, False, None, False, "Snapshot snap1 does not exist for instance vm1"),
        (True, True, None, None, "Instance vm1 would be restored to snapshot snap1"),
        (True, False, {"success": True}, True, "Instance vm1 restored to snapshot snap1"),
        (
            True,
            False,
            {"success": False, "error": "restore failed"},
            False,
            "Failed to restore snapshot snap1: restore failed",
        ),
    ],
)
def test_instance_snapshot_restored(
    state_runtime,
    exists,
    test_mode,
    restore_result,
    expected_result,
    comment,
):
    salt_funcs, opts = state_runtime
    opts["test"] = test_mode
    _existing_instance(salt_funcs)
    _snapshots(salt_funcs, *([{"name": "snap1"}] if exists else []))
    if restore_result is not None:
        salt_funcs["incus.instance_snapshot_restore"].return_value = restore_result

    result = incus_instance_snapshot_mod.instance_snapshot_restored("vm1", "snap1")

    assert result["result"] is expected_result
    assert result["comment"] == comment
    if restore_result is not None:
        salt_funcs["incus.instance_snapshot_restore"].assert_called_once_with("vm1", "snap1")


def test_instance_snapshots_managed_validates_inputs(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.instance_get"].return_value = {"success": False}
    result = incus_instance_snapshot_mod.instance_snapshots_managed("vm1", {})
    assert result["comment"] == "Instance vm1 does not exist"

    _existing_instance(salt_funcs)
    salt_funcs["incus.instance_snapshot_list"].return_value = {
        "success": False,
        "error": "list failed",
    }
    result = incus_instance_snapshot_mod.instance_snapshots_managed("vm1", {})
    assert result["comment"] == "Failed to list snapshots: list failed"

    _snapshots(salt_funcs)
    result = incus_instance_snapshot_mod.instance_snapshots_managed("vm1", {"daily": {}})
    assert result["result"] is False
    assert result["comment"] == "Snapshot configuration 'daily' missing 'name' field"


def test_instance_snapshots_managed_test_mode_creates_and_rotates(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _existing_instance(salt_funcs)
    _snapshots(
        salt_funcs,
        {"name": "daily-1", "created_at": "2024-01-01"},
        {"name": "daily-2", "created_at": "2024-01-02"},
    )

    result = incus_instance_snapshot_mod.instance_snapshots_managed(
        "vm1",
        {
            "daily": {
                "name": "daily-3",
                "pattern": "daily-*",
                "keep": 1,
            }
        },
    )

    assert result == {
        "name": "vm1_snapshots",
        "result": None,
        "changes": {
            "created": {"old": None, "new": ["daily-3"]},
            "rotated": {"old": ["daily-1"], "new": None},
        },
        "comment": "Instance vm1 snapshots would be managed",
    }
    salt_funcs["incus.instance_snapshot_create"].assert_not_called()
    salt_funcs["incus.instance_snapshot_delete"].assert_not_called()


def test_instance_snapshots_managed_creates_updates_expiry_and_rotates(
    state_runtime,
    monkeypatch,
):
    salt_funcs, _ = state_runtime
    _existing_instance(salt_funcs)
    _snapshots(
        salt_funcs,
        {"name": "daily-1", "created_at": "2024-01-01"},
        {"name": "daily-2", "created_at": "2024-01-02"},
    )
    salt_funcs["incus.instance_snapshot_create"].return_value = {"success": True}
    salt_funcs["incus.instance_snapshot_update"].return_value = {
        "success": False,
        "error": "expiry failed",
    }
    salt_funcs["incus.instance_snapshot_delete"].side_effect = [
        {"success": True},
        {"success": False, "error": "delete failed"},
    ]
    warning = Mock()
    monkeypatch.setattr(incus_instance_snapshot_mod.log, "warning", warning)

    result = incus_instance_snapshot_mod.instance_snapshots_managed(
        "vm1",
        {
            "daily": {
                "name": "daily-3",
                "stateful": True,
                "description": "daily",
                "expires_at": "2030-01-01T00:00:00Z",
                "pattern": "daily-*",
                "keep": 0,
            }
        },
    )

    assert result["result"] is True
    assert result["changes"] == {
        "created": {"old": None, "new": ["daily-3"]},
        "rotated": {"old": ["daily-1"], "new": None},
    }
    salt_funcs["incus.instance_snapshot_create"].assert_called_once_with(
        "vm1", "daily-3", stateful=True, description="daily"
    )
    salt_funcs["incus.instance_snapshot_update"].assert_called_once_with(
        "vm1", "daily-3", expires_at="2030-01-01T00:00:00Z"
    )
    assert warning.call_count == 2


def test_instance_snapshots_managed_reports_create_error(state_runtime):
    salt_funcs, _ = state_runtime
    _existing_instance(salt_funcs)
    _snapshots(salt_funcs)
    salt_funcs["incus.instance_snapshot_create"].return_value = {
        "success": False,
        "error": "create failed",
    }

    result = incus_instance_snapshot_mod.instance_snapshots_managed(
        "vm1", {"daily": {"name": "daily-1"}}
    )

    assert result["result"] is False
    assert result["comment"] == "Failed to create snapshot daily-1: create failed"


def test_instance_snapshots_managed_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    _existing_instance(salt_funcs)
    _snapshots(salt_funcs, {"name": "daily-1", "created_at": "2024-01-01"})

    result = incus_instance_snapshot_mod.instance_snapshots_managed(
        "vm1", {"daily": {"name": "daily-1", "pattern": "daily-*", "keep": 2}}
    )

    assert result["result"] is True
    assert not result["changes"]
    assert result["comment"] == "Instance vm1 snapshots already in desired state"


def test_instance_snapshots_rotated_validates_instance_and_list(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.instance_get"].return_value = {"success": False}
    result = incus_instance_snapshot_mod.instance_snapshots_rotated("vm1", "daily-*", 1)
    assert result["comment"] == "Instance vm1 does not exist"

    _existing_instance(salt_funcs)
    salt_funcs["incus.instance_snapshot_list"].return_value = {
        "success": False,
        "error": "list failed",
    }
    result = incus_instance_snapshot_mod.instance_snapshots_rotated("vm1", "daily-*", 1)
    assert result["comment"] == "Failed to list snapshots: list failed"


def test_instance_snapshots_rotated_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    _existing_instance(salt_funcs)
    _snapshots(
        salt_funcs,
        {"name": "daily-1", "created_at": "2024-01-01"},
        {"name": "weekly-1", "created_at": "2024-01-01"},
    )

    result = incus_instance_snapshot_mod.instance_snapshots_rotated("vm1", "daily-*", 1)

    assert result["result"] is True
    assert result["comment"] == "Snapshot rotation not needed: 1 snapshots (keeping 1)"


def test_instance_snapshots_rotated_test_mode_uses_oldest_first(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _existing_instance(salt_funcs)
    _snapshots(
        salt_funcs,
        {"name": "daily-2", "created_at": "2024-01-02"},
        {"name": "daily-1", "created_at": "2024-01-01"},
        {"name": "daily-3", "created_at": "2024-01-03"},
    )

    result = incus_instance_snapshot_mod.instance_snapshots_rotated("vm1", "daily-*", 1)

    assert result == {
        "name": "vm1_rotate_daily-*",
        "result": None,
        "changes": {"deleted": {"old": ["daily-1", "daily-2"], "new": None}},
        "comment": "Would delete 2 old snapshots matching pattern 'daily-*'",
    }


def test_instance_snapshots_rotated_reports_partial_failure(state_runtime):
    salt_funcs, _ = state_runtime
    _existing_instance(salt_funcs)
    _snapshots(
        salt_funcs,
        {"name": "daily-1", "created_at": "2024-01-01"},
        {"name": "daily-2", "created_at": "2024-01-02"},
        {"name": "daily-3", "created_at": "2024-01-03"},
    )
    salt_funcs["incus.instance_snapshot_delete"].side_effect = [
        {"success": True},
        {"success": False, "error": "busy"},
    ]

    result = incus_instance_snapshot_mod.instance_snapshots_rotated("vm1", "daily-*", 1)

    assert result["result"] is False
    assert result["changes"] == {"deleted": {"old": ["daily-1"], "new": None}}
    assert "daily-2" in result["comment"]
    assert "busy" in result["comment"]


def test_instance_snapshots_rotated_deletes_old_snapshots(state_runtime):
    salt_funcs, _ = state_runtime
    _existing_instance(salt_funcs)
    _snapshots(
        salt_funcs,
        {"name": "daily-1", "created_at": "2024-01-01"},
        {"name": "daily-2", "created_at": "2024-01-02"},
    )
    salt_funcs["incus.instance_snapshot_delete"].return_value = {"success": True}

    result = incus_instance_snapshot_mod.instance_snapshots_rotated("vm1", "daily-*", 1)

    assert result["result"] is True
    assert result["changes"] == {"deleted": {"old": ["daily-1"], "new": None}}
    assert result["comment"] == "Deleted 1 old snapshots matching pattern 'daily-*'"
