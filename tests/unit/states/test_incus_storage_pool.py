from unittest.mock import Mock

import pytest

from incus.states import incus_storage_pool_mod


@pytest.fixture
def state_runtime(monkeypatch):
    salt_funcs = {
        "incus.storage_pool_list": Mock(),
        "incus.storage_pool_create": Mock(),
        "incus.storage_pool_delete": Mock(),
        "incus.storage_pool_get": Mock(),
        "incus.storage_pool_update": Mock(),
    }
    opts = {"test": False}
    monkeypatch.setattr(incus_storage_pool_mod, "__salt__", salt_funcs, raising=False)
    monkeypatch.setattr(incus_storage_pool_mod, "__opts__", opts, raising=False)
    return salt_funcs, opts


def _pool_list(salt_funcs, pools):
    salt_funcs["incus.storage_pool_list"].return_value = {
        "success": True,
        "pools": pools,
    }


def _pool_info(salt_funcs, config=None, description=""):
    salt_funcs["incus.storage_pool_get"].return_value = {
        "success": True,
        "pool": {
            "config": config or {},
            "description": description,
        },
    }


def test_virtual_loads_only_with_storage_pool_execution_functions(monkeypatch):
    monkeypatch.setattr(
        incus_storage_pool_mod,
        "__salt__",
        {"incus.storage_pool_list": Mock()},
        raising=False,
    )
    assert incus_storage_pool_mod.__virtual__() == "incus"

    monkeypatch.setattr(incus_storage_pool_mod, "__salt__", {}, raising=False)
    assert incus_storage_pool_mod.__virtual__() == (
        False,
        "incus storage-pool execution functions are not available",
    )


def test_storage_pool_present_reports_list_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.storage_pool_list"].return_value = {
        "success": False,
        "error": "connection failed",
    }

    result = incus_storage_pool_mod.storage_pool_present("data", "dir")

    assert result == {
        "name": "data",
        "result": False,
        "changes": {},
        "comment": "Failed to list storage pools: connection failed",
    }


def test_storage_pool_present_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    _pool_list(salt_funcs, [{"name": "other"}, {"name": "data"}])

    result = incus_storage_pool_mod.storage_pool_present("data", "dir")

    assert result == {
        "name": "data",
        "result": True,
        "changes": {},
        "comment": "Storage pool data already exists",
    }
    salt_funcs["incus.storage_pool_create"].assert_not_called()


def test_storage_pool_present_test_mode_reports_creation(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _pool_list(salt_funcs, None)

    result = incus_storage_pool_mod.storage_pool_present("data", "zfs")

    assert result == {
        "name": "data",
        "result": None,
        "changes": {"pool": {"old": None, "new": "data"}},
        "comment": "Storage pool data would be created",
    }
    salt_funcs["incus.storage_pool_create"].assert_not_called()


@pytest.mark.parametrize(
    ("create_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {"pool": {"old": None, "new": "data"}},
            "Storage pool data created",
        ),
        (
            {"success": False, "error": "create failed"},
            False,
            {},
            "Failed to create storage pool data: create failed",
        ),
    ],
)
def test_storage_pool_present_creation_results(
    state_runtime,
    create_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _pool_list(salt_funcs, [])
    salt_funcs["incus.storage_pool_create"].return_value = create_result
    config = {"source": "/srv/incus"}

    result = incus_storage_pool_mod.storage_pool_present(
        "data",
        "dir",
        config=config,
        description="Data pool",
    )

    assert result == {
        "name": "data",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.storage_pool_create"].assert_called_once_with(
        "data",
        "dir",
        config=config,
        description="Data pool",
    )


def test_storage_pool_absent_reports_list_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.storage_pool_list"].return_value = {
        "success": False,
        "error": "connection failed",
    }

    result = incus_storage_pool_mod.storage_pool_absent("data")

    assert result == {
        "name": "data",
        "result": False,
        "changes": {},
        "comment": "Failed to list storage pools: connection failed",
    }


def test_storage_pool_absent_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    _pool_list(salt_funcs, None)

    result = incus_storage_pool_mod.storage_pool_absent("data")

    assert result == {
        "name": "data",
        "result": True,
        "changes": {},
        "comment": "Storage pool data already absent",
    }
    salt_funcs["incus.storage_pool_delete"].assert_not_called()


def test_storage_pool_absent_test_mode_reports_deletion(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _pool_list(salt_funcs, [{"name": "data"}])

    result = incus_storage_pool_mod.storage_pool_absent("data")

    assert result == {
        "name": "data",
        "result": None,
        "changes": {"pool": {"old": "data", "new": None}},
        "comment": "Storage pool data would be deleted",
    }
    salt_funcs["incus.storage_pool_delete"].assert_not_called()


@pytest.mark.parametrize(
    ("delete_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {"pool": {"old": "data", "new": None}},
            "Storage pool data deleted",
        ),
        (
            {"success": False, "error": "pool is in use"},
            False,
            {},
            "Failed to delete storage pool data: pool is in use",
        ),
    ],
)
def test_storage_pool_absent_deletion_results(
    state_runtime,
    delete_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _pool_list(salt_funcs, [{"name": "data"}])
    salt_funcs["incus.storage_pool_delete"].return_value = delete_result

    result = incus_storage_pool_mod.storage_pool_absent("data")

    assert result == {
        "name": "data",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.storage_pool_delete"].assert_called_once_with("data")


def test_storage_pool_config_reports_get_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.storage_pool_get"].return_value = {
        "success": False,
        "error": "not found",
    }

    result = incus_storage_pool_mod.storage_pool_config("data", {"size": "10GiB"})

    assert result == {
        "name": "data",
        "result": False,
        "changes": {},
        "comment": "Failed to get pool data: not found",
    }


@pytest.mark.parametrize("config", [None, {}])
def test_storage_pool_config_is_idempotent_for_empty_config(state_runtime, config):
    salt_funcs, _ = state_runtime
    _pool_info(salt_funcs, {"source": "/srv/incus"}, "Current")

    result = incus_storage_pool_mod.storage_pool_config("data", config)

    assert result == {
        "name": "data",
        "result": True,
        "changes": {},
        "comment": "Storage pool data already has desired configuration",
    }
    salt_funcs["incus.storage_pool_update"].assert_not_called()


def test_storage_pool_config_is_idempotent_with_matching_values(state_runtime):
    salt_funcs, _ = state_runtime
    _pool_info(salt_funcs, {"size": "10GiB"}, "Data pool")

    result = incus_storage_pool_mod.storage_pool_config(
        "data", {"size": "10GiB"}, description="Data pool"
    )

    assert result["result"] is True
    assert not result["changes"]
    assert result["comment"] == "Storage pool data already has desired configuration"
    salt_funcs["incus.storage_pool_update"].assert_not_called()


def test_storage_pool_config_test_mode_reports_all_changes(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _pool_info(salt_funcs, {"size": "5GiB"}, "Old description")

    result = incus_storage_pool_mod.storage_pool_config(
        "data",
        {"size": "10GiB", "rsync.bwlimit": "100"},
        description="New description",
    )

    assert result == {
        "name": "data",
        "result": None,
        "changes": {
            "config": {
                "size": {"old": "5GiB", "new": "10GiB"},
                "rsync.bwlimit": {"old": None, "new": "100"},
            },
            "description": {
                "old": "Old description",
                "new": "New description",
            },
        },
        "comment": "Storage pool data configuration would be updated",
    }
    salt_funcs["incus.storage_pool_update"].assert_not_called()


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
            "Storage pool data configuration updated",
        ),
        (
            {"success": False, "error": "update failed"},
            False,
            {},
            "Failed to update pool data: update failed",
        ),
    ],
)
def test_storage_pool_config_update_results(
    state_runtime,
    update_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _pool_info(salt_funcs, {"size": "5GiB"}, "Old")
    salt_funcs["incus.storage_pool_update"].return_value = update_result
    config = {"size": "10GiB"}

    result = incus_storage_pool_mod.storage_pool_config("data", config, description="New")

    assert result == {
        "name": "data",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.storage_pool_update"].assert_called_once_with(
        "data", config=config, description="New"
    )
