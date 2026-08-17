from unittest.mock import Mock
from unittest.mock import call
from unittest.mock import mock_open

import pytest

from incus.modules import incus_image_mod


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    client.base_url = "https://incus.example/1.0"
    monkeypatch.setattr(incus_image_mod, "_client", Mock(return_value=client))
    return client


def test_client_creates_incus_client(monkeypatch):
    from incus.modules import incus_mod

    mock_client = Mock()
    monkeypatch.setattr(incus_image_mod, "__salt__", {}, raising=False)
    monkeypatch.setattr(incus_mod, "IncusClient", Mock(return_value=mock_client))

    assert incus_image_mod._client() is mock_client


@pytest.mark.parametrize(
    ("function", "request_method", "path", "result", "expected"),
    [
        (
            incus_image_mod.image_list,
            "_request",
            "/images",
            {"error_code": 0, "metadata": ["one"]},
            {"success": True, "images": ["one"]},
        ),
        (
            incus_image_mod.image_get,
            "_request",
            "/images/fp%20one",
            {"error_code": 0, "metadata": {"fingerprint": "fp one"}},
            {"success": True, "image": {"fingerprint": "fp one"}},
        ),
        (
            incus_image_mod.image_delete,
            "_sync_request",
            "/images/fp%20one",
            {"error_code": 0},
            {"success": True, "message": "Image fp one deleted successfully"},
        ),
        (
            incus_image_mod.image_alias_list,
            "_request",
            "/images/aliases",
            {"error_code": 0, "metadata": [{"name": "stable"}]},
            {"success": True, "aliases": [{"name": "stable"}]},
        ),
    ],
)
def test_basic_image_queries(client, function, request_method, path, result, expected):
    request = getattr(client, request_method)
    request.return_value = result

    if function in (incus_image_mod.image_list, incus_image_mod.image_alias_list):
        actual = function(recursion=1)
        request.assert_called_once_with("GET", path, params={"recursion": 1})
    else:
        actual = function("fp one")
        request.assert_called_once_with(
            "DELETE" if function is incus_image_mod.image_delete else "GET", path
        )

    assert actual == expected


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (incus_image_mod.image_list, ()),
        (incus_image_mod.image_get, ("fp",)),
        (incus_image_mod.image_delete, ("fp",)),
        (incus_image_mod.image_alias_list, ()),
    ],
)
def test_basic_image_queries_return_api_errors(client, function, args):
    client._request.return_value = {"error_code": 9, "error": "boom"}
    client._sync_request.return_value = {"error_code": 9, "error": "boom"}

    assert function(*args) == {"success": False, "error": "boom"}


def test_image_create_from_file_waits_for_operation_and_adds_aliases(client, monkeypatch):
    response = Mock()
    response.json.return_value = {"type": "async", "operation": "/operations/1"}
    client.session.post.return_value = response
    client._wait_for_operation.return_value = {
        "error_code": 0,
        "metadata": {"metadata": {"fingerprint": "new-fp", "size": 12}},
    }
    client._sync_request.side_effect = [
        {"error_code": 0},
        {"error_code": 1, "error": "duplicate"},
    ]
    opened = mock_open(read_data=b"image")
    monkeypatch.setattr("builtins.open", opened)
    warning = Mock()
    monkeypatch.setattr(incus_image_mod.log, "warning", warning)

    result = incus_image_mod.image_create_from_file(
        "/tmp/image.tar.xz",
        public=True,
        properties={"os": "ubuntu", "release": 24},
        aliases=["stable", "latest"],
    )

    assert result == {
        "success": True,
        "fingerprint": "new-fp",
        "metadata": {"fingerprint": "new-fp", "size": 12},
    }
    opened.assert_called_once_with("/tmp/image.tar.xz", "rb")
    client.session.post.assert_called_once_with(
        "https://incus.example/1.0/images",
        files={"file": opened()},
        headers={
            "X-Incus-public": "1",
            "X-Incus-properties.os": "ubuntu",
            "X-Incus-properties.release": "24",
        },
        timeout=600,
    )
    response.raise_for_status.assert_called_once_with()
    client._wait_for_operation.assert_called_once_with("/operations/1")
    assert client._sync_request.call_args_list == [
        call("POST", "/images/aliases", data={"name": "stable", "target": "new-fp"}),
        call("POST", "/images/aliases", data={"name": "latest", "target": "new-fp"}),
    ]
    warning.assert_called_once_with("Failed to add alias latest: duplicate")


def test_image_create_from_file_handles_sync_response(client, monkeypatch):
    response = Mock()
    response.json.return_value = {"type": "sync", "metadata": {"size": 12}}
    client.session.post.return_value = response
    monkeypatch.setattr("builtins.open", mock_open(read_data=b"image"))

    assert incus_image_mod.image_create_from_file("image.tar", public=False) == {
        "success": True,
        "metadata": {"size": 12},
    }
    assert client.session.post.call_args.kwargs["headers"] == {"X-Incus-public": "0"}
    client._wait_for_operation.assert_not_called()


def test_image_create_from_file_returns_operation_error(client, monkeypatch):
    response = Mock()
    response.json.return_value = {"type": "async", "operation": "/operations/1"}
    client.session.post.return_value = response
    client._wait_for_operation.return_value = {"error_code": 1}
    monkeypatch.setattr("builtins.open", mock_open(read_data=b"image"))

    assert incus_image_mod.image_create_from_file("image.tar") == {
        "success": False,
        "error": "Unknown error",
    }


def test_image_create_from_file_reports_missing_file(client, monkeypatch):
    monkeypatch.setattr("builtins.open", Mock(side_effect=FileNotFoundError))

    assert incus_image_mod.image_create_from_file("missing.tar") == {
        "success": False,
        "error": "File not found: missing.tar",
    }


def test_image_create_from_file_reports_http_errors(client, monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = RuntimeError("upload failed")
    client.session.post.return_value = response
    monkeypatch.setattr("builtins.open", mock_open(read_data=b"image"))

    assert incus_image_mod.image_create_from_file("image.tar") == {
        "success": False,
        "error": "upload failed",
    }


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"server": None, "alias": "ubuntu"}, "Parameter 'server' is required"),
        ({"server": "remote"}, "Either 'alias' or 'fingerprint' must be provided"),
        (
            {"server": "remote", "alias": "ubuntu", "fingerprint": "fp"},
            "Only one of 'alias' or 'fingerprint' may be provided",
        ),
        (
            {"server": "remote", "alias": "ubuntu", "protocol": "ftp"},
            "Invalid protocol 'ftp'",
        ),
        (
            {"server": "remote", "alias": "ubuntu", "image_type": "disk"},
            "Invalid image_type",
        ),
    ],
)
def test_image_create_from_remote_validates_before_creating_client(monkeypatch, kwargs, error):
    factory = Mock()
    monkeypatch.setattr(incus_image_mod, "_client", factory)

    result = incus_image_mod.image_create_from_remote(**kwargs)

    assert result["success"] is False
    assert error in result["error"]
    factory.assert_not_called()


def test_image_create_from_remote_builds_full_request_and_post_processes(client, monkeypatch):
    client._sync_request.side_effect = [
        {"error_code": 0, "metadata": {"metadata": {"fingerprint": "new-fp"}}},
        {"error_code": 1, "error": "alias exists"},
    ]
    update = Mock(return_value={"success": False, "error": "profiles failed"})
    monkeypatch.setattr(incus_image_mod, "image_update", update)
    warning = Mock()
    monkeypatch.setattr(incus_image_mod.log, "warning", warning)

    result = incus_image_mod.image_create_from_remote(
        "https://images.example",
        fingerprint="source-fp",
        protocol="incus",
        image_type="virtual-machine",
        name="custom",
        project="images",
        auto_update=True,
        public=True,
        aliases=["stable"],
        profiles=["default"],
        properties={"os": "ubuntu"},
        compression_algorithm="gzip",
        expires_at="2030-01-01T00:00:00Z",
        format="unified",
        secret="secret",
        certificate="certificate",
        url="https://download.example/image",
    )

    expected_data = {
        "auto_update": True,
        "public": True,
        "source": {
            "type": "image",
            "mode": "pull",
            "server": "https://images.example",
            "protocol": "incus",
            "fingerprint": "source-fp",
            "image_type": "virtual-machine",
            "name": "custom",
            "project": "images",
            "secret": "secret",
            "certificate": "certificate",
            "url": "https://download.example/image",
        },
        "properties": {"os": "ubuntu"},
        "compression_algorithm": "gzip",
        "expires_at": "2030-01-01T00:00:00Z",
        "format": "unified",
    }
    assert client._sync_request.call_args_list == [
        call("POST", "/images", data=expected_data),
        call("POST", "/images/aliases", data={"name": "stable", "target": "new-fp"}),
    ]
    update.assert_called_once_with("new-fp", {"profiles": ["default"]})
    assert warning.call_args_list == [
        call("Failed to add alias stable: alias exists"),
        call("Failed to set profiles on image: profiles failed"),
    ]
    assert result == {
        "success": True,
        "fingerprint": "new-fp",
        "metadata": {"fingerprint": "new-fp"},
    }


def test_image_create_from_remote_uses_alias_and_returns_api_error(client):
    client._sync_request.return_value = {"error_code": 1}

    result = incus_image_mod.image_create_from_remote("remote", alias="ubuntu")

    assert result == {"success": False, "error": "Unknown error"}
    assert client._sync_request.call_args.kwargs["data"] == {
        "auto_update": False,
        "public": False,
        "source": {
            "type": "image",
            "mode": "pull",
            "server": "remote",
            "protocol": "simplestreams",
            "alias": "ubuntu",
        },
    }


def test_image_update_properties_merges_existing_properties(client):
    metadata = {"properties": {"os": "ubuntu"}, "public": False}
    client._request.return_value = {"error_code": 0, "metadata": metadata}
    client._sync_request.return_value = {"error_code": 0}

    result = incus_image_mod.image_update_properties("fp one", {"release": "24.04"})

    assert result == {"success": True, "message": "Image fp one updated successfully"}
    client._sync_request.assert_called_once_with(
        "PUT",
        "/images/fp%20one",
        data={
            "properties": {"os": "ubuntu", "release": "24.04"},
            "public": False,
        },
    )


@pytest.mark.parametrize(
    "function",
    [incus_image_mod.image_update_properties, incus_image_mod.image_set_public],
)
def test_image_metadata_updates_return_read_error(client, function):
    client._request.return_value = {"error": "not found"}
    second_arg = {} if function is incus_image_mod.image_update_properties else True

    assert function("fp", second_arg) == {"success": False, "error": "not found"}


@pytest.mark.parametrize(
    "function",
    [incus_image_mod.image_update_properties, incus_image_mod.image_set_public],
)
def test_image_metadata_updates_return_write_error(client, function):
    client._request.return_value = {"error_code": 0, "metadata": {}}
    client._sync_request.return_value = {"error_code": 1, "error": "write failed"}
    second_arg = {} if function is incus_image_mod.image_update_properties else True

    assert function("fp", second_arg) == {"success": False, "error": "write failed"}


def test_image_set_public_updates_metadata(client):
    client._request.return_value = {"error_code": 0, "metadata": {"public": True}}
    client._sync_request.return_value = {"error_code": 0}

    result = incus_image_mod.image_set_public("fp", public=False)

    assert result == {"success": True, "message": "Image fp set to private"}
    client._sync_request.assert_called_once_with("PUT", "/images/fp", data={"public": False})


def test_image_update_changes_fields_and_synchronizes_aliases(client, monkeypatch):
    client._request.side_effect = [
        {"error_code": 0, "metadata": {"public": False}},
        {
            "error_code": 0,
            "metadata": [
                {"name": "old alias", "target": "fp"},
                {"name": "keep", "target": "fp"},
                {"name": "other", "target": "other-fp"},
                "invalid",
            ],
        },
    ]
    client._sync_request.side_effect = [
        {"error_code": 0},
        {"error_code": 1, "error": "delete failed"},
        {"error_code": 0},
    ]
    warning = Mock()
    monkeypatch.setattr(incus_image_mod.log, "warning", warning)
    update_body = {"public": True, "aliases": ["keep", "new"]}

    result = incus_image_mod.image_update("fp", update_body)

    assert result == {"success": True, "message": "Image fp updated successfully"}
    assert update_body == {"public": True, "aliases": ["keep", "new"]}
    assert client._request.call_args_list == [
        call("GET", "/images/fp"),
        call("GET", "/images/aliases", params={"recursion": 1}),
    ]
    assert client._sync_request.call_args_list == [
        call("PUT", "/images/fp", data={"public": True}),
        call("DELETE", "/images/aliases/old%20alias"),
        call("POST", "/images/aliases", data={"name": "new", "target": "fp"}),
    ]
    warning.assert_called_once_with("Failed to delete alias old alias: delete failed")


def test_image_update_can_only_update_aliases(client):
    client._request.side_effect = [
        {"error_code": 0, "metadata": {}},
        {"error_code": 0, "metadata": []},
    ]
    client._sync_request.return_value = {"error_code": 0}

    incus_image_mod.image_update("fp", {"aliases": ["new"]})

    client._sync_request.assert_called_once_with(
        "POST", "/images/aliases", data={"name": "new", "target": "fp"}
    )


@pytest.mark.parametrize(
    ("requests", "expected_error"),
    [
        ([{"error_code": 1}], "read failed"),
        (
            [
                {"error_code": 0, "metadata": {}},
                {"error_code": 1, "error": "write failed"},
            ],
            "write failed",
        ),
        (
            [
                {"error_code": 0, "metadata": {}},
                {"error_code": 0},
                {"error_code": 1},
            ],
            "Failed to get current aliases",
        ),
    ],
)
def test_image_update_returns_request_errors(client, requests, expected_error):
    if len(requests) == 1:
        requests[0]["error"] = "read failed"
        client._request.return_value = requests[0]
        result = incus_image_mod.image_update("fp", {})
    elif len(requests) == 2:
        client._request.return_value = requests[0]
        client._sync_request.return_value = requests[1]
        result = incus_image_mod.image_update("fp", {"public": True})
    else:
        client._request.side_effect = [requests[0], requests[2]]
        client._sync_request.return_value = requests[1]
        result = incus_image_mod.image_update("fp", {"public": True, "aliases": []})

    assert result == {"success": False, "error": expected_error}


def test_image_update_returns_alias_creation_error(client):
    client._request.side_effect = [
        {"error_code": 0, "metadata": {}},
        {"error_code": 0, "metadata": []},
    ]
    client._sync_request.return_value = {"error_code": 1, "error": "duplicate"}

    assert incus_image_mod.image_update("fp", {"aliases": ["new"]}) == {
        "success": False,
        "error": "Failed to add alias new: duplicate",
    }


@pytest.mark.parametrize(
    ("function", "args", "error"),
    [
        (incus_image_mod.image_alias_get, (None,), "Alias name is required"),
        (incus_image_mod.image_alias_create, (None, "fp"), "Alias name is required"),
        (incus_image_mod.image_alias_create, ("name", None), "Target fingerprint is required"),
        (incus_image_mod.image_alias_update, (None,), "Alias name is required"),
        (
            incus_image_mod.image_alias_rename,
            ("old", None),
            "Both old and new alias names are required",
        ),
        (incus_image_mod.image_alias_delete, (None,), "Alias name is required"),
        (incus_image_mod.image_copy, (None,), "Fingerprint is required"),
        (incus_image_mod.image_export, (None,), "Fingerprint is required"),
        (incus_image_mod.image_refresh, (None,), "Fingerprint is required"),
        (incus_image_mod.image_secret_create, (None,), "Fingerprint is required"),
    ],
)
def test_required_arguments_are_validated(monkeypatch, function, args, error):
    factory = Mock()
    monkeypatch.setattr(incus_image_mod, "_client", factory)

    assert function(*args) == {"success": False, "error": error}
    factory.assert_not_called()


def test_image_alias_get(client):
    client._request.return_value = {"error_code": 0, "metadata": {"name": "ubuntu 24"}}

    assert incus_image_mod.image_alias_get("ubuntu 24") == {
        "success": True,
        "alias": {"name": "ubuntu 24"},
    }
    client._request.assert_called_once_with("GET", "/images/aliases/ubuntu%2024")


def test_image_alias_create_includes_optional_description(client):
    client._sync_request.return_value = {"error_code": 0}

    result = incus_image_mod.image_alias_create("stable", "fp", "Stable image")

    assert result["success"] is True
    client._sync_request.assert_called_once_with(
        "POST",
        "/images/aliases",
        data={"name": "stable", "target": "fp", "description": "Stable image"},
    )


def test_image_alias_create_omits_empty_description(client):
    client._sync_request.return_value = {"error_code": 0}

    incus_image_mod.image_alias_create("stable", "fp")

    assert client._sync_request.call_args.kwargs["data"] == {"name": "stable", "target": "fp"}


def test_image_alias_update_merges_requested_fields(client):
    client._request.return_value = {
        "error_code": 0,
        "metadata": {"target": "old", "description": "old"},
    }
    client._sync_request.return_value = {"error_code": 0}

    result = incus_image_mod.image_alias_update("stable", target="new", description="")

    assert result["success"] is True
    client._sync_request.assert_called_once_with(
        "PUT",
        "/images/aliases/stable",
        data={"target": "new", "description": ""},
    )


def test_image_alias_update_returns_write_error(client):
    client._request.return_value = {"error_code": 0, "metadata": {}}
    client._sync_request.return_value = {"error_code": 1}

    assert incus_image_mod.image_alias_update("stable") == {
        "success": False,
        "error": "Failed to update alias",
    }


@pytest.mark.parametrize(
    ("function", "args", "method", "path", "success_message"),
    [
        (
            incus_image_mod.image_alias_rename,
            ("old", "new"),
            "POST",
            "/images/aliases/old",
            "Image alias old renamed to new successfully",
        ),
        (
            incus_image_mod.image_alias_delete,
            ("stable",),
            "DELETE",
            "/images/aliases/stable",
            "Image alias stable deleted successfully",
        ),
        (
            incus_image_mod.image_refresh,
            ("fp",),
            "PATCH",
            "/images/fp",
            "Image fp refreshed successfully",
        ),
    ],
)
def test_simple_mutations(client, function, args, method, path, success_message):
    client._sync_request.return_value = {"error_code": 0}

    assert function(*args) == {"success": True, "message": success_message}
    expected_data = {"name": "new"} if function is incus_image_mod.image_alias_rename else {}
    if function is incus_image_mod.image_alias_delete:
        client._sync_request.assert_called_once_with(method, path)
    else:
        client._sync_request.assert_called_once_with(method, path, data=expected_data)


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (incus_image_mod.image_alias_get, ("stable",)),
        (incus_image_mod.image_alias_create, ("stable", "fp")),
        (incus_image_mod.image_alias_update, ("stable",)),
        (incus_image_mod.image_alias_rename, ("old", "new")),
        (incus_image_mod.image_alias_delete, ("stable",)),
        (incus_image_mod.image_refresh, ("fp",)),
    ],
)
def test_alias_and_refresh_operations_return_api_errors(client, function, args):
    client._request.return_value = {"error_code": 1, "error": "api failed"}
    client._sync_request.return_value = {"error_code": 1, "error": "api failed"}

    result = function(*args)

    assert result["success"] is False
    assert result["error"] == "api failed"


def test_image_copy_builds_remote_source_and_adds_aliases(client, monkeypatch):
    client._request.return_value = {"error_code": 0, "metadata": {"fingerprint": "source"}}
    client._sync_request.side_effect = [
        {"error_code": 0, "metadata": {"metadata": {"fingerprint": "copied"}}},
        {"error_code": 1, "error": "duplicate"},
    ]
    warning = Mock()
    monkeypatch.setattr(incus_image_mod.log, "warning", warning)

    result = incus_image_mod.image_copy(
        "source",
        target_server="https://target.example",
        target_certificate="cert",
        target_secret="secret",
        aliases=["copy"],
        public=True,
        auto_update=True,
    )

    assert result == {
        "success": True,
        "fingerprint": "copied",
        "message": "Image source copied successfully",
    }
    assert client._sync_request.call_args_list == [
        call(
            "POST",
            "/images",
            data={
                "source": {
                    "type": "copy",
                    "fingerprint": "source",
                    "server": "https://target.example",
                    "mode": "pull",
                    "protocol": "incus",
                    "certificate": "cert",
                    "secret": "secret",
                },
                "public": True,
                "auto_update": True,
            },
        ),
        call("POST", "/images/aliases", data={"name": "copy", "target": "copied"}),
    ]
    warning.assert_called_once_with("Failed to add alias copy: duplicate")


def test_image_copy_uses_source_fingerprint_when_response_has_none(client):
    client._request.return_value = {"error_code": 0, "metadata": {}}
    client._sync_request.return_value = {"error_code": 0, "metadata": {}}

    result = incus_image_mod.image_copy("source")

    assert result["fingerprint"] == "source"
    assert client._sync_request.call_args.kwargs["data"] == {
        "source": {"type": "copy", "fingerprint": "source"},
        "public": False,
        "auto_update": False,
    }


@pytest.mark.parametrize("failure", ["source", "copy"])
def test_image_copy_returns_api_errors(client, failure):
    if failure == "source":
        client._request.return_value = {"error_code": 1, "error": "source failed"}
    else:
        client._request.return_value = {"error_code": 0, "metadata": {}}
        client._sync_request.return_value = {"error_code": 1, "error": "copy failed"}

    result = incus_image_mod.image_copy("fp")

    assert result == {"success": False, "error": f"{failure} failed"}


def test_image_export_returns_content(client):
    response = Mock(content=b"archive")
    client.session.get.return_value = response

    assert incus_image_mod.image_export("fp one") == {
        "success": True,
        "content": b"archive",
    }
    client.session.get.assert_called_once_with(
        "https://incus.example/1.0/images/fp%20one/export",
        stream=True,
        timeout=600,
    )
    response.raise_for_status.assert_called_once_with()


def test_image_export_writes_nonempty_and_empty_chunks(client, monkeypatch):
    response = Mock()
    response.iter_content.return_value = [b"part-one", b"", b"part-two"]
    client.session.get.return_value = response
    opened = mock_open()
    monkeypatch.setattr("builtins.open", opened)

    result = incus_image_mod.image_export("fp", "/tmp/image.tar")

    assert result == {
        "success": True,
        "message": "Image fp exported to /tmp/image.tar",
    }
    opened.assert_called_once_with("/tmp/image.tar", "wb")
    assert opened().write.call_args_list == [call(b"part-one"), call(b""), call(b"part-two")]
    response.iter_content.assert_called_once_with(chunk_size=8192)


def test_image_export_returns_download_or_file_error(client):
    client.session.get.side_effect = RuntimeError("download failed")

    assert incus_image_mod.image_export("fp", "/tmp/image.tar") == {
        "success": False,
        "error": "download failed",
    }


def test_image_secret_create_unwraps_operation_metadata(client):
    client._sync_request.return_value = {
        "error_code": 0,
        "metadata": {"metadata": {"secret": "one-time"}},
    }

    assert incus_image_mod.image_secret_create("fp") == {
        "success": True,
        "secret": {"secret": "one-time"},
    }
    client._sync_request.assert_called_once_with("POST", "/images/fp/secret", data={})


def test_image_secret_create_returns_api_error(client):
    client._sync_request.return_value = {"error_code": 1}

    assert incus_image_mod.image_secret_create("fp") == {
        "success": False,
        "error": "Failed to create image secret",
    }
