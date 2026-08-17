from unittest.mock import Mock

import pytest

from incus.modules import incus_profile_mod


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    monkeypatch.setattr(incus_profile_mod, "_client", Mock(return_value=client))
    return client


def test_client_creates_incus_client(monkeypatch):
    from incus.modules import incus_mod

    mock_client = Mock()
    monkeypatch.setattr(incus_profile_mod, "__salt__", {}, raising=False)
    monkeypatch.setattr(incus_mod, "IncusClient", Mock(return_value=mock_client))

    assert incus_profile_mod._client() is mock_client


def test_profile_list_passes_recursion_and_returns_metadata(client):
    profiles = [{"name": "default"}, {"name": "web"}]
    client._request.return_value = {"error_code": 0, "metadata": profiles}

    assert incus_profile_mod.profile_list(recursion=2) == {
        "success": True,
        "profiles": profiles,
    }
    client._request.assert_called_once_with("GET", "/profiles", params={"recursion": 2})


def test_profile_list_defaults_to_empty_metadata(client):
    client._request.return_value = {"error_code": 0}

    assert incus_profile_mod.profile_list() == {"success": True, "profiles": []}
    client._request.assert_called_once_with("GET", "/profiles", params={"recursion": 0})


def test_profile_get_quotes_name_and_returns_metadata(client):
    profile = {"name": "web profile", "config": {}, "devices": {}}
    client._request.return_value = {"error_code": 0, "metadata": profile}

    assert incus_profile_mod.profile_get("web profile") == {
        "success": True,
        "profile": profile,
    }
    client._request.assert_called_once_with("GET", "/profiles/web%20profile")


def test_profile_get_defaults_to_empty_metadata(client):
    client._request.return_value = {"error_code": 0}

    assert incus_profile_mod.profile_get("default") == {"success": True, "profile": {}}


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (incus_profile_mod.profile_list, ()),
        (incus_profile_mod.profile_get, ("profile",)),
        (incus_profile_mod.profile_create, ("profile",)),
        (incus_profile_mod.profile_rename, ("profile", "new")),
        (incus_profile_mod.profile_delete, ("profile",)),
    ],
)
def test_direct_profile_functions_return_api_errors(client, function, args):
    client._request.return_value = {"error_code": 1, "error": "boom"}
    client._sync_request.return_value = {"error_code": 1, "error": "boom"}

    assert function(*args) == {"success": False, "error": "boom"}


def test_profile_create_builds_complete_request(client):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_profile_mod.profile_create(
        "web profile",
        config={"limits.cpu": "4"},
        devices={"eth0": {"type": "nic", "network": "default"}},
        description="Web servers",
    )

    assert result == {
        "success": True,
        "message": "Profile web profile created successfully",
    }
    client._sync_request.assert_called_once_with(
        "POST",
        "/profiles",
        data={
            "name": "web profile",
            "config": {"limits.cpu": "4"},
            "devices": {"eth0": {"type": "nic", "network": "default"}},
            "description": "Web servers",
        },
    )


@pytest.mark.parametrize("empty_value", [None, {}])
def test_profile_create_normalizes_empty_config_and_devices(client, empty_value):
    client._sync_request.return_value = {"error_code": 0}

    incus_profile_mod.profile_create("profile", config=empty_value, devices=empty_value)

    client._sync_request.assert_called_once_with(
        "POST",
        "/profiles",
        data={"name": "profile", "config": {}, "devices": {}, "description": ""},
    )


def test_profile_update_deep_merges_existing_and_new_devices(client, monkeypatch):
    profile = {
        "name": "web profile",
        "config": {"limits.cpu": "2", "limits.memory": "2GiB"},
        "devices": {
            "root": {"type": "disk", "path": "/", "pool": "default"},
            "eth0": {"type": "nic", "network": "old"},
        },
        "description": "Old",
        "used_by": ["/instances/web"],
    }
    get = Mock(return_value={"success": True, "profile": profile})
    monkeypatch.setattr(incus_profile_mod, "profile_get", get)
    client._sync_request.return_value = {"error_code": 0}

    result = incus_profile_mod.profile_update(
        "web profile",
        config={"limits.cpu": "8"},
        devices={
            "root": {"pool": "fast"},
            "eth1": {"type": "nic", "network": "new"},
        },
        description="",
    )

    assert result == {
        "success": True,
        "message": "Profile web profile updated successfully",
    }
    get.assert_called_once_with("web profile")
    client._sync_request.assert_called_once_with(
        "PUT",
        "/profiles/web%20profile",
        data={
            "name": "web profile",
            "config": {"limits.cpu": "8", "limits.memory": "2GiB"},
            "devices": {
                "root": {"type": "disk", "path": "/", "pool": "fast"},
                "eth0": {"type": "nic", "network": "old"},
                "eth1": {"type": "nic", "network": "new"},
            },
            "description": "",
            "used_by": ["/instances/web"],
        },
    )


def test_profile_update_preserves_unrequested_fields_and_returns_put_error(client, monkeypatch):
    profile = {
        "config": {"limits.cpu": "2"},
        "devices": {"root": {"type": "disk"}},
        "description": "Keep",
    }
    monkeypatch.setattr(
        incus_profile_mod,
        "profile_get",
        Mock(return_value={"success": True, "profile": profile}),
    )
    client._sync_request.return_value = {"error_code": 1, "error": "read-only"}

    assert incus_profile_mod.profile_update("profile") == {
        "success": False,
        "error": "read-only",
    }
    client._sync_request.assert_called_once_with("PUT", "/profiles/profile", data=profile)


def test_profile_update_returns_get_error_without_put(client, monkeypatch):
    error = {"success": False, "error": "missing"}
    monkeypatch.setattr(incus_profile_mod, "profile_get", Mock(return_value=error))

    assert incus_profile_mod.profile_update("missing") is error
    client._sync_request.assert_not_called()


def test_profile_rename_quotes_source_name(client):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_profile_mod.profile_rename("web profile", "web new")

    assert result == {
        "success": True,
        "message": "Profile web profile renamed to web new successfully",
    }
    client._sync_request.assert_called_once_with(
        "POST", "/profiles/web%20profile", data={"name": "web new"}
    )


def test_profile_copy_inherits_source_description(client, monkeypatch):
    source = {
        "config": {"limits.cpu": "4"},
        "devices": {"eth0": {"type": "nic"}},
        "description": "Source profile",
    }
    get = Mock(return_value={"success": True, "profile": source})
    monkeypatch.setattr(incus_profile_mod, "profile_get", get)
    client._sync_request.return_value = {"error_code": 0}

    result = incus_profile_mod.profile_copy("web profile", "web copy")

    assert result == {
        "success": True,
        "message": "Profile web profile copied to web copy successfully",
    }
    get.assert_called_once_with("web profile")
    client._sync_request.assert_called_once_with(
        "POST",
        "/profiles",
        data={
            "name": "web copy",
            "config": {"limits.cpu": "4"},
            "devices": {"eth0": {"type": "nic"}},
            "description": "Source profile",
        },
    )


def test_profile_copy_uses_explicit_empty_description_and_source_defaults(client, monkeypatch):
    monkeypatch.setattr(
        incus_profile_mod,
        "profile_get",
        Mock(return_value={"success": True, "profile": {}}),
    )
    client._sync_request.return_value = {"error_code": 0}

    incus_profile_mod.profile_copy("source", "copy", description="")

    client._sync_request.assert_called_once_with(
        "POST",
        "/profiles",
        data={"name": "copy", "config": {}, "devices": {}, "description": ""},
    )


def test_profile_copy_returns_get_error_without_post(client, monkeypatch):
    error = {"success": False, "error": "missing"}
    monkeypatch.setattr(incus_profile_mod, "profile_get", Mock(return_value=error))

    assert incus_profile_mod.profile_copy("missing", "copy") is error
    client._sync_request.assert_not_called()


def test_profile_copy_returns_post_error(client, monkeypatch):
    monkeypatch.setattr(
        incus_profile_mod,
        "profile_get",
        Mock(return_value={"success": True, "profile": {}}),
    )
    client._sync_request.return_value = {"error_code": 1, "error": "duplicate"}

    assert incus_profile_mod.profile_copy("source", "copy") == {
        "success": False,
        "error": "duplicate",
    }


def test_profile_delete_quotes_name(client):
    client._sync_request.return_value = {"error_code": 0}

    assert incus_profile_mod.profile_delete("web profile") == {
        "success": True,
        "message": "Profile web profile deleted successfully",
    }
    client._sync_request.assert_called_once_with("DELETE", "/profiles/web%20profile")
