import builtins
import runpy
from unittest.mock import Mock
from unittest.mock import call

import pytest
import requests

from incus.modules import incus_mod


def make_client(**attributes):
    """Create a client without running its network-related constructor."""
    client = object.__new__(incus_mod.IncusClient)
    client._temp_files = []
    client._salt = {}
    for name, value in attributes.items():
        setattr(client, name, value)
    return client


@pytest.mark.parametrize(
    ("has_requests", "expected"),
    [
        (True, "incus"),
        (False, (False, "python-requests is required")),
    ],
)
def test_virtual(monkeypatch, has_requests, expected):
    monkeypatch.setattr(incus_mod, "HAS_REQUESTS", has_requests)

    assert incus_mod.__virtual__() == expected


def test_deep_merge_recursively_merges_without_replacing_nested_mapping():
    base = {
        "connection": {"type": "unix", "socket": "/old/socket"},
        "unchanged": True,
    }
    override = {
        "connection": {"socket": "/new/socket"},
        "new_option": "value",
    }

    result = incus_mod.deep_merge(base, override)

    assert result is base
    assert result == {
        "connection": {"type": "unix", "socket": "/new/socket"},
        "unchanged": True,
        "new_option": "value",
    }


@pytest.mark.parametrize(
    ("base", "override", "expected"),
    [
        ({"option": "old"}, {"option": "new"}, {"option": "new"}),
        ({"option": {}}, {"option": "new"}, {"option": "new"}),
        ({"option": "old"}, {"option": {}}, {"option": {}}),
    ],
)
def test_deep_merge_replaces_non_mapping_values(base, override, expected):
    assert incus_mod.deep_merge(base, override) == expected


def test_load_config_merges_defaults_and_uses_cloud_certificate_fallback(monkeypatch):
    config_get = Mock(
        return_value={
            "connection": {"socket": "/custom/incus.socket"},
            "api_client": {
                "salt_cloud_storage": {
                    "cert": "sdb://incus/cert",
                    "key": "sdb://incus/key",
                }
            },
        }
    )
    client = make_client(_salt={"config.get": config_get})

    result = client._load_config()

    config_get.assert_called_once_with("incus", {})
    assert result["connection"]["type"] == "unix"
    assert result["connection"]["socket"] == "/custom/incus.socket"
    assert result["connection"]["cert_storage"]["cert"] == "sdb://incus/cert"
    assert result["connection"]["cert_storage"]["key"] == "sdb://incus/key"
    assert incus_mod.DEFAULT_CFG["connection"]["cert_storage"]["cert"] is None


@pytest.mark.parametrize(
    "pillar_config",
    [
        {"api_client": "invalid"},
        {"api_client": {"salt_cloud_storage": "invalid"}},
        {
            "connection": {"cert_storage": {"cert": "configured-cert", "key": "configured-key"}},
            "api_client": {"salt_cloud_storage": {"cert": "fallback-cert", "key": "fallback-key"}},
        },
    ],
)
def test_load_config_ignores_inapplicable_cloud_certificate_fallback(pillar_config):
    result = make_client(_salt={"config.get": Mock(return_value=pillar_config)})._load_config()

    if isinstance(pillar_config.get("connection"), dict):
        assert result["connection"]["cert_storage"]["cert"] == "configured-cert"
        assert result["connection"]["cert_storage"]["key"] == "configured-key"


def test_unix_http_connection_connects_to_configured_socket(monkeypatch):
    sock = Mock()
    socket_factory = Mock(return_value=sock)
    monkeypatch.setattr(incus_mod.socket, "socket", socket_factory)
    connection = incus_mod.UnixHTTPConnection("/run/incus/custom.socket")

    connection.connect()

    socket_factory.assert_called_once_with(incus_mod.socket.AF_UNIX, incus_mod.socket.SOCK_STREAM)
    sock.connect.assert_called_once_with("/run/incus/custom.socket")
    assert connection.sock is sock


def test_unix_socket_pool_manager_uses_configured_socket():
    manager = incus_mod.UnixSocketPoolManager("/run/incus/custom.socket")

    from_host = manager.connection_from_host("ignored.example")
    from_url = manager.connection_from_url("https://ignored.example/1.0")

    assert isinstance(from_host, incus_mod.UnixHTTPConnectionPool)
    assert isinstance(from_url, incus_mod.UnixHTTPConnectionPool)
    assert from_host.socket_path == "/run/incus/custom.socket"
    assert from_url.socket_path == "/run/incus/custom.socket"


def test_unix_http_connection_pool_creates_connection_for_its_socket():
    connection_factory = Mock(return_value=Mock())
    pool = incus_mod.UnixHTTPConnectionPool("/run/incus/custom.socket")
    pool.ConnectionCls = connection_factory

    result = pool._new_conn()

    connection_factory.assert_called_once_with(unix_socket="/run/incus/custom.socket")
    assert result is connection_factory.return_value


def test_unix_http_adapter_rewrites_request_url():
    adapter = incus_mod.UnixHTTPAdapter("/run/incus.socket")
    request = Mock(path_url="/1.0/instances?project=default")

    assert adapter.request_url(request, proxies={}) == (
        "http://localhost/1.0/instances?project=default"
    )
    assert adapter.proxy_manager_for("https://proxy.example") is None


def test_create_unix_session_disables_environment_and_mounts_adapter(monkeypatch):
    session = Mock()
    adapter = Mock()
    monkeypatch.setattr(incus_mod.requests, "Session", Mock(return_value=session))
    adapter_factory = Mock(return_value=adapter)
    monkeypatch.setattr(incus_mod, "UnixHTTPAdapter", adapter_factory)
    client = make_client(config={"connection": {"type": "unix", "socket": "/run/incus.socket"}})

    result = client._create_session()

    assert result is session
    assert session.verify is False
    assert session.cert is None
    assert session.trust_env is False
    adapter_factory.assert_called_once_with("/run/incus.socket")
    assert session.mount.call_args_list == [call("http://", adapter), call("https://", adapter)]


def test_client_constructor_uses_explicit_config(monkeypatch):
    session = Mock()
    monkeypatch.setattr(incus_mod.IncusClient, "_load_config", Mock())
    monkeypatch.setattr(incus_mod.IncusClient, "_create_session", Mock(return_value=session))
    monkeypatch.setattr(
        incus_mod.IncusClient,
        "_get_base_url",
        Mock(return_value="http://localhost/1.0"),
    )
    config = {"connection": {"type": "unix"}}

    client = incus_mod.IncusClient(config)

    assert client.config is config
    assert client.session is session
    assert client.base_url == "http://localhost/1.0"
    incus_mod.IncusClient._load_config.assert_not_called()


def test_client_constructor_loads_config_when_not_provided(monkeypatch):
    config = {"connection": {"type": "unix"}}
    monkeypatch.setattr(incus_mod.IncusClient, "_load_config", Mock(return_value=config))
    monkeypatch.setattr(incus_mod.IncusClient, "_create_session", Mock(return_value=Mock()))
    monkeypatch.setattr(
        incus_mod.IncusClient,
        "_get_base_url",
        Mock(return_value="http://localhost/1.0"),
    )

    client = incus_mod.IncusClient()

    assert client.config is config
    incus_mod.IncusClient._load_config.assert_called_once_with()


def test_track_temp_file_ignores_empty_paths():
    client = make_client()

    client._track_temp_file(None)
    client._track_temp_file("/tmp/incus-cert.crt")

    assert client._temp_files == ["/tmp/incus-cert.crt"]


def install_https_storage_helpers(
    monkeypatch,
    *,
    cert=(None, False),
    key=(None, False),
    verify=(True, False),
    paths=None,
):
    """Install the certificate-storage collaborators used by the HTTPS branch."""
    monkeypatch.setattr(incus_mod, "_normalize_cert_storage", Mock(return_value={}), raising=False)

    def resolve(_storage, name, default=None):
        return {"cert": cert, "key": key, "verify": verify}[name]

    monkeypatch.setattr(
        incus_mod, "_resolve_cert_storage_value", Mock(side_effect=resolve), raising=False
    )
    monkeypatch.setattr(
        incus_mod, "_coerce_verify_value", Mock(side_effect=lambda value: value), raising=False
    )
    monkeypatch.setattr(
        incus_mod,
        "_ensure_file_path",
        Mock(side_effect=paths or []),
        raising=False,
    )


def test_create_https_session_requires_certificate_and_key(monkeypatch):
    monkeypatch.setattr(incus_mod.requests, "Session", Mock(return_value=Mock()))
    install_https_storage_helpers(monkeypatch, cert=("certificate", False))
    client = make_client(config={"connection": {"type": "https"}})

    with pytest.raises(ValueError, match="requires both cert and key"):
        client._create_session()


def test_create_https_session_materializes_and_tracks_sdb_values(monkeypatch):
    session = Mock()
    monkeypatch.setattr(incus_mod.requests, "Session", Mock(return_value=session))
    install_https_storage_helpers(
        monkeypatch,
        cert=("certificate-data", True),
        key=("key-data", False),
        verify=("ca-data", True),
        paths=[
            ("/tmp/client.crt", True),
            ("/etc/incus/client.key", False),
            ("/tmp/ca.crt", True),
        ],
    )
    client = make_client(config={"connection": {"type": "https"}})

    result = client._create_session()

    assert result is session
    assert session.cert == ("/tmp/client.crt", "/etc/incus/client.key")
    assert session.verify == "/tmp/ca.crt"
    assert client._temp_files == ["/tmp/client.crt", "/tmp/ca.crt"]


def test_create_https_session_handles_local_certificates_and_boolean_verify(monkeypatch):
    session = Mock()
    monkeypatch.setattr(incus_mod.requests, "Session", Mock(return_value=session))
    install_https_storage_helpers(
        monkeypatch,
        cert=("/etc/incus/client.crt", False),
        key=("key-data", True),
        verify=(False, False),
        paths=[
            ("/etc/incus/client.crt", False),
            ("/tmp/client.key", True),
        ],
    )
    client = make_client(config={"connection": {"type": "https"}})

    result = client._create_session()

    assert result is session
    assert session.cert == ("/etc/incus/client.crt", "/tmp/client.key")
    assert session.verify is False
    assert client._temp_files == ["/tmp/client.key"]


def test_create_https_session_without_client_certificate(monkeypatch):
    session = Mock()
    monkeypatch.setattr(incus_mod.requests, "Session", Mock(return_value=session))
    install_https_storage_helpers(monkeypatch)
    client = make_client(config={"connection": {"type": "https"}})

    assert client._create_session() is session
    assert session.verify is True
    incus_mod._ensure_file_path.assert_not_called()


def test_create_https_session_uses_existing_ca_file(monkeypatch):
    session = Mock()
    monkeypatch.setattr(incus_mod.requests, "Session", Mock(return_value=session))
    install_https_storage_helpers(
        monkeypatch,
        verify=("/etc/incus/ca.crt", False),
        paths=[("/etc/incus/ca.crt", False)],
    )
    client = make_client(config={"connection": {"type": "https"}})

    assert client._create_session() is session
    assert session.verify == "/etc/incus/ca.crt"
    assert not client._temp_files


def test_create_session_rejects_unsupported_connection_type(monkeypatch):
    monkeypatch.setattr(incus_mod.requests, "Session", Mock(return_value=Mock()))
    client = make_client(config={"connection": {"type": "tcp"}})

    with pytest.raises(ValueError, match="Unsupported connection type: tcp"):
        client._create_session()


@pytest.mark.parametrize(
    ("connection", "expected"),
    [
        ({"type": "unix"}, "http://localhost/1.0"),
        ({"type": "https", "url": "https://incus.example:8443/"}, "https://incus.example:8443/1.0"),
    ],
)
def test_get_base_url(connection, expected):
    client = make_client(config={"connection": connection})

    assert client._get_base_url() == expected


def test_get_base_url_rejects_https_without_url():
    client = make_client(config={"connection": {"type": "https"}})

    with pytest.raises(ValueError, match="HTTPS connection requires url="):
        client._get_base_url()


def test_get_base_url_rejects_unsupported_connection_type():
    client = make_client(config={"connection": {"type": "tcp"}})

    with pytest.raises(ValueError, match="Unsupported connection type: tcp"):
        client._get_base_url()


def test_request_builds_url_and_returns_json_response():
    response = Mock()
    response.json.return_value = {"type": "sync", "metadata": {"api_version": "1.0"}}
    session = Mock()
    session.request.return_value = response
    client = make_client(session=session, base_url="https://incus.example/1.0")

    result = client._request("GET", "/instances", params={"project": "default"})

    session.request.assert_called_once_with(
        "GET",
        "https://incus.example/1.0/instances",
        json=None,
        params={"project": "default"},
        timeout=30,
    )
    response.raise_for_status.assert_called_once_with()
    assert result == {"type": "sync", "metadata": {"api_version": "1.0"}}


def test_request_converts_request_exception_to_error_result():
    response = Mock(status_code=404)
    error = requests.exceptions.HTTPError("not found", response=response)
    session = Mock()
    session.request.side_effect = error
    client = make_client(session=session, base_url="https://incus.example/1.0")

    result = client._request("GET", "missing")

    assert result == {"error": "not found", "error_code": 404}


def test_request_uses_base_url_for_empty_endpoint():
    response = Mock()
    response.json.return_value = {"type": "sync"}
    session = Mock()
    session.request.return_value = response
    client = make_client(session=session, base_url="https://incus.example/1.0")

    assert client._request("GET", "") == {"type": "sync"}
    session.request.assert_called_once_with(
        "GET",
        "https://incus.example/1.0",
        json=None,
        params=None,
        timeout=30,
    )


def test_request_logs_structured_server_error(caplog):
    response = Mock(status_code=500)
    response.json.return_value = {
        "error": "database unavailable",
        "metadata": {"err": "storage is offline"},
    }
    error = requests.exceptions.HTTPError("server error", response=response)
    session = Mock()
    session.request.side_effect = error
    client = make_client(session=session, base_url="https://incus.example/1.0")

    result = client._request("POST", "instances", data={"name": "test"})

    assert result == {"error": "server error", "error_code": 500}
    assert "Incus error message: database unavailable" in caplog.text
    assert "Incus metadata error: storage is offline" in caplog.text


def test_request_logs_raw_server_error_body(caplog):
    response = Mock(status_code=503, text="proxy unavailable")
    response.json.side_effect = ValueError("not JSON")
    error = requests.exceptions.HTTPError("service unavailable", response=response)
    session = Mock()
    session.request.side_effect = error
    client = make_client(session=session, base_url="https://incus.example/1.0")

    result = client._request("GET", "instances")

    assert result == {"error": "service unavailable", "error_code": 503}
    assert "Response body (raw): proxy unavailable" in caplog.text


@pytest.mark.parametrize(
    "error_body",
    [
        ["not", "a", "mapping"],
        {},
        {"metadata": "not a mapping"},
        {"metadata": {}},
    ],
)
def test_request_logs_server_error_with_optional_fields_absent(error_body):
    response = Mock(status_code=500)
    response.json.return_value = error_body
    error = requests.exceptions.HTTPError("server error", response=response)
    session = Mock()
    session.request.side_effect = error
    client = make_client(session=session, base_url="https://incus.example/1.0")

    assert client._request("GET", "instances") == {
        "error": "server error",
        "error_code": 500,
    }


def test_request_handles_connection_error_without_response():
    session = Mock()
    session.request.side_effect = requests.exceptions.ConnectionError("offline")
    client = make_client(session=session, base_url="https://incus.example/1.0")

    assert client._request("GET", "instances") == {
        "error": "offline",
        "error_code": None,
    }


def test_wait_for_operation_polls_until_success(monkeypatch):
    client = make_client()
    client._sync_request = Mock(
        side_effect=[
            {"error_code": 0, "metadata": {"status_code": 103}},
            {"error_code": 0, "metadata": {"status_code": 200}, "success": True},
        ]
    )
    sleep = Mock()
    time_mock = Mock()
    time_mock.monotonic.return_value = 0
    time_mock.sleep = sleep
    monkeypatch.setattr(incus_mod, "time", time_mock)

    result = client._wait_for_operation("/1.0/operations/operation-id", interval=0.25)

    assert result == {"error_code": 0, "metadata": {"status_code": 200}, "success": True}
    assert client._sync_request.call_args_list == [
        call("GET", "/operations/operation-id"),
        call("GET", "/operations/operation-id"),
    ]
    sleep.assert_called_once_with(0.25)


def test_wait_for_operation_rejects_invalid_url():
    client = make_client()

    result = client._wait_for_operation("/operations/not-versioned")

    assert result == {
        "success": False,
        "error": "Invalid operation URL: /operations/not-versioned",
    }


def test_wait_for_operation_returns_api_failure():
    client = make_client()
    client._sync_request = Mock(
        return_value={
            "error_code": 0,
            "metadata": {"status_code": 400, "err": "Instance failed to start"},
        }
    )

    result = client._wait_for_operation("/1.0/operations/operation-id")

    assert result == {
        "success": False,
        "operation": {"status_code": 400, "err": "Instance failed to start"},
        "error": "Instance failed to start",
    }


def test_wait_for_operation_times_out(monkeypatch):
    time_mock = Mock()
    time_mock.monotonic.side_effect = [10, 311]
    monkeypatch.setattr(incus_mod, "time", time_mock)
    client = make_client()
    client._sync_request = Mock()

    result = client._wait_for_operation("/1.0/operations/operation-id", timeout=300)

    assert result == {
        "success": False,
        "error": "Timeout waiting for operation to finish",
    }


def test_wait_for_operation_uses_configured_backoff(monkeypatch):
    client = make_client(
        config={
            "connection": {
                "polling": {
                    "operation": {
                        "backoff_enabled": True,
                        "initial_interval": 1,
                        "backoff_factor": 1.5,
                        "max_interval": 30,
                        "jitter": 0,
                    }
                }
            }
        }
    )
    client._sync_request = Mock(
        side_effect=[
            {"error_code": 0, "metadata": {"status_code": 103}},
            {"error_code": 0, "metadata": {"status_code": 103}},
            {"error_code": 0, "metadata": {"status_code": 200}},
        ]
    )
    time_mock = Mock()
    time_mock.monotonic.return_value = 0
    monkeypatch.setattr(incus_mod, "time", time_mock)

    client._wait_for_operation("/1.0/operations/operation-id")

    assert time_mock.sleep.call_args_list == [call(1), call(1.5)]


def test_wait_for_operation_explicit_options_override_config(monkeypatch):
    client = make_client(
        config={
            "connection": {
                "polling": {
                    "operation": {
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
    client._sync_request = Mock(
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
        initial_interval=2,
        backoff_factor=2,
        jitter=0,
    )

    assert time_mock.sleep.call_args_list == [call(2), call(4)]


def test_wait_for_operation_rejects_both_interval_names():
    client = make_client()

    with pytest.raises(ValueError, match="mutually exclusive"):
        client._wait_for_operation(
            "/1.0/operations/operation-id",
            interval=1,
            initial_interval=2,
        )


def test_wait_for_operation_caps_sleep_at_timeout_and_polls_at_boundary(monkeypatch):
    client = make_client()
    client._sync_request = Mock(
        side_effect=[
            {"error_code": 0, "metadata": {"status_code": 103}},
            {"error_code": 0, "metadata": {"status_code": 200}},
        ]
    )
    time_mock = Mock()
    time_mock.monotonic.side_effect = [0, 0, 0.75, 1]
    monkeypatch.setattr(incus_mod, "time", time_mock)

    result = client._wait_for_operation("/1.0/operations/operation-id", timeout=1)

    assert result["metadata"]["status_code"] == 200
    time_mock.sleep.assert_called_once_with(0.25)


def test_wait_for_operation_returns_request_error():
    client = make_client()
    client._sync_request = Mock(
        return_value={
            "error_code": 503,
            "error": "offline",
        }
    )

    result = client._wait_for_operation("/1.0/operations/operation-id")

    assert result == {
        "success": False,
        "error": "offline",
        "operation": {"error_code": 503, "error": "offline"},
    }


def test_wait_for_operation_returns_success():
    client = make_client()
    client._sync_request = Mock(
        return_value={
            "error_code": 0,
            "metadata": {"status_code": 200},
        }
    )

    result = client._wait_for_operation("/1.0/operations/operation-id")

    assert result == {"error_code": 0, "metadata": {"status_code": 200}}


def test_wait_for_operation_returns_unexpected_status():
    client = make_client()
    client._sync_request = Mock(
        return_value={
            "error_code": 0,
            "metadata": {"status_code": 999},
        }
    )

    result = client._wait_for_operation("/1.0/operations/operation-id")

    assert result == {
        "success": False,
        "operation": {"status_code": 999},
        "error": "Unexpected status_code: 999",
    }


def test_sync_request_waits_for_async_operation():
    client = make_client()
    client._request = Mock(
        return_value={
            "error_code": 0,
            "type": "async",
            "operation": "/1.0/operations/operation-id",
        }
    )
    client._wait_for_operation = Mock(return_value={"success": True})

    result = client._sync_request("POST", "instances", data={"name": "test-instance"})

    client._request.assert_called_once_with(
        "POST", "instances", data={"name": "test-instance"}, params=None
    )
    client._wait_for_operation.assert_called_once_with("/1.0/operations/operation-id")
    assert result == {"success": True}


@pytest.mark.parametrize(
    "response",
    [
        {"error_code": 400, "error": "bad request"},
        {"error_code": 0, "type": "async"},
        {"error_code": 0, "type": "sync", "metadata": {}},
    ],
)
def test_sync_request_returns_response_without_waiting(response):
    client = make_client()
    client._request = Mock(return_value=response)
    client._wait_for_operation = Mock()

    assert client._sync_request("GET", "instances") is response
    client._wait_for_operation.assert_not_called()


def test_client_factory_constructs_client(monkeypatch):
    client = Mock()
    client_factory = Mock(return_value=client)
    salt_funcs = {"test.ping": Mock()}
    monkeypatch.setattr(incus_mod, "IncusClient", client_factory)
    monkeypatch.setattr(incus_mod, "__salt__", salt_funcs, raising=False)

    assert incus_mod._client() is client
    client_factory.assert_called_once_with(salt_funcs=salt_funcs)


def test_close_closes_session_and_removes_temporary_files(monkeypatch):
    session = Mock()
    unlink = Mock()
    monkeypatch.setattr(incus_mod.os, "unlink", unlink)
    client = make_client(session=session)
    client._temp_files = ["/tmp/incus-cert.crt", "/tmp/incus-key.key"]

    client.close()

    session.close.assert_called_once_with()
    assert unlink.call_args_list == [call("/tmp/incus-cert.crt"), call("/tmp/incus-key.key")]
    assert not client._temp_files


def test_close_ignores_session_and_unlink_errors(monkeypatch):
    session = Mock()
    session.close.side_effect = RuntimeError("already closed")
    unlink = Mock(side_effect=OSError("already removed"))
    monkeypatch.setattr(incus_mod.os, "unlink", unlink)
    client = make_client(session=session)
    client._temp_files = ["/tmp/missing.crt"]

    client.close()

    assert not client._temp_files


def test_close_without_session_and_destructor(monkeypatch):
    close = Mock()
    client = make_client()
    monkeypatch.setattr(client, "close", close)

    client.__del__()  # pylint: disable=unnecessary-dunder-call

    close.assert_called_once_with()


def test_module_handles_missing_requests_dependency(monkeypatch):
    original_import = builtins.__import__

    def import_without_requests(name, *args, **kwargs):
        if name == "requests":
            raise ImportError("requests is unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_requests)

    # The module records the optional dependency as unavailable before its
    # transport base classes fail to resolve.
    with pytest.raises(NameError, match="HTTPConnection"):
        runpy.run_path(incus_mod.__file__)
