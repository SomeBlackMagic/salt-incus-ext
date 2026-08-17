from unittest.mock import Mock

import pytest

from incus.states import incus_settings_mod


@pytest.fixture
def state_runtime(monkeypatch):
    salt_funcs = {
        "incus.settings_get": Mock(),
        "incus.settings_update": Mock(),
        "incus.settings_set": Mock(),
        "incus.settings_unset": Mock(),
        "incus.settings_replace": Mock(),
    }
    opts = {"test": False}
    monkeypatch.setattr(incus_settings_mod, "__salt__", salt_funcs, raising=False)
    monkeypatch.setattr(incus_settings_mod, "__opts__", opts, raising=False)
    return salt_funcs, opts


def _current_config(salt_funcs, config):
    salt_funcs["incus.settings_get"].return_value = {
        "success": True,
        "settings": {"config": config},
    }


def test_virtual_loads_only_with_settings_execution_functions(monkeypatch):
    monkeypatch.setattr(
        incus_settings_mod,
        "__salt__",
        {"incus.settings_get": Mock()},
        raising=False,
    )
    assert incus_settings_mod.__virtual__() == "incus"

    monkeypatch.setattr(incus_settings_mod, "__salt__", {}, raising=False)
    assert incus_settings_mod.__virtual__() == (
        False,
        "incus settings execution functions are not available",
    )


def test_settings_present_reports_get_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.settings_get"].return_value = {
        "success": False,
        "error": "connection failed",
    }

    result = incus_settings_mod.settings_present("server", {"key": "value"})

    assert result == {
        "name": "server",
        "result": False,
        "changes": {},
        "comment": "Failed to get server settings: connection failed",
    }


@pytest.mark.parametrize("config", [None, {}])
def test_settings_present_is_idempotent_for_empty_config(state_runtime, config):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.settings_get"].return_value = {
        "success": True,
        "settings": None,
    }

    result = incus_settings_mod.settings_present("server", config)

    assert result == {
        "name": "server",
        "result": True,
        "changes": {},
        "comment": "Server settings already in desired state",
    }
    salt_funcs["incus.settings_update"].assert_not_called()


def test_settings_present_is_idempotent_and_normalizes_values(state_runtime):
    salt_funcs, _ = state_runtime
    _current_config(
        salt_funcs,
        {"images.auto_update_interval": "12", "unmanaged": "preserved"},
    )

    result = incus_settings_mod.settings_present("server", {"images.auto_update_interval": 12})

    assert result["result"] is True
    assert not result["changes"]
    assert result["comment"] == "Server settings already in desired state"
    salt_funcs["incus.settings_update"].assert_not_called()


def test_settings_present_test_mode_reports_changes(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _current_config(salt_funcs, {"changed": "old"})
    config = {"changed": "new", "added": 3}

    result = incus_settings_mod.settings_present("server", config)

    assert result == {
        "name": "server",
        "result": None,
        "changes": {
            "config": {
                "changed": {"old": "old", "new": "new"},
                "added": {"old": None, "new": "3"},
            }
        },
        "comment": "Server settings would be updated",
    }
    salt_funcs["incus.settings_update"].assert_not_called()


@pytest.mark.parametrize(
    ("update_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {"config": {"key": {"old": "old", "new": "new"}}},
            "Server settings updated",
        ),
        (
            {"success": False, "error": "update failed"},
            False,
            {},
            "Failed to update server settings: update failed",
        ),
    ],
)
def test_settings_present_update_results(
    state_runtime,
    update_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _current_config(salt_funcs, {"key": "old"})
    salt_funcs["incus.settings_update"].return_value = update_result
    config = {"key": "new"}

    result = incus_settings_mod.settings_present("server", config)

    assert result == {
        "name": "server",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.settings_update"].assert_called_once_with(config)


def test_settings_config_reports_get_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.settings_get"].return_value = {
        "success": False,
        "error": "connection failed",
    }

    result = incus_settings_mod.settings_config("interval", "images.interval", 12)

    assert result["result"] is False
    assert not result["changes"]
    assert result["comment"] == "Failed to get server settings: connection failed"


def test_settings_config_is_idempotent_and_normalizes_value(state_runtime):
    salt_funcs, _ = state_runtime
    _current_config(salt_funcs, {"images.interval": "12"})

    result = incus_settings_mod.settings_config("interval", "images.interval", 12)

    assert result == {
        "name": "interval",
        "result": True,
        "changes": {},
        "comment": "Setting images.interval already has value 12",
    }
    salt_funcs["incus.settings_set"].assert_not_called()


def test_settings_config_test_mode_reports_change(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _current_config(salt_funcs, {})

    result = incus_settings_mod.settings_config("interval", "images.interval", 12)

    assert result == {
        "name": "interval",
        "result": None,
        "changes": {"images.interval": {"old": None, "new": "12"}},
        "comment": "Setting images.interval would be updated",
    }
    salt_funcs["incus.settings_set"].assert_not_called()


@pytest.mark.parametrize(
    ("set_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {"images.interval": {"old": "6", "new": "12"}},
            "Setting images.interval updated to 12",
        ),
        (
            {"success": False, "error": "set failed"},
            False,
            {},
            "Failed to update setting images.interval: set failed",
        ),
    ],
)
def test_settings_config_update_results(
    state_runtime,
    set_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _current_config(salt_funcs, {"images.interval": "6"})
    salt_funcs["incus.settings_set"].return_value = set_result

    result = incus_settings_mod.settings_config("interval", "images.interval", 12)

    assert result == {
        "name": "interval",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.settings_set"].assert_called_once_with("images.interval", 12)


def test_settings_absent_reports_get_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.settings_get"].return_value = {
        "success": False,
        "error": "connection failed",
    }

    result = incus_settings_mod.settings_absent("remove", "obsolete")

    assert result["result"] is False
    assert not result["changes"]
    assert result["comment"] == "Failed to get server settings: connection failed"


def test_settings_absent_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    _current_config(salt_funcs, {})

    result = incus_settings_mod.settings_absent("remove", "obsolete")

    assert result == {
        "name": "remove",
        "result": True,
        "changes": {},
        "comment": "Setting obsolete already absent",
    }
    salt_funcs["incus.settings_unset"].assert_not_called()


def test_settings_absent_test_mode_reports_removal(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _current_config(salt_funcs, {"obsolete": "value"})

    result = incus_settings_mod.settings_absent("remove", "obsolete")

    assert result == {
        "name": "remove",
        "result": None,
        "changes": {"obsolete": {"old": "value", "new": None}},
        "comment": "Setting obsolete would be removed",
    }
    salt_funcs["incus.settings_unset"].assert_not_called()


@pytest.mark.parametrize(
    ("unset_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {"obsolete": {"old": "value", "new": None}},
            "Setting obsolete removed",
        ),
        (
            {"success": False, "error": "unset failed"},
            False,
            {},
            "Failed to remove setting obsolete: unset failed",
        ),
    ],
)
def test_settings_absent_removal_results(
    state_runtime,
    unset_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _current_config(salt_funcs, {"obsolete": "value"})
    salt_funcs["incus.settings_unset"].return_value = unset_result

    result = incus_settings_mod.settings_absent("remove", "obsolete")

    assert result == {
        "name": "remove",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.settings_unset"].assert_called_once_with("obsolete")


def test_settings_managed_reports_get_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.settings_get"].return_value = {
        "success": False,
        "error": "connection failed",
    }

    result = incus_settings_mod.settings_managed("server", {"key": "value"})

    assert result["result"] is False
    assert not result["changes"]
    assert result["comment"] == "Failed to get server settings: connection failed"


def test_settings_managed_is_idempotent_and_normalizes_config(state_runtime):
    salt_funcs, _ = state_runtime
    _current_config(salt_funcs, {"12": "true"})

    result = incus_settings_mod.settings_managed("server", {12: "true"})

    assert result == {
        "name": "server",
        "result": True,
        "changes": {},
        "comment": "Server settings already match desired state exactly",
    }
    salt_funcs["incus.settings_replace"].assert_not_called()


def test_settings_managed_test_mode_reports_add_update_and_remove(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _current_config(salt_funcs, {"changed": "old", "removed": "value"})

    result = incus_settings_mod.settings_managed("server", {"changed": "new", "added": 3})

    assert result == {
        "name": "server",
        "result": None,
        "changes": {
            "config": {
                "changed": {"old": "old", "new": "new"},
                "added": {"old": None, "new": "3"},
                "removed": {"old": "value", "new": None},
            }
        },
        "comment": "Server settings would be replaced",
    }
    salt_funcs["incus.settings_replace"].assert_not_called()


@pytest.mark.parametrize(
    ("replace_result", "expected_result", "expected_changes", "comment"),
    [
        (
            {"success": True},
            True,
            {"config": {"key": {"old": "old", "new": "new"}}},
            "Server settings replaced",
        ),
        (
            {"success": False, "error": "replace failed"},
            False,
            {},
            "Failed to replace server settings: replace failed",
        ),
    ],
)
def test_settings_managed_replace_results(
    state_runtime,
    replace_result,
    expected_result,
    expected_changes,
    comment,
):
    salt_funcs, _ = state_runtime
    _current_config(salt_funcs, {"key": "old"})
    salt_funcs["incus.settings_replace"].return_value = replace_result

    result = incus_settings_mod.settings_managed("server", {"key": "new"})

    assert result == {
        "name": "server",
        "result": expected_result,
        "changes": expected_changes,
        "comment": comment,
    }
    salt_funcs["incus.settings_replace"].assert_called_once_with({"key": "new"})
