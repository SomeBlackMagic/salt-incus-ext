"""
Salt cloud driver for Incus containers and VMs.

Allows salt-cloud to create, list and destroy Incus instances (containers
and virtual machines) on a local or remote Incus server.

:configuration: Configure a provider in ``/etc/salt/cloud.providers.d/incus.conf``:

    .. code-block:: yaml

        my-incus:
          driver: incus
          connection:
            type: unix
            socket: /var/lib/incus/unix.socket

        # Remote HTTPS example:
        my-incus-remote:
          driver: incus
          connection:
            type: https
            url: https://incus.example.com:8443
            cert_storage:
              type: local_files  # or sdb
              cert: /path/to/client.crt
              key: /path/to/client.key
              verify: True  # or False or /path/to/ca.crt

:profile: Configure profiles in ``/etc/salt/cloud.profiles.d/incus.conf``:

    .. code-block:: yaml

        incus-ubuntu-container:
          provider: my-incus
          image: ubuntu/22.04       # Incus image alias
          instance_type: container  # or virtual-machine
          profiles:
            - default
          config:
            limits.cpu: "2"
            limits.memory: 2GB
          devices: {}
          location: ""              # Optional: target cluster member

        incus-ubuntu-vm:
          provider: my-incus
          image: ubuntu/22.04
          instance_type: virtual-machine
          profiles:
            - default

:depends: requests
"""

import copy
import json
import logging
import os
import socket
import tempfile
import time
import ast
from urllib.parse import quote, urljoin

try:
    import requests
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.connection import HTTPConnection
    from requests.packages.urllib3.connectionpool import HTTPConnectionPool
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False

import salt.config as config
import salt.utils.cloud
from salt.exceptions import SaltCloudException, SaltCloudSystemExit, SaltCloudNotFound

log = logging.getLogger(__name__)

__virtualname__ = "incus"


def __virtual__():
    if not HAS_REQUESTS:
        return False, "python-requests is required for the Incus cloud driver"
    return __virtualname__


# ==============================================================
# DEFAULT CONFIG + DEEP MERGE
# ==============================================================

INCUS_SOCKET_PATH = "/var/lib/incus/unix.socket"

DEFAULT_CFG = {
    "connection": {
        "type": "unix",               # "unix" | "https"
        "socket": INCUS_SOCKET_PATH,  # path to unix socket
        "url": None,                  # https URL, e.g. https://incus.example.com:8443
        "cert_storage": {
            "type": "local_files",    # "local_files" | "sdb"
            "cert": None,             # local path or sdb:// URI (for type=sdb)
            "key": None,              # local path or sdb:// URI (for type=sdb)
            "verify": True,           # bool/path or sdb:// URI (for type=sdb)
        },
    }
}


def deep_merge(base, override):
    """
    Recursively merge override into base.
    """
    for k, v in override.items():
        if (
            k in base
            and isinstance(base[k], dict)
            and isinstance(v, dict)
        ):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base



def _resolve_connection_value(conn, key, default=None):
    """
    Compatibility helper used by tests and old call sites.
    """
    cert_storage = _normalize_cert_storage(conn)
    return _resolve_cert_storage_value(cert_storage, key, default=default)


def _filter_event_safe(tag, data, defaults):
    """
    Wrapper around salt.utils.cloud.filter_event that tolerates runtimes
    where salt.utils.cloud.__opts__ is not initialized.
    """
    try:
        return salt.utils.cloud.filter_event(tag, data, defaults)
    except Exception as exc:
        log.debug("Fallback event filtering for tag '%s': %s", tag, exc)
        if not isinstance(data, dict):
            return {}
        return {key: data.get(key) for key in (defaults or []) if key in data}


def _normalize_cert_storage(conn):
    """
    Normalize TLS storage configuration for HTTPS connection.

    Supports the nested structure:
      connection:
        cert_storage:
          cert: /path/client.crt
          key: /path/client.key
          verify: true|false|/path/ca.crt

    and legacy flat keys under ``connection``:
      cert, key, verify
    """
    if not isinstance(conn, dict):
        conn = {}

    defaults = DEFAULT_CFG.get("connection", {}).get("cert_storage", {})
    normalized = copy.deepcopy(defaults) if isinstance(defaults, dict) else {
        "type": "local_files",
        "cert": None,
        "key": None,
        "verify": True,
    }

    nested = conn.get("cert_storage", {})
    if isinstance(nested, dict):
        normalized.update(nested)

    # Backward-compatible flat keys.
    if normalized.get("cert") in (None, "") and conn.get("cert") not in (None, ""):
        normalized["cert"] = conn.get("cert")
    if normalized.get("key") in (None, "") and conn.get("key") not in (None, ""):
        normalized["key"] = conn.get("key")
    if conn.get("verify") is not None and (
        "verify" not in (nested if isinstance(nested, dict) else {})
    ):
        normalized["verify"] = conn.get("verify")

    return normalized


def _resolve_cert_storage_value(cert_storage, key, default=None):
    """
    Resolve a single TLS storage value.

    This project flow uses local files only. ``sdb://`` URIs are rejected with
    a clear error to avoid silent misconfiguration.
    """
    if default is None:
        default = True if key == "verify" else None

    if not isinstance(cert_storage, dict):
        return default, False

    value = cert_storage.get(key, default)
    if value in (None, ""):
        return default, False

    if isinstance(value, str) and value.startswith("sdb://"):
        raise SaltCloudException(
            "sdb:// values are not supported in this project setup for "
            "incus cloud driver. Use local file paths in connection.cert_storage."
        )

    return value, False


def _write_temp_file(contents, suffix):
    """
    Write secret/certificate material to a temporary file.
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="incus-cloud-",
        suffix=suffix,
        delete=False,
    ) as fp:
        fp.write(contents)
        path = fp.name

    os.chmod(path, 0o600)
    return path


def _ensure_file_path(value, suffix, force_temp=False):
    """
    Ensure value is a filesystem path for requests, materializing content if needed.
    Returns (path_or_value, is_temporary_file).
    """
    if value is None:
        return None, False

    if not isinstance(value, str):
        value = str(value)

    if not force_temp and os.path.exists(value):
        return value, False

    # PEM-like inline data or explicit SDB materialization
    if force_temp or "\n" in value or "-----BEGIN " in value:
        return _write_temp_file(value, suffix), True

    return value, False


def _coerce_verify_value(value):
    """
    Normalize verify setting to bool or path-like string.
    """
    if isinstance(value, bool):
        return value

    if value is None:
        return True

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
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
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
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

    def connection_from_host(self, host, port=None, scheme="http", pool_kwargs=None):
        # host/port/scheme are ignored — we always use unix socket
        return UnixHTTPConnectionPool(self.socket_path)

    def connection_from_url(self, url, pool_kwargs=None):
        # url is ignored — we always use unix socket
        return UnixHTTPConnectionPool(self.socket_path)


class UnixHTTPAdapter(HTTPAdapter):
    """
    Requests adapter for Incus via unix socket.
    """

    def __init__(self, socket_path=INCUS_SOCKET_PATH, **kwargs):
        self.socket_path = socket_path
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        # substitute our custom PoolManager instead of the standard one
        self.poolmanager = UnixSocketPoolManager(self.socket_path)

    def proxy_manager_for(self, *args, **kwargs):
        # proxies are not applicable for unix socket
        return None

    def request_url(self, request, proxies):
        # Actual transport is AF_UNIX, URL is only needed for formal HTTP
        return "http://localhost" + request.path_url


# ==============================================================
# CLIENT
# ==============================================================

class IncusClient:
    def __init__(self, cfg):
        self.config = cfg
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
            except Exception:
                pass
        for path in self._temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass
        self._temp_files = []

    def __del__(self):
        self.close()

    def _create_session(self):
        session = requests.Session()
        conn = self.config.get("connection", {})
        ctype = conn.get("type", "unix")

        # ============================================
        # LOCAL UNIX SOCKET
        # ============================================
        if ctype == "unix":
            adapter = UnixHTTPAdapter(conn.get("socket", INCUS_SOCKET_PATH))

            # Disable TLS/proxy inheritance from environment
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
                cert_path, cert_temp = _ensure_file_path(cert_value, ".crt", force_temp=cert_from_sdb)
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
        if endpoint:
            url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        else:
            url = self.base_url

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
            if hasattr(e, "response") and e.response is not None:
                status_code = e.response.status_code
                api_error = None
                try:
                    error_body = e.response.json()
                    if isinstance(error_body, dict):
                        api_error = error_body.get("error")
                        metadata = error_body.get("metadata")
                        if not api_error and isinstance(metadata, dict):
                            api_error = metadata.get("err")
                except Exception:
                    api_error = None

                if not api_error:
                    text = (e.response.text or "").strip()
                    api_error = text if text else str(e)

                log.error(
                    "Incus API request failed: %s %s -> HTTP %s: %s",
                    method,
                    url,
                    status_code,
                    api_error,
                )
            return {
                "error": api_error if "api_error" in locals() and api_error else str(e),
                "error_code": getattr(getattr(e, "response", None), "status_code", None),
            }

    def _wait_for_operation(self, operation_url, timeout=300, interval=1):
        """
        Wait for an Incus async operation to finish.

        :param operation_url: e.g. "/1.0/operations/abc-123"
        :param timeout: maximum seconds to wait
        :param interval: poll interval in seconds
        :return: operation result dict

        Incus operation status codes:
          100 - Operation created
          101 - Started
          103 - Running
          200 - Success
          400 - Failure
        """
        started = time.time()

        if not operation_url.startswith("/1.0/operations/"):
            return {
                "success": False,
                "error": f"Invalid operation URL: {operation_url}"
            }

        while True:
            if time.time() - started > timeout:
                return {
                    "success": False,
                    "error": "Timeout waiting for operation to finish"
                }

            result = self._request("GET", operation_url.replace("/1.0/", "/"))

            if result.get("error_code") not in (None, 0):
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "operation": result,
                }

            op = result.get("metadata", {})
            status_code = op.get("status_code")

            # Running: 100, 101, 103
            if status_code in (100, 101, 103):
                time.sleep(interval)
                continue

            # Success
            if status_code == 200:
                return result

            # Failure
            if status_code == 400:
                return {
                    "success": False,
                    "operation": op,
                    "error": op.get("err", "Operation failed"),
                }

            return {
                "success": False,
                "operation": op,
                "error": f"Unexpected status_code: {status_code}"
            }

    def _sync_request(self, method, endpoint, data=None, params=None):
        result = self._request(method, endpoint, data=data, params=params)

        if result.get("error_code") not in (None, 0):
            return result

        if result.get("type") == "async":
            op = result.get("operation")
            if op:
                return self._wait_for_operation(op)

        return result


# ==============================================================
# PROVIDER HELPERS
# ==============================================================

def get_configured_provider():
    """
    Return the provider configuration if properly configured.
    """
    return config.is_provider_configured(
        __opts__,
        __active_provider_name__ or __virtualname__,
        ("connection",),
    )


def get_dependencies():
    """
    Check required python dependencies.
    """
    return config.check_driver_dependencies(__virtualname__, {"requests": HAS_REQUESTS})


def _client():
    """
    Return an IncusClient configured from the active cloud provider.
    """
    provider = get_configured_provider()
    if not provider:
        raise SaltCloudSystemExit("Incus cloud provider is not configured")

    conn_cfg = provider.get("connection", {})
    cfg = deep_merge(copy.deepcopy(DEFAULT_CFG), {"connection": conn_cfg})
    return IncusClient(cfg)


def _get_node_state(state_code):
    """
    Map Incus status_code to a human-readable state string.

    Incus status codes:
      100 - Operartion created
      101 - Started
      102 - Stopped
      103 - Running
      104 - Cancelling
      105 - Pending
      106 - Starting
      107 - Stopping
      108 - Aborting
      109 - Freezing
      110 - Frozen
      111 - Thawed
      200 - Success
      400 - Failure
    """
    _map = {
        100: "pending",
        101: "pending",
        102: "stopped",
        103: "running",
        104: "stopping",
        105: "pending",
        106: "pending",
        107: "stopping",
        108: "stopping",
        109: "stopped",
        110: "stopped",
        111: "running",
        200: "running",
        400: "error",
    }
    return _map.get(state_code, "unknown")


def _extract_ips(network_state):
    """
    Extract IPv4 addresses from an Incus instance network state dict.

    :param network_state: dict of {interface: {addresses: [...]}}
    :return: list of IPv4 address strings (excluding loopback)
    """
    ips = []
    if not network_state:
        return ips
    for iface_name, iface_data in network_state.items():
        if iface_name == "lo":
            continue
        for addr in iface_data.get("addresses", []):
            if addr.get("family") == "inet" and addr.get("scope") == "global":
                ips.append(addr["address"])
    return ips


# ==============================================================
# SALT-CLOUD INTERFACE: LIST FUNCTIONS
# ==============================================================

def list_nodes(call=None):
    """
    List all Incus instances with basic information.

    Returns a dict in the standard salt-cloud format required by:
    ``salt-cloud -Q``

    CLI Example:

    .. code-block:: bash

        salt-cloud -Q
        salt-cloud -f list_nodes my-incus

    :return: Dict of {instance_name: {id, image, size, state, private_ips, public_ips}}
    """
    if call == "action":
        raise SaltCloudSystemExit(
            "The list_nodes function must be called with -f or --function."
        )

    client = _client()
    result = client._request("GET", "/instances", params={"recursion": 1})

    if result.get("error_code") not in (None, 0):
        log.error("Failed to list Incus instances: %s", result.get("error"))
        return {}

    nodes = {}
    instances = result.get("metadata", []) or []

    for instance in instances:
        name = instance.get("name", "")
        if not name:
            continue

        # Get network state for IP addresses
        state_result = client._request("GET", f"/instances/{quote(name)}/state")
        network_state = {}
        instance_status = instance.get("status", "")
        if state_result.get("error_code") in (None, 0):
            meta = state_result.get("metadata", {}) or {}
            network_state = meta.get("network", {}) or {}

        private_ips = _extract_ips(network_state)

        # Use first profile as "size" representation
        profiles = instance.get("profiles", []) or []
        size = profiles[0] if profiles else ""

        # Use expanded_config image.description or type as image label
        expanded = instance.get("expanded_config", {}) or {}
        image_label = (
            expanded.get("image.description")
            or expanded.get("image.os", "")
        )

        nodes[name] = {
            "id": name,
            "image": image_label,
            "size": size,
            "state": instance_status.lower(),
            "private_ips": private_ips,
            "public_ips": [],
        }

    return nodes


def list_nodes_full(call=None):
    """
    List all Incus instances with full details.

    CLI Example:

    .. code-block:: bash

        salt-cloud -F
        salt-cloud -f list_nodes_full my-incus

    :return: Dict of {instance_name: full_instance_dict}
    """
    if call == "action":
        raise SaltCloudSystemExit(
            "The list_nodes_full function must be called with -f or --function."
        )

    client = _client()
    result = client._request("GET", "/instances", params={"recursion": 2})

    if result.get("error_code") not in (None, 0):
        log.error("Failed to list Incus instances: %s", result.get("error"))
        return {}

    nodes = {}
    for instance in result.get("metadata", []) or []:
        name = instance.get("name", "")
        if name:
            nodes[name] = instance

    return nodes


def list_nodes_select(call=None):
    """
    List Incus instances with the fields defined in ``query.selection`` in the
    cloud configuration.

    CLI Example:

    .. code-block:: bash

        salt-cloud -S
        salt-cloud -f list_nodes_select my-incus

    :return: Dict of selected node fields
    """
    return salt.utils.cloud.list_nodes_select(
        list_nodes_full("function"),
        __opts__.get("query.selection"),
        call,
    )


def list_images(call=None):
    """
    List available Incus image aliases.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f list_images my-incus

    :return: Dict of {alias_name: {name, description, type, architecture}}
    """
    if call == "action":
        raise SaltCloudSystemExit(
            "The list_images function must be called with -f or --function."
        )

    client = _client()
    result = client._request("GET", "/images/aliases", params={"recursion": 1})

    if result.get("error_code") not in (None, 0):
        log.error("Failed to list Incus image aliases: %s", result.get("error"))
        return {}

    images = {}
    for alias in result.get("metadata", []) or []:
        name = alias.get("name", "")
        if not name:
            continue
        target = alias.get("target")
        if isinstance(target, dict):
            target_type = target.get("type", "")
            target_arch = target.get("architecture", "")
            target_fp = target.get("fingerprint", "")
        elif isinstance(target, str):
            # Incus API commonly returns alias.target as fingerprint string.
            target_type = ""
            target_arch = ""
            target_fp = target
        else:
            target_type = ""
            target_arch = ""
            target_fp = ""
        images[name] = {
            "name": name,
            "description": alias.get("description", ""),
            "type": target_type,
            "architecture": target_arch,
            "fingerprint": target_fp,
        }

    return images


def avail_images(call=None):
    """
    Return available Incus image aliases.

    CLI Example:

    .. code-block:: bash

        salt-cloud --list-images my-incus

    :return: Dict of available images
    """
    return list_images()


def list_sizes(call=None):
    """
    List available Incus profiles (used as instance "sizes").

    Incus does not have traditional cloud sizes; profiles serve this role
    by grouping configuration such as CPU and memory limits.

    CLI Example:

    .. code-block:: bash

        salt-cloud -f list_sizes my-incus

    :return: Dict of {profile_name: {name, description, config, devices}}
    """
    if call == "action":
        raise SaltCloudSystemExit(
            "The list_sizes function must be called with -f or --function."
        )

    client = _client()
    result = client._request("GET", "/profiles", params={"recursion": 1})

    if result.get("error_code") not in (None, 0):
        log.error("Failed to list Incus profiles: %s", result.get("error"))
        return {}

    sizes = {}
    for profile in result.get("metadata", []) or []:
        name = profile.get("name", "")
        if not name:
            continue
        sizes[name] = {
            "name": name,
            "description": profile.get("description", ""),
            "config": profile.get("config", {}),
            "devices": profile.get("devices", {}),
        }

    return sizes


def avail_sizes(call=None):
    """
    Return available Incus profiles as instance sizes.

    CLI Example:

    .. code-block:: bash

        salt-cloud --list-sizes my-incus

    :return: Dict of available sizes (profiles)
    """
    return list_sizes()


def avail_locations(call=None):
    """
    Return available locations (Incus cluster members).

    For non-clustered Incus servers, returns a single "local" entry.

    CLI Example:

    .. code-block:: bash

        salt-cloud --list-locations my-incus

    :return: Dict of {member_name: {name, url, database, status, message}}
    """
    client = _client()
    result = client._request("GET", "/cluster/members", params={"recursion": 1})

    if result.get("error_code") not in (None, 0):
        # Not clustered — return a single local location
        return {"local": {"name": "local", "description": "Local Incus server"}}

    members = result.get("metadata", []) or []
    if not members:
        return {"local": {"name": "local", "description": "Local Incus server"}}

    locations = {}
    for member in members:
        name = member.get("server_name", "") or member.get("name", "")
        if not name:
            continue
        locations[name] = {
            "name": name,
            "url": member.get("url", ""),
            "database": member.get("database", False),
            "status": member.get("status", ""),
            "message": member.get("message", ""),
        }

    return locations


# ==============================================================
# SALT-CLOUD INTERFACE: CREATE / DESTROY
# ==============================================================

def create(vm_):
    """
    Create an Incus instance via salt-cloud.

    Required profile keys:
      - ``image``: Incus image alias (e.g. ``ubuntu/22.04``)

    Optional profile keys:
      - ``instance_type``: ``container`` (default) or ``virtual-machine``
      - ``profiles``: list of Incus profiles to apply (default: ``["default"]``)
      - ``config``: Incus config dict (e.g. ``{"limits.cpu": "2"}``)
      - ``devices``: Incus devices dict
      - ``location``: target cluster member name

    CLI Example:

    .. code-block:: bash

        salt-cloud -p incus-ubuntu-container my-new-instance

    :param vm_: VM definition dict from salt-cloud profile
    :return: Node info dict
    """
    name = vm_["name"]
    image_alias = vm_.get("image")

    if not image_alias:
        raise SaltCloudException(
            f"Cannot create instance '{name}': 'image' is required in the profile"
        )

    salt.utils.cloud.fire_event(
        "event",
        "starting create",
        f"salt/cloud/{name}/creating",
        args=_filter_event_safe(
            "creating", vm_, ["name", "profile", "provider", "driver"]
        ),
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )

    log.info("Creating Incus instance '%s' from image alias '%s'", name, image_alias)

    client = _client()

    instance_type = vm_.get("instance_type", "container")
    profiles = vm_.get("profiles", ["default"])
    cfg = vm_.get("config") or {}
    devices = vm_.get("devices") or {}
    location = vm_.get("location") or ""

    # Build POST body
    data = {
        "name": name,
        "type": instance_type,
        "source": {
            "type": "image",
            "alias": image_alias,
        },
        "profiles": profiles,
    }

    if cfg:
        data["config"] = cfg

    if devices:
        data["devices"] = devices

    if location:
        data["location"] = location

    salt.utils.cloud.fire_event(
        "event",
        "requesting instance",
        f"salt/cloud/{name}/requesting",
        args=_filter_event_safe(
            "requesting", vm_, ["name", "profile", "provider", "driver"]
        ),
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )

    # Create the instance (async operation)
    result = client._sync_request("POST", "/instances", data=data)

    if result.get("success") is False or result.get("error_code") not in (None, 0):
        error_msg = result.get("error") or result.get("comment") or "Unknown error"
        raise SaltCloudException(
            f"Failed to create Incus instance '{name}': {error_msg}"
        )

    log.info("Incus instance '%s' created, starting it now", name)

    # Start the instance
    start_result = client._sync_request(
        "PUT",
        f"/instances/{quote(name)}/state",
        data={"action": "start", "force": False},
    )

    if start_result.get("success") is False or start_result.get("error_code") not in (None, 0):
        error_msg = start_result.get("error") or start_result.get("comment") or "Unknown error"
        raise SaltCloudException(
            f"Failed to start Incus instance '{name}': {error_msg}"
        )

    log.info("Waiting for Incus instance '%s' to be running and have an IP", name)

    # Wait for instance to be running and have an IP address
    timeout = vm_.get("wait_for_ip_timeout", 120)
    interval = vm_.get("wait_for_ip_interval", 2)
    private_ips = _wait_for_ip(client, name, timeout=timeout, interval=interval)

    if not private_ips:
        log.warning(
            "Instance '%s' is running but no IP address was obtained within %ds",
            name, timeout,
        )

    node = {
        "id": name,
        "image": image_alias,
        "size": profiles[0] if profiles else "",
        "state": "running",
        "private_ips": private_ips,
        "public_ips": [],
    }

    salt.utils.cloud.fire_event(
        "event",
        "created instance",
        f"salt/cloud/{name}/created",
        args=_filter_event_safe(
            "created", vm_, ["name", "profile", "provider", "driver"]
        ),
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )

    # Deploy salt-minion unless explicitly disabled
    if vm_.get("deploy", True) and private_ips:
        deploy_kwargs = salt.utils.cloud.get_deploy_kwargs(vm_=vm_, fallback_kwargs={})
        deploy_kwargs["host"] = private_ips[0]

        deploy_result = salt.utils.cloud.deploy_linux(**deploy_kwargs)
        if deploy_result is False:
            log.error("Failed to deploy salt-minion on '%s'", name)

    return node


def _wait_for_ip(client, name, timeout=120, interval=2):
    """
    Poll instance state until it has a global IPv4 address or timeout is reached.

    :param client: IncusClient instance
    :param name: Instance name
    :param timeout: Maximum seconds to wait
    :param interval: Poll interval in seconds
    :return: List of IP address strings (may be empty on timeout)
    """
    started = time.time()

    while time.time() - started < timeout:
        result = client._request("GET", f"/instances/{quote(name)}/state")

        if result.get("error_code") in (None, 0):
            meta = result.get("metadata", {}) or {}
            status = meta.get("status", "")
            network = meta.get("network", {}) or {}
            ips = _extract_ips(network)

            if status == "Running" and ips:
                return ips

        time.sleep(interval)

    # Final attempt — return whatever IPs we can find even without running status
    result = client._request("GET", f"/instances/{quote(name)}/state")
    if result.get("error_code") in (None, 0):
        network = result.get("metadata", {}).get("network", {}) or {}
        return _extract_ips(network)

    return []


def destroy(name, call=None):
    """
    Destroy an Incus instance.

    Stops the instance if it is running, then deletes it.

    CLI Example:

    .. code-block:: bash

        salt-cloud -d my-instance

    :param name: Instance name
    :param call: Call type (must be "action")
    :return: Dict with destruction result
    """
    if call != "action":
        raise SaltCloudSystemExit(
            "The destroy action must be called with -a or --action."
        )

    salt.utils.cloud.fire_event(
        "event",
        "destroying instance",
        f"salt/cloud/{name}/destroying",
        args={"name": name},
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )

    client = _client()

    # Check if instance exists
    check = client._request("GET", f"/instances/{quote(name)}")
    if check.get("error_code") not in (None, 0):
        raise SaltCloudNotFound(f"Instance '{name}' not found")

    instance = check.get("metadata", {}) or {}
    status = instance.get("status", "")

    # Stop the instance if it is running
    if status == "Running":
        log.info("Stopping Incus instance '%s' before deletion", name)
        stop_result = client._sync_request(
            "PUT",
            f"/instances/{quote(name)}/state",
            data={"action": "stop", "force": True, "timeout": 30},
        )

        if stop_result.get("error_code") not in (None, 0):
            error_msg = stop_result.get("error", "Unknown error")
            raise SaltCloudException(
                f"Failed to stop Incus instance '{name}' before deletion: {error_msg}"
            )

    log.info("Deleting Incus instance '%s'", name)

    delete_result = client._sync_request("DELETE", f"/instances/{quote(name)}")

    if delete_result.get("error_code") not in (None, 0):
        error_msg = delete_result.get("error", "Unknown error")
        raise SaltCloudException(
            f"Failed to delete Incus instance '{name}': {error_msg}"
        )

    salt.utils.cloud.fire_event(
        "event",
        "destroyed instance",
        f"salt/cloud/{name}/destroyed",
        args={"name": name},
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )

    return {name: {"destroyed": True}}
