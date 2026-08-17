from unittest.mock import Mock

import pytest

from incus.states import incus_network_mod

RESOURCE_CASES = [
    pytest.param(
        {
            "present": incus_network_mod.network_present,
            "absent": incus_network_mod.network_absent,
            "args": ("br0",),
            "kwargs": {
                "network_type": "ovn",
                "config": {"enabled": True},
                "description": "desired",
            },
            "current_key": "network",
            "current": {"config": {"enabled": "true"}, "description": "desired"},
            "get": "incus.network_get",
            "create": "incus.network_create",
            "update": "incus.network_update",
            "delete": "incus.network_delete",
            "create_call": (
                ("br0",),
                {
                    "network_type": "ovn",
                    "config": {"enabled": True},
                    "description": "desired",
                },
            ),
            "update_call": (("br0", {"enabled": True}), {}),
            "delete_call": (("br0",), {}),
            "state_name": "br0",
            "change_key": "network",
            "change_value": "br0",
            "label": "Network br0",
            "failure_resource": "network br0",
        },
        id="network",
    ),
    pytest.param(
        {
            "present": incus_network_mod.network_acl_present,
            "absent": incus_network_mod.network_acl_absent,
            "args": ("acl1",),
            "kwargs": {
                "config": {"enabled": True},
                "description": "desired",
                "egress": [{"action": "allow"}],
                "ingress": [{"action": "drop"}],
            },
            "current_key": "acl",
            "current": {
                "config": {"enabled": "true"},
                "description": "desired",
                "egress": [{"action": "allow"}],
                "ingress": [{"action": "drop"}],
            },
            "get": "incus.network_acl_get",
            "create": "incus.network_acl_create",
            "update": "incus.network_acl_update",
            "delete": "incus.network_acl_delete",
            "create_call": (
                ("acl1",),
                {
                    "config": {"enabled": True},
                    "description": "desired",
                    "egress": [{"action": "allow"}],
                    "ingress": [{"action": "drop"}],
                },
            ),
            "update_call": (
                ("acl1",),
                {
                    "config": {"enabled": True},
                    "description": "desired",
                    "egress": [{"action": "allow"}],
                    "ingress": [{"action": "drop"}],
                },
            ),
            "delete_call": (("acl1",), {}),
            "state_name": "acl1",
            "change_key": "acl",
            "change_value": "acl1",
            "label": "Network ACL acl1",
            "failure_resource": "network ACL acl1",
        },
        id="acl",
    ),
    pytest.param(
        {
            "present": incus_network_mod.network_forward_present,
            "absent": incus_network_mod.network_forward_absent,
            "args": ("br0", "192.0.2.10"),
            "kwargs": {
                "config": {"enabled": True},
                "description": "desired",
                "ports": [{"protocol": "tcp", "listen_port": "80"}],
            },
            "current_key": "forward",
            "current": {
                "config": {"enabled": "true"},
                "description": "desired",
                "ports": [{"protocol": "tcp", "listen_port": "80"}],
            },
            "get": "incus.network_forward_get",
            "create": "incus.network_forward_create",
            "update": "incus.network_forward_update",
            "delete": "incus.network_forward_delete",
            "create_call": (
                ("br0", "192.0.2.10"),
                {
                    "config": {"enabled": True},
                    "description": "desired",
                    "ports": [{"protocol": "tcp", "listen_port": "80"}],
                },
            ),
            "update_call": (
                ("br0", "192.0.2.10"),
                {
                    "config": {"enabled": True},
                    "description": "desired",
                    "ports": [{"protocol": "tcp", "listen_port": "80"}],
                },
            ),
            "delete_call": (("br0", "192.0.2.10"), {}),
            "state_name": "br0_192.0.2.10",
            "change_key": "forward",
            "change_value": "192.0.2.10",
            "label": "Network forward 192.0.2.10",
            "failure_resource": "network forward 192.0.2.10",
        },
        id="forward",
    ),
    pytest.param(
        {
            "present": incus_network_mod.network_peer_present,
            "absent": incus_network_mod.network_peer_absent,
            "args": ("br0", "peer1"),
            "kwargs": {
                "config": {"enabled": True},
                "description": "desired",
                "target_network": "br1",
                "target_project": "other",
            },
            "current_key": "peer",
            "current": {
                "config": {"enabled": "true"},
                "description": "desired",
                "target_network": "br1",
                "target_project": "other",
            },
            "get": "incus.network_peer_get",
            "create": "incus.network_peer_create",
            "update": "incus.network_peer_update",
            "delete": "incus.network_peer_delete",
            "create_call": (
                ("br0", "peer1"),
                {
                    "config": {"enabled": True},
                    "description": "desired",
                    "target_network": "br1",
                    "target_project": "other",
                },
            ),
            "update_call": (
                ("br0", "peer1"),
                {
                    "config": {"enabled": True},
                    "description": "desired",
                    "target_network": "br1",
                    "target_project": "other",
                },
            ),
            "delete_call": (("br0", "peer1"), {}),
            "state_name": "br0_peer1",
            "change_key": "peer",
            "change_value": "peer1",
            "label": "Network peer peer1",
            "failure_resource": "network peer peer1",
        },
        id="peer",
    ),
    pytest.param(
        {
            "present": incus_network_mod.network_zone_present,
            "absent": incus_network_mod.network_zone_absent,
            "args": ("example.com",),
            "kwargs": {"config": {"enabled": True}, "description": "desired"},
            "current_key": "zone",
            "current": {"config": {"enabled": "true"}, "description": "desired"},
            "get": "incus.network_zone_get",
            "create": "incus.network_zone_create",
            "update": "incus.network_zone_update",
            "delete": "incus.network_zone_delete",
            "create_call": (
                ("example.com",),
                {"config": {"enabled": True}, "description": "desired"},
            ),
            "update_call": (
                ("example.com",),
                {"config": {"enabled": True}, "description": "desired"},
            ),
            "delete_call": (("example.com",), {}),
            "state_name": "example.com",
            "change_key": "zone",
            "change_value": "example.com",
            "label": "Network zone example.com",
            "failure_resource": "network zone example.com",
        },
        id="zone",
    ),
    pytest.param(
        {
            "present": incus_network_mod.network_zone_record_present,
            "absent": incus_network_mod.network_zone_record_absent,
            "args": ("example.com", "www"),
            "kwargs": {
                "config": {"enabled": True},
                "description": "desired",
                "entries": [{"type": "A", "value": "192.0.2.10"}],
            },
            "current_key": "record",
            "current": {
                "config": {"enabled": "true"},
                "description": "desired",
                "entries": [{"type": "A", "value": "192.0.2.10"}],
            },
            "get": "incus.network_zone_record_get",
            "create": "incus.network_zone_record_create",
            "update": "incus.network_zone_record_update",
            "delete": "incus.network_zone_record_delete",
            "create_call": (
                ("example.com", "www"),
                {
                    "config": {"enabled": True},
                    "description": "desired",
                    "entries": [{"type": "A", "value": "192.0.2.10"}],
                },
            ),
            "update_call": (
                ("example.com", "www"),
                {
                    "config": {"enabled": True},
                    "description": "desired",
                    "entries": [{"type": "A", "value": "192.0.2.10"}],
                },
            ),
            "delete_call": (("example.com", "www"), {}),
            "state_name": "example.com_www",
            "change_key": "record",
            "change_value": "www",
            "label": "Network zone record www",
            "failure_resource": "network zone record www",
        },
        id="zone-record",
    ),
]


@pytest.fixture
def state_runtime(monkeypatch):
    suffixes = [
        "network",
        "network_acl",
        "network_forward",
        "network_peer",
        "network_zone",
        "network_zone_record",
    ]
    names = ["incus.network_list"]
    for suffix in suffixes:
        names.extend(
            [
                f"incus.{suffix}_get",
                f"incus.{suffix}_create",
                f"incus.{suffix}_update",
                f"incus.{suffix}_delete",
            ]
        )
    salt_funcs = {name: Mock() for name in names}
    opts = {"test": False}
    monkeypatch.setattr(incus_network_mod, "__salt__", salt_funcs, raising=False)
    monkeypatch.setattr(incus_network_mod, "__opts__", opts, raising=False)
    return salt_funcs, opts


def _assert_called(mock, expected_call):
    args, kwargs = expected_call
    mock.assert_called_once_with(*args, **kwargs)


def test_virtual_loads_only_with_network_execution_functions(monkeypatch):
    monkeypatch.setattr(
        incus_network_mod,
        "__salt__",
        {"incus.network_list": Mock()},
        raising=False,
    )
    assert incus_network_mod.__virtual__() == "incus"

    monkeypatch.setattr(incus_network_mod, "__salt__", {}, raising=False)
    assert incus_network_mod.__virtual__() == (
        False,
        "incus network execution functions are not available",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "true"), (False, "false"), (2, "2"), (None, "None")],
)
def test_normalize_config_value(value, expected):
    assert incus_network_mod._normalize_config_value(value) == expected


def test_format_error_message_for_regular_error():
    assert (
        incus_network_mod._format_error_message("create", "network br0", {"error": "invalid"})
        == "Failed to create network br0: invalid"
    )


def test_format_error_message_enriches_server_errors():
    result = incus_network_mod._format_error_message(
        "create",
        "network br0",
        {"error": "server failed", "error_code": 500},
        extra_info={"type": "ovn"},
    )

    assert result.startswith("Failed to create network br0: server failed")
    assert "Server Error (HTTP 500)" in result
    assert "type: ovn" in result
    assert "Troubleshooting:" in result


@pytest.mark.parametrize("case", RESOURCE_CASES)
def test_network_resource_present_is_idempotent(state_runtime, case):
    salt_funcs, _ = state_runtime
    salt_funcs[case["get"]].return_value = {
        "success": True,
        case["current_key"]: case["current"],
    }

    result = case["present"](*case["args"], **case["kwargs"])

    assert result == {
        "name": case["state_name"],
        "result": True,
        "changes": {},
        "comment": f"{case['label']} already in desired state",
    }
    salt_funcs[case["update"]].assert_not_called()


@pytest.mark.parametrize("case", RESOURCE_CASES)
def test_network_resource_present_test_mode_reports_update(state_runtime, case):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    salt_funcs[case["get"]].return_value = {
        "success": True,
        case["current_key"]: {},
    }

    result = case["present"](*case["args"], **case["kwargs"])

    assert result["name"] == case["state_name"]
    assert result["result"] is None
    assert result["changes"]["config"] == {"enabled": {"old": None, "new": "true"}}
    assert result["changes"]["description"] == {
        "old": "",
        "new": "desired",
    }
    assert result["comment"] == f"{case['label']} would be updated"
    salt_funcs[case["update"]].assert_not_called()


@pytest.mark.parametrize("case", RESOURCE_CASES)
@pytest.mark.parametrize(
    ("update_result", "expected_result", "comment_template"),
    [
        ({"success": True}, True, "{label} updated"),
        (
            {"success": False, "error": "update failed"},
            False,
            "Failed to update {failure_resource}: update failed",
        ),
    ],
)
def test_network_resource_present_update_results(
    state_runtime,
    case,
    update_result,
    expected_result,
    comment_template,
):
    salt_funcs, _ = state_runtime
    salt_funcs[case["get"]].return_value = {
        "success": True,
        case["current_key"]: {},
    }
    salt_funcs[case["update"]].return_value = update_result

    result = case["present"](*case["args"], **case["kwargs"])

    assert result["result"] is expected_result
    assert result["comment"] == comment_template.format(**case)
    _assert_called(salt_funcs[case["update"]], case["update_call"])


@pytest.mark.parametrize("case", RESOURCE_CASES)
def test_network_resource_present_test_mode_reports_creation(state_runtime, case):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    salt_funcs[case["get"]].return_value = {"success": False}

    result = case["present"](*case["args"], **case["kwargs"])

    assert result == {
        "name": case["state_name"],
        "result": None,
        "changes": {
            case["change_key"]: {
                "old": None,
                "new": (
                    {
                        "name": "br0",
                        "type": "ovn",
                        "config": {"enabled": True},
                        "description": "desired",
                    }
                    if case["change_key"] == "network"
                    else case["change_value"]
                ),
            }
        },
        "comment": f"{case['label']} would be created",
    }
    salt_funcs[case["create"]].assert_not_called()


@pytest.mark.parametrize("case", RESOURCE_CASES)
@pytest.mark.parametrize(
    ("create_result", "expected_result", "comment_template"),
    [
        ({"success": True}, True, "{label} created"),
        (
            {"success": False, "error": "create failed", "error_code": 1},
            False,
            "Failed to create {failure_resource}: create failed",
        ),
    ],
)
def test_network_resource_present_creation_results(
    state_runtime,
    case,
    create_result,
    expected_result,
    comment_template,
):
    salt_funcs, _ = state_runtime
    salt_funcs[case["get"]].return_value = {"success": False}
    salt_funcs[case["create"]].return_value = create_result

    result = case["present"](*case["args"], **case["kwargs"])

    assert result["result"] is expected_result
    assert result["comment"] == comment_template.format(**case)
    if expected_result:
        assert result["changes"] == {case["change_key"]: {"old": None, "new": case["change_value"]}}
    else:
        assert not result["changes"]
    _assert_called(salt_funcs[case["create"]], case["create_call"])


@pytest.mark.parametrize("case", RESOURCE_CASES)
@pytest.mark.parametrize(
    ("exists", "test_mode", "delete_result", "expected_result", "comment_template"),
    [
        (False, False, None, True, "{label} already absent"),
        (True, True, None, None, "{label} would be deleted"),
        (True, False, {"success": True}, True, "{label} deleted"),
        (
            True,
            False,
            {"success": False, "error": "delete failed"},
            False,
            "Failed to delete {failure_resource}: delete failed",
        ),
    ],
)
def test_network_resource_absent(
    state_runtime,
    case,
    exists,
    test_mode,
    delete_result,
    expected_result,
    comment_template,
):
    salt_funcs, opts = state_runtime
    opts["test"] = test_mode
    salt_funcs[case["get"]].return_value = {"success": exists}
    if delete_result is not None:
        salt_funcs[case["delete"]].return_value = delete_result

    result = case["absent"](*case["args"])

    assert result["name"] == case["state_name"]
    assert result["result"] is expected_result
    assert result["comment"] == comment_template.format(**case)
    if test_mode or (delete_result and delete_result.get("success")):
        assert result["changes"] == {case["change_key"]: {"old": case["change_value"], "new": None}}
    else:
        assert not result["changes"]
    if delete_result is not None:
        _assert_called(salt_funcs[case["delete"]], case["delete_call"])
    else:
        salt_funcs[case["delete"]].assert_not_called()
