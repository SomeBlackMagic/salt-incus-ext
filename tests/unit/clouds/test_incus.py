from unittest.mock import Mock

import pytest

from incus.clouds import incus_mod


def test_virtual_reports_missing_requests(monkeypatch):
    monkeypatch.setattr(incus_mod, "HAS_REQUESTS", False)
    assert incus_mod.__virtual__() == (
        False,
        "python-requests is required for the Incus cloud driver",
    )


def test_filter_event_safe_falls_back_when_salt_cloud_is_not_initialized(monkeypatch):
    filter_event = Mock(side_effect=NameError("__opts__ is not defined"))
    monkeypatch.setattr(incus_mod.salt.utils.cloud, "filter_event", filter_event)

    assert incus_mod._filter_event_safe(
        "creating",
        {"name": "vm1", "provider": "incus", "secret": "hidden"},
        ["name", "provider"],
    ) == {"name": "vm1", "provider": "incus"}


def test_unix_connection_initializes_socket_attribute():
    connection = incus_mod.UnixHTTPConnection("/tmp/incus-test.socket")
    assert connection.unix_socket == "/tmp/incus-test.socket"
    assert connection.sock is None


def test_unix_pool_manager_ignores_tcp_connection_arguments():
    manager = incus_mod.UnixSocketPoolManager("/tmp/incus-test.socket")

    from_host = manager.connection_from_host(
        "example.invalid",
        port=8443,
        scheme="https",
        pool_kwargs={"timeout": 1},
    )
    from_url = manager.connection_from_url(
        "https://example.invalid:8443",
        pool_kwargs={"timeout": 1},
    )

    assert from_host.socket_path == "/tmp/incus-test.socket"
    assert from_url.socket_path == "/tmp/incus-test.socket"


def test_unix_adapter_callbacks_use_unix_transport():
    adapter = incus_mod.UnixHTTPAdapter("/tmp/incus-test.socket")
    request = Mock(path_url="/1.0/instances?recursion=1")

    assert adapter.poolmanager.socket_path == "/tmp/incus-test.socket"
    assert adapter.proxy_manager_for("http://proxy.invalid") is None
    assert adapter.request_url(request, {"http": "http://proxy.invalid"}) == (
        "http://localhost/1.0/instances?recursion=1"
    )


def test_client_close_tolerates_session_close_error_and_removes_temp_files(tmp_path):
    temp_file = tmp_path / "client.crt"
    temp_file.write_text("certificate", encoding="utf-8")
    client = incus_mod.IncusClient.__new__(incus_mod.IncusClient)
    client.session = Mock()
    client.session.close.side_effect = OSError("already closed")
    client._temp_files = [str(temp_file)]

    client.close()

    assert not temp_file.exists()
    assert not client._temp_files


def test_request_uses_response_text_when_error_body_is_not_json():
    response = Mock(status_code=403, text="certificate is not trusted")
    response.json.side_effect = ValueError("not json")
    error = incus_mod.requests.exceptions.HTTPError("forbidden", response=response)
    session = Mock()
    session.request.side_effect = error
    client = incus_mod.IncusClient.__new__(incus_mod.IncusClient)
    client.session = session
    client.base_url = "https://incus.example.test:8443/1.0"
    client._temp_files = []

    assert client._request("GET", "") == {
        "error": "certificate is not trusted",
        "error_code": 403,
    }


@pytest.mark.parametrize(
    ("function_name", "target_name"),
    [
        ("avail_images", "list_images"),
        ("avail_sizes", "list_sizes"),
    ],
)
def test_avail_helpers_forward_call(monkeypatch, function_name, target_name):
    target = Mock(return_value={"item": {}})
    monkeypatch.setattr(incus_mod, target_name, target)

    assert getattr(incus_mod, function_name)(call="function") == {"item": {}}
    target.assert_called_once_with(call="function")


def test_avail_locations_accepts_call_argument(monkeypatch):
    client = Mock()
    client._request.return_value = {"error_code": 404, "error": "not clustered"}
    monkeypatch.setattr(incus_mod, "_client", Mock(return_value=client))

    assert incus_mod.avail_locations(call="function") == {
        "local": {"name": "local", "description": "Local Incus server"}
    }
