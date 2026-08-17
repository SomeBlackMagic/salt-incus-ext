from unittest.mock import Mock

import pytest

from incus.modules import incus_volume_mod


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    monkeypatch.setattr(incus_volume_mod, "_client", Mock(return_value=client))
    return client


def test_client_creates_incus_client(monkeypatch):
    from incus.modules import incus_mod

    mock_client = Mock()
    monkeypatch.setattr(incus_volume_mod, "__salt__", {}, raising=False)
    monkeypatch.setattr(incus_mod, "IncusClient", Mock(return_value=mock_client))

    assert incus_volume_mod._client() is mock_client


@pytest.mark.parametrize(
    ("function", "args", "path", "params", "result_key", "metadata"),
    [
        (
            incus_volume_mod.volume_list,
            ("pool one", 2),
            "/storage-pools/pool%20one/volumes",
            {"recursion": 2},
            "volumes",
            ["volume one"],
        ),
        (
            incus_volume_mod.volume_get,
            ("pool one", "volume one", "virtual-machine"),
            "/storage-pools/pool%20one/volumes/virtual-machine/volume%20one",
            None,
            "volume",
            {"name": "volume one"},
        ),
        (
            incus_volume_mod.volume_snapshot_list,
            ("pool one", "volume one", "custom", 1),
            "/storage-pools/pool%20one/volumes/custom/volume%20one/snapshots",
            {"recursion": 1},
            "snapshots",
            ["snap one"],
        ),
        (
            incus_volume_mod.volume_snapshot_get,
            ("pool one", "volume one", "snap one", "custom"),
            "/storage-pools/pool%20one/volumes/custom/volume%20one/snapshots/snap%20one",
            None,
            "snapshot",
            {"name": "snap one"},
        ),
    ],
)
def test_volume_queries(client, function, args, path, params, result_key, metadata):
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
            incus_volume_mod.volume_list,
            ("pool",),
            {"success": True, "volumes": []},
        ),
        (
            incus_volume_mod.volume_get,
            ("pool", "volume"),
            {"success": True, "volume": {}},
        ),
        (
            incus_volume_mod.volume_snapshot_list,
            ("pool", "volume"),
            {"success": True, "snapshots": []},
        ),
        (
            incus_volume_mod.volume_snapshot_get,
            ("pool", "volume", "snapshot"),
            {"success": True, "snapshot": {}},
        ),
    ],
)
def test_volume_queries_default_to_empty_metadata(client, function, args, expected):
    client._request.return_value = {"error_code": 0}

    assert function(*args) == expected


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (incus_volume_mod.volume_list, ("pool",)),
        (incus_volume_mod.volume_create, ("pool", "volume")),
        (incus_volume_mod.volume_get, ("pool", "volume")),
        (incus_volume_mod.volume_update, ("pool", "volume")),
        (incus_volume_mod.volume_rename, ("pool", "volume", "new")),
        (incus_volume_mod.volume_copy, ("pool", "volume")),
        (
            incus_volume_mod.volume_create_from_snapshot,
            ("pool", "volume", "snapshot", "new"),
        ),
        (incus_volume_mod.volume_move, ("pool", "volume", "target")),
        (incus_volume_mod.volume_snapshot_list, ("pool", "volume")),
        (
            incus_volume_mod.volume_snapshot_create,
            ("pool", "volume", "snapshot"),
        ),
        (incus_volume_mod.volume_snapshot_get, ("pool", "volume", "snapshot")),
        (
            incus_volume_mod.volume_snapshot_rename,
            ("pool", "volume", "snapshot", "new"),
        ),
        (
            incus_volume_mod.volume_snapshot_restore,
            ("pool", "volume", "snapshot"),
        ),
        (
            incus_volume_mod.volume_snapshot_delete,
            ("pool", "volume", "snapshot"),
        ),
        (incus_volume_mod.volume_delete, ("pool", "volume")),
    ],
)
def test_volume_functions_return_api_errors(client, function, args):
    client._request.return_value = {"error_code": 1, "error": "boom"}
    client._sync_request.return_value = {"error_code": 1, "error": "boom"}

    assert function(*args) == {"success": False, "error": "boom"}


def test_volume_create_builds_complete_request(client):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_volume_mod.volume_create(
        "pool one",
        "volume one",
        volume_type="virtual-machine",
        config={"size": "20GiB"},
        description="VM disk",
    )

    assert result == {
        "success": True,
        "message": "Volume volume one created successfully",
    }
    client._sync_request.assert_called_once_with(
        "POST",
        "/storage-pools/pool%20one/volumes/virtual-machine",
        data={
            "name": "volume one",
            "type": "virtual-machine",
            "config": {"size": "20GiB"},
            "description": "VM disk",
        },
    )


@pytest.mark.parametrize("config", [None, {}])
def test_volume_create_normalizes_empty_config(client, config):
    client._sync_request.return_value = {"error_code": 0}

    incus_volume_mod.volume_create("pool", "volume", config=config)

    client._sync_request.assert_called_once_with(
        "POST",
        "/storage-pools/pool/volumes/custom",
        data={
            "name": "volume",
            "type": "custom",
            "config": {},
            "description": "",
        },
    )


def test_volume_update_merges_config_and_replaces_description(client):
    client._request.return_value = {
        "error_code": 0,
        "metadata": {
            "name": "volume one",
            "type": "custom",
            "config": {"size": "10GiB", "security.shifted": "false"},
            "description": "Old",
            "used_by": ["/instances/vm"],
        },
    }
    client._sync_request.return_value = {"error_code": 0}

    result = incus_volume_mod.volume_update(
        "pool one",
        "volume one",
        config={"size": "20GiB", "snapshots.expiry": "7d"},
        description="",
    )

    assert result == {
        "success": True,
        "message": "Volume volume one updated successfully",
    }
    path = "/storage-pools/pool%20one/volumes/custom/volume%20one"
    client._request.assert_called_once_with("GET", path)
    client._sync_request.assert_called_once_with(
        "PUT",
        path,
        data={
            "name": "volume one",
            "type": "custom",
            "config": {
                "size": "20GiB",
                "security.shifted": "false",
                "snapshots.expiry": "7d",
            },
            "description": "",
            "used_by": ["/instances/vm"],
        },
    )


def test_volume_update_preserves_fields_and_returns_put_error(client):
    metadata = {"config": {"size": "10GiB"}, "description": "Keep"}
    client._request.return_value = {"error_code": 0, "metadata": metadata}
    client._sync_request.return_value = {"error_code": 1, "error": "read-only"}

    assert incus_volume_mod.volume_update("pool", "volume") == {
        "success": False,
        "error": "read-only",
    }
    client._sync_request.assert_called_once_with(
        "PUT", "/storage-pools/pool/volumes/custom/volume", data=metadata
    )


def test_volume_update_returns_get_error_without_put(client):
    client._request.return_value = {"error_code": 1, "error": "missing"}

    assert incus_volume_mod.volume_update("pool", "missing") == {
        "success": False,
        "error": "missing",
    }
    client._sync_request.assert_not_called()


def test_volume_copy_uses_explicit_target_and_config(client):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_volume_mod.volume_copy(
        "source pool",
        "source volume",
        target_pool="target pool",
        target_volume="target volume",
        volume_type="virtual-machine",
        config={"size": "40GiB"},
    )

    assert result == {
        "success": True,
        "message": "Volume source volume copied to target volume successfully",
    }
    client._sync_request.assert_called_once_with(
        "POST",
        "/storage-pools/target%20pool/volumes/virtual-machine",
        data={
            "name": "target volume",
            "source": {
                "pool": "source pool",
                "name": "source volume",
                "type": "virtual-machine",
            },
            "config": {"size": "40GiB"},
        },
    )


@pytest.mark.parametrize("empty_value", [None, ""])
def test_volume_copy_defaults_target_and_config(client, empty_value):
    client._sync_request.return_value = {"error_code": 0}

    incus_volume_mod.volume_copy(
        "source pool",
        "source volume",
        target_pool=empty_value,
        target_volume=empty_value,
        config=None,
    )

    client._sync_request.assert_called_once_with(
        "POST",
        "/storage-pools/source%20pool/volumes/custom",
        data={
            "name": "source volume",
            "source": {
                "pool": "source pool",
                "name": "source volume",
                "type": "custom",
            },
            "config": {},
        },
    )


def test_volume_create_from_snapshot_builds_request(client):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_volume_mod.volume_create_from_snapshot(
        "pool one",
        "volume one",
        "snap one",
        "restored volume",
        config={"size": "30GiB"},
    )

    assert result == {
        "success": True,
        "message": "Volume restored volume created from snapshot snap one successfully",
    }
    client._sync_request.assert_called_once_with(
        "POST",
        "/storage-pools/pool%20one/volumes/custom",
        data={
            "name": "restored volume",
            "source": {
                "pool": "pool one",
                "name": "volume one",
                "type": "custom",
                "snapshot": "snap one",
            },
            "config": {"size": "30GiB"},
        },
    )


@pytest.mark.parametrize("config", [None, {}])
def test_volume_create_from_snapshot_normalizes_empty_config(client, config):
    client._sync_request.return_value = {"error_code": 0}

    incus_volume_mod.volume_create_from_snapshot("pool", "volume", "snapshot", "new", config=config)

    assert not client._sync_request.call_args.kwargs["data"]["config"]


@pytest.mark.parametrize(
    ("target_volume", "expected_name"),
    [(None, "volume one"), ("", "volume one"), ("volume two", "volume two")],
)
def test_volume_move_handles_target_name(client, target_volume, expected_name):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_volume_mod.volume_move(
        "source pool",
        "volume one",
        "target pool",
        target_volume=target_volume,
        volume_type="custom",
    )

    assert result == {
        "success": True,
        "message": "Volume volume one moved to pool target pool successfully",
    }
    client._sync_request.assert_called_once_with(
        "POST",
        "/storage-pools/source%20pool/volumes/custom/volume%20one",
        data={"name": expected_name, "pool": "target pool"},
    )


@pytest.mark.parametrize(
    ("function", "args", "method", "path", "data", "message"),
    [
        (
            incus_volume_mod.volume_rename,
            ("pool one", "volume one", "volume two", "custom"),
            "POST",
            "/storage-pools/pool%20one/volumes/custom/volume%20one",
            {"name": "volume two"},
            "Volume volume one renamed to volume two successfully",
        ),
        (
            incus_volume_mod.volume_snapshot_create,
            ("pool one", "volume one", "snap one", "custom", "Before update"),
            "POST",
            "/storage-pools/pool%20one/volumes/custom/volume%20one/snapshots",
            {"name": "snap one", "description": "Before update"},
            "Snapshot snap one of volume volume one created successfully",
        ),
        (
            incus_volume_mod.volume_snapshot_rename,
            ("pool one", "volume one", "snap one", "snap two", "custom"),
            "POST",
            "/storage-pools/pool%20one/volumes/custom/volume%20one/snapshots/snap%20one",
            {"name": "snap two"},
            "Snapshot snap one renamed to snap two successfully",
        ),
        (
            incus_volume_mod.volume_snapshot_restore,
            ("pool one", "volume one", "snap one", "custom"),
            "PUT",
            "/storage-pools/pool%20one/volumes/custom/volume%20one",
            {"restore": "snap one"},
            "Volume volume one restored from snapshot snap one successfully",
        ),
        (
            incus_volume_mod.volume_snapshot_delete,
            ("pool one", "volume one", "snap one", "custom"),
            "DELETE",
            "/storage-pools/pool%20one/volumes/custom/volume%20one/snapshots/snap%20one",
            None,
            "Snapshot snap one of volume volume one deleted successfully",
        ),
        (
            incus_volume_mod.volume_delete,
            ("pool one", "volume one", "custom"),
            "DELETE",
            "/storage-pools/pool%20one/volumes/custom/volume%20one",
            None,
            "Volume volume one deleted successfully",
        ),
    ],
)
def test_simple_volume_mutations(client, function, args, method, path, data, message):
    client._sync_request.return_value = {"error_code": 0}

    assert function(*args) == {"success": True, "message": message}
    if data is None:
        client._sync_request.assert_called_once_with(method, path)
    else:
        client._sync_request.assert_called_once_with(method, path, data=data)
