import builtins
import hashlib
import os
import runpy
from unittest.mock import Mock, call, mock_open

import pytest

from incus.modules import incus_pki_mod


def test_module_handles_missing_cryptography(monkeypatch):
    original_import = builtins.__import__

    def import_without_cryptography(name, *args, **kwargs):
        if name == "cryptography" or name.startswith("cryptography."):
            raise ImportError("cryptography unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_cryptography)

    namespace = runpy.run_path(incus_pki_mod.__file__)

    assert namespace["HAS_CRYPTOGRAPHY"] is False


@pytest.mark.parametrize(
    ("has_cryptography", "expected"),
    [
        (True, "incus_pki"),
        (False, (False, "python-cryptography is required")),
    ],
)
def test_virtual(monkeypatch, has_cryptography, expected):
    monkeypatch.setattr(incus_pki_mod, "HAS_CRYPTOGRAPHY", has_cryptography)

    assert incus_pki_mod.__virtual__() == expected


def test_api_client_cfg_reads_mapping(monkeypatch):
    config_get = Mock(return_value={"api_client": {"generate": {"cn": "client"}}})
    monkeypatch.setattr(
        incus_pki_mod, "__salt__", {"config.get": config_get}, raising=False
    )

    assert incus_pki_mod._api_client_cfg() == {"generate": {"cn": "client"}}
    config_get.assert_called_once_with("incus", {})


def test_api_client_cfg_uses_fallback_when_config_get_is_missing(monkeypatch):
    monkeypatch.setattr(incus_pki_mod, "__salt__", {}, raising=False)

    assert incus_pki_mod._api_client_cfg() == {}


@pytest.mark.parametrize(
    "config",
    [None, "invalid", [], {"api_client": None}, {"api_client": "invalid"}],
)
def test_api_client_cfg_rejects_non_mapping_sections(monkeypatch, config):
    monkeypatch.setattr(
        incus_pki_mod,
        "__salt__",
        {"config.get": Mock(return_value=config)},
        raising=False,
    )

    assert incus_pki_mod._api_client_cfg() == {}


@pytest.mark.parametrize(
    ("api_client", "expected"),
    [
        (
            {"generate_storage": {"cert": "gen.crt", "key": "gen.key"}},
            {"cert": "gen.crt", "key": "gen.key"},
        ),
        (
            {"import_storage": {"cert": "import.crt", "key": "import.key"}},
            {"cert": "import.crt", "key": "import.key"},
        ),
        ({}, incus_pki_mod.DEFAULT_STORAGE),
    ],
)
def test_normalize_storage_uses_configured_precedence(
    monkeypatch, api_client, expected
):
    monkeypatch.setattr(
        incus_pki_mod, "_api_client_cfg", Mock(return_value=api_client)
    )

    assert incus_pki_mod._normalize_storage() == expected


def test_normalize_storage_accepts_json_and_merges_defaults():
    assert incus_pki_mod._normalize_storage('{"cert": "custom.crt"}') == {
        "cert": "custom.crt",
        "key": incus_pki_mod.DEFAULT_STORAGE["key"],
    }


def test_normalize_storage_rejects_invalid_json():
    with pytest.raises(ValueError, match="storage must be a mapping, got string"):
        incus_pki_mod._normalize_storage("not-json")


@pytest.mark.parametrize("storage", [[], 1, True])
def test_normalize_storage_rejects_non_mapping(storage):
    with pytest.raises(ValueError, match="storage must be a mapping"):
        incus_pki_mod._normalize_storage(storage)


@pytest.mark.parametrize(
    "storage",
    [
        {"cert": None, "key": "key.pem"},
        {"cert": "cert.pem", "key": None},
    ],
)
def test_normalize_storage_requires_both_targets(storage):
    with pytest.raises(ValueError, match="storage.cert and storage.key are required"):
        incus_pki_mod._normalize_storage(storage)


@pytest.mark.parametrize(
    ("generate_cfg", "cn", "days", "expected"),
    [
        ({"cn": "configured", "days": "30"}, None, None, ("configured", 30)),
        ({"cn": "configured", "days": 30}, "explicit", 10, ("explicit", 10)),
        ({}, None, None, ("salt-cloud", 3650)),
        ("invalid", None, None, ("salt-cloud", 3650)),
    ],
)
def test_normalize_generate(monkeypatch, generate_cfg, cn, days, expected):
    monkeypatch.setattr(
        incus_pki_mod,
        "_api_client_cfg",
        Mock(return_value={"generate": generate_cfg}),
    )

    assert incus_pki_mod._normalize_generate(cn=cn, days=days) == expected


@pytest.mark.parametrize("days", ["invalid", None, object()])
def test_normalize_generate_rejects_non_integer_days(monkeypatch, days):
    configured = {"days": days} if days is None else {}
    monkeypatch.setattr(
        incus_pki_mod,
        "_api_client_cfg",
        Mock(return_value={"generate": configured}),
    )

    with pytest.raises(ValueError, match="days must be an integer"):
        incus_pki_mod._normalize_generate(days=days if days is not None else None)


@pytest.mark.parametrize("days", [0, -1, "0"])
def test_normalize_generate_requires_positive_days(monkeypatch, days):
    monkeypatch.setattr(incus_pki_mod, "_api_client_cfg", Mock(return_value={}))

    with pytest.raises(ValueError, match="days must be greater than 0"):
        incus_pki_mod._normalize_generate(days=days)


def test_storage_read_returns_none_for_missing_target():
    assert incus_pki_mod._storage_read({}, "cert") is None


def test_storage_read_gets_sdb_value_with_strict_mode(monkeypatch):
    sdb_get = Mock(return_value="certificate")
    monkeypatch.setattr(
        incus_pki_mod, "__salt__", {"sdb.get": sdb_get}, raising=False
    )

    assert incus_pki_mod._storage_read({"cert": "sdb://pki/cert"}, "cert") == (
        "certificate"
    )
    sdb_get.assert_called_once_with("sdb://pki/cert", strict=True)


def test_storage_read_retries_sdb_without_strict_for_old_salt(monkeypatch):
    sdb_get = Mock(side_effect=[TypeError("unsupported"), "certificate"])
    monkeypatch.setattr(
        incus_pki_mod, "__salt__", {"sdb.get": sdb_get}, raising=False
    )

    assert incus_pki_mod._storage_read({"cert": "sdb://pki/cert"}, "cert") == (
        "certificate"
    )
    assert sdb_get.call_args_list == [
        call("sdb://pki/cert", strict=True),
        call("sdb://pki/cert"),
    ]


def test_storage_read_wraps_sdb_error(monkeypatch):
    monkeypatch.setattr(
        incus_pki_mod,
        "__salt__",
        {"sdb.get": Mock(side_effect=RuntimeError("backend down"))},
        raising=False,
    )

    with pytest.raises(ValueError, match="Failed to read SDB URI.*backend down"):
        incus_pki_mod._storage_read({"cert": "sdb://pki/cert"}, "cert")


def test_storage_read_rejects_unresolved_sdb_uri(monkeypatch):
    target = "sdb://pki/cert"
    monkeypatch.setattr(
        incus_pki_mod,
        "__salt__",
        {"sdb.get": Mock(return_value=target)},
        raising=False,
    )

    with pytest.raises(ValueError, match="was not resolved"):
        incus_pki_mod._storage_read({"cert": target}, "cert")


@pytest.mark.parametrize("value", [None, ""])
def test_storage_read_normalizes_empty_sdb_value(monkeypatch, value):
    monkeypatch.setattr(
        incus_pki_mod,
        "__salt__",
        {"sdb.get": Mock(return_value=value)},
        raising=False,
    )

    assert incus_pki_mod._storage_read({"cert": "sdb://pki/cert"}, "cert") is None


@pytest.mark.parametrize(
    ("value", "expected"), [("certificate", "certificate"), ("", None), (None, None)]
)
def test_storage_read_uses_salt_fileserver(monkeypatch, value, expected):
    get_file = Mock(return_value=value)
    monkeypatch.setattr(
        incus_pki_mod, "__salt__", {"cp.get_file_str": get_file}, raising=False
    )

    assert incus_pki_mod._storage_read({"cert": "salt://pki/cert"}, "cert") == expected
    get_file.assert_called_once_with("salt://pki/cert")


def test_storage_read_returns_none_for_missing_local_file(tmp_path):
    target = tmp_path / "missing.crt"

    assert incus_pki_mod._storage_read({"cert": str(target)}, "cert") is None


def test_storage_read_reads_local_file(tmp_path):
    target = tmp_path / "client.crt"
    target.write_text("certificate", encoding="utf-8")

    assert incus_pki_mod._storage_read({"cert": str(target)}, "cert") == "certificate"


def test_storage_write_sets_sdb_value(monkeypatch):
    sdb_set = Mock()
    monkeypatch.setattr(
        incus_pki_mod, "__salt__", {"sdb.set": sdb_set}, raising=False
    )

    incus_pki_mod._storage_write(
        {"cert": "sdb://pki/cert"}, "cert", "certificate", 0o644
    )

    sdb_set.assert_called_once_with("sdb://pki/cert", "certificate")


def test_storage_write_rejects_salt_fileserver_target():
    with pytest.raises(ValueError, match="salt:// is read-only"):
        incus_pki_mod._storage_write(
            {"cert": "salt://pki/cert"}, "cert", "certificate", 0o644
        )


def test_storage_write_creates_secure_directory_and_file(tmp_path):
    target = tmp_path / "pki" / "client.key"

    incus_pki_mod._storage_write(
        {"key": str(target)}, "key", "private-key", 0o600
    )

    assert target.read_text(encoding="utf-8") == "private-key"
    assert os.stat(target).st_mode & 0o777 == 0o600
    assert os.stat(target.parent).st_mode & 0o777 == 0o700


def test_storage_write_handles_target_without_directory(monkeypatch):
    opened = mock_open()
    monkeypatch.setattr("builtins.open", opened)
    chmod = Mock()
    monkeypatch.setattr(incus_pki_mod.os, "chmod", chmod)

    incus_pki_mod._storage_write({"cert": "client.crt"}, "cert", "cert", 0o644)

    opened.assert_called_once_with("client.crt", "w", encoding="utf-8")
    opened().write.assert_called_once_with("cert")
    chmod.assert_called_once_with("client.crt", 0o644)


def test_storage_write_pair_uses_certificate_and_key_modes(monkeypatch):
    write = Mock()
    monkeypatch.setattr(incus_pki_mod, "_storage_write", write)
    storage = {"cert": "cert.crt", "key": "key.pem"}

    incus_pki_mod._storage_write_pair(storage, "certificate", "private-key")

    assert write.call_args_list == [
        call(storage, "cert", "certificate", 0o644),
        call(storage, "key", "private-key", 0o600),
    ]


def test_generate_keypair_and_fingerprint_are_valid():
    cert_pem, key_pem = incus_pki_mod._generate_keypair("test-client", 30)

    assert cert_pem.startswith("-----BEGIN CERTIFICATE-----")
    assert "PRIVATE KEY-----" in key_pem
    incus_pki_mod._validate_cert_pem(cert_pem, "generated")
    incus_pki_mod._validate_private_key_pem(key_pem, "generated")
    fingerprint = incus_pki_mod._fingerprint_from_cert(cert_pem)
    cert_obj = incus_pki_mod.x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    cert_der = cert_obj.public_bytes(incus_pki_mod.serialization.Encoding.DER)
    assert fingerprint == hashlib.sha256(cert_der).hexdigest()


@pytest.mark.parametrize("cert_pem", [None, b"certificate", 1])
def test_validate_cert_rejects_non_text(cert_pem):
    with pytest.raises(ValueError, match="must be a text PEM string"):
        incus_pki_mod._validate_cert_pem(cert_pem, "source")


def test_validate_cert_rejects_non_pem_text():
    with pytest.raises(ValueError, match="is not a PEM certificate"):
        incus_pki_mod._validate_cert_pem("certificate", "source")


def test_validate_cert_wraps_parser_error(monkeypatch):
    monkeypatch.setattr(
        incus_pki_mod.x509,
        "load_pem_x509_certificate",
        Mock(side_effect=ValueError("bad cert")),
    )

    with pytest.raises(ValueError, match="Invalid certificate PEM.*bad cert"):
        incus_pki_mod._validate_cert_pem(
            "-----BEGIN CERTIFICATE-----\nbad", "source"
        )


@pytest.mark.parametrize("key_pem", [None, b"private-key", 1])
def test_validate_private_key_rejects_non_text(key_pem):
    with pytest.raises(ValueError, match="must be a text PEM string"):
        incus_pki_mod._validate_private_key_pem(key_pem, "source")


@pytest.mark.parametrize(
    "key_pem", ["private-key", "-----BEGIN SOMETHING-----", "PRIVATE KEY-----"]
)
def test_validate_private_key_rejects_non_pem_text(key_pem):
    with pytest.raises(ValueError, match="is not a PEM private key"):
        incus_pki_mod._validate_private_key_pem(key_pem, "source")


def test_validate_private_key_wraps_parser_error(monkeypatch):
    monkeypatch.setattr(
        incus_pki_mod.serialization,
        "load_pem_private_key",
        Mock(side_effect=ValueError("bad key")),
    )

    with pytest.raises(ValueError, match="Invalid private key PEM.*bad key"):
        incus_pki_mod._validate_private_key_pem(
            "-----BEGIN PRIVATE KEY-----\nbad", "source"
        )


def test_cert_get_returns_valid_certificate(monkeypatch):
    storage = {"cert": "cert.crt", "key": "key.pem"}
    monkeypatch.setattr(
        incus_pki_mod, "_normalize_storage", Mock(return_value=storage)
    )
    monkeypatch.setattr(
        incus_pki_mod, "_storage_read", Mock(return_value="certificate")
    )
    validate = Mock()
    monkeypatch.setattr(incus_pki_mod, "_validate_cert_pem", validate)

    assert incus_pki_mod.cert_get() == {
        "success": True,
        "changed": False,
        "comment": "Certificate loaded from storage",
        "cert": "certificate",
    }
    validate.assert_called_once_with("certificate", "cert.crt")


def test_cert_get_reports_missing_certificate(monkeypatch):
    storage = {"cert": "cert.crt", "key": "key.pem"}
    monkeypatch.setattr(
        incus_pki_mod, "_normalize_storage", Mock(return_value=storage)
    )
    monkeypatch.setattr(incus_pki_mod, "_storage_read", Mock(return_value=None))

    assert incus_pki_mod.cert_get() == {
        "success": False,
        "changed": False,
        "comment": "Certificate not found in storage: cert.crt",
        "error": "certificate_not_found",
    }


def test_cert_get_reports_exception(monkeypatch):
    monkeypatch.setattr(
        incus_pki_mod,
        "_normalize_storage",
        Mock(side_effect=ValueError("invalid storage")),
    )

    assert incus_pki_mod.cert_get() == {
        "success": False,
        "changed": False,
        "comment": "Failed to read certificate from storage: invalid storage",
        "error": "invalid storage",
    }


def test_key_get_returns_valid_key(monkeypatch):
    storage = {"cert": "cert.crt", "key": "key.pem"}
    monkeypatch.setattr(
        incus_pki_mod, "_normalize_storage", Mock(return_value=storage)
    )
    monkeypatch.setattr(
        incus_pki_mod, "_storage_read", Mock(return_value="private-key")
    )
    validate = Mock()
    monkeypatch.setattr(incus_pki_mod, "_validate_private_key_pem", validate)

    assert incus_pki_mod.key_get() == {
        "success": True,
        "changed": False,
        "comment": "Private key loaded from storage",
        "key": "private-key",
    }
    validate.assert_called_once_with("private-key", "key.pem")


def test_key_get_reports_missing_key(monkeypatch):
    storage = {"cert": "cert.crt", "key": "key.pem"}
    monkeypatch.setattr(
        incus_pki_mod, "_normalize_storage", Mock(return_value=storage)
    )
    monkeypatch.setattr(incus_pki_mod, "_storage_read", Mock(return_value=""))

    assert incus_pki_mod.key_get() == {
        "success": False,
        "changed": False,
        "comment": "Private key not found in storage: key.pem",
        "error": "key_not_found",
    }


def test_key_get_reports_exception(monkeypatch):
    monkeypatch.setattr(
        incus_pki_mod,
        "_normalize_storage",
        Mock(side_effect=ValueError("invalid storage")),
    )

    assert incus_pki_mod.key_get() == {
        "success": False,
        "changed": False,
        "comment": "Failed to read private key from storage: invalid storage",
        "error": "invalid storage",
    }


def test_cert_fingerprint_uses_explicit_certificate(monkeypatch):
    fingerprint = Mock(return_value="abc123")
    monkeypatch.setattr(incus_pki_mod, "_fingerprint_from_cert", fingerprint)
    cert_get = Mock()
    monkeypatch.setattr(incus_pki_mod, "cert_get", cert_get)

    assert incus_pki_mod.cert_fingerprint(cert_pem="certificate") == {
        "success": True,
        "changed": False,
        "comment": "Certificate fingerprint calculated",
        "fingerprint": "abc123",
    }
    fingerprint.assert_called_once_with("certificate")
    cert_get.assert_not_called()


def test_cert_fingerprint_loads_certificate_from_storage(monkeypatch):
    cert_get = Mock(return_value={"success": True, "cert": "stored-certificate"})
    monkeypatch.setattr(incus_pki_mod, "cert_get", cert_get)
    monkeypatch.setattr(
        incus_pki_mod, "_fingerprint_from_cert", Mock(return_value="abc123")
    )

    result = incus_pki_mod.cert_fingerprint(storage={"cert": "cert", "key": "key"})

    assert result["success"] is True
    assert result["fingerprint"] == "abc123"
    cert_get.assert_called_once_with(storage={"cert": "cert", "key": "key"})


def test_cert_fingerprint_returns_cert_get_error(monkeypatch):
    error = {"success": False, "changed": False, "error": "missing"}
    monkeypatch.setattr(incus_pki_mod, "cert_get", Mock(return_value=error))

    assert incus_pki_mod.cert_fingerprint() is error


def test_cert_fingerprint_reports_exception(monkeypatch):
    monkeypatch.setattr(
        incus_pki_mod,
        "_fingerprint_from_cert",
        Mock(side_effect=ValueError("invalid certificate")),
    )

    assert incus_pki_mod.cert_fingerprint(cert_pem="certificate") == {
        "success": False,
        "changed": False,
        "comment": "Failed to calculate certificate fingerprint: invalid certificate",
        "error": "invalid certificate",
    }


def test_generate_keypair_skips_existing_pair(monkeypatch):
    storage = {"cert": "cert", "key": "key"}
    monkeypatch.setattr(
        incus_pki_mod, "_normalize_storage", Mock(return_value=storage)
    )
    monkeypatch.setattr(
        incus_pki_mod, "_normalize_generate", Mock(return_value=("client", 30))
    )
    monkeypatch.setattr(
        incus_pki_mod, "_storage_read", Mock(side_effect=["cert", "key"])
    )
    generate = Mock()
    monkeypatch.setattr(incus_pki_mod, "_generate_keypair", generate)

    assert incus_pki_mod.generate_keypair() == {
        "success": True,
        "changed": False,
        "comment": "Certificate and key already exist in storage",
    }
    generate.assert_not_called()


@pytest.mark.parametrize(
    ("existing", "force"),
    [
        ((None, None), False),
        (("cert", None), False),
        ((None, "key"), False),
        (("cert", "key"), True),
    ],
)
def test_generate_keypair_writes_new_pair(monkeypatch, existing, force):
    storage = {"cert": "cert", "key": "key"}
    monkeypatch.setattr(
        incus_pki_mod, "_normalize_storage", Mock(return_value=storage)
    )
    normalize_generate = Mock(return_value=("client", 30))
    monkeypatch.setattr(incus_pki_mod, "_normalize_generate", normalize_generate)
    monkeypatch.setattr(
        incus_pki_mod, "_storage_read", Mock(side_effect=list(existing))
    )
    generate = Mock(return_value=("new-cert", "new-key"))
    monkeypatch.setattr(incus_pki_mod, "_generate_keypair", generate)
    write = Mock()
    monkeypatch.setattr(incus_pki_mod, "_storage_write_pair", write)
    monkeypatch.setattr(
        incus_pki_mod, "_fingerprint_from_cert", Mock(return_value="abc123")
    )

    assert incus_pki_mod.generate_keypair(
        cn="client", days=30, storage=storage, force=force
    ) == {
        "success": True,
        "changed": True,
        "comment": "TLS keypair generated and stored",
        "fingerprint": "abc123",
    }
    normalize_generate.assert_called_once_with(cn="client", days=30)
    generate.assert_called_once_with("client", 30)
    write.assert_called_once_with(storage, "new-cert", "new-key")


def test_generate_keypair_reports_exception(monkeypatch):
    monkeypatch.setattr(
        incus_pki_mod,
        "_normalize_storage",
        Mock(side_effect=ValueError("invalid storage")),
    )

    assert incus_pki_mod.generate_keypair() == {
        "success": False,
        "changed": False,
        "comment": "Failed to generate TLS keypair: invalid storage",
        "error": "invalid storage",
    }
