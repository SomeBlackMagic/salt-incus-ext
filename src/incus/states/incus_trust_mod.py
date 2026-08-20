"""Salt state functions for managing the Incus trust store."""

import binascii
import hashlib
import ssl

from incus.utils import log_state_changes

__virtualname__ = "incus"

_REQUIRED_FUNCTIONS = {
    "incus.trust_add",
    "incus.trust_list",
    "incus.trust_remove",
    "incus.trust_update",
}


def __virtual__():
    """Load when all trust execution functions are available."""
    missing = sorted(_REQUIRED_FUNCTIONS.difference(__salt__))
    if not missing:
        return __virtualname__
    return False, f"Incus trust execution functions are not available: {', '.join(missing)}"


def _ret(name):
    return {"name": name, "result": True, "changes": {}, "comment": ""}


def _normalize_fingerprint(value):
    if value is None:
        return ""
    return str(value).replace(":", "").strip().lower()


def _fingerprint_from_pem(cert_pem):
    if not isinstance(cert_pem, str) or not cert_pem.strip():
        raise ValueError("cert_pem must be a non-empty PEM certificate string")
    try:
        certificate_der = ssl.PEM_cert_to_DER_cert(cert_pem.strip())
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"cert_pem is not a valid PEM certificate: {exc}") from exc
    if not certificate_der:
        raise ValueError("cert_pem is not a valid PEM certificate")
    return hashlib.sha256(certificate_der).hexdigest()


def _normalize_projects(projects):
    if projects is None:
        return []
    if not isinstance(projects, (list, tuple, set)):
        raise ValueError("projects must be a list of project names")
    return [str(project) for project in projects]


def _list_certificates(ret):
    result = __salt__["incus.trust_list"](recursion=1)
    if not result.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list trusted certificates: {result.get('error')}"
        return None
    return result.get("certificates", []) or []


@log_state_changes
def trust_present(name, cert_pem, restricted=False, projects=None):
    """
    Ensure a Salt Cloud client certificate is present in the Incus trust store.

    The certificate is identified by its SHA-256 fingerprint. ``name`` is the
    display name stored by Incus, not the certificate identity.

    .. code-block:: yaml

        salt-cloud-client:
          incus.trust_present:
            - cert_pem: |
                -----BEGIN CERTIFICATE-----
                ...
                -----END CERTIFICATE-----
            - restricted: false
    """
    ret = _ret(name)
    try:
        fingerprint = _fingerprint_from_pem(cert_pem)
        desired_projects = _normalize_projects(projects)
    except ValueError as exc:
        ret["result"] = False
        ret["comment"] = str(exc)
        return ret

    certificates = _list_certificates(ret)
    if certificates is None:
        return ret

    existing = next(
        (
            certificate
            for certificate in certificates
            if _normalize_fingerprint(certificate.get("fingerprint")) == fingerprint
        ),
        None,
    )
    desired = {
        "fingerprint": fingerprint,
        "name": name,
        "restricted": bool(restricted),
        "projects": desired_projects,
    }

    if existing is None:
        if __opts__.get("test"):
            ret["result"] = None
            ret["changes"] = {"trust": {"old": None, "new": desired}}
            ret["comment"] = f"Certificate {name} would be added to the Incus trust store"
            return ret

        add_result = __salt__["incus.trust_add"](
            cert_pem=cert_pem,
            name=name,
            restricted=restricted,
            projects=desired_projects,
        )
        if not add_result.get("success"):
            ret["result"] = False
            ret["comment"] = f"Failed to add certificate {name}: {add_result.get('error')}"
            return ret

        ret["changes"] = {"trust": {"old": None, "new": desired}}
        ret["comment"] = f"Certificate {name} added to the Incus trust store"
        return ret

    current = {
        "fingerprint": fingerprint,
        "name": existing.get("name"),
        "restricted": bool(existing.get("restricted", False)),
        "projects": existing.get("projects", []) or [],
    }
    metadata_matches = (
        current["name"] == name
        and current["restricted"] == bool(restricted)
        and sorted(current["projects"]) == sorted(desired_projects)
    )
    if metadata_matches:
        ret["comment"] = f"Certificate {name} is already present in the Incus trust store"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["changes"] = {"trust": {"old": current, "new": desired}}
        ret["comment"] = f"Certificate {name} trust metadata would be updated"
        return ret

    update_result = __salt__["incus.trust_update"](
        fingerprint,
        name=name,
        restricted=restricted,
        projects=desired_projects,
    )
    if not update_result.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to update certificate {name}: {update_result.get('error')}"
        return ret

    ret["changes"] = {"trust": {"old": current, "new": desired}}
    ret["comment"] = f"Certificate {name} trust metadata updated"
    return ret


@log_state_changes
def trust_absent(name, fingerprint=None, cert_pem=None):
    """
    Ensure a client certificate is absent from the Incus trust store.

    Prefer ``fingerprint`` or ``cert_pem`` for unambiguous identification. If
    neither is supplied, an exact display-name match is used and ambiguous
    matches are rejected.
    """
    ret = _ret(name)
    try:
        pem_fingerprint = _fingerprint_from_pem(cert_pem) if cert_pem is not None else None
    except ValueError as exc:
        ret["result"] = False
        ret["comment"] = str(exc)
        return ret

    requested_fingerprint = _normalize_fingerprint(fingerprint)
    if requested_fingerprint and pem_fingerprint and requested_fingerprint != pem_fingerprint:
        ret["result"] = False
        ret["comment"] = "fingerprint does not match cert_pem"
        return ret
    target_fingerprint = requested_fingerprint or pem_fingerprint

    certificates = _list_certificates(ret)
    if certificates is None:
        return ret

    if target_fingerprint:
        matches = [
            certificate
            for certificate in certificates
            if _normalize_fingerprint(certificate.get("fingerprint")) == target_fingerprint
        ]
    else:
        matches = [certificate for certificate in certificates if certificate.get("name") == name]

    if not matches:
        ret["comment"] = f"Certificate {name} is already absent from the Incus trust store"
        return ret
    if len(matches) > 1:
        ret["result"] = False
        ret["comment"] = (
            f"Multiple certificates named {name} exist; specify fingerprint or cert_pem"
        )
        return ret

    existing = matches[0]
    existing_fingerprint = _normalize_fingerprint(existing.get("fingerprint"))
    if not existing_fingerprint:
        ret["result"] = False
        ret["comment"] = f"Trusted certificate {name} has no fingerprint"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["changes"] = {"trust": {"old": existing, "new": None}}
        ret["comment"] = f"Certificate {name} would be removed from the Incus trust store"
        return ret

    remove_result = __salt__["incus.trust_remove"](existing_fingerprint)
    if not remove_result.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to remove certificate {name}: {remove_result.get('error')}"
        return ret

    ret["changes"] = {"trust": {"old": existing, "new": None}}
    ret["comment"] = f"Certificate {name} removed from the Incus trust store"
    return ret
