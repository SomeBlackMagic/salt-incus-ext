from unittest.mock import Mock

import pytest

from incus.modules import incus_storage_pool_mod


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    monkeypatch.setattr(incus_storage_pool_mod, "_client", Mock(return_value=client))
    return client


def test_client_creates_incus_client(monkeypatch):
    from incus.modules import incus_mod

    mock_client = Mock()
    monkeypatch.setattr(incus_storage_pool_mod, "__salt__", {}, raising=False)
    monkeypatch.setattr(incus_mod, "IncusClient", Mock(return_value=mock_client))

    assert incus_storage_pool_mod._client() is mock_client


@pytest.mark.parametrize(
    ("function", "args", "path", "params", "result_key", "metadata"),
    [
        (
            incus_storage_pool_mod.storage_pool_list,
            (2,),
            "/storage-pools",
            {"recursion": 2},
            "pools",
            ["pool one"],
        ),
        (
            incus_storage_pool_mod.storage_pool_get,
            ("pool one",),
            "/storage-pools/pool%20one",
            None,
            "pool",
            {"name": "pool one", "driver": "zfs"},
        ),
        (
            incus_storage_pool_mod.storage_pool_resources,
            ("pool one",),
            "/storage-pools/pool%20one/resources",
            None,
            "resources",
            {"space": {"used": 1024}},
        ),
    ],
)
def test_storage_pool_queries(
    client, function, args, path, params, result_key, metadata
):
    client._request.return_value = {"error_code": 0, "metadata": metadata}

    assert function(*args) == {"success": True, result_key: metadata}
    if params is None:
        client._request.assert_called_once_with("GET", path)
    else:
        client._request.assert_called_once_with("GET", path, params=params)


@pytest.mark.parametrize(
    ("function", "args", "expected"),
    [
        (
            incus_storage_pool_mod.storage_pool_list,
            (),
            {"success": True, "pools": []},
        ),
        (
            incus_storage_pool_mod.storage_pool_get,
            ("pool",),
            {"success": True, "pool": {}},
        ),
        (
            incus_storage_pool_mod.storage_pool_resources,
            ("pool",),
            {"success": True, "resources": {}},
        ),
    ],
)
def test_storage_pool_queries_default_to_empty_metadata(
    client, function, args, expected
):
    client._request.return_value = {"error_code": 0}

    assert function(*args) == expected


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (incus_storage_pool_mod.storage_pool_list, ()),
        (incus_storage_pool_mod.storage_pool_create, ("pool", "dir")),
        (incus_storage_pool_mod.storage_pool_get, ("pool",)),
        (incus_storage_pool_mod.storage_pool_update, ("pool",)),
        (incus_storage_pool_mod.storage_pool_rename, ("pool", "new")),
        (incus_storage_pool_mod.storage_pool_resources, ("pool",)),
        (incus_storage_pool_mod.storage_pool_delete, ("pool",)),
    ],
)
def test_storage_pool_functions_return_api_errors(client, function, args):
    client._request.return_value = {"error_code": 1, "error": "boom"}
    client._sync_request.return_value = {"error_code": 1, "error": "boom"}

    assert function(*args) == {"success": False, "error": "boom"}


def test_storage_pool_create_builds_complete_request(client):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_storage_pool_mod.storage_pool_create(
        "pool one",
        "zfs",
        config={"source": "tank/incus", "zfs.pool_name": "tank"},
        description="Primary pool",
    )

    assert result == {
        "success": True,
        "message": "Storage pool pool one created successfully",
    }
    client._sync_request.assert_called_once_with(
        "POST",
        "/storage-pools",
        data={
            "name": "pool one",
            "driver": "zfs",
            "config": {"source": "tank/incus", "zfs.pool_name": "tank"},
            "description": "Primary pool",
        },
    )


@pytest.mark.parametrize("config", [None, {}])
def test_storage_pool_create_normalizes_empty_config(client, config):
    client._sync_request.return_value = {"error_code": 0}

    incus_storage_pool_mod.storage_pool_create("pool", "dir", config=config)

    client._sync_request.assert_called_once_with(
        "POST",
        "/storage-pools",
        data={"name": "pool", "driver": "dir", "config": {}, "description": ""},
    )


def test_storage_pool_update_merges_config_and_replaces_description(client):
    client._request.return_value = {
        "error_code": 0,
        "metadata": {
            "name": "pool one",
            "driver": "zfs",
            "config": {"source": "tank/incus", "rsync.bwlimit": "50"},
            "description": "Old",
            "used_by": ["/storage-volumes/custom/data"],
        },
    }
    client._sync_request.return_value = {"error_code": 0}

    result = incus_storage_pool_mod.storage_pool_update(
        "pool one",
        config={"rsync.bwlimit": "100", "volatile.initial_source": "tank"},
        description="",
    )

    assert result == {
        "success": True,
        "message": "Storage pool pool one updated successfully",
    }
    client._request.assert_called_once_with("GET", "/storage-pools/pool%20one")
    client._sync_request.assert_called_once_with(
        "PUT",
        "/storage-pools/pool%20one",
        data={
            "name": "pool one",
            "driver": "zfs",
            "config": {
                "source": "tank/incus",
                "rsync.bwlimit": "100",
                "volatile.initial_source": "tank",
            },
            "description": "",
            "used_by": ["/storage-volumes/custom/data"],
        },
    )


def test_storage_pool_update_preserves_fields_and_returns_put_error(client):
    metadata = {
        "config": {"source": "/var/lib/incus/storage-pools/pool"},
        "description": "Keep",
    }
    client._request.return_value = {"error_code": 0, "metadata": metadata}
    client._sync_request.return_value = {"error_code": 1, "error": "read-only"}

    assert incus_storage_pool_mod.storage_pool_update("pool") == {
        "success": False,
        "error": "read-only",
    }
    client._sync_request.assert_called_once_with(
        "PUT", "/storage-pools/pool", data=metadata
    )


def test_storage_pool_update_returns_get_error_without_put(client):
    client._request.return_value = {"error_code": 1, "error": "missing"}

    assert incus_storage_pool_mod.storage_pool_update("missing") == {
        "success": False,
        "error": "missing",
    }
    client._sync_request.assert_not_called()


def test_storage_pool_rename_quotes_source_name(client):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_storage_pool_mod.storage_pool_rename("pool one", "pool two")

    assert result == {
        "success": True,
        "message": "Storage pool pool one renamed to pool two successfully",
    }
    client._sync_request.assert_called_once_with(
        "POST", "/storage-pools/pool%20one", data={"name": "pool two"}
    )


def test_storage_pool_delete_quotes_name(client):
    client._sync_request.return_value = {"error_code": 0}

    assert incus_storage_pool_mod.storage_pool_delete("pool one") == {
        "success": True,
        "message": "Storage pool pool one deleted successfully",
    }
    client._sync_request.assert_called_once_with(
        "DELETE", "/storage-pools/pool%20one"
    )
