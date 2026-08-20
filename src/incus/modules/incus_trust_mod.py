"""Trust management functions for the Incus Salt module."""

import logging
from urllib.parse import quote

log = logging.getLogger(__name__)

__virtualname__ = "incus"


def __virtual__():
    from incus.modules import incus_mod

    return incus_mod.__virtual__()


def _client():
    from incus.modules.incus_mod import IncusClient

    return IncusClient(salt_funcs=__salt__)


# ========== Trust Management Functions ==========


def trust_list(recursion=1):
    """
    List trusted client certificates.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.trust_list
    """
    client = _client()
    result = client._request("GET", "/certificates", params={"recursion": recursion})

    if result.get("error_code") != 0:
        return {
            "success": False,
            "error": result.get("error", "Failed to list trusted certificates"),
        }

    return {"success": True, "certificates": result.get("metadata", [])}


def trust_get(fingerprint):
    """
    Get trusted certificate details by fingerprint.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.trust_get <fingerprint>
    """
    if not fingerprint:
        return {"success": False, "error": "fingerprint is required"}

    client = _client()
    result = client._request("GET", f"/certificates/{quote(fingerprint)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to get trusted certificate")}

    return {"success": True, "certificate": result.get("metadata", {})}


def trust_add(cert_pem, name=None, restricted=False, projects=None):
    """
    Add a client certificate to the Incus trust store.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.trust_add cert_pem="$(cat /path/client.crt)" name=salt-cloud restricted=False
    """
    trust_name = name or "salt-cloud"
    log.info("Adding certificate '%s' to Incus trust store", trust_name)
    if not cert_pem:
        return {"success": False, "error": "cert_pem is required"}

    data = {
        "type": "client",
        "certificate": cert_pem,
        "name": trust_name,
        "restricted": bool(restricted),
    }
    if projects is not None:
        data["projects"] = list(projects)

    client = _client()
    result = client._sync_request("POST", "/certificates", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to add trusted certificate")}

    log.info("Certificate '%s' added to Incus trust store", trust_name)
    return {"success": True, "message": "Certificate added to trust store"}


def trust_update(fingerprint, name=None, restricted=None, projects=None):
    """
    Partially update a trusted certificate by fingerprint.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.trust_update <fingerprint> name=salt-cloud restricted=False
    """
    if not fingerprint:
        return {"success": False, "error": "fingerprint is required"}

    data = {}
    if name is not None:
        data["name"] = name
    if restricted is not None:
        data["restricted"] = bool(restricted)
    if projects is not None:
        data["projects"] = list(projects)

    if not data:
        return {"success": False, "error": "at least one update field is required"}

    client = _client()
    result = client._sync_request("PATCH", f"/certificates/{quote(fingerprint)}", data=data)

    if result.get("error_code") != 0:
        return {
            "success": False,
            "error": result.get("error", "Failed to update trusted certificate"),
        }

    return {"success": True, "message": f"Certificate {fingerprint} updated"}


def trust_remove(fingerprint):
    """
    Remove a trusted certificate by fingerprint.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.trust_remove <fingerprint>
    """
    log.info("Removing certificate '%s' from Incus trust store", fingerprint)
    if not fingerprint:
        return {"success": False, "error": "fingerprint is required"}

    client = _client()
    result = client._sync_request("DELETE", f"/certificates/{quote(fingerprint)}")

    if result.get("error_code") != 0:
        if result.get("error_code") == 404:
            log.warning("Certificate '%s' not found in trust store", fingerprint)
        return {
            "success": False,
            "error": result.get("error", "Failed to remove trusted certificate"),
        }

    log.info("Certificate '%s' removed from Incus trust store", fingerprint)
    return {"success": True, "message": f"Certificate {fingerprint} removed from trust store"}


__all__ = [
    "trust_list",
    "trust_get",
    "trust_add",
    "trust_update",
    "trust_remove",
]
