from unittest.mock import Mock
from unittest.mock import call

import pytest

from incus.clouds import incus_mod


def make_client(**attributes):
    """Create a client without running its network-related constructor."""
    client = object.__new__(incus_mod.IncusClient)
    client._temp_files = []
    for name, value in attributes.items():
        setattr(client, name, value)
    return client


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


def test_wait_for_operation_uses_backoff(monkeypatch):
    client = make_client(config={})
    client._request = Mock(
        side_effect=[
            {"error_code": 0, "metadata": {"status_code": 103}},
            {"error_code": 0, "metadata": {"status_code": 103}},
            {"error_code": 0, "metadata": {"status_code": 200}},
        ]
    )
    time_mock = Mock()
    time_mock.monotonic.return_value = 0
    monkeypatch.setattr(incus_mod, "time", time_mock)

    client._wait_for_operation(
        "/1.0/operations/operation-id",
        backoff_enabled=True,
        backoff_factor=1.5,
        jitter=0,
    )

    assert time_mock.sleep.call_args_list == [call(1), call(1.5)]


def test_wait_for_ip_kwargs_translates_profile_overrides():
    vm_ = {
        "wait_for_ip_timeout": 90,
        "wait_for_ip_initial_interval": 1,
        "wait_for_ip_backoff_enabled": True,
        "wait_for_ip_backoff_factor": 2,
        "wait_for_ip_max_interval": 10,
        "wait_for_ip_jitter": 0.1,
    }

    assert incus_mod._wait_for_ip_kwargs(vm_) == {
        "timeout": 90,
        "initial_interval": 1,
        "backoff_enabled": True,
        "backoff_factor": 2,
        "max_interval": 10,
        "jitter": 0.1,
    }


def test_wait_for_ip_kwargs_preserves_legacy_interval():
    assert incus_mod._wait_for_ip_kwargs({"wait_for_ip_interval": 4}) == {
        "timeout": 120,
        "interval": 4,
    }


def test_wait_for_ip_uses_provider_backoff(monkeypatch):
    client = make_client(
        config={
            "connection": {
                "polling": {
                    "ip": {
                        "backoff_enabled": True,
                        "initial_interval": 2,
                        "backoff_factor": 1.5,
                        "max_interval": 15,
                        "jitter": 0,
                    }
                }
            }
        }
    )
    client._request = Mock(
        side_effect=[
            {"error_code": 0, "metadata": {"status": "Starting", "network": {}}},
            {"error_code": 0, "metadata": {"status": "Starting", "network": {}}},
            {
                "error_code": 0,
                "metadata": {
                    "status": "Running",
                    "network": {
                        "eth0": {
                            "addresses": [
                                {"family": "inet", "scope": "global", "address": "10.0.0.2"}
                            ]
                        }
                    },
                },
            },
        ]
    )
    time_mock = Mock()
    time_mock.monotonic.return_value = 0
    monkeypatch.setattr(incus_mod, "time", time_mock)

    result = incus_mod._wait_for_ip(client, "vm1")

    assert result == ["10.0.0.2"]
    assert time_mock.sleep.call_args_list == [call(2), call(3)]


def test_wait_for_ip_explicit_options_override_provider(monkeypatch):
    client = make_client(
        config={
            "connection": {
                "polling": {
                    "ip": {
                        "backoff_enabled": True,
                        "initial_interval": 10,
                        "backoff_factor": 3,
                        "max_interval": 30,
                        "jitter": 0,
                    }
                }
            }
        }
    )
    client._request = Mock(
        side_effect=[
            {"error_code": 0, "metadata": {}},
            {"error_code": 0, "metadata": {}},
            {
                "error_code": 0,
                "metadata": {
                    "status": "Running",
                    "network": {
                        "eth0": {
                            "addresses": [
                                {"family": "inet", "scope": "global", "address": "10.0.0.3"}
                            ]
                        }
                    },
                },
            },
        ]
    )
    time_mock = Mock()
    time_mock.monotonic.return_value = 0
    monkeypatch.setattr(incus_mod, "time", time_mock)

    result = incus_mod._wait_for_ip(
        client,
        "vm1",
        initial_interval=1,
        backoff_factor=2,
        jitter=0,
    )

    assert result == ["10.0.0.3"]
    assert time_mock.sleep.call_args_list == [call(1), call(2)]


def test_wait_for_ip_caps_sleep_and_polls_at_timeout_boundary(monkeypatch):
    client = make_client(config={})
    client._request = Mock(
        side_effect=[
            {"error_code": 0, "metadata": {}},
            {
                "error_code": 0,
                "metadata": {
                    "status": "Running",
                    "network": {
                        "eth0": {
                            "addresses": [
                                {"family": "inet", "scope": "global", "address": "10.0.0.4"}
                            ]
                        }
                    },
                },
            },
        ]
    )
    time_mock = Mock()
    time_mock.monotonic.side_effect = [0, 0, 1.75, 2]
    monkeypatch.setattr(incus_mod, "time", time_mock)

    result = incus_mod._wait_for_ip(client, "vm1", timeout=2)

    assert result == ["10.0.0.4"]
    time_mock.sleep.assert_called_once_with(0.25)


def test_wait_for_ip_keeps_final_request_after_timeout(monkeypatch):
    client = make_client(config={})
    client._request = Mock(
        return_value={
            "error_code": 0,
            "metadata": {
                "status": "Stopped",
                "network": {
                    "eth0": {
                        "addresses": [{"family": "inet", "scope": "global", "address": "10.0.0.5"}]
                    }
                },
            },
        }
    )
    time_mock = Mock()
    time_mock.monotonic.side_effect = [0, 1]
    monkeypatch.setattr(incus_mod, "time", time_mock)

    result = incus_mod._wait_for_ip(client, "vm1", timeout=0)

    assert result == ["10.0.0.5"]
    client._request.assert_called_once_with("GET", "/instances/vm1/state")
    time_mock.sleep.assert_not_called()
