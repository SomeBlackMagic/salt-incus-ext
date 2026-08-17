from unittest.mock import Mock, call

import pytest

from incus.modules import incus_network_mod


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    monkeypatch.setattr(incus_network_mod, "_client", Mock(return_value=client))
    return client


def test_client_creates_incus_client(monkeypatch):
    from incus.modules import incus_mod

    mock_client = Mock()
    monkeypatch.setattr(incus_network_mod, "__salt__", {}, raising=False)
    monkeypatch.setattr(incus_mod, "IncusClient", Mock(return_value=mock_client))

    assert incus_network_mod._client() is mock_client


@pytest.mark.parametrize(
    ("function", "args", "path", "params", "result_key", "metadata"),
    [
        (
            incus_network_mod.network_list,
            (2,),
            "/networks",
            {"recursion": 2},
            "networks",
            ["net one"],
        ),
        (
            incus_network_mod.network_get,
            ("net one",),
            "/networks/net%20one",
            None,
            "network",
            {"name": "net one"},
        ),
        (
            incus_network_mod.network_state,
            ("net one",),
            "/networks/net%20one/state",
            None,
            "state",
            {"state": "Created"},
        ),
        (
            incus_network_mod.network_lease_list,
            ("net one",),
            "/networks/net%20one/leases",
            None,
            "leases",
            [{"hostname": "vm"}],
        ),
        (
            incus_network_mod.network_acl_list,
            (1,),
            "/network-acls",
            {"recursion": 1},
            "acls",
            ["acl one"],
        ),
        (
            incus_network_mod.network_acl_get,
            ("acl one",),
            "/network-acls/acl%20one",
            None,
            "acl",
            {"name": "acl one"},
        ),
        (
            incus_network_mod.network_forward_list,
            ("net one", 1),
            "/networks/net%20one/forwards",
            {"recursion": 1},
            "forwards",
            ["192.0.2.1"],
        ),
        (
            incus_network_mod.network_forward_get,
            ("net one", "2001:db8::1"),
            "/networks/net%20one/forwards/2001%3Adb8%3A%3A1",
            None,
            "forward",
            {"listen_address": "2001:db8::1"},
        ),
        (
            incus_network_mod.network_peer_list,
            ("net one", 2),
            "/networks/net%20one/peers",
            {"recursion": 2},
            "peers",
            ["peer one"],
        ),
        (
            incus_network_mod.network_peer_get,
            ("net one", "peer one"),
            "/networks/net%20one/peers/peer%20one",
            None,
            "peer",
            {"name": "peer one"},
        ),
        (
            incus_network_mod.network_zone_list,
            (1,),
            "/network-zones",
            {"recursion": 1},
            "zones",
            ["example.test"],
        ),
        (
            incus_network_mod.network_zone_get,
            ("example test",),
            "/network-zones/example%20test",
            None,
            "zone",
            {"name": "example test"},
        ),
        (
            incus_network_mod.network_zone_record_list,
            ("example test", 1),
            "/network-zones/example%20test/records",
            {"recursion": 1},
            "records",
            ["www"],
        ),
        (
            incus_network_mod.network_zone_record_get,
            ("example test", "www one"),
            "/network-zones/example%20test/records/www%20one",
            None,
            "record",
            {"name": "www one"},
        ),
    ],
)
def test_network_queries(client, function, args, path, params, result_key, metadata):
    client._request.return_value = {"error_code": 0, "metadata": metadata}

    assert function(*args) == {"success": True, result_key: metadata}
    if params is None:
        client._request.assert_called_once_with("GET", path)
    else:
        client._request.assert_called_once_with("GET", path, params=params)


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (incus_network_mod.network_list, ()),
        (incus_network_mod.network_create, ("net",)),
        (incus_network_mod.network_get, ("net",)),
        (incus_network_mod.network_delete, ("net",)),
        (incus_network_mod.network_update, ("net", {})),
        (incus_network_mod.network_rename, ("net", "new")),
        (incus_network_mod.network_state, ("net",)),
        (incus_network_mod.network_lease_list, ("net",)),
        (incus_network_mod.network_acl_list, ()),
        (incus_network_mod.network_acl_get, ("acl",)),
        (incus_network_mod.network_acl_create, ("acl",)),
        (incus_network_mod.network_acl_update, ("acl",)),
        (incus_network_mod.network_acl_delete, ("acl",)),
        (incus_network_mod.network_acl_rename, ("acl", "new")),
        (incus_network_mod.network_forward_list, ("net",)),
        (incus_network_mod.network_forward_get, ("net", "192.0.2.1")),
        (incus_network_mod.network_forward_create, ("net", "192.0.2.1")),
        (incus_network_mod.network_forward_update, ("net", "192.0.2.1")),
        (incus_network_mod.network_forward_delete, ("net", "192.0.2.1")),
        (incus_network_mod.network_peer_list, ("net",)),
        (incus_network_mod.network_peer_get, ("net", "peer")),
        (incus_network_mod.network_peer_create, ("net", "peer")),
        (incus_network_mod.network_peer_update, ("net", "peer")),
        (incus_network_mod.network_peer_delete, ("net", "peer")),
        (incus_network_mod.network_zone_list, ()),
        (incus_network_mod.network_zone_get, ("example.test",)),
        (incus_network_mod.network_zone_create, ("example.test",)),
        (incus_network_mod.network_zone_update, ("example.test",)),
        (incus_network_mod.network_zone_delete, ("example.test",)),
        (incus_network_mod.network_zone_record_list, ("example.test",)),
        (incus_network_mod.network_zone_record_get, ("example.test", "www")),
        (incus_network_mod.network_zone_record_create, ("example.test", "www")),
        (incus_network_mod.network_zone_record_update, ("example.test", "www")),
        (incus_network_mod.network_zone_record_delete, ("example.test", "www")),
    ],
)
def test_network_functions_return_api_errors(client, function, args):
    client._request.return_value = {"error_code": 1, "error": "boom"}
    client._sync_request.return_value = {"error_code": 1, "error": "boom"}

    assert function(*args) == {"success": False, "error": "boom"}


def test_network_create_builds_complete_request(client):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_network_mod.network_create(
        "net one",
        network_type="ovn",
        config={"ipv4.address": "10.0.0.1/24"},
        description="Application network",
    )

    assert result == {"success": True, "message": "Network net one created successfully"}
    client._sync_request.assert_called_once_with(
        "POST",
        "/networks",
        data={
            "name": "net one",
            "type": "ovn",
            "config": {"ipv4.address": "10.0.0.1/24"},
            "description": "Application network",
        },
    )


def test_network_create_uses_defaults(client):
    client._sync_request.return_value = {"error_code": 0}

    incus_network_mod.network_create("net")

    client._sync_request.assert_called_once_with(
        "POST",
        "/networks",
        data={"name": "net", "type": "bridge", "config": {}, "description": ""},
    )


def test_network_update_merges_config_and_preserves_metadata(client):
    client._request.return_value = {
        "error_code": 0,
        "metadata": {
            "name": "net one",
            "type": "bridge",
            "description": "Existing",
            "config": {"ipv4.nat": "true", "ipv6.nat": "true"},
        },
    }
    client._sync_request.return_value = {"error_code": 0}

    result = incus_network_mod.network_update(
        "net one", {"ipv4.nat": "false", "dns.mode": "managed"}
    )

    assert result == {"success": True, "message": "Network net one updated successfully"}
    client._sync_request.assert_called_once_with(
        "PUT",
        "/networks/net%20one",
        data={
            "name": "net one",
            "type": "bridge",
            "description": "Existing",
            "config": {
                "ipv4.nat": "false",
                "ipv6.nat": "true",
                "dns.mode": "managed",
            },
        },
    )


def test_network_update_returns_put_error_after_successful_get(client):
    metadata = {"config": {"ipv4.nat": "true"}}
    client._request.return_value = {"error_code": 0, "metadata": metadata}
    client._sync_request.return_value = {"error_code": 1, "error": "read-only"}

    assert incus_network_mod.network_update("net", {"ipv4.nat": "false"}) == {
        "success": False,
        "error": "read-only",
    }
    client._sync_request.assert_called_once_with(
        "PUT", "/networks/net", data={"config": {"ipv4.nat": "false"}}
    )


@pytest.mark.parametrize(
    ("function", "args", "method", "path", "data", "message"),
    [
        (
            incus_network_mod.network_delete,
            ("net one",),
            "DELETE",
            "/networks/net%20one",
            None,
            "Network net one deleted successfully",
        ),
        (
            incus_network_mod.network_rename,
            ("net one", "net two"),
            "POST",
            "/networks/net%20one",
            {"name": "net two"},
            "Network net one renamed to net two successfully",
        ),
        (
            incus_network_mod.network_acl_delete,
            ("acl one",),
            "DELETE",
            "/network-acls/acl%20one",
            None,
            "Network ACL acl one deleted successfully",
        ),
        (
            incus_network_mod.network_acl_rename,
            ("acl one", "acl two"),
            "POST",
            "/network-acls/acl%20one",
            {"name": "acl two"},
            "Network ACL acl one renamed to acl two successfully",
        ),
        (
            incus_network_mod.network_forward_delete,
            ("net one", "2001:db8::1"),
            "DELETE",
            "/networks/net%20one/forwards/2001%3Adb8%3A%3A1",
            None,
            "Network forward 2001:db8::1 deleted successfully",
        ),
        (
            incus_network_mod.network_peer_delete,
            ("net one", "peer one"),
            "DELETE",
            "/networks/net%20one/peers/peer%20one",
            None,
            "Network peer peer one deleted successfully",
        ),
        (
            incus_network_mod.network_zone_delete,
            ("example test",),
            "DELETE",
            "/network-zones/example%20test",
            None,
            "Network zone example test deleted successfully",
        ),
        (
            incus_network_mod.network_zone_record_delete,
            ("example test", "www one"),
            "DELETE",
            "/network-zones/example%20test/records/www%20one",
            None,
            "Network zone record www one deleted successfully",
        ),
    ],
)
def test_simple_network_mutations(
    client, function, args, method, path, data, message
):
    client._sync_request.return_value = {"error_code": 0}

    assert function(*args) == {"success": True, "message": message}
    if data is None:
        client._sync_request.assert_called_once_with(method, path)
    else:
        client._sync_request.assert_called_once_with(method, path, data=data)


@pytest.mark.parametrize(
    ("function", "args", "path", "data", "message"),
    [
        (
            incus_network_mod.network_acl_create,
            ("acl one", {"user.note": "test"}, "ACL", [{"action": "deny"}], [{"action": "allow"}]),
            "/network-acls",
            {
                "name": "acl one",
                "config": {"user.note": "test"},
                "description": "ACL",
                "egress": [{"action": "deny"}],
                "ingress": [{"action": "allow"}],
            },
            "Network ACL acl one created successfully",
        ),
        (
            incus_network_mod.network_forward_create,
            ("net one", "192.0.2.1", {"user.note": "test"}, "Forward", [{"protocol": "tcp"}]),
            "/networks/net%20one/forwards",
            {
                "listen_address": "192.0.2.1",
                "config": {"user.note": "test"},
                "description": "Forward",
                "ports": [{"protocol": "tcp"}],
            },
            "Network forward 192.0.2.1 created successfully",
        ),
        (
            incus_network_mod.network_peer_create,
            ("net one", "peer one", {"user.note": "test"}, "Peer", "target net", "target project"),
            "/networks/net%20one/peers",
            {
                "name": "peer one",
                "config": {"user.note": "test"},
                "description": "Peer",
                "target_network": "target net",
                "target_project": "target project",
            },
            "Network peer peer one created successfully",
        ),
        (
            incus_network_mod.network_zone_create,
            ("example.test", {"dns.nameservers": "ns1.example.test"}, "Zone"),
            "/network-zones",
            {
                "name": "example.test",
                "config": {"dns.nameservers": "ns1.example.test"},
                "description": "Zone",
            },
            "Network zone example.test created successfully",
        ),
        (
            incus_network_mod.network_zone_record_create,
            (
                "example test",
                "www one",
                {"user.note": "test"},
                "Record",
                [{"type": "A", "value": "192.0.2.2"}],
            ),
            "/network-zones/example%20test/records",
            {
                "name": "www one",
                "config": {"user.note": "test"},
                "description": "Record",
                "entries": [{"type": "A", "value": "192.0.2.2"}],
            },
            "Network zone record www one created successfully",
        ),
    ],
)
def test_resource_create_builds_complete_request(
    client, function, args, path, data, message
):
    client._sync_request.return_value = {"error_code": 0}

    assert function(*args) == {"success": True, "message": message}
    client._sync_request.assert_called_once_with("POST", path, data=data)


@pytest.mark.parametrize(
    ("function", "args", "path", "data"),
    [
        (
            incus_network_mod.network_acl_create,
            ("acl",),
            "/network-acls",
            {"name": "acl", "config": {}, "description": "", "egress": [], "ingress": []},
        ),
        (
            incus_network_mod.network_forward_create,
            ("net", "192.0.2.1"),
            "/networks/net/forwards",
            {"listen_address": "192.0.2.1", "config": {}, "description": "", "ports": []},
        ),
        (
            incus_network_mod.network_peer_create,
            ("net", "peer"),
            "/networks/net/peers",
            {"name": "peer", "config": {}, "description": ""},
        ),
        (
            incus_network_mod.network_zone_create,
            ("example.test",),
            "/network-zones",
            {"name": "example.test", "config": {}, "description": ""},
        ),
        (
            incus_network_mod.network_zone_record_create,
            ("example.test", "www"),
            "/network-zones/example.test/records",
            {"name": "www", "config": {}, "description": "", "entries": []},
        ),
    ],
)
def test_resource_create_uses_defaults(client, function, args, path, data):
    client._sync_request.return_value = {"error_code": 0}

    function(*args)

    client._sync_request.assert_called_once_with("POST", path, data=data)


@pytest.mark.parametrize(
    ("getter_name", "function", "args", "resource_key", "path", "message"),
    [
        (
            "network_acl_get",
            incus_network_mod.network_acl_update,
            ("acl one",),
            "acl",
            "/network-acls/acl%20one",
            "Network ACL acl one updated successfully",
        ),
        (
            "network_forward_get",
            incus_network_mod.network_forward_update,
            ("net one", "2001:db8::1"),
            "forward",
            "/networks/net%20one/forwards/2001%3Adb8%3A%3A1",
            "Network forward 2001:db8::1 updated successfully",
        ),
        (
            "network_peer_get",
            incus_network_mod.network_peer_update,
            ("net one", "peer one"),
            "peer",
            "/networks/net%20one/peers/peer%20one",
            "Network peer peer one updated successfully",
        ),
        (
            "network_zone_get",
            incus_network_mod.network_zone_update,
            ("example test",),
            "zone",
            "/network-zones/example%20test",
            "Network zone example test updated successfully",
        ),
        (
            "network_zone_record_get",
            incus_network_mod.network_zone_record_update,
            ("example test", "www one"),
            "record",
            "/network-zones/example%20test/records/www%20one",
            "Network zone record www one updated successfully",
        ),
    ],
)
def test_resource_update_merges_and_replaces_requested_fields(
    client,
    monkeypatch,
    getter_name,
    function,
    args,
    resource_key,
    path,
    message,
):
    original = {
        "config": {"old": "keep"},
        "description": "old",
        "egress": ["old"],
        "ingress": ["old"],
        "ports": ["old"],
        "target_network": "old",
        "target_project": "old",
        "entries": ["old"],
    }
    monkeypatch.setattr(
        incus_network_mod,
        getter_name,
        Mock(return_value={"success": True, resource_key: original}),
    )
    client._sync_request.return_value = {"error_code": 0}

    if function is incus_network_mod.network_acl_update:
        result = function(*args, config={"new": "value"}, description="", egress=[], ingress=[])
        changed = {"description": "", "egress": [], "ingress": []}
    elif function is incus_network_mod.network_forward_update:
        result = function(*args, config={"new": "value"}, description="", ports=[])
        changed = {"description": "", "ports": []}
    elif function is incus_network_mod.network_peer_update:
        result = function(
            *args,
            config={"new": "value"},
            description="",
            target_network="",
            target_project="",
        )
        changed = {
            "description": "",
            "target_network": "",
            "target_project": "",
        }
    elif function is incus_network_mod.network_zone_update:
        result = function(*args, config={"new": "value"}, description="")
        changed = {"description": ""}
    else:
        result = function(*args, config={"new": "value"}, description="", entries=[])
        changed = {"description": "", "entries": []}

    assert result == {"success": True, "message": message}
    expected = {
        "config": {"old": "keep", "new": "value"},
        "description": "old",
        "egress": ["old"],
        "ingress": ["old"],
        "ports": ["old"],
        "target_network": "old",
        "target_project": "old",
        "entries": ["old"],
    }
    expected.update(changed)
    client._sync_request.assert_called_once_with("PUT", path, data=expected)


@pytest.mark.parametrize(
    ("getter_name", "function", "args"),
    [
        ("network_acl_get", incus_network_mod.network_acl_update, ("acl",)),
        (
            "network_forward_get",
            incus_network_mod.network_forward_update,
            ("net", "192.0.2.1"),
        ),
        ("network_peer_get", incus_network_mod.network_peer_update, ("net", "peer")),
        ("network_zone_get", incus_network_mod.network_zone_update, ("example.test",)),
        (
            "network_zone_record_get",
            incus_network_mod.network_zone_record_update,
            ("example.test", "www"),
        ),
    ],
)
def test_resource_update_returns_get_error_without_put(
    client, monkeypatch, getter_name, function, args
):
    error = {"success": False, "error": "missing"}
    monkeypatch.setattr(incus_network_mod, getter_name, Mock(return_value=error))

    assert function(*args) is error
    client._sync_request.assert_not_called()


@pytest.mark.parametrize(
    ("getter_name", "function", "args", "resource_key", "path"),
    [
        (
            "network_acl_get",
            incus_network_mod.network_acl_update,
            ("acl",),
            "acl",
            "/network-acls/acl",
        ),
        (
            "network_forward_get",
            incus_network_mod.network_forward_update,
            ("net", "192.0.2.1"),
            "forward",
            "/networks/net/forwards/192.0.2.1",
        ),
        (
            "network_peer_get",
            incus_network_mod.network_peer_update,
            ("net", "peer"),
            "peer",
            "/networks/net/peers/peer",
        ),
        (
            "network_zone_get",
            incus_network_mod.network_zone_update,
            ("example.test",),
            "zone",
            "/network-zones/example.test",
        ),
        (
            "network_zone_record_get",
            incus_network_mod.network_zone_record_update,
            ("example.test", "www"),
            "record",
            "/network-zones/example.test/records/www",
        ),
    ],
)
def test_resource_update_preserves_unrequested_fields_and_returns_put_error(
    client,
    monkeypatch,
    getter_name,
    function,
    args,
    resource_key,
    path,
):
    current = {
        "config": {"old": "keep"},
        "description": "keep",
        "egress": ["keep"],
        "ingress": ["keep"],
        "ports": ["keep"],
        "target_network": "keep",
        "target_project": "keep",
        "entries": ["keep"],
    }
    monkeypatch.setattr(
        incus_network_mod,
        getter_name,
        Mock(return_value={"success": True, resource_key: current}),
    )
    client._sync_request.return_value = {"error_code": 1, "error": "read-only"}

    assert function(*args) == {"success": False, "error": "read-only"}
    client._sync_request.assert_called_once_with("PUT", path, data=current)
