"""
Salt execution module for managing Incus containers and VMs via API.

This module provides functions to interact with Incus API for managing:
- Instances (containers and VMs)
- Instance snapshots
- Storage pools and volumes
- Networks
- Profiles
- Cluster members

Supports both local (Unix socket) and remote (HTTPS) connections.

:configuration: Can be configured via pillar or minion config:

    incus:
      connection:
        type: unix  # or https
        socket: /var/lib/incus/unix.socket  # for unix type
        # For HTTPS type:
        # url: https://incus.example.com:8443
        # cert_storage:
        #   type: local_files  # or sdb
        #   cert: /path/to/client.crt
        #   key: /path/to/client.key
        #   verify: True  # or False or /path/to/ca.crt
        polling:
          operation:
            backoff_enabled: true
            initial_interval: 1.0
            backoff_factor: 1.5
            max_interval: 30.0
            jitter: 0.2

:depends: requests
"""

import copy
import json
import logging
import os
import socket
import tempfile
import time
from urllib.parse import urljoin

from incus.utils import redact_sensitive_data
from incus.utils import resolve_polling_settings
from incus.utils import validate_timeout

try:
    import requests
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.connection import HTTPConnection  # pylint: disable=import-error
    from requests.packages.urllib3.connectionpool import (
        HTTPConnectionPool,  # pylint: disable=import-error
    )

    HAS_REQUESTS = True
except Exception:  # pylint: disable=broad-exception-caught
    HAS_REQUESTS = False

log = logging.getLogger(__name__)

__virtualname__ = "incus"


def __virtual__():
    if not HAS_REQUESTS:
        return False, "python-requests is required"
    return __virtualname__


# ==============================================================
# DEFAULT CONFIG + DEEP MERGE
# ==============================================================

INCUS_SOCKET_PATH = "/var/lib/incus/unix.socket"

DEFAULT_CFG = {
    "connection": {
        "type": "unix",  # "unix" | "https"
        "socket": INCUS_SOCKET_PATH,  # path to unix socket
        "url": None,  # https URL for remote, e.g. https://incus.example.com:8443
        "cert_storage": {
            "type": "local_files",  # "local_files" | "sdb"
            "cert": None,  # local path or sdb:// URI for type=sdb
            "key": None,  # local path or sdb:// URI for type=sdb
            "verify": True,  # bool/path or sdb:// URI for type=sdb
        },
        "polling": {
            "operation": {
                "backoff_enabled": False,
                "initial_interval": 1.0,
                "backoff_factor": 1.5,
                "max_interval": 30.0,
                "jitter": 0.2,
            },
            "ip": {
                "backoff_enabled": False,
                "initial_interval": 2.0,
                "backoff_factor": 1.5,
                "max_interval": 15.0,
                "jitter": 0.2,
            },
        },
    }
}


def deep_merge(base, override):
    """
    Recursively merge override into base.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.deep_merge base='{"a": 1}' override='{"b": 2}'
    """
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


# ==============================================================
# CERT STORAGE HELPERS (HTTPS)
# ==============================================================


def _normalize_cert_storage(conn):
    """Extract and return the cert_storage dict from a connection config."""
    return conn.get("cert_storage", {}) or {}


def _resolve_cert_storage_value(cert_storage, key, default=None):
    """
    Return (value, from_sdb) for a cert_storage key.

    If the value starts with "sdb://", it is fetched via Salt SDB and
    from_sdb is set to True so the caller knows the content came from
    an in-memory string (not a file path).
    """
    value = cert_storage.get(key, default)
    if isinstance(value, str) and value.startswith("sdb://"):
        resolved = __salt__["sdb.get"](value)
        return resolved, True
    return value, False


def _write_temp_file(content, suffix):
    """Write *content* to a named temporary file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
    except Exception:  # pylint: disable=broad-exception-caught
        os.unlink(path)
        raise
    return path


def _ensure_file_path(value, suffix, force_temp=False):
    """
    Return (path, is_temp).

    If *force_temp* is True (value is raw content, not a path) the content
    is written to a temporary file.  Otherwise the value is returned as-is
    assuming it is already a filesystem path.
    """
    if force_temp or (isinstance(value, str) and "\n" in value):
        return _write_temp_file(value, suffix), True
    return value, False


def _coerce_verify_value(value):
    """Convert string "true"/"false" to bool; pass through other values."""
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    return value


# ==============================================================
# UNIX SOCKET BACKEND
# ==============================================================


class UnixHTTPConnection(HTTPConnection):
    """
    HTTPConnection over Unix socket.
    """

    def __init__(self, unix_socket=INCUS_SOCKET_PATH, **kwargs):
        # host/port are dummy values, used only for format
        super().__init__("localhost", **kwargs)
        self.unix_socket = unix_socket

    def connect(self):
        self.sock = socket.socket(  # pylint: disable=attribute-defined-outside-init
            socket.AF_UNIX, socket.SOCK_STREAM
        )
        self.sock.connect(self.unix_socket)


class UnixHTTPConnectionPool(HTTPConnectionPool):
    """
    Connection pool returning UnixHTTPConnection.
    """

    ConnectionCls = UnixHTTPConnection

    def __init__(self, socket_path=INCUS_SOCKET_PATH, **kwargs):
        super().__init__("localhost", **kwargs)
        self.socket_path = socket_path

    def _new_conn(self):
        return self.ConnectionCls(unix_socket=self.socket_path)


class UnixSocketPoolManager:
    """
    Minimal PoolManager-compatible object for HTTPAdapter.

    Requests/HTTPAdapter expects poolmanager to have connection_from_host() method,
    which we implement here, returning UnixHTTPConnectionPool.
    """

    def __init__(self, socket_path=INCUS_SOCKET_PATH):
        self.socket_path = socket_path

    def connection_from_host(
        self, host, port=None, scheme="http", pool_kwargs=None
    ):  # pylint: disable=unused-argument
        # host/port/scheme are ignored — we always use unix socket
        return UnixHTTPConnectionPool(self.socket_path)

    def connection_from_url(self, url, pool_kwargs=None):  # pylint: disable=unused-argument
        # url is ignored — we always use unix socket
        return UnixHTTPConnectionPool(self.socket_path)


class UnixHTTPAdapter(HTTPAdapter):
    """
    Requests adapter for Incus via unix socket.
    """

    def __init__(self, socket_path=INCUS_SOCKET_PATH, **kwargs):
        self.socket_path = socket_path
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):  # pylint: disable=unused-argument
        # substitute our custom PoolManager instead of the standard one
        self.poolmanager = UnixSocketPoolManager(
            self.socket_path
        )  # pylint: disable=attribute-defined-outside-init

    def proxy_manager_for(self, *args, **kwargs):  # pylint: disable=unused-argument
        # proxies are not applicable for unix socket
        return None

    def request_url(self, request, proxies):  # pylint: disable=unused-argument
        # Actual transport is AF_UNIX, URL is only needed for formal HTTP
        return "http://localhost" + request.path_url


# ==============================================================
# CLIENT
# ==============================================================


class IncusClient:
    _salt = {}  # default; overridden in __init__ when salt_funcs are provided

    def __init__(self, config=None, salt_funcs=None):
        self._salt = salt_funcs or {}
        self.config = config or self._load_config()
        self._temp_files = []
        self.session = self._create_session()
        self.base_url = self._get_base_url()

    def _track_temp_file(self, path):
        if path:
            self._temp_files.append(path)

    def close(self):
        if getattr(self, "session", None):
            try:
                self.session.close()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        for path in self._temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass
        self._temp_files = []

    def __del__(self):
        self.close()

    def _load_config(self):
        pillar_cfg = self._salt.get("config.get", lambda *_: {})("incus", {})
        merged_cfg = deep_merge(copy.deepcopy(DEFAULT_CFG), pillar_cfg)

        # Optional convenience fallback:
        # api_client.salt_cloud_storage -> connection.cert_storage (cert/key only).
        api_client_cfg = merged_cfg.get("api_client", {})
        conn_cfg = merged_cfg.get("connection", {})
        if isinstance(api_client_cfg, dict) and isinstance(conn_cfg, dict):
            cloud_storage = api_client_cfg.get("salt_cloud_storage", {})
            cert_storage = conn_cfg.get("cert_storage", {})
            if isinstance(cloud_storage, dict) and isinstance(cert_storage, dict):
                if not cert_storage.get("cert") and cloud_storage.get("cert"):
                    cert_storage["cert"] = cloud_storage.get("cert")
                if not cert_storage.get("key") and cloud_storage.get("key"):
                    cert_storage["key"] = cloud_storage.get("key")

        return merged_cfg

    def _create_session(self):
        session = requests.Session()
        conn = self.config.get("connection", {})
        ctype = conn.get("type", "unix")

        # ============================================
        # LOCAL UNIX SOCKET
        # ============================================
        if ctype == "unix":
            adapter = UnixHTTPAdapter(conn.get("socket", INCUS_SOCKET_PATH))

            # Just in case, disable TLS/proxy inheritance from environment
            session.verify = False
            session.cert = None
            session.trust_env = False

            # Mount adapter on both schemes so that any https transitions
            # inside requests don't bypass our adapter
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            return session

        # ============================================
        # REMOTE HTTPS
        # ============================================
        elif ctype == "https":
            cert_storage = _normalize_cert_storage(conn)
            cert_value, cert_from_sdb = _resolve_cert_storage_value(cert_storage, "cert")
            key_value, key_from_sdb = _resolve_cert_storage_value(cert_storage, "key")

            if bool(cert_value) != bool(key_value):
                raise ValueError("HTTPS connection requires both cert and key")

            if cert_value and key_value:
                cert_path, cert_temp = _ensure_file_path(
                    cert_value, ".crt", force_temp=cert_from_sdb
                )
                key_path, key_temp = _ensure_file_path(key_value, ".key", force_temp=key_from_sdb)
                if cert_temp:
                    self._track_temp_file(cert_path)
                if key_temp:
                    self._track_temp_file(key_path)
                session.cert = (cert_path, key_path)

            verify_value, verify_from_sdb = _resolve_cert_storage_value(
                cert_storage, "verify", True
            )
            verify_value = _coerce_verify_value(verify_value)
            if isinstance(verify_value, str):
                verify_path, verify_temp = _ensure_file_path(
                    verify_value,
                    ".crt",
                    force_temp=verify_from_sdb,
                )
                if verify_temp:
                    self._track_temp_file(verify_path)
                session.verify = verify_path
            else:
                session.verify = verify_value
            return session

        raise ValueError(f"Unsupported connection type: {ctype}")

    def _get_base_url(self):
        conn = self.config.get("connection", {})
        ctype = conn.get("type", "unix")

        if ctype == "unix":
            # host is dummy, only path /1.0 matters
            return "http://localhost/1.0"

        if ctype == "https":
            url = conn.get("url")
            if not url:
                raise ValueError("HTTPS connection requires url=")
            return url.rstrip("/") + "/1.0"

        raise ValueError(f"Unsupported connection type: {ctype}")

    # ==========================================================
    # REQUEST API
    # ==========================================================

    def _request(self, method, endpoint, data=None, params=None):
        # Build URL: if endpoint is empty, use base_url as-is
        # Otherwise join with slash separator
        if endpoint:
            url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        else:
            url = self.base_url

        log.debug("Incus API %s %s (params=%s)", method, url, params)

        try:
            response = self.session.request(
                method,
                url,
                json=data,
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:

            # Enhanced error logging for 5xx errors
            if hasattr(e, "response") and e.response is not None:
                status_code = e.response.status_code

                # Log detailed information for server errors (5xx)
                if 500 <= status_code < 600:
                    log.error("=" * 60)
                    log.error("Incus API Server Error (HTTP %d)", status_code)
                    log.error("=" * 60)
                    log.error("Request URL: %s %s", method, url)
                    log.error("Request params: %s", params)
                    log.error(
                        "Request data (JSON): %s",
                        json.dumps(redact_sensitive_data(data), indent=2) if data else "None",
                    )

                    try:
                        error_body = e.response.json()
                        log.error(
                            "Response body: %s",
                            json.dumps(redact_sensitive_data(error_body), indent=2),
                        )

                        # Extract error message from Incus API response
                        if isinstance(error_body, dict):
                            if "error" in error_body:
                                log.error("Incus error message: %s", error_body["error"])
                            if "metadata" in error_body and isinstance(
                                error_body["metadata"], dict
                            ):
                                if "err" in error_body["metadata"]:
                                    log.error(
                                        "Incus metadata error: %s", error_body["metadata"]["err"]
                                    )
                    except Exception:  # pylint: disable=broad-exception-caught
                        # If response is not JSON, log raw text
                        log.error("Response body (raw): %s", e.response.text)

                    log.error("=" * 60)

            return {
                "error": str(e),
                "error_code": getattr(getattr(e, "response", None), "status_code", None),
            }

    def _wait_for_operation(
        self,
        operation_url,
        timeout=300,
        interval=None,
        *,
        initial_interval=None,
        backoff_enabled=None,
        backoff_factor=None,
        max_interval=None,
        jitter=None,
    ):
        """
        Wait for an Incus async operation to finish.

        :param operation_url: e.g. "/1.0/operations/abc-123"
        :param timeout: maximum seconds to wait
        :param interval: deprecated alias for initial_interval
        :param initial_interval: first polling interval
        :param backoff_enabled: whether to increase the interval after each poll
        :param backoff_factor: exponential interval multiplier
        :param max_interval: maximum interval before jitter
        :param jitter: fractional random variation applied after the first interval
        :return: dict {
            "success": bool,
            "operation": <operation dict>,
            "error": <error or None>
        }

        Incus operation states:
          100 - Operation created
          101 - Started
          103 - Running
          200 - Success
          400 - Failure
        """

        defaults = DEFAULT_CFG["connection"]["polling"]["operation"]
        connection = getattr(self, "config", {}).get("connection", {})
        settings = connection.get("polling", {}).get("operation", {})
        polling = resolve_polling_settings(
            settings,
            defaults,
            interval=interval,
            initial_interval=initial_interval,
            backoff_enabled=backoff_enabled,
            backoff_factor=backoff_factor,
            max_interval=max_interval,
            jitter=jitter,
        )
        validate_timeout(timeout)
        log.debug("Waiting for operation %s (timeout=%ds)", operation_url, timeout)

        deadline = time.monotonic() + timeout
        attempt = 0

        # Operations must begin with /1.0/operations
        if not operation_url.startswith("/1.0/operations/"):
            error = f"Invalid operation URL: {operation_url}"
            log.error("Operation %s failed: %s", operation_url, error)
            return {"success": False, "error": error}

        while True:
            # Timeout
            if time.monotonic() > deadline:
                error = "Timeout waiting for operation to finish"
                log.error("Operation %s failed: %s", operation_url, error)
                return {"success": False, "error": error}

            # Query operation state
            result = self._sync_request("GET", operation_url.replace("/1.0/", "/"))

            if result.get("error_code") != 0:
                error = result.get("error", "Unknown error")
                log.error("Operation %s failed: %s", operation_url, error)
                return {
                    "success": False,
                    "error": error,
                    "operation": result,
                }

            # Structure: result["metadata"] contains the operation itself
            op = result.get("metadata", {})
            status_code = op.get("status_code")
            log.debug("Operation %s status_code=%s", operation_url, status_code)

            # Running: 100, 101, 103
            if status_code in (100, 101, 103):
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(polling.delay(attempt), remaining))
                attempt += 1
                continue

            # Success
            if status_code == 200:
                log.info("Operation %s completed successfully", operation_url)
                return result

            # Failure
            if status_code == 400:
                error = op.get("err", "Operation failed")
                log.error("Operation %s failed: %s", operation_url, error)
                return {
                    "success": False,
                    "operation": op,
                    "error": error,
                }

            # Unknown code (just in case)
            error = f"Unexpected status_code: {status_code}"
            log.error("Operation %s failed: %s", operation_url, error)
            return {
                "success": False,
                "operation": op,
                "error": error,
            }

    def _sync_request(self, method, endpoint, data=None, params=None):
        result = self._request(method, endpoint, data=data, params=params)

        if result.get("error_code", "") != 0:
            return result

        if result.get("type") == "async":
            op = result.get("operation")
            if op:
                return self._wait_for_operation(op)

        return result


def _client():
    return IncusClient(salt_funcs=__salt__)
