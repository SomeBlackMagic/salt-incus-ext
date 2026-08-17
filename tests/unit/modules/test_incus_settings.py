from unittest.mock import Mock

import pytest

from incus.modules import incus_settings_mod


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    monkeypatch.setattr(incus_settings_mod, "_client", Mock(return_value=client))
    return client


def test_client_creates_incus_client(monkeypatch):
    from incus.modules import incus_mod

    mock_client = Mock()
    monkeypatch.setattr(incus_settings_mod, "__salt__", {}, raising=False)
    monkeypatch.setattr(incus_mod, "IncusClient", Mock(return_value=mock_client))

    assert incus_settings_mod._client() is mock_client


def test_settings_get_returns_metadata(client):
    metadata = {
        "config": {
            "core.https_address": "[::]:8443",
            "images.auto_update_cached": "true",
        }
    }
    client._request.return_value = {"error_code": 0, "metadata": metadata}

    assert incus_settings_mod.settings_get() == {
        "success": True,
        "settings": metadata,
    }
    client._request.assert_called_once_with("GET", "")


def test_settings_get_defaults_to_empty_metadata(client):
    client._request.return_value = {"error_code": 0}

    assert incus_settings_mod.settings_get() == {"success": True, "settings": {}}


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "connection failed"}, "connection failed"),
        ({"error_code": 1}, "Failed to get settings"),
    ],
)
def test_settings_get_returns_api_error(client, response, error):
    client._request.return_value = response

    assert incus_settings_mod.settings_get() == {"success": False, "error": error}


@pytest.mark.parametrize("config", [None, {}, [], "invalid", 1])
def test_settings_update_rejects_invalid_config_before_creating_client(monkeypatch, config):
    factory = Mock()
    monkeypatch.setattr(incus_settings_mod, "_client", factory)

    assert incus_settings_mod.settings_update(config) == {
        "success": False,
        "error": "config parameter must be a dictionary",
    }
    factory.assert_not_called()


def test_settings_update_merges_existing_config_and_preserves_metadata(client):
    client._request.return_value = {
        "error_code": 0,
        "metadata": {
            "api_status": "stable",
            "config": {
                "core.https_address": "127.0.0.1:8443",
                "images.auto_update_cached": "false",
            },
        },
    }
    client._sync_request.return_value = {"error_code": 0}

    result = incus_settings_mod.settings_update(
        {
            "core.https_address": "[::]:8443",
            "images.auto_update_interval": "12",
        }
    )

    assert result == {
        "success": True,
        "message": "Server settings updated successfully",
    }
    client._request.assert_called_once_with("GET", "")
    client._sync_request.assert_called_once_with(
        "PUT",
        "",
        data={
            "api_status": "stable",
            "config": {
                "core.https_address": "[::]:8443",
                "images.auto_update_cached": "false",
                "images.auto_update_interval": "12",
            },
        },
    )


def test_settings_update_creates_missing_config_mapping(client):
    client._request.return_value = {
        "error_code": 0,
        "metadata": {"api_status": "stable"},
    }
    client._sync_request.return_value = {"error_code": 0}

    incus_settings_mod.settings_update({"core.https_address": "[::]:8443"})

    client._sync_request.assert_called_once_with(
        "PUT",
        "",
        data={
            "api_status": "stable",
            "config": {"core.https_address": "[::]:8443"},
        },
    )


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "read failed"}, "read failed"),
        ({"error_code": 1}, "Failed to get current settings"),
    ],
)
def test_settings_update_returns_get_error_without_put(client, response, error):
    client._request.return_value = response

    assert incus_settings_mod.settings_update({"key": "value"}) == {
        "success": False,
        "error": error,
    }
    client._sync_request.assert_not_called()


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "write failed"}, "write failed"),
        ({"error_code": 1}, "Failed to update settings"),
    ],
)
def test_settings_update_returns_put_error(client, response, error):
    client._request.return_value = {"error_code": 0, "metadata": {"config": {}}}
    client._sync_request.return_value = response

    assert incus_settings_mod.settings_update({"key": "value"}) == {
        "success": False,
        "error": error,
    }


@pytest.mark.parametrize("key", [None, "", 1, [], {}])
def test_settings_set_rejects_invalid_key(monkeypatch, key):
    update = Mock()
    monkeypatch.setattr(incus_settings_mod, "settings_update", update)

    assert incus_settings_mod.settings_set(key, "value") == {
        "success": False,
        "error": "key parameter must be a non-empty string",
    }
    update.assert_not_called()


@pytest.mark.parametrize(
    ("value", "string_value"),
    [(12, "12"), (True, "True"), (None, "None"), ("zstd", "zstd")],
)
def test_settings_set_converts_value_and_delegates(monkeypatch, value, string_value):
    expected = {"success": True, "message": "updated"}
    update = Mock(return_value=expected)
    monkeypatch.setattr(incus_settings_mod, "settings_update", update)

    assert incus_settings_mod.settings_set("images.option", value) is expected
    update.assert_called_once_with({"images.option": string_value})


@pytest.mark.parametrize("key", [None, "", 1, [], {}])
def test_settings_unset_rejects_invalid_key_before_creating_client(monkeypatch, key):
    factory = Mock()
    monkeypatch.setattr(incus_settings_mod, "_client", factory)

    assert incus_settings_mod.settings_unset(key) == {
        "success": False,
        "error": "key parameter must be a non-empty string",
    }
    factory.assert_not_called()


def test_settings_unset_removes_key_and_preserves_other_data(client):
    client._request.return_value = {
        "error_code": 0,
        "metadata": {
            "api_status": "stable",
            "config": {"remove": "old", "keep": "value"},
        },
    }
    client._sync_request.return_value = {"error_code": 0}

    assert incus_settings_mod.settings_unset("remove") == {
        "success": True,
        "message": 'Configuration key "remove" unset successfully',
    }
    client._sync_request.assert_called_once_with(
        "PUT",
        "",
        data={"api_status": "stable", "config": {"keep": "value"}},
    )


@pytest.mark.parametrize(
    "metadata",
    [{}, {"api_status": "stable"}, {"config": {}}, {"config": {"other": "value"}}],
)
def test_settings_unset_reports_missing_key_without_put(client, metadata):
    client._request.return_value = {"error_code": 0, "metadata": metadata}

    assert incus_settings_mod.settings_unset("missing") == {
        "success": False,
        "error": 'Configuration key "missing" not found',
    }
    client._sync_request.assert_not_called()


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "read failed"}, "read failed"),
        ({"error_code": 1}, "Failed to get current settings"),
    ],
)
def test_settings_unset_returns_get_error_without_put(client, response, error):
    client._request.return_value = response

    assert incus_settings_mod.settings_unset("key") == {
        "success": False,
        "error": error,
    }
    client._sync_request.assert_not_called()


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "write failed"}, "write failed"),
        ({"error_code": 1}, "Failed to update settings"),
    ],
)
def test_settings_unset_returns_put_error_after_removing_key(client, response, error):
    client._request.return_value = {
        "error_code": 0,
        "metadata": {"config": {"key": "value"}},
    }
    client._sync_request.return_value = response

    assert incus_settings_mod.settings_unset("key") == {
        "success": False,
        "error": error,
    }


@pytest.mark.parametrize("config", [None, {}, [], "invalid", 1])
def test_settings_replace_rejects_invalid_config_before_creating_client(monkeypatch, config):
    factory = Mock()
    monkeypatch.setattr(incus_settings_mod, "_client", factory)

    assert incus_settings_mod.settings_replace(config) == {
        "success": False,
        "error": "config parameter must be a dictionary",
    }
    factory.assert_not_called()


def test_settings_replace_replaces_config_and_preserves_metadata(client):
    client._request.return_value = {
        "error_code": 0,
        "metadata": {
            "api_status": "stable",
            "config": {"old": "removed"},
        },
    }
    client._sync_request.return_value = {"error_code": 0}
    replacement = {"core.https_address": "[::]:8443"}

    assert incus_settings_mod.settings_replace(replacement) == {
        "success": True,
        "message": "Server settings replaced successfully",
    }
    client._sync_request.assert_called_once_with(
        "PUT",
        "",
        data={"api_status": "stable", "config": replacement},
    )


def test_settings_replace_handles_missing_metadata(client):
    client._request.return_value = {"error_code": 0}
    client._sync_request.return_value = {"error_code": 0}

    incus_settings_mod.settings_replace({"key": "value"})

    client._sync_request.assert_called_once_with("PUT", "", data={"config": {"key": "value"}})


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "read failed"}, "read failed"),
        ({"error_code": 1}, "Failed to get current settings"),
    ],
)
def test_settings_replace_returns_get_error_without_put(client, response, error):
    client._request.return_value = response

    assert incus_settings_mod.settings_replace({"key": "value"}) == {
        "success": False,
        "error": error,
    }
    client._sync_request.assert_not_called()


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "write failed"}, "write failed"),
        ({"error_code": 1}, "Failed to replace settings"),
    ],
)
def test_settings_replace_returns_put_error(client, response, error):
    client._request.return_value = {"error_code": 0, "metadata": {}}
    client._sync_request.return_value = response

    assert incus_settings_mod.settings_replace({"key": "value"}) == {
        "success": False,
        "error": error,
    }
