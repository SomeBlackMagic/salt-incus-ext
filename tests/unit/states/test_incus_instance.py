from unittest.mock import Mock

import pytest

from incus.states import incus_instance_mod


@pytest.fixture
def state_runtime(monkeypatch):
    function_names = [
        "incus.instance_list",
        "incus.instance_get",
        "incus.instance_update",
        "incus.instance_create",
        "incus.instance_delete",
        "incus.instance_start",
        "incus.instance_wait_ready",
        "incus.instance_stop",
        "incus.instance_check_cloudinit_enabled",
        "incus.instance_wait_cloudinit",
    ]
    salt_funcs = {name: Mock() for name in function_names}
    opts = {"test": False}
    monkeypatch.setattr(incus_instance_mod, "__salt__", salt_funcs, raising=False)
    monkeypatch.setattr(incus_instance_mod, "__opts__", opts, raising=False)
    return salt_funcs, opts


def _existing_instance(salt_funcs, status="Stopped", **extra):
    instance = {"status": status, **extra}
    salt_funcs["incus.instance_get"].return_value = {
        "success": True,
        "instance": instance,
    }
    return instance


def test_virtual_loads_only_with_instance_execution_functions(monkeypatch):
    monkeypatch.setattr(
        incus_instance_mod,
        "__salt__",
        {"incus.instance_list": Mock()},
        raising=False,
    )
    assert incus_instance_mod.__virtual__() == "incus"

    monkeypatch.setattr(incus_instance_mod, "__salt__", {}, raising=False)
    assert incus_instance_mod.__virtual__() == (
        False,
        "incus execution module is not available",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "true"), (False, "false"), (2, "2"), (None, "None")],
)
def test_normalize_config_value(value, expected):
    assert incus_instance_mod._normalize_config_value(value) == expected


def test_instance_present_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    _existing_instance(
        salt_funcs,
        config={"security.nesting": "true"},
        profiles=["default", "extra"],
        devices={"eth0": {"type": "nic", "mtu": "1500"}},
    )

    result = incus_instance_mod.instance_present(
        "vm1",
        config={"security.nesting": True},
        profiles=["extra", "default"],
        devices={"eth0": {"type": "nic", "mtu": 1500}},
    )

    assert result == {
        "name": "vm1",
        "result": True,
        "changes": {},
        "comment": "Instance vm1 already in desired state",
    }
    salt_funcs["incus.instance_update"].assert_not_called()


def test_instance_present_updates_config_profiles_and_devices(state_runtime):
    salt_funcs, _ = state_runtime
    _existing_instance(
        salt_funcs,
        config={"limits.cpu": "1"},
        profiles=["default"],
        devices={"root": {"type": "disk", "pool": "old"}},
    )
    salt_funcs["incus.instance_update"].return_value = {"success": True}
    config = {"limits.cpu": 2}
    profiles = ["default", "gpu"]
    devices = {
        "root": {"type": "disk", "pool": "new"},
        "eth0": {"type": "nic"},
    }

    result = incus_instance_mod.instance_present(
        "vm1",
        config=config,
        profiles=profiles,
        devices=devices,
    )

    assert result["result"] is True
    assert result["comment"] == "Instance vm1 updated"
    assert result["changes"] == {
        "config": {"limits.cpu": {"old": "1", "new": "2"}},
        "profiles": {"old": ["default"], "new": profiles},
        "devices": {
            "root": {"pool": {"old": "old", "new": "new"}},
            "eth0": {"old": None, "new": {"type": "nic"}},
        },
    }
    salt_funcs["incus.instance_update"].assert_called_once_with(
        "vm1",
        config=config,
        devices=devices,
        profiles=profiles,
    )


@pytest.mark.parametrize(
    ("test_mode", "update_result", "expected_result", "expected_comment"),
    [
        (True, None, None, "Instance vm1 would be updated"),
        (
            False,
            {"success": False, "error": "update failed"},
            False,
            "Failed to update instance vm1: update failed",
        ),
    ],
)
def test_instance_present_update_dry_run_and_error(
    state_runtime,
    test_mode,
    update_result,
    expected_result,
    expected_comment,
):
    salt_funcs, opts = state_runtime
    opts["test"] = test_mode
    _existing_instance(salt_funcs, config={"limits.cpu": "1"})
    if update_result is not None:
        salt_funcs["incus.instance_update"].return_value = update_result

    result = incus_instance_mod.instance_present("vm1", config={"limits.cpu": "2"})

    assert result["result"] is expected_result
    assert result["comment"] == expected_comment
    if test_mode:
        salt_funcs["incus.instance_update"].assert_not_called()


def test_instance_present_test_mode_reports_creation(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    salt_funcs["incus.instance_get"].return_value = {"success": False}
    source = {"type": "image", "alias": "ubuntu/24.04"}

    result = incus_instance_mod.instance_present(
        "vm1",
        source=source,
        instance_type="virtual-machine",
        config={"limits.cpu": "2"},
        devices={"root": {"type": "disk"}},
        profiles=["default"],
        ephemeral=True,
    )

    assert result["result"] is None
    assert result["comment"] == "Instance vm1 would be created"
    assert result["changes"]["instance"]["new"] == {
        "name": "vm1",
        "type": "virtual-machine",
        "config": {"limits.cpu": "2"},
        "devices": {"root": {"type": "disk"}},
        "profiles": ["default"],
        "ephemeral": True,
        "source": source,
    }
    salt_funcs["incus.instance_create"].assert_not_called()


@pytest.mark.parametrize(
    ("create_result", "expected_result", "expected_comment"),
    [
        ({"success": True}, True, "Instance vm1 created"),
        (
            {"success": False, "error": "create failed"},
            False,
            "Failed to create instance vm1: create failed",
        ),
    ],
)
def test_instance_present_creation_result(
    state_runtime,
    create_result,
    expected_result,
    expected_comment,
):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.instance_get"].return_value = {"success": False}
    salt_funcs["incus.instance_create"].return_value = create_result

    result = incus_instance_mod.instance_present("vm1", source={"type": "none"})

    assert result["result"] is expected_result
    assert result["comment"] == expected_comment
    salt_funcs["incus.instance_create"].assert_called_once_with(
        "vm1",
        source={"type": "none"},
        instance_type="container",
        config=None,
        devices=None,
        profiles=None,
        ephemeral=False,
    )


@pytest.mark.parametrize(
    ("exists", "test_mode", "delete_result", "expected_result", "comment"),
    [
        (False, False, None, True, "Instance vm1 already absent"),
        (True, True, None, None, "Instance vm1 would be deleted"),
        (True, False, {"success": True}, True, "Instance vm1 deleted"),
        (
            True,
            False,
            {"success": False, "error": "busy"},
            False,
            "Failed to delete instance vm1: busy",
        ),
    ],
)
def test_instance_absent(
    state_runtime,
    exists,
    test_mode,
    delete_result,
    expected_result,
    comment,
):
    salt_funcs, opts = state_runtime
    opts["test"] = test_mode
    salt_funcs["incus.instance_get"].return_value = {"success": exists}
    if delete_result is not None:
        salt_funcs["incus.instance_delete"].return_value = delete_result

    result = incus_instance_mod.instance_absent("vm1", force=True)

    assert result["result"] is expected_result
    assert result["comment"] == comment
    if delete_result is not None:
        salt_funcs["incus.instance_delete"].assert_called_once_with("vm1", force=True)
    else:
        salt_funcs["incus.instance_delete"].assert_not_called()


def test_instance_running_requires_existing_instance(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.instance_get"].return_value = {"success": False}

    result = incus_instance_mod.instance_running("vm1")

    assert result["result"] is False
    assert result["comment"] == "Instance vm1 does not exist"


@pytest.mark.parametrize(
    ("wait_result", "expected_result", "expected_comment"),
    [
        (None, True, "Instance vm1 is already running"),
        (
            {"success": True, "elapsed_time": 1.25},
            True,
            "Instance vm1 is running and ready (waited 1.2s)",
        ),
        (
            {"success": False, "error": "agent missing"},
            False,
            "Instance vm1 is running but agent is not ready: agent missing",
        ),
    ],
)
def test_instance_running_when_already_running(
    state_runtime,
    wait_result,
    expected_result,
    expected_comment,
):
    salt_funcs, _ = state_runtime
    _existing_instance(salt_funcs, status="Running")
    if wait_result is not None:
        salt_funcs["incus.instance_wait_ready"].return_value = wait_result

    result = incus_instance_mod.instance_running(
        "vm1",
        wait_is_ready=wait_result is not None,
        ready_timeout=42,
    )

    assert result["result"] is expected_result
    assert result["comment"] == expected_comment
    if wait_result is not None:
        salt_funcs["incus.instance_wait_ready"].assert_called_once_with("vm1", timeout=42)


def test_instance_running_test_mode_reports_start_and_wait(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _existing_instance(salt_funcs, status="Stopped")

    result = incus_instance_mod.instance_running("vm1", wait_is_ready=True)

    assert result == {
        "name": "vm1",
        "result": None,
        "changes": {"state": {"old": "Stopped", "new": "Running"}},
        "comment": "Instance vm1 would be started and wait for agent to be ready",
    }
    salt_funcs["incus.instance_start"].assert_not_called()


@pytest.mark.parametrize(
    ("start_result", "wait_result", "expected_result", "expected_comment"),
    [
        (
            {"success": False, "error": "start failed"},
            None,
            False,
            "Failed to start instance vm1: start failed",
        ),
        ({"success": True}, None, True, "Instance vm1 started"),
        (
            {"success": True},
            {"success": True, "elapsed_time": 2},
            True,
            "Instance vm1 started and ready (waited 2.0s)",
        ),
        (
            {"success": True},
            {"success": False, "error": "not ready"},
            False,
            "Instance vm1 started but agent is not ready: not ready",
        ),
    ],
)
def test_instance_running_start_results(
    state_runtime,
    start_result,
    wait_result,
    expected_result,
    expected_comment,
):
    salt_funcs, _ = state_runtime
    _existing_instance(salt_funcs, status="Stopped")
    salt_funcs["incus.instance_start"].return_value = start_result
    if wait_result is not None:
        salt_funcs["incus.instance_wait_ready"].return_value = wait_result

    result = incus_instance_mod.instance_running(
        "vm1",
        wait_is_ready=wait_result is not None,
        ready_timeout=90,
    )

    assert result["result"] is expected_result
    assert result["comment"] == expected_comment
    salt_funcs["incus.instance_start"].assert_called_once_with("vm1")


@pytest.mark.parametrize(
    ("exists", "status", "test_mode", "stop_result", "expected_result", "comment"),
    [
        (False, None, False, None, False, "Instance vm1 does not exist"),
        (True, "Stopped", False, None, True, "Instance vm1 is already stopped"),
        (True, "Running", True, None, None, "Instance vm1 would be stopped"),
        (True, "Running", False, {"success": True}, True, "Instance vm1 stopped"),
        (
            True,
            "Running",
            False,
            {"success": False, "error": "stop failed"},
            False,
            "Failed to stop instance vm1: stop failed",
        ),
    ],
)
def test_instance_stopped(
    state_runtime,
    exists,
    status,
    test_mode,
    stop_result,
    expected_result,
    comment,
):
    salt_funcs, opts = state_runtime
    opts["test"] = test_mode
    if exists:
        _existing_instance(salt_funcs, status=status)
    else:
        salt_funcs["incus.instance_get"].return_value = {"success": False}
    if stop_result is not None:
        salt_funcs["incus.instance_stop"].return_value = stop_result

    result = incus_instance_mod.instance_stopped("vm1", force=True)

    assert result["result"] is expected_result
    assert result["comment"] == comment
    if stop_result is not None:
        salt_funcs["incus.instance_stop"].assert_called_once_with("vm1", force=True)


@pytest.mark.parametrize(
    ("instance_result", "test_mode", "expected_result", "comment"),
    [
        ({"success": False}, False, False, "Instance vm1 does not exist"),
        (
            {"success": True, "instance": {"status": "Stopped"}},
            False,
            False,
            "Instance vm1 is not running (status: Stopped). Cannot check cloud-init status.",
        ),
        (
            {"success": True, "instance": {"status": "Running"}},
            True,
            None,
            "Would check if cloud-init is enabled on instance vm1",
        ),
    ],
)
def test_instance_initialized_preconditions(
    state_runtime,
    instance_result,
    test_mode,
    expected_result,
    comment,
):
    salt_funcs, opts = state_runtime
    opts["test"] = test_mode
    salt_funcs["incus.instance_get"].return_value = instance_result

    result = incus_instance_mod.instance_initialized("vm1")

    assert result["result"] is expected_result
    assert result["comment"] == comment
    salt_funcs["incus.instance_check_cloudinit_enabled"].assert_not_called()


@pytest.mark.parametrize(
    ("check_result", "expected_result", "comment"),
    [
        (
            {"success": False, "error": "exec failed"},
            False,
            "Failed to check cloud-init status on vm1: exec failed",
        ),
        (
            {"success": True, "enabled": False},
            True,
            "Instance vm1 does not have cloud-init installed. Skipping initialization check.",
        ),
    ],
)
def test_instance_initialized_cloudinit_check(
    state_runtime,
    check_result,
    expected_result,
    comment,
):
    salt_funcs, _ = state_runtime
    _existing_instance(salt_funcs, status="Running")
    salt_funcs["incus.instance_check_cloudinit_enabled"].return_value = check_result

    result = incus_instance_mod.instance_initialized("vm1")

    assert result["result"] is expected_result
    assert result["comment"] == comment
    salt_funcs["incus.instance_wait_cloudinit"].assert_not_called()


@pytest.mark.parametrize(
    ("wait_result", "expected_result", "comment", "expected_changes"),
    [
        (
            {
                "success": False,
                "status": "error",
                "error": "module failed",
                "details": {"stage": "final"},
            },
            False,
            "cloud-init on instance vm1 completed with errors: module failed",
            {"cloud-init": {"status": "error", "details": {"stage": "final"}}},
        ),
        (
            {"success": False, "status": "timeout", "error": "too slow"},
            False,
            "Timeout waiting for cloud-init on instance vm1: too slow",
            {},
        ),
        (
            {"success": False, "status": "unknown", "error": "broken"},
            False,
            "Failed to wait for cloud-init on instance vm1: broken",
            {},
        ),
        (
            {"success": True, "status": "done", "elapsed_time": 3.25},
            True,
            "cloud-init completed successfully on instance vm1 (waited 3.2s)",
            {"cloud-init": {"status": "done", "elapsed_time": "3.2s"}},
        ),
        (
            {"success": True, "status": "already_completed"},
            True,
            "cloud-init was already completed on instance vm1",
            {},
        ),
        (
            {"success": True, "status": "disabled"},
            True,
            "cloud-init is disabled on instance vm1",
            {},
        ),
        (
            {"success": True, "status": "running"},
            True,
            "cloud-init status on instance vm1: running",
            {},
        ),
    ],
)
def test_instance_initialized_wait_results(
    state_runtime,
    wait_result,
    expected_result,
    comment,
    expected_changes,
):
    salt_funcs, _ = state_runtime
    _existing_instance(salt_funcs, status="Running")
    salt_funcs["incus.instance_check_cloudinit_enabled"].return_value = {
        "success": True,
        "enabled": True,
    }
    salt_funcs["incus.instance_wait_cloudinit"].return_value = wait_result

    result = incus_instance_mod.instance_initialized("vm1", timeout=900, check_interval=10)

    assert result["result"] is expected_result
    assert result["comment"] == comment
    assert result["changes"] == expected_changes
    salt_funcs["incus.instance_wait_cloudinit"].assert_called_once_with(
        "vm1", timeout=900, interval=10
    )
