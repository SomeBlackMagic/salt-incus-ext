from unittest.mock import Mock
from unittest.mock import call

import pytest

from incus.modules import incus_instance_mod


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    monkeypatch.setattr(incus_instance_mod, "_client", Mock(return_value=client))
    return client


def test_client_creates_incus_client(monkeypatch):
    from incus.modules import incus_mod

    mock_client = Mock()
    monkeypatch.setattr(incus_instance_mod, "__salt__", {}, raising=False)
    monkeypatch.setattr(incus_mod, "IncusClient", Mock(return_value=mock_client))

    assert incus_instance_mod._client() is mock_client


def test_instance_list_and_get_quote_names(client):
    client._request.side_effect = [
        {"error_code": 0, "metadata": ["/instances/vm one"]},
        {"error_code": 0, "metadata": {"name": "vm one"}},
    ]

    assert incus_instance_mod.instance_list(recursion=2) == {
        "success": True,
        "instances": ["/instances/vm one"],
    }
    assert incus_instance_mod.instance_get("vm one") == {
        "success": True,
        "instance": {"name": "vm one"},
    }
    assert client._request.call_args_list == [
        call("GET", "/instances", params={"recursion": 2}),
        call("GET", "/instances/vm%20one"),
    ]


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (incus_instance_mod.instance_list, ()),
        (incus_instance_mod.instance_get, ("vm",)),
        (incus_instance_mod.instance_create, ("vm",)),
        (incus_instance_mod.instance_start, ("vm",)),
        (incus_instance_mod.instance_stop, ("vm",)),
        (incus_instance_mod.instance_restart, ("vm",)),
        (incus_instance_mod.instance_snapshot_list, ("vm",)),
        (incus_instance_mod.instance_snapshot_get, ("vm", "snap")),
        (incus_instance_mod.instance_snapshot_create, ("vm", "snap")),
        (incus_instance_mod.instance_snapshot_rename, ("vm", "snap", "new")),
        (incus_instance_mod.instance_snapshot_restore, ("vm", "snap")),
        (incus_instance_mod.instance_snapshot_delete, ("vm", "snap")),
        (incus_instance_mod.instance_snapshot_publish, ("vm", "snap")),
    ],
)
def test_api_functions_return_errors(client, function, args):
    client._request.return_value = {"error_code": 1, "error": "boom"}
    client._sync_request.return_value = {"error_code": 1, "error": "boom"}

    assert function(*args) == {"success": False, "error": "boom"}


def test_instance_create_builds_complete_request(client):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_instance_mod.instance_create(
        "vm one",
        source={"type": "image", "alias": "ubuntu"},
        instance_type="virtual-machine",
        config={"limits.cpu": "2"},
        devices={"root": {"type": "disk", "path": "/"}},
        profiles=["default"],
        ephemeral=True,
    )

    assert result == {"success": True, "message": "Instance vm one created successfully"}
    client._sync_request.assert_called_once_with(
        "POST",
        "/instances",
        data={
            "name": "vm one",
            "type": "virtual-machine",
            "ephemeral": True,
            "source": {"type": "image", "alias": "ubuntu"},
            "config": {"limits.cpu": "2"},
            "devices": {"root": {"type": "disk", "path": "/"}},
            "profiles": ["default"],
        },
    )


def test_instance_create_omits_optional_empty_values(client):
    client._sync_request.return_value = {"error_code": 0}

    incus_instance_mod.instance_create("container")

    client._sync_request.assert_called_once_with(
        "POST",
        "/instances",
        data={"name": "container", "type": "container", "ephemeral": False},
    )


def test_instance_delete_force_stops_running_instance(client, monkeypatch):
    client._sync_request.return_value = {"error_code": 0}
    get = Mock(return_value={"success": True, "instance": {"status": "Running"}})
    stop = Mock()
    monkeypatch.setattr(incus_instance_mod, "instance_get", get)
    monkeypatch.setattr(incus_instance_mod, "instance_stop", stop)

    result = incus_instance_mod.instance_delete("vm one", force=True)

    assert result == {"success": True, "message": "Instance vm one deleted successfully"}
    get.assert_called_once_with("vm one")
    stop.assert_called_once_with("vm one", force=True)
    client._sync_request.assert_called_once_with("DELETE", "/instances/vm%20one")


def test_instance_delete_without_force_does_not_inspect_instance(client, monkeypatch):
    client._sync_request.return_value = {"error_code": 0}
    get = Mock()
    monkeypatch.setattr(incus_instance_mod, "instance_get", get)

    incus_instance_mod.instance_delete("vm")

    get.assert_not_called()


def test_instance_update_merges_config_and_device_properties(client, monkeypatch):
    current = {
        "name": "vm",
        "config": {"limits.cpu": "1", "limits.memory": "1GiB"},
        "devices": {"root": {"type": "disk", "path": "/", "pool": "old"}},
        "profiles": ["default"],
    }
    monkeypatch.setattr(
        incus_instance_mod,
        "instance_get",
        Mock(return_value={"success": True, "instance": current}),
    )
    client._sync_request.return_value = {"error_code": 0}

    result = incus_instance_mod.instance_update(
        "vm",
        config={"limits.cpu": "4"},
        devices={
            "root": {"pool": "fast"},
            "eth0": {"type": "nic", "network": "default"},
        },
        profiles=[],
    )

    assert result == {"success": True, "message": "Instance vm updated successfully"}
    client._sync_request.assert_called_once_with(
        "PUT",
        "/instances/vm",
        data={
            "name": "vm",
            "config": {"limits.cpu": "4", "limits.memory": "1GiB"},
            "devices": {
                "root": {"type": "disk", "path": "/", "pool": "fast"},
                "eth0": {"type": "nic", "network": "default"},
            },
            "profiles": [],
        },
    )


def test_instance_update_returns_get_error_without_put(client, monkeypatch):
    error = {"success": False, "error": "missing"}
    monkeypatch.setattr(incus_instance_mod, "instance_get", Mock(return_value=error))

    assert incus_instance_mod.instance_update("missing") is error
    client._sync_request.assert_not_called()


@pytest.mark.parametrize(
    ("function", "kwargs", "action", "expected_data", "message"),
    [
        (
            incus_instance_mod.instance_start,
            {"force": True, "stateful": True},
            "start",
            {"action": "start", "force": True, "stateful": True},
            "started",
        ),
        (
            incus_instance_mod.instance_stop,
            {"force": True, "stateful": True, "timeout": 12},
            "stop",
            {"action": "stop", "force": True, "stateful": True, "timeout": 12},
            "stopped",
        ),
        (
            incus_instance_mod.instance_restart,
            {"force": True, "timeout": 12},
            "restart",
            {"action": "restart", "force": True, "timeout": 12},
            "restarted",
        ),
    ],
)
def test_instance_state_actions(client, function, kwargs, action, expected_data, message):
    client._sync_request.return_value = {"error_code": 0}

    assert function("vm one", **kwargs) == {
        "success": True,
        "message": f"Instance vm one {message} successfully",
    }
    client._sync_request.assert_called_once_with(
        "PUT", "/instances/vm%20one/state", data=expected_data
    )


def test_instance_wait_ready_retries_until_exec_succeeds(client, monkeypatch):
    client._sync_request.side_effect = [
        {"error_code": 1, "error": "agent unavailable"},
        {"error_code": 0},
    ]
    time_mock = Mock()
    time_mock.time.side_effect = [0, 0, 1, 2]
    sleep = Mock()
    time_mock.sleep = sleep
    monkeypatch.setattr(incus_instance_mod, "time", time_mock)

    result = incus_instance_mod.instance_wait_ready("vm one", timeout=10, interval=3)

    assert result == {
        "success": True,
        "message": "Instance vm one is ready",
        "elapsed_time": 2,
    }
    request = call(
        "POST",
        "/instances/vm%20one/exec",
        data={
            "command": ["/bin/true"],
            "wait-for-websocket": False,
            "interactive": False,
        },
    )
    assert client._sync_request.call_args_list == [request, request]
    sleep.assert_called_once_with(3)


def test_instance_wait_ready_reports_timeout_without_request(client, monkeypatch):
    time_mock = Mock()
    time_mock.time.side_effect = [0, 5, 5]
    monkeypatch.setattr(incus_instance_mod, "time", time_mock)
    monkeypatch.setattr(incus_instance_mod.log, "warning", Mock())

    assert incus_instance_mod.instance_wait_ready("vm", timeout=5) == {
        "success": False,
        "error": "Timeout waiting for instance to become ready after 5.0s",
    }
    client._sync_request.assert_not_called()


def test_snapshot_queries_quote_instance_and_snapshot_names(client):
    client._request.side_effect = [
        {"error_code": 0, "metadata": ["snap one"]},
        {"error_code": 0, "metadata": {"name": "snap one"}},
    ]

    assert incus_instance_mod.instance_snapshot_list("vm one", recursion=1) == {
        "success": True,
        "snapshots": ["snap one"],
    }
    assert incus_instance_mod.instance_snapshot_get("vm one", "snap one") == {
        "success": True,
        "snapshot": {"name": "snap one"},
    }
    assert client._request.call_args_list == [
        call("GET", "/instances/vm%20one/snapshots", params={"recursion": 1}),
        call("GET", "/instances/vm%20one/snapshots/snap%20one"),
    ]


def test_snapshot_mutations_build_expected_requests(client):
    client._sync_request.return_value = {"error_code": 0}

    assert incus_instance_mod.instance_snapshot_create(
        "vm", "snap", stateful=True, description="before upgrade"
    )["success"]
    assert incus_instance_mod.instance_snapshot_rename("vm", "snap", "new")["success"]
    assert incus_instance_mod.instance_snapshot_restore("vm", "new", stateful=False)["success"]
    assert incus_instance_mod.instance_snapshot_delete("vm", "new")["success"]
    assert client._sync_request.call_args_list == [
        call(
            "POST",
            "/instances/vm/snapshots",
            data={"name": "snap", "stateful": True, "description": "before upgrade"},
        ),
        call("POST", "/instances/vm/snapshots/snap", data={"name": "new"}),
        call("PUT", "/instances/vm", data={"restore": "new", "stateful": False}),
        call("DELETE", "/instances/vm/snapshots/new"),
    ]


def test_snapshot_update_preserves_metadata_and_updates_requested_fields(client):
    client._request.return_value = {
        "error_code": 0,
        "metadata": {"description": "old", "expires_at": None, "stateful": False},
    }
    client._sync_request.return_value = {"error_code": 0}

    result = incus_instance_mod.instance_snapshot_update(
        "vm one", "snap one", description="", expires_at="2030-01-01T00:00:00Z"
    )

    assert result == {"success": True, "message": "Snapshot snap one updated successfully"}
    client._sync_request.assert_called_once_with(
        "PUT",
        "/instances/vm%20one/snapshots/snap%20one",
        data={
            "description": "",
            "expires_at": "2030-01-01T00:00:00Z",
            "stateful": False,
        },
    )


def test_snapshot_update_returns_read_and_write_errors(client):
    client._request.return_value = {"error_code": 1}
    assert incus_instance_mod.instance_snapshot_update("vm", "snap") == {
        "success": False,
        "error": "Failed to get snapshot",
    }

    client._request.return_value = {"error_code": 0, "metadata": {}}
    client._sync_request.return_value = {"error_code": 1, "error": "read-only"}
    assert incus_instance_mod.instance_snapshot_update("vm", "snap") == {
        "success": False,
        "error": "read-only",
    }


def test_snapshot_publish_normalizes_aliases_and_returns_fingerprint(client):
    client._sync_request.return_value = {
        "error_code": 0,
        "metadata": {"fingerprint": "abc123"},
    }

    result = incus_instance_mod.instance_snapshot_publish(
        "vm",
        "snap",
        properties={"os": "ubuntu"},
        public=True,
        aliases=["stable", {"name": "latest", "description": "Latest"}],
    )

    assert result == {
        "success": True,
        "message": "Snapshot snap published as image successfully",
        "fingerprint": "abc123",
    }
    client._sync_request.assert_called_once_with(
        "POST",
        "/images",
        data={
            "public": True,
            "source": {"type": "snapshot", "name": "vm/snap"},
            "properties": {"os": "ubuntu"},
            "aliases": [
                {"name": "stable"},
                {"name": "latest", "description": "Latest"},
            ],
        },
    )


@pytest.mark.parametrize(
    ("response", "enabled"),
    [({"error_code": 0}, True), ({"error_code": 1}, False)],
)
def test_check_cloudinit_enabled(client, response, enabled):
    client._sync_request.return_value = response

    result = incus_instance_mod.instance_check_cloudinit_enabled("vm one")

    assert result["success"] is True
    assert result["enabled"] is enabled
    client._sync_request.assert_called_once_with(
        "POST",
        "/instances/vm%20one/exec",
        data={
            "command": ["cloud-init", "--version"],
            "wait-for-websocket": False,
            "interactive": False,
            "environment": {},
        },
    )


def test_check_cloudinit_enabled_reports_request_exception(client):
    client._sync_request.side_effect = RuntimeError("connection lost")

    assert incus_instance_mod.instance_check_cloudinit_enabled("vm") == {
        "success": False,
        "error": "Failed to check cloud-init status: connection lost",
    }


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"error_code": 0, "metadata": {"metadata": {"return": 0}}}, (True, None)),
        ({"error_code": 0, "metadata": {"metadata": {"return": 1}}}, (False, None)),
        (
            {"error_code": 1, "error": "not running"},
            (False, "Failed to check cloud-init marker: not running"),
        ),
    ],
)
def test_check_cloudinit_boot_finished(client, response, expected):
    client._sync_request.return_value = response

    assert incus_instance_mod._check_cloudinit_boot_finished(client, "vm one") == expected
    client._sync_request.assert_called_once_with(
        "POST",
        "/instances/vm%20one/exec",
        data={
            "command": ["test", "-f", "/var/lib/cloud/instance/boot-finished"],
            "wait-for-websocket": False,
            "interactive": False,
            "environment": {},
        },
    )


def test_get_cloudinit_status_maps_helper_result(client, monkeypatch):
    helper = Mock(side_effect=[(True, None), (False, None), (False, "agent unavailable")])
    monkeypatch.setattr(incus_instance_mod, "_check_cloudinit_boot_finished", helper)

    assert incus_instance_mod.instance_get_cloudinit_status("vm") == {
        "success": True,
        "completed": True,
        "status": "done",
    }
    assert incus_instance_mod.instance_get_cloudinit_status("vm") == {
        "success": True,
        "completed": False,
        "status": "running",
    }
    assert incus_instance_mod.instance_get_cloudinit_status("vm") == {
        "success": False,
        "error": "agent unavailable",
    }


def test_wait_cloudinit_returns_immediately_if_already_completed(client, monkeypatch):
    helper = Mock(return_value=(True, None))
    monkeypatch.setattr(incus_instance_mod, "_check_cloudinit_boot_finished", helper)

    assert incus_instance_mod.instance_wait_cloudinit("vm") == {
        "success": True,
        "status": "already_completed",
        "message": "cloud-init was already completed on vm",
        "elapsed_time": 0,
    }
    helper.assert_called_once_with(client, "vm")


def test_wait_cloudinit_retries_errors_then_completes(client, monkeypatch):
    helper = Mock(side_effect=[(False, None), (False, "agent unavailable"), (True, None)])
    monkeypatch.setattr(incus_instance_mod, "_check_cloudinit_boot_finished", helper)
    time_mock = Mock()
    time_mock.time.side_effect = [0, 0, 1, 2]
    sleep = Mock()
    time_mock.sleep = sleep
    monkeypatch.setattr(incus_instance_mod, "time", time_mock)

    assert incus_instance_mod.instance_wait_cloudinit("vm", timeout=10, interval=3) == {
        "success": True,
        "status": "done",
        "message": "cloud-init completed on vm",
        "elapsed_time": 2,
    }
    sleep.assert_called_once_with(3)


def test_wait_cloudinit_reports_timeout(client, monkeypatch):
    helper = Mock(return_value=(False, None))
    monkeypatch.setattr(incus_instance_mod, "_check_cloudinit_boot_finished", helper)
    time_mock = Mock()
    time_mock.time.side_effect = [0, 5, 5]
    monkeypatch.setattr(incus_instance_mod, "time", time_mock)
    monkeypatch.setattr(incus_instance_mod.log, "warning", Mock())

    assert incus_instance_mod.instance_wait_cloudinit("vm", timeout=5) == {
        "success": False,
        "status": "timeout",
        "error": "Timeout waiting for cloud-init to complete after 5.0s",
    }
