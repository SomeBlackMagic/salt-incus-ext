"""
Salt state module for managing Incus API client TLS certificates.
"""

import logging

from incus.utils import log_state_changes

log = logging.getLogger(__name__)

__virtualname__ = "incus_pki"


def __virtual__():
    if "incus_pki.cert_get" not in __salt__:
        return (
            False,
            "incus_pki execution module is unavailable; ensure modules are synced and python-cryptography is installed",
        )
    return __virtualname__


def _normalize_fingerprint(value):
    if value is None:
        return ""
    return str(value).replace(":", "").strip().lower()


def _get_trust_entry_from_storage(storage=None):
    cert_fp = __salt__["incus_pki.cert_fingerprint"](storage=storage)
    if not cert_fp.get("success"):
        return (
            None,
            None,
            cert_fp.get("comment") or cert_fp.get("error") or "Failed to calculate fingerprint",
        )

    fingerprint = cert_fp.get("fingerprint")
    trust_result = __salt__["incus.trust_get"](fingerprint)
    if trust_result.get("success"):
        return trust_result.get("certificate", {}), fingerprint, None

    # 404 means not found — not an error
    error = trust_result.get("error", "")
    if "not found" in error.lower() or "404" in error:
        return None, fingerprint, None

    return None, fingerprint, error


@log_state_changes
def keypair_present(name, storage=None, generate=None, force=False):
    """
    Ensure API client keypair exists in configured storage.
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    cert_result = __salt__["incus_pki.cert_get"](storage=storage)
    key_result = __salt__["incus_pki.key_get"](storage=storage)

    if cert_result.get("success") and key_result.get("success") and not force:
        ret["comment"] = "TLS keypair already present in storage"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = "TLS keypair would be generated"
        return ret

    generate = generate or {}
    if not isinstance(generate, dict):
        generate = {}

    gen_result = __salt__["incus_pki.generate_keypair"](
        cn=generate.get("cn"),
        days=generate.get("days"),
        storage=storage,
        force=force,
    )

    if not gen_result.get("success"):
        ret["result"] = False
        ret["comment"] = (
            gen_result.get("comment") or gen_result.get("error") or "Failed to generate TLS keypair"
        )
        return ret

    ret["comment"] = gen_result.get("comment", "TLS keypair is present")
    if gen_result.get("changed"):
        ret["changes"] = {
            "keypair": {
                "old": None,
                "new": gen_result.get("fingerprint", "generated"),
            }
        }
    return ret


@log_state_changes
def trust_present(name, storage=None, restricted=False):
    """
    Ensure certificate from storage is present in Incus trust store.
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    cert_result = __salt__["incus_pki.cert_get"](storage=storage)
    if not cert_result.get("success"):
        ret["result"] = False
        ret["comment"] = cert_result.get("comment", "Certificate not found in storage")
        return ret

    existing, fingerprint, error = _get_trust_entry_from_storage(storage=storage)
    if error:
        ret["result"] = False
        ret["comment"] = error
        return ret

    desired_restricted = bool(restricted)
    if existing:
        current_name = existing.get("name")
        current_restricted = bool(existing.get("restricted", False))

        if current_name == name and current_restricted == desired_restricted:
            ret["comment"] = "Certificate already present in trust store"
            return ret

        if __opts__.get("test"):
            ret["result"] = None
            ret["comment"] = "Certificate trust entry would be updated"
            return ret

        __salt__["incus.trust_remove"](fingerprint)
        add_result = __salt__["incus.trust_add"](
            cert_pem=cert_result["cert"],
            name=name,
            restricted=restricted,
        )
        if not add_result.get("success"):
            ret["result"] = False
            ret["comment"] = add_result.get("error", "Failed to update trust entry")
            return ret

        ret["changes"] = {
            "trust": {
                "old": {"name": current_name, "restricted": current_restricted},
                "new": {"name": name, "restricted": desired_restricted},
            }
        }
        ret["comment"] = "Certificate trust entry updated"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = "Certificate would be added to trust store"
        return ret

    add_result = __salt__["incus.trust_add"](
        cert_pem=cert_result["cert"],
        name=name,
        restricted=restricted,
    )
    if not add_result.get("success"):
        ret["result"] = False
        ret["comment"] = add_result.get("error", "Failed to add certificate to trust store")
        return ret

    ret["changes"] = {"trust": {"old": None, "new": fingerprint}}
    ret["comment"] = "Certificate added to trust store"
    return ret


@log_state_changes
def trust_absent(name, storage=None):
    """
    Ensure certificate from storage is absent from Incus trust store.
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    cert_result = __salt__["incus_pki.cert_get"](storage=storage)
    if not cert_result.get("success"):
        ret["result"] = False
        ret["comment"] = cert_result.get("comment", "Certificate not found in storage")
        return ret

    existing, fingerprint, error = _get_trust_entry_from_storage(storage=storage)
    if error:
        ret["result"] = False
        ret["comment"] = error
        return ret

    if not existing:
        ret["comment"] = "Certificate already absent from trust store"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = "Certificate would be removed from trust store"
        return ret

    remove_result = __salt__["incus.trust_remove"](fingerprint)
    if not remove_result.get("success"):
        ret["result"] = False
        ret["comment"] = remove_result.get("error", "Failed to remove certificate from trust store")
        return ret

    ret["changes"] = {"trust": {"old": fingerprint, "new": None}}
    ret["comment"] = "Certificate removed from trust store"
    return ret


@log_state_changes
def client_trusted(name, storage=None, generate=None, restricted=False):
    """
    Ensure API client keypair exists in storage and is trusted by Incus.

    Combines keypair generation and trust store registration in a single state.
    Idempotent: skips generation if keypair exists, skips trust_add if fingerprint
    is already in Incus trust store.

    name
        Name to register in the Incus trust store.

    storage
        Storage config dict with ``cert`` and ``key`` paths or sdb:// URIs.
        If omitted, execution module storage defaults are used.

    generate
        Dict with optional ``cn`` and ``days`` overrides for certificate generation.
        Defaults to ``incus:api_client:generate`` from pillar/config.

    restricted
        Whether to add certificate as restricted in Incus trust store.

    CLI Example:

    .. code-block:: bash

        salt '*' state.apply incus.pki
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # 1. Generate keypair if missing
    generate = generate or {}
    if not isinstance(generate, dict):
        generate = {}

    gen_result = __salt__["incus_pki.generate_keypair"](
        cn=generate.get("cn"),
        days=generate.get("days"),
        storage=storage,
    )
    if not gen_result.get("success"):
        ret["result"] = False
        ret["comment"] = (
            gen_result.get("comment") or gen_result.get("error") or "Failed to generate TLS keypair"
        )
        return ret

    if gen_result.get("changed"):
        ret["changes"]["keypair"] = {"old": None, "new": gen_result.get("fingerprint")}

    # 2. Check if already trusted
    existing, fingerprint, error = _get_trust_entry_from_storage(storage=storage)
    if error:
        ret["result"] = False
        ret["comment"] = error
        return ret

    if existing:
        if ret["changes"]:
            ret["comment"] = "TLS keypair generated and certificate is already trusted by Incus"
        else:
            ret["comment"] = "TLS keypair is present and trusted by Incus"
        return ret

    # 3. Add to trust store
    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = "Client certificate would be added to Incus trust store"
        return ret

    cert_result = __salt__["incus_pki.cert_get"](storage=storage)
    if not cert_result.get("success"):
        ret["result"] = False
        ret["comment"] = cert_result.get("comment", "Failed to read certificate from storage")
        return ret

    add_result = __salt__["incus.trust_add"](
        cert_pem=cert_result["cert"],
        name=name,
        restricted=restricted,
    )
    if not add_result.get("success"):
        ret["result"] = False
        ret["comment"] = add_result.get("error", "Failed to add certificate to Incus trust store")
        return ret

    ret["changes"]["trust"] = {"old": None, "new": fingerprint}
    ret["comment"] = "TLS keypair is present and added to Incus trust store"
    return ret
