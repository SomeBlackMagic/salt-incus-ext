from unittest.mock import Mock
from unittest.mock import call

import pytest

from incus.modules import incus_cluster_mod


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    monkeypatch.setattr(incus_cluster_mod, "_client", Mock(return_value=client))
    return client


def test_client_creates_incus_client(monkeypatch):
    from incus.modules import incus_mod

    mock_client = Mock()
    monkeypatch.setattr(incus_cluster_mod, "__salt__", {}, raising=False)
    monkeypatch.setattr(incus_mod, "IncusClient", Mock(return_value=mock_client))

    assert incus_cluster_mod._client() is mock_client


def test_cluster_info_returns_metadata(client):
    client._request.return_value = {
        "error_code": 0,
        "metadata": {"enabled": True, "server_name": "node1"},
    }

    assert incus_cluster_mod.cluster_info() == {
        "success": True,
        "cluster": {"enabled": True, "server_name": "node1"},
    }
    client._request.assert_called_once_with("GET", "/cluster")


def test_cluster_info_defaults_to_empty_metadata(client):
    client._request.return_value = {"error_code": 0}

    assert incus_cluster_mod.cluster_info() == {"success": True, "cluster": {}}


def test_cluster_member_list_passes_recursion(client):
    members = [{"server_name": "node1"}, {"server_name": "node2"}]
    client._request.return_value = {"error_code": 0, "metadata": members}

    assert incus_cluster_mod.cluster_member_list(recursion=2) == {
        "success": True,
        "members": members,
    }
    client._request.assert_called_once_with("GET", "/cluster/members", params={"recursion": 2})


def test_cluster_member_list_defaults_to_empty_metadata(client):
    client._request.return_value = {"error_code": 0}

    assert incus_cluster_mod.cluster_member_list() == {"success": True, "members": []}
    client._request.assert_called_once_with("GET", "/cluster/members", params={"recursion": 0})


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (incus_cluster_mod.cluster_info, ()),
        (incus_cluster_mod.cluster_member_list, ()),
        (incus_cluster_mod.cluster_member_add, ("node2", "192.0.2.2")),
        (incus_cluster_mod.cluster_member_remove, ("node2",)),
    ],
)
def test_cluster_functions_return_api_errors(client, function, args):
    client._request.return_value = {"error_code": 1, "error": "cluster unavailable"}
    client._sync_request.return_value = {
        "error_code": 1,
        "error": "cluster unavailable",
    }

    assert function(*args) == {"success": False, "error": "cluster unavailable"}


def test_cluster_member_add_includes_password(client):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_cluster_mod.cluster_member_add(
        "node2", "192.0.2.2:8443", cluster_password="secret"
    )

    assert result == {
        "success": True,
        "message": "Cluster member node2 added successfully",
    }
    client._sync_request.assert_called_once_with(
        "POST",
        "/cluster/members",
        data={
            "server_name": "node2",
            "server_address": "192.0.2.2:8443",
            "cluster_password": "secret",
        },
    )


@pytest.mark.parametrize("cluster_password", [None, ""])
def test_cluster_member_add_omits_empty_password(client, cluster_password):
    client._sync_request.return_value = {"error_code": 0}

    incus_cluster_mod.cluster_member_add(
        "node2", "192.0.2.2:8443", cluster_password=cluster_password
    )

    client._sync_request.assert_called_once_with(
        "POST",
        "/cluster/members",
        data={"server_name": "node2", "server_address": "192.0.2.2:8443"},
    )


@pytest.mark.parametrize(
    ("force", "expected_params"),
    [(False, {}), (True, {"force": "1"})],
)
def test_cluster_member_remove_quotes_name_and_handles_force(client, force, expected_params):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_cluster_mod.cluster_member_remove("node two/primary", force=force)

    assert result == {
        "success": True,
        "message": "Cluster member node two/primary removed successfully",
    }
    client._sync_request.assert_called_once_with(
        "DELETE", "/cluster/members/node%20two/primary", params=expected_params
    )


def test_cluster_calls_use_one_client_each(monkeypatch):
    clients = [Mock(), Mock(), Mock(), Mock()]
    for client in clients:
        client._request.return_value = {"error_code": 0}
        client._sync_request.return_value = {"error_code": 0}
    factory = Mock(side_effect=clients)
    monkeypatch.setattr(incus_cluster_mod, "_client", factory)

    incus_cluster_mod.cluster_info()
    incus_cluster_mod.cluster_member_list()
    incus_cluster_mod.cluster_member_add("node", "192.0.2.2")
    incus_cluster_mod.cluster_member_remove("node")

    assert factory.call_args_list == [call(), call(), call(), call()]
