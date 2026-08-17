from unittest.mock import Mock

import pytest

from incus.states import incus_cluster_mod


@pytest.fixture
def state_runtime(monkeypatch):
    salt_funcs = {
        "incus.cluster_member_list": Mock(),
        "incus.cluster_member_add": Mock(),
        "incus.cluster_member_remove": Mock(),
    }
    opts = {"test": False}
    monkeypatch.setattr(incus_cluster_mod, "__salt__", salt_funcs, raising=False)
    monkeypatch.setattr(incus_cluster_mod, "__opts__", opts, raising=False)
    return salt_funcs, opts


def test_virtual_loads_when_cluster_execution_functions_are_available(monkeypatch):
    monkeypatch.setattr(
        incus_cluster_mod,
        "__salt__",
        {"incus.cluster_member_list": Mock()},
        raising=False,
    )

    assert incus_cluster_mod.__virtual__() == "incus"


def test_virtual_rejects_missing_cluster_execution_functions(monkeypatch):
    monkeypatch.setattr(incus_cluster_mod, "__salt__", {}, raising=False)

    assert incus_cluster_mod.__virtual__() == (
        False,
        "incus cluster execution functions are not available",
    )


@pytest.mark.parametrize(
    "function",
    [incus_cluster_mod.cluster_member_present, incus_cluster_mod.cluster_member_absent],
)
def test_cluster_states_report_member_list_errors(state_runtime, function):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.cluster_member_list"].return_value = {
        "success": False,
        "error": "cluster unavailable",
    }

    if function is incus_cluster_mod.cluster_member_present:
        result = function("node2", "192.0.2.2")
    else:
        result = function("node2")

    assert result == {
        "name": "node2",
        "result": False,
        "changes": {},
        "comment": "Failed to list cluster members: cluster unavailable",
    }
    salt_funcs["incus.cluster_member_list"].assert_called_once_with(recursion=1)


def test_cluster_member_present_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.cluster_member_list"].return_value = {
        "success": True,
        "members": [{"server_name": "node2"}],
    }

    result = incus_cluster_mod.cluster_member_present("node2", "192.0.2.2")

    assert result == {
        "name": "node2",
        "result": True,
        "changes": {},
        "comment": "Cluster member node2 already exists",
    }
    salt_funcs["incus.cluster_member_add"].assert_not_called()


def test_cluster_member_present_test_mode_reports_planned_change(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    salt_funcs["incus.cluster_member_list"].return_value = {
        "success": True,
        "members": [],
    }

    result = incus_cluster_mod.cluster_member_present("node2", "192.0.2.2")

    assert result == {
        "name": "node2",
        "result": None,
        "changes": {"member": {"old": None, "new": "node2"}},
        "comment": "Cluster member node2 would be added",
    }
    salt_funcs["incus.cluster_member_add"].assert_not_called()


def test_cluster_member_present_adds_member(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.cluster_member_list"].return_value = {
        "success": True,
        "members": None,
    }
    salt_funcs["incus.cluster_member_add"].return_value = {"success": True}

    result = incus_cluster_mod.cluster_member_present(
        "node2",
        "192.0.2.2:8443",
        cluster_password="secret",
    )

    assert result == {
        "name": "node2",
        "result": True,
        "changes": {"member": {"old": None, "new": "node2"}},
        "comment": "Cluster member node2 added",
    }
    salt_funcs["incus.cluster_member_add"].assert_called_once_with(
        "node2",
        "192.0.2.2:8443",
        cluster_password="secret",
    )


def test_cluster_member_present_reports_add_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.cluster_member_list"].return_value = {
        "success": True,
        "members": [],
    }
    salt_funcs["incus.cluster_member_add"].return_value = {
        "success": False,
        "error": "join rejected",
    }

    result = incus_cluster_mod.cluster_member_present("node2", "192.0.2.2")

    assert result == {
        "name": "node2",
        "result": False,
        "changes": {},
        "comment": "Failed to add cluster member node2: join rejected",
    }
    salt_funcs["incus.cluster_member_add"].assert_called_once_with(
        "node2",
        "192.0.2.2",
        cluster_password=None,
    )


def test_cluster_member_absent_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.cluster_member_list"].return_value = {
        "success": True,
        "members": [],
    }

    result = incus_cluster_mod.cluster_member_absent("node2")

    assert result == {
        "name": "node2",
        "result": True,
        "changes": {},
        "comment": "Cluster member node2 already absent",
    }
    salt_funcs["incus.cluster_member_remove"].assert_not_called()


def test_cluster_member_absent_test_mode_reports_planned_change(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    salt_funcs["incus.cluster_member_list"].return_value = {
        "success": True,
        "members": [{"server_name": "node2"}],
    }

    result = incus_cluster_mod.cluster_member_absent("node2", force=True)

    assert result == {
        "name": "node2",
        "result": None,
        "changes": {"member": {"old": "node2", "new": None}},
        "comment": "Cluster member node2 would be removed",
    }
    salt_funcs["incus.cluster_member_remove"].assert_not_called()


def test_cluster_member_absent_removes_member_with_force(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.cluster_member_list"].return_value = {
        "success": True,
        "members": [{"server_name": "node2"}],
    }
    salt_funcs["incus.cluster_member_remove"].return_value = {"success": True}

    result = incus_cluster_mod.cluster_member_absent("node2", force=True)

    assert result == {
        "name": "node2",
        "result": True,
        "changes": {"member": {"old": "node2", "new": None}},
        "comment": "Cluster member node2 removed",
    }
    salt_funcs["incus.cluster_member_remove"].assert_called_once_with("node2", force=True)


def test_cluster_member_absent_reports_remove_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.cluster_member_list"].return_value = {
        "success": True,
        "members": [{"server_name": "node2"}],
    }
    salt_funcs["incus.cluster_member_remove"].return_value = {
        "success": False,
        "error": "member is leader",
    }

    result = incus_cluster_mod.cluster_member_absent("node2")

    assert result == {
        "name": "node2",
        "result": False,
        "changes": {},
        "comment": "Failed to remove cluster member node2: member is leader",
    }
    salt_funcs["incus.cluster_member_remove"].assert_called_once_with("node2", force=False)
