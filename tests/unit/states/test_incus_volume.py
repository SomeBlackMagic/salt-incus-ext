from unittest.mock import Mock

import pytest

from incus.states import incus_volume_mod


@pytest.fixture
def state_runtime(monkeypatch):
    salt_funcs = {
        "incus.volume_list": Mock(),
        "incus.volume_create": Mock(),
        "incus.volume_delete": Mock(),
        "incus.volume_get": Mock(),
        "incus.volume_update": Mock(),
        "incus.volume_snapshot_list": Mock(),
        "incus.volume_snapshot_create": Mock(),
        "incus.volume_snapshot_delete": Mock(),
        "incus.instance_get": Mock(),
        "incus.instance_update": Mock(),
    }
    opts = {"test": False}
    monkeypatch.setattr(incus_volume_mod, "__salt__", salt_funcs, raising=False)
    monkeypatch.setattr(incus_volume_mod, "__opts__", opts, raising=False)
    return salt_funcs, opts


def _volume_list(salt_funcs, volumes):
    salt_funcs["incus.volume_list"].return_value = {
        "success": True,
        "volumes": volumes,
    }


def _volume_info(salt_funcs, config=None, description=""):
    salt_funcs["incus.volume_get"].return_value = {
        "success": True,
        "volume": {"config": config or {}, "description": description},
    }


def _snapshot_list(salt_funcs, snapshots):
    salt_funcs["incus.volume_snapshot_list"].return_value = {
        "success": True,
        "snapshots": snapshots,
    }


def _instance_info(salt_funcs, devices):
    salt_funcs["incus.instance_get"].return_value = {
        "success": True,
        "instance": {"devices": devices},
    }


def test_virtual_loads_only_with_volume_execution_functions(monkeypatch):
    monkeypatch.setattr(
        incus_volume_mod,
        "__salt__",
        {"incus.volume_list": Mock()},
        raising=False,
    )
    assert incus_volume_mod.__virtual__() == "incus"

    monkeypatch.setattr(incus_volume_mod, "__salt__", {}, raising=False)
    assert incus_volume_mod.__virtual__() == (
        False,
        "incus volume execution functions are not available",
    )


def test_volume_present_reports_list_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.volume_list"].return_value = {
        "success": False,
        "error": "connection failed",
    }

    result = incus_volume_mod.volume_present("data", "default")

    assert result == {
        "name": "data",
        "result": False,
        "changes": {},
        "comment": "Failed to list volumes in pool default: connection failed",
    }


def test_volume_present_matches_name_and_type(state_runtime):
    salt_funcs, _ = state_runtime
    _volume_list(
        salt_funcs,
        [
            {"name": "data", "type": "image"},
            {"name": "data", "type": "custom"},
        ],
    )

    result = incus_volume_mod.volume_present("data", "default")

    assert result == {
        "name": "data",
        "result": True,
        "changes": {},
        "comment": "Volume data already exists in pool default",
    }
    salt_funcs["incus.volume_create"].assert_not_called()


def test_volume_present_test_mode_reports_creation(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _volume_list(salt_funcs, None)

    result = incus_volume_mod.volume_present("data", "default")

    assert result == {
        "name": "data",
        "result": None,
        "changes": {"volume": {"old": None, "new": "data"}},
        "comment": "Volume data would be created in pool default",
    }
    salt_funcs["incus.volume_create"].assert_not_called()


@pytest.mark.parametrize(
    ("create_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {"volume": {"old": None, "new": "data"}},
            "Volume data created in pool default",
        ),
        (
            {"success": False, "error": "create failed"},
            False,
            {},
            "Failed to create volume data: create failed",
        ),
    ],
)
def test_volume_present_creation_results(
    state_runtime,
    create_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _volume_list(salt_funcs, [])
    salt_funcs["incus.volume_create"].return_value = create_result
    config = {"size": "10GiB"}

    result = incus_volume_mod.volume_present(
        "data",
        "default",
        volume_type="custom",
        config=config,
        description="Data volume",
    )

    assert result == {
        "name": "data",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.volume_create"].assert_called_once_with(
        "default",
        "data",
        volume_type="custom",
        config=config,
        description="Data volume",
    )


def test_volume_absent_reports_list_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.volume_list"].return_value = {
        "success": False,
        "error": "connection failed",
    }

    result = incus_volume_mod.volume_absent("data", "default")

    assert result["result"] is False
    assert not result["changes"]
    assert result["comment"] == ("Failed to list volumes in pool default: connection failed")


def test_volume_absent_is_idempotent_when_type_does_not_match(state_runtime):
    salt_funcs, _ = state_runtime
    _volume_list(salt_funcs, [{"name": "data", "type": "image"}])

    result = incus_volume_mod.volume_absent("data", "default")

    assert result == {
        "name": "data",
        "result": True,
        "changes": {},
        "comment": "Volume data already absent from pool default",
    }
    salt_funcs["incus.volume_delete"].assert_not_called()


def test_volume_absent_test_mode_reports_deletion(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _volume_list(salt_funcs, [{"name": "data", "type": "custom"}])

    result = incus_volume_mod.volume_absent("data", "default")

    assert result == {
        "name": "data",
        "result": None,
        "changes": {"volume": {"old": "data", "new": None}},
        "comment": "Volume data would be deleted from pool default",
    }
    salt_funcs["incus.volume_delete"].assert_not_called()


@pytest.mark.parametrize(
    ("delete_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {"volume": {"old": "data", "new": None}},
            "Volume data deleted from pool default",
        ),
        (
            {"success": False, "error": "in use"},
            False,
            {},
            "Failed to delete volume data: in use",
        ),
    ],
)
def test_volume_absent_deletion_results(
    state_runtime,
    delete_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _volume_list(salt_funcs, [{"name": "data", "type": "custom"}])
    salt_funcs["incus.volume_delete"].return_value = delete_result

    result = incus_volume_mod.volume_absent("data", "default")

    assert result == {
        "name": "data",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.volume_delete"].assert_called_once_with("default", "data", "custom")


def test_volume_config_reports_get_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.volume_get"].return_value = {
        "success": False,
        "error": "not found",
    }

    result = incus_volume_mod.volume_config("data", "default")

    assert result == {
        "name": "data",
        "result": False,
        "changes": {},
        "comment": "Failed to get volume data: not found",
    }


@pytest.mark.parametrize("config", [None, {}])
def test_volume_config_is_idempotent_for_empty_config(state_runtime, config):
    salt_funcs, _ = state_runtime
    _volume_info(salt_funcs, {"size": "10GiB"}, "Current")

    result = incus_volume_mod.volume_config("data", "default", config=config)

    assert result["result"] is True
    assert not result["changes"]
    assert result["comment"] == "Volume data already has desired configuration"
    salt_funcs["incus.volume_update"].assert_not_called()


def test_volume_config_test_mode_reports_config_and_description(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _volume_info(salt_funcs, {"size": "5GiB"}, "Old")

    result = incus_volume_mod.volume_config(
        "data",
        "default",
        config={"size": "10GiB", "snapshots.expiry": "1d"},
        description="New",
    )

    assert result == {
        "name": "data",
        "result": None,
        "changes": {
            "config": {
                "size": {"old": "5GiB", "new": "10GiB"},
                "snapshots.expiry": {"old": None, "new": "1d"},
            },
            "description": {"old": "Old", "new": "New"},
        },
        "comment": "Volume data configuration would be updated",
    }
    salt_funcs["incus.volume_update"].assert_not_called()


@pytest.mark.parametrize(
    ("update_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {
                "config": {"size": {"old": "5GiB", "new": "10GiB"}},
                "description": {"old": "Old", "new": "New"},
            },
            "Volume data configuration updated",
        ),
        (
            {"success": False, "error": "update failed"},
            False,
            {},
            "Failed to update volume data: update failed",
        ),
    ],
)
def test_volume_config_update_results(
    state_runtime,
    update_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _volume_info(salt_funcs, {"size": "5GiB"}, "Old")
    salt_funcs["incus.volume_update"].return_value = update_result
    config = {"size": "10GiB"}

    result = incus_volume_mod.volume_config("data", "default", config=config, description="New")

    assert result == {
        "name": "data",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.volume_update"].assert_called_once_with(
        "default",
        "data",
        volume_type="custom",
        config=config,
        description="New",
    )


def test_volume_snapshot_present_reports_list_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.volume_snapshot_list"].return_value = {
        "success": False,
        "error": "connection failed",
    }

    result = incus_volume_mod.volume_snapshot_present("snap0", "default", "data")

    assert result["result"] is False
    assert not result["changes"]
    assert result["comment"] == "Failed to list snapshots: connection failed"


def test_volume_snapshot_present_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    _snapshot_list(salt_funcs, [{"name": "snap0"}])

    result = incus_volume_mod.volume_snapshot_present("snap0", "default", "data")

    assert result["result"] is True
    assert not result["changes"]
    assert result["comment"] == "Snapshot snap0 already exists for volume data"
    salt_funcs["incus.volume_snapshot_create"].assert_not_called()


def test_volume_snapshot_present_test_mode_reports_creation(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _snapshot_list(salt_funcs, None)

    result = incus_volume_mod.volume_snapshot_present("snap0", "default", "data")

    assert result == {
        "name": "snap0",
        "result": None,
        "changes": {"snapshot": {"old": None, "new": "snap0"}},
        "comment": "Snapshot snap0 would be created for volume data",
    }
    salt_funcs["incus.volume_snapshot_create"].assert_not_called()


@pytest.mark.parametrize(
    ("create_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {"snapshot": {"old": None, "new": "snap0"}},
            "Snapshot snap0 created for volume data",
        ),
        (
            {"success": False, "error": "create failed"},
            False,
            {},
            "Failed to create snapshot snap0: create failed",
        ),
    ],
)
def test_volume_snapshot_present_creation_results(
    state_runtime,
    create_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _snapshot_list(salt_funcs, [])
    salt_funcs["incus.volume_snapshot_create"].return_value = create_result

    result = incus_volume_mod.volume_snapshot_present(
        "snap0",
        "default",
        "data",
        volume_type="custom",
        description="Backup",
    )

    assert result == {
        "name": "snap0",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.volume_snapshot_create"].assert_called_once_with(
        "default",
        "data",
        "snap0",
        volume_type="custom",
        description="Backup",
    )


def test_volume_snapshot_absent_reports_list_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.volume_snapshot_list"].return_value = {
        "success": False,
        "error": "connection failed",
    }

    result = incus_volume_mod.volume_snapshot_absent("snap0", "default", "data")

    assert result["result"] is False
    assert not result["changes"]
    assert result["comment"] == "Failed to list snapshots: connection failed"


def test_volume_snapshot_absent_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    _snapshot_list(salt_funcs, None)

    result = incus_volume_mod.volume_snapshot_absent("snap0", "default", "data")

    assert result["result"] is True
    assert not result["changes"]
    assert result["comment"] == "Snapshot snap0 already absent from volume data"
    salt_funcs["incus.volume_snapshot_delete"].assert_not_called()


def test_volume_snapshot_absent_test_mode_reports_deletion(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _snapshot_list(salt_funcs, [{"name": "snap0"}])

    result = incus_volume_mod.volume_snapshot_absent("snap0", "default", "data")

    assert result == {
        "name": "snap0",
        "result": None,
        "changes": {"snapshot": {"old": "snap0", "new": None}},
        "comment": "Snapshot snap0 would be deleted from volume data",
    }
    salt_funcs["incus.volume_snapshot_delete"].assert_not_called()


@pytest.mark.parametrize(
    ("delete_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {"snapshot": {"old": "snap0", "new": None}},
            "Snapshot snap0 deleted from volume data",
        ),
        (
            {"success": False, "error": "delete failed"},
            False,
            {},
            "Failed to delete snapshot snap0: delete failed",
        ),
    ],
)
def test_volume_snapshot_absent_deletion_results(
    state_runtime,
    delete_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _snapshot_list(salt_funcs, [{"name": "snap0"}])
    salt_funcs["incus.volume_snapshot_delete"].return_value = delete_result

    result = incus_volume_mod.volume_snapshot_absent("snap0", "default", "data")

    assert result == {
        "name": "snap0",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.volume_snapshot_delete"].assert_called_once_with(
        "default", "data", "snap0", "custom"
    )


def test_volume_attached_reports_instance_get_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.instance_get"].return_value = {
        "success": False,
        "error": "not found",
    }

    result = incus_volume_mod.volume_attached("data", "default", "web")

    assert result == {
        "name": "data",
        "result": False,
        "changes": {},
        "comment": "Failed to get instance web: not found",
    }


def test_volume_attached_is_idempotent_for_matching_device(state_runtime):
    salt_funcs, _ = state_runtime
    device = {
        "type": "disk",
        "pool": "default",
        "source": "data",
        "path": "/old-path",
    }
    _instance_info(salt_funcs, {"storage": device})

    result = incus_volume_mod.volume_attached(
        "data", "default", "web", device_name="storage", path="/new-path"
    )

    assert result["result"] is True
    assert not result["changes"]
    assert result["comment"] == "Volume data already attached to instance web"
    salt_funcs["incus.instance_update"].assert_not_called()


def test_volume_attached_test_mode_reports_replacement(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    old_device = {"type": "disk", "source": "other", "pool": "default"}
    _instance_info(salt_funcs, {"storage": old_device})

    result = incus_volume_mod.volume_attached(
        "data", "default", "web", device_name="storage", path=None
    )

    assert result == {
        "name": "data",
        "result": None,
        "changes": {
            "device": {
                "old": old_device,
                "new": {
                    "type": "disk",
                    "pool": "default",
                    "source": "data",
                    "path": None,
                },
            }
        },
        "comment": "Volume data would be attached to instance web",
    }
    salt_funcs["incus.instance_update"].assert_not_called()


@pytest.mark.parametrize(
    ("update_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {
                "device": {
                    "old": None,
                    "new": {
                        "type": "disk",
                        "pool": "default",
                        "source": "data",
                        "path": "/mnt/data",
                    },
                }
            },
            "Volume data attached to instance web",
        ),
        (
            {"success": False, "error": "update failed"},
            False,
            {},
            "Failed to attach volume data: update failed",
        ),
    ],
)
def test_volume_attached_update_results(
    state_runtime,
    update_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _instance_info(salt_funcs, {})
    salt_funcs["incus.instance_update"].return_value = update_result
    device = {
        "data": {
            "type": "disk",
            "pool": "default",
            "source": "data",
            "path": "/mnt/data",
        }
    }

    result = incus_volume_mod.volume_attached("data", "default", "web", path="/mnt/data")

    assert result == {
        "name": "data",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.instance_update"].assert_called_once_with("web", devices=device)


def test_volume_attached_omits_empty_path_from_live_update(state_runtime):
    salt_funcs, _ = state_runtime
    _instance_info(salt_funcs, {})
    salt_funcs["incus.instance_update"].return_value = {"success": True}

    incus_volume_mod.volume_attached("data", "default", "web")

    salt_funcs["incus.instance_update"].assert_called_once_with(
        "web",
        devices={"data": {"type": "disk", "pool": "default", "source": "data"}},
    )


def test_volume_detached_reports_instance_get_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.instance_get"].return_value = {
        "success": False,
        "error": "not found",
    }

    result = incus_volume_mod.volume_detached("data", "default", "web")

    assert result["result"] is False
    assert not result["changes"]
    assert result["comment"] == "Failed to get instance web: not found"


def test_volume_detached_is_idempotent_when_device_is_missing(state_runtime):
    salt_funcs, _ = state_runtime
    _instance_info(salt_funcs, {})

    result = incus_volume_mod.volume_detached("data", "default", "web")

    assert result["result"] is True
    assert not result["changes"]
    assert result["comment"] == "Volume data already detached from instance web"
    salt_funcs["incus.instance_update"].assert_not_called()


@pytest.mark.parametrize(
    "device",
    [
        {"type": "disk", "pool": "other", "source": "data"},
        {"type": "disk", "pool": "default", "source": "other"},
    ],
)
def test_volume_detached_does_not_remove_a_different_device(state_runtime, device):
    salt_funcs, _ = state_runtime
    _instance_info(salt_funcs, {"storage": device})

    result = incus_volume_mod.volume_detached("data", "default", "web", device_name="storage")

    assert result["result"] is True
    assert not result["changes"]
    assert result["comment"] == ("Device storage is not volume data from pool default")
    salt_funcs["incus.instance_update"].assert_not_called()


def test_volume_detached_test_mode_reports_removal(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    device = {"type": "disk", "pool": "default", "source": "data"}
    _instance_info(salt_funcs, {"storage": device})

    result = incus_volume_mod.volume_detached("data", "default", "web", device_name="storage")

    assert result == {
        "name": "data",
        "result": None,
        "changes": {"device": {"old": device, "new": None}},
        "comment": "Volume data would be detached from instance web",
    }
    salt_funcs["incus.instance_update"].assert_not_called()


@pytest.mark.parametrize(
    ("update_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {
                "device": {
                    "old": {
                        "type": "disk",
                        "pool": "default",
                        "source": "data",
                    },
                    "new": None,
                }
            },
            "Volume data detached from instance web",
        ),
        (
            {"success": False, "error": "update failed"},
            False,
            {},
            "Failed to detach volume data: update failed",
        ),
    ],
)
def test_volume_detached_update_results(
    state_runtime,
    update_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    device = {"type": "disk", "pool": "default", "source": "data"}
    _instance_info(salt_funcs, {"storage": device, "eth0": {"type": "nic"}})
    salt_funcs["incus.instance_update"].return_value = update_result

    result = incus_volume_mod.volume_detached("data", "default", "web", device_name="storage")

    assert result == {
        "name": "data",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.instance_update"].assert_called_once_with("web", devices={"storage": {}})
