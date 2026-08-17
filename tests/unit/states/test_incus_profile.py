from unittest.mock import Mock

import pytest

from incus.states import incus_profile_mod


@pytest.fixture
def state_runtime(monkeypatch):
    salt_funcs = {
        "incus.profile_list": Mock(),
        "incus.profile_get": Mock(),
        "incus.profile_create": Mock(),
        "incus.profile_update": Mock(),
        "incus.profile_delete": Mock(),
    }
    opts = {"test": False}
    monkeypatch.setattr(incus_profile_mod, "__salt__", salt_funcs, raising=False)
    monkeypatch.setattr(incus_profile_mod, "__opts__", opts, raising=False)
    return salt_funcs, opts


def _existing_profile(salt_funcs, **profile):
    salt_funcs["incus.profile_get"].return_value = {
        "success": True,
        "profile": profile,
    }


def test_virtual_loads_only_with_profile_execution_functions(monkeypatch):
    monkeypatch.setattr(
        incus_profile_mod,
        "__salt__",
        {"incus.profile_list": Mock()},
        raising=False,
    )
    assert incus_profile_mod.__virtual__() == "incus"

    monkeypatch.setattr(incus_profile_mod, "__salt__", {}, raising=False)
    assert incus_profile_mod.__virtual__() == (
        False,
        "incus profile execution functions are not available",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "true"), (False, "false"), (4, "4"), (None, "None")],
)
def test_normalize_config_value(value, expected):
    assert incus_profile_mod._normalize_config_value(value) == expected


def test_profile_present_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    _existing_profile(
        salt_funcs,
        config={"security.nesting": "true"},
        devices={"eth0": {"type": "nic", "mtu": "1500"}},
        description="desired",
    )

    result = incus_profile_mod.profile_present(
        "web",
        config={"security.nesting": True},
        devices={"eth0": {"type": "nic", "mtu": 1500}},
        description="desired",
    )

    assert result == {
        "name": "web",
        "result": True,
        "changes": {},
        "comment": "Profile web already in desired state",
    }
    salt_funcs["incus.profile_update"].assert_not_called()


def test_profile_present_updates_all_reconciled_fields(state_runtime):
    salt_funcs, _ = state_runtime
    _existing_profile(
        salt_funcs,
        config={"limits.cpu": "1"},
        devices={"root": {"type": "disk", "pool": "old"}},
        description="old",
    )
    salt_funcs["incus.profile_update"].return_value = {"success": True}
    config = {"limits.cpu": 2}
    devices = {
        "root": {"type": "disk", "pool": "new"},
        "eth0": {"type": "nic"},
    }

    result = incus_profile_mod.profile_present(
        "web",
        config=config,
        devices=devices,
        description="desired",
    )

    assert result == {
        "name": "web",
        "result": True,
        "changes": {
            "config": {"limits.cpu": {"old": "1", "new": "2"}},
            "devices": {
                "root": {"pool": {"old": "old", "new": "new"}},
                "eth0": {"old": None, "new": {"type": "nic"}},
            },
            "description": {"old": "old", "new": "desired"},
        },
        "comment": "Profile web updated",
    }
    salt_funcs["incus.profile_update"].assert_called_once_with(
        "web",
        config=config,
        devices=devices,
        description="desired",
    )


@pytest.mark.parametrize(
    ("test_mode", "update_result", "expected_result", "comment"),
    [
        (True, None, None, "Profile web would be updated"),
        (
            False,
            {"success": False, "error": "update failed"},
            False,
            "Failed to update profile web: update failed",
        ),
    ],
)
def test_profile_present_update_dry_run_and_error(
    state_runtime,
    test_mode,
    update_result,
    expected_result,
    comment,
):
    salt_funcs, opts = state_runtime
    opts["test"] = test_mode
    _existing_profile(salt_funcs, config={"limits.cpu": "1"}, description="desired")
    if update_result is not None:
        salt_funcs["incus.profile_update"].return_value = update_result

    result = incus_profile_mod.profile_present(
        "web", config={"limits.cpu": "2"}, description="desired"
    )

    assert result["result"] is expected_result
    assert result["comment"] == comment
    assert result["changes"] == (
        {"config": {"limits.cpu": {"old": "1", "new": "2"}}} if test_mode else {}
    )
    if test_mode:
        salt_funcs["incus.profile_update"].assert_not_called()


def test_profile_present_test_mode_reports_creation(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    salt_funcs["incus.profile_get"].return_value = {"success": False}
    config = {"limits.cpu": "2"}
    devices = {"eth0": {"type": "nic"}}

    result = incus_profile_mod.profile_present(
        "web",
        config=config,
        devices=devices,
        description="desired",
    )

    assert result == {
        "name": "web",
        "result": None,
        "changes": {
            "profile": {
                "old": None,
                "new": {
                    "name": "web",
                    "config": config,
                    "devices": devices,
                    "description": "desired",
                },
            }
        },
        "comment": "Profile web would be created",
    }
    salt_funcs["incus.profile_create"].assert_not_called()


@pytest.mark.parametrize(
    ("create_result", "expected_result", "comment"),
    [
        ({"success": True}, True, "Profile web created"),
        (
            {"success": False, "error": "create failed"},
            False,
            "Failed to create profile web: create failed",
        ),
    ],
)
def test_profile_present_creation_results(
    state_runtime,
    create_result,
    expected_result,
    comment,
):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.profile_get"].return_value = {"success": False}
    salt_funcs["incus.profile_create"].return_value = create_result

    result = incus_profile_mod.profile_present(
        "web", config={"limits.cpu": "2"}, description="desired"
    )

    assert result["result"] is expected_result
    assert result["comment"] == comment
    assert result["changes"] == (
        {"profile": {"old": None, "new": "web"}} if expected_result else {}
    )
    salt_funcs["incus.profile_create"].assert_called_once_with(
        "web",
        config={"limits.cpu": "2"},
        devices=None,
        description="desired",
    )


@pytest.mark.parametrize(
    ("exists", "test_mode", "delete_result", "expected_result", "comment"),
    [
        (False, False, None, True, "Profile web already absent"),
        (True, True, None, None, "Profile web would be deleted"),
        (True, False, {"success": True}, True, "Profile web deleted"),
        (
            True,
            False,
            {"success": False, "error": "in use"},
            False,
            "Failed to delete profile web: in use",
        ),
    ],
)
def test_profile_absent(
    state_runtime,
    exists,
    test_mode,
    delete_result,
    expected_result,
    comment,
):
    salt_funcs, opts = state_runtime
    opts["test"] = test_mode
    salt_funcs["incus.profile_get"].return_value = {"success": exists}
    if delete_result is not None:
        salt_funcs["incus.profile_delete"].return_value = delete_result

    result = incus_profile_mod.profile_absent("web")

    assert result["result"] is expected_result
    assert result["comment"] == comment
    if test_mode or (delete_result and delete_result.get("success")):
        assert result["changes"] == {"profile": {"old": "web", "new": None}}
    else:
        assert not result["changes"]
    if delete_result is not None:
        salt_funcs["incus.profile_delete"].assert_called_once_with("web")
    else:
        salt_funcs["incus.profile_delete"].assert_not_called()


def test_profile_config_reports_missing_profile(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.profile_get"].return_value = {
        "success": False,
        "error": "not found",
    }

    result = incus_profile_mod.profile_config("web", {"limits.cpu": "2"})

    assert result == {
        "name": "web",
        "result": False,
        "changes": {},
        "comment": "Failed to get profile web: not found",
    }


def test_profile_config_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    _existing_profile(
        salt_funcs,
        config={"security.nesting": "true"},
        description="desired",
    )

    result = incus_profile_mod.profile_config(
        "web", {"security.nesting": True}, description="desired"
    )

    assert result == {
        "name": "web",
        "result": True,
        "changes": {},
        "comment": "Profile web already has desired configuration",
    }
    salt_funcs["incus.profile_update"].assert_not_called()


def test_profile_config_test_mode_reports_config_and_description(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _existing_profile(
        salt_funcs,
        config={"limits.cpu": "1"},
        description="old",
    )

    result = incus_profile_mod.profile_config("web", {"limits.cpu": 2}, description="desired")

    assert result == {
        "name": "web",
        "result": None,
        "changes": {
            "config": {"limits.cpu": {"old": "1", "new": "2"}},
            "description": {"old": "old", "new": "desired"},
        },
        "comment": "Profile web configuration would be updated",
    }
    salt_funcs["incus.profile_update"].assert_not_called()


@pytest.mark.parametrize(
    ("update_result", "expected_result", "comment"),
    [
        ({"success": True}, True, "Profile web configuration updated"),
        (
            {"success": False, "error": "update failed"},
            False,
            "Failed to update profile web: update failed",
        ),
    ],
)
def test_profile_config_update_results(
    state_runtime,
    update_result,
    expected_result,
    comment,
):
    salt_funcs, _ = state_runtime
    _existing_profile(
        salt_funcs,
        config={"limits.cpu": "1"},
        description="old",
    )
    salt_funcs["incus.profile_update"].return_value = update_result

    result = incus_profile_mod.profile_config("web", {"limits.cpu": "2"}, description="desired")

    assert result["result"] is expected_result
    assert result["comment"] == comment
    assert result["changes"] == (
        {
            "config": {"limits.cpu": {"old": "1", "new": "2"}},
            "description": {"old": "old", "new": "desired"},
        }
        if expected_result
        else {}
    )
    salt_funcs["incus.profile_update"].assert_called_once_with(
        "web",
        config={"limits.cpu": "2"},
        description="desired",
    )
