"""
Salt execution module for managing Incus API client certificates.

This module provides:
- keypair generation (EC P-384 self-signed certificate)
- storage helpers for local filesystem and Salt SDB
"""

import datetime
import hashlib
import json
import logging
import os

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


log = logging.getLogger(__name__)

__virtualname__ = "incus_pki"

DEFAULT_STORAGE = {
    "cert": "/etc/salt/pki/incus/client.crt",
    "key": "/etc/salt/pki/incus/client.key",
}


def __virtual__():
    if not HAS_CRYPTOGRAPHY:
        return False, "python-cryptography is required"
    return __virtualname__


def _api_client_cfg():
    cfg_get = __salt__.get("config.get", lambda *_: {})
    incus_cfg = cfg_get("incus", {}) or {}
    if not isinstance(incus_cfg, dict):
        return {}
    api_client = incus_cfg.get("api_client", {}) or {}
    return api_client if isinstance(api_client, dict) else {}


def _normalize_storage(storage=None):
    if storage is None:
        api_client_cfg = _api_client_cfg()
        storage = (
            api_client_cfg.get("generate_storage")
            or api_client_cfg.get("import_storage")
            or {}
        )
    elif isinstance(storage, str):
        # Salt may pass inline JSON mapping as string from Jinja/YAML rendering.
        try:
            storage = json.loads(storage)
        except ValueError as exc:
            raise ValueError(f"storage must be a mapping, got string: {exc}") from exc
    if not isinstance(storage, dict):
        raise ValueError("storage must be a mapping")

    normalized = dict(DEFAULT_STORAGE)
    normalized.update(storage)

    if not normalized.get("cert") or not normalized.get("key"):
        raise ValueError("storage.cert and storage.key are required")

    return {"cert": normalized["cert"], "key": normalized["key"]}


def _normalize_generate(cn=None, days=None):
    generate_cfg = _api_client_cfg().get("generate", {}) or {}
    if not isinstance(generate_cfg, dict):
        generate_cfg = {}

    cert_cn = cn or generate_cfg.get("cn") or "salt-cloud"
    cert_days = days if days is not None else generate_cfg.get("days", 3650)

    try:
        cert_days = int(cert_days)
    except (TypeError, ValueError):
        raise ValueError("days must be an integer")

    if cert_days <= 0:
        raise ValueError("days must be greater than 0")

    return cert_cn, cert_days


def _storage_read(storage, key):
    target = storage.get(key)
    if not target:
        return None
    if target.startswith("sdb://"):
        try:
            value = __salt__["sdb.get"](target, strict=True)
        except TypeError:
            # Backward compatibility with older Salt versions.
            value = __salt__["sdb.get"](target)
        except Exception as exc:
            raise ValueError(f"Failed to read SDB URI '{target}': {exc}") from exc

        if value == target:
            raise ValueError(
                f"SDB URI '{target}' was not resolved. Check that the SDB profile is configured on this minion."
            )
        return value if value not in (None, "") else None
    if target.startswith("salt://"):
        return __salt__["cp.get_file_str"](target) or None
    if not os.path.exists(target):
        return None
    with open(target, "r", encoding="utf-8") as fp:
        return fp.read()


def _storage_write(storage, key, value, mode):
    target = storage.get(key)
    if target.startswith("sdb://"):
        __salt__["sdb.set"](target, value)
        return
    if target.startswith("salt://"):
        raise ValueError(f"salt:// is read-only, cannot write to {target}")
    directory = os.path.dirname(target)
    if directory:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
    with open(target, "w", encoding="utf-8") as fp:
        fp.write(value)
    os.chmod(target, mode)


def _storage_write_pair(storage, cert_pem, key_pem):
    _storage_write(storage, "cert", cert_pem, 0o644)
    _storage_write(storage, "key", key_pem, 0o600)


def _generate_keypair(cn, days):
    private_key = ec.generate_private_key(ec.SECP384R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key=private_key, algorithm=hashes.SHA384())
    )

    cert_pem = certificate.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    return cert_pem, key_pem


def _fingerprint_from_cert(cert_pem):
    cert_obj = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    cert_der = cert_obj.public_bytes(serialization.Encoding.DER)
    return hashlib.sha256(cert_der).hexdigest()


def _validate_cert_pem(cert_pem, source):
    if not isinstance(cert_pem, str):
        raise ValueError(f"Certificate from {source} must be a text PEM string")
    if "-----BEGIN CERTIFICATE-----" not in cert_pem:
        raise ValueError(f"Certificate from {source} is not a PEM certificate")
    try:
        x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid certificate PEM in {source}: {exc}") from exc


def _validate_private_key_pem(key_pem, source):
    if not isinstance(key_pem, str):
        raise ValueError(f"Private key from {source} must be a text PEM string")
    if "-----BEGIN " not in key_pem or "PRIVATE KEY-----" not in key_pem:
        raise ValueError(f"Private key from {source} is not a PEM private key")
    try:
        serialization.load_pem_private_key(key_pem.encode("utf-8"), password=None)
    except Exception as exc:
        raise ValueError(f"Invalid private key PEM in {source}: {exc}") from exc


def cert_get(storage=None):
    """
    Read certificate from configured storage.
    """
    try:
        normalized_storage = _normalize_storage(storage)
        cert_pem = _storage_read(normalized_storage, "cert")
        if not cert_pem:
            return {
                "success": False,
                "changed": False,
                "comment": f"Certificate not found in storage: {normalized_storage.get('cert')}",
                "error": "certificate_not_found",
            }
        _validate_cert_pem(cert_pem, normalized_storage.get("cert"))
        return {
            "success": True,
            "changed": False,
            "comment": "Certificate loaded from storage",
            "cert": cert_pem,
        }
    except Exception as exc:
        log.error("Failed to read certificate from storage: %s", exc)
        return {
            "success": False,
            "changed": False,
            "comment": f"Failed to read certificate from storage: {exc}",
            "error": str(exc),
        }


def key_get(storage=None):
    """
    Read private key from configured storage.
    """
    try:
        normalized_storage = _normalize_storage(storage)
        key_pem = _storage_read(normalized_storage, "key")
        if not key_pem:
            return {
                "success": False,
                "changed": False,
                "comment": f"Private key not found in storage: {normalized_storage.get('key')}",
                "error": "key_not_found",
            }
        _validate_private_key_pem(key_pem, normalized_storage.get("key"))
        return {
            "success": True,
            "changed": False,
            "comment": "Private key loaded from storage",
            "key": key_pem,
        }
    except Exception as exc:
        log.error("Failed to read private key from storage: %s", exc)
        return {
            "success": False,
            "changed": False,
            "comment": f"Failed to read private key from storage: {exc}",
            "error": str(exc),
        }


def cert_fingerprint(cert_pem=None, storage=None):
    """
    Calculate SHA-256 fingerprint from certificate PEM.
    """
    try:
        cert_value = cert_pem
        if cert_value is None:
            cert_result = cert_get(storage=storage)
            if not cert_result.get("success"):
                return cert_result
            cert_value = cert_result.get("cert")

        fingerprint = _fingerprint_from_cert(cert_value)
        return {
            "success": True,
            "changed": False,
            "comment": "Certificate fingerprint calculated",
            "fingerprint": fingerprint,
        }
    except Exception as exc:
        log.error("Failed to calculate certificate fingerprint: %s", exc)
        return {
            "success": False,
            "changed": False,
            "comment": f"Failed to calculate certificate fingerprint: {exc}",
            "error": str(exc),
        }


def generate_keypair(cn=None, days=None, storage=None, force=False):
    """
    Generate an EC P-384 client keypair and save it to storage.
    """
    try:
        normalized_storage = _normalize_storage(storage)
        cert_cn, cert_days = _normalize_generate(cn=cn, days=days)

        existing_cert = _storage_read(normalized_storage, "cert")
        existing_key = _storage_read(normalized_storage, "key")

        if existing_cert and existing_key and not force:
            log.info("TLS keypair already exists in storage, skipping generation")
            return {
                "success": True,
                "changed": False,
                "comment": "Certificate and key already exist in storage",
            }

        cert_pem, key_pem = _generate_keypair(cert_cn, cert_days)
        _storage_write_pair(normalized_storage, cert_pem, key_pem)
        fingerprint = _fingerprint_from_cert(cert_pem)

        log.info("Generated new TLS keypair for CN '%s'", cert_cn)
        return {
            "success": True,
            "changed": True,
            "comment": "TLS keypair generated and stored",
            "fingerprint": fingerprint,
        }
    except Exception as exc:
        log.error("Failed to generate TLS keypair: %s", exc)
        return {
            "success": False,
            "changed": False,
            "comment": f"Failed to generate TLS keypair: {exc}",
            "error": str(exc),
        }
