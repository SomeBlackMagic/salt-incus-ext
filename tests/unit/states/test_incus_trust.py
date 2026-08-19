import hashlib
from unittest.mock import Mock

import pytest

from incus.states import incus_trust_mod

CERT_PEM = """-----BEGIN CERTIFICATE-----
AQID
-----END CERTIFICATE-----"""
FINGERPRINT = hashlib.sha256(b"\x01\x02\x03").hexdigest()


@pytest.fixture
def state_runtime(monkeypatch):
    salt_funcs = {
        "incus.trust_add": Mock(),
        "incus.trust_list": Mock(),
        "incus.trust_remove": Mock(),
        "incus.trust_update": Mock(),
    }
    opts = {"test": False}
    monkeypatch.setattr(incus_trust_mod, "__salt__", salt_funcs, raising=False)
    monkeypatch.setattr(incus_trust_mod, "__opts__", opts, raising=False)
    return salt_funcs, opts


def _cert(name="salt-cloud", fingerprint=FINGERPRINT, restricted=False, projects=None):
    return {
        "name": name,
        "fingerprint": fingerprint,
        "restricted": restricted,
        "projects": projects or [],
    }


def _listed(salt_funcs, *certificates):
    salt_funcs["incus.trust_list"].return_value = {
        "success": True,
        "certificates": list(certificates),
    }


def test_virtual_requires_all_execution_functions(monkeypatch):
    functions = {name: Mock() for name in incus_trust_mod._REQUIRED_FUNCTIONS}
    monkeypatch.setattr(incus_trust_mod, "__salt__", functions, raising=False)
    assert incus_trust_mod.__virtual__() == "incus"

    functions.pop("incus.trust_update")
    assert incus_trust_mod.__virtual__() == (
        False,
        "Incus trust execution functions are not available: incus.trust_update",
    )


def test_fingerprint_from_pem_uses_sha256_der():
    assert incus_trust_mod._fingerprint_from_pem(CERT_PEM) == FINGERPRINT


@pytest.mark.parametrize("cert_pem", [None, "", "not a certificate"])
def test_trust_present_rejects_invalid_pem(state_runtime, cert_pem):
    salt_funcs, _ = state_runtime
    result = incus_trust_mod.trust_present("salt-cloud", cert_pem)
    assert result["result"] is False
    salt_funcs["incus.trust_list"].assert_not_called()


def test_trust_present_rejects_invalid_projects(state_runtime):
    salt_funcs, _ = state_runtime
    result = incus_trust_mod.trust_present("salt-cloud", CERT_PEM, projects="default")
    assert result["result"] is False
    assert result["comment"] == "projects must be a list of project names"
    salt_funcs["incus.trust_list"].assert_not_called()


@pytest.mark.parametrize(
    "function,args",
    [
        (incus_trust_mod.trust_present, ("salt-cloud", CERT_PEM)),
        (incus_trust_mod.trust_absent, ("salt-cloud",)),
    ],
)
def test_trust_states_report_list_errors(state_runtime, function, args):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.trust_list"].return_value = {"success": False, "error": "offline"}
    result = function(*args)
    assert result["result"] is False
    assert result["comment"] == "Failed to list trusted certificates: offline"


def test_trust_present_adds_certificate(state_runtime):
    salt_funcs, _ = state_runtime
    _listed(salt_funcs)
    salt_funcs["incus.trust_add"].return_value = {"success": True}

    result = incus_trust_mod.trust_present(
        "salt-cloud", CERT_PEM, restricted=True, projects=["default"]
    )

    assert result["result"] is True
    assert result["changes"]["trust"]["new"]["fingerprint"] == FINGERPRINT
    salt_funcs["incus.trust_add"].assert_called_once_with(
        cert_pem=CERT_PEM,
        name="salt-cloud",
        restricted=True,
        projects=["default"],
    )


def test_trust_present_reports_add_error(state_runtime):
    salt_funcs, _ = state_runtime
    _listed(salt_funcs)
    salt_funcs["incus.trust_add"].return_value = {"success": False, "error": "denied"}
    result = incus_trust_mod.trust_present("salt-cloud", CERT_PEM)
    assert result["result"] is False
    assert result["comment"] == "Failed to add certificate salt-cloud: denied"


def test_trust_present_add_test_mode(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _listed(salt_funcs)
    result = incus_trust_mod.trust_present("salt-cloud", CERT_PEM)
    assert result["result"] is None
    assert result["changes"]
    salt_funcs["incus.trust_add"].assert_not_called()


def test_trust_present_is_idempotent_and_normalizes_fingerprint(state_runtime):
    salt_funcs, _ = state_runtime
    colon_fingerprint = ":".join(
        FINGERPRINT[index : index + 2].upper() for index in range(0, len(FINGERPRINT), 2)
    )
    _listed(salt_funcs, _cert(fingerprint=colon_fingerprint))
    result = incus_trust_mod.trust_present("salt-cloud", CERT_PEM)
    assert result["result"] is True
    assert not result["changes"]
    salt_funcs["incus.trust_update"].assert_not_called()


def test_trust_present_updates_metadata(state_runtime):
    salt_funcs, _ = state_runtime
    _listed(salt_funcs, _cert(name="old", restricted=False))
    salt_funcs["incus.trust_update"].return_value = {"success": True}
    result = incus_trust_mod.trust_present(
        "salt-cloud", CERT_PEM, restricted=True, projects=["cloud"]
    )
    assert result["result"] is True
    assert result["changes"]["trust"]["old"]["name"] == "old"
    salt_funcs["incus.trust_update"].assert_called_once_with(
        FINGERPRINT,
        name="salt-cloud",
        restricted=True,
        projects=["cloud"],
    )


def test_trust_present_update_test_mode(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _listed(salt_funcs, _cert(name="old"))
    result = incus_trust_mod.trust_present("salt-cloud", CERT_PEM)
    assert result["result"] is None
    salt_funcs["incus.trust_update"].assert_not_called()


def test_trust_present_reports_update_error(state_runtime):
    salt_funcs, _ = state_runtime
    _listed(salt_funcs, _cert(name="old"))
    salt_funcs["incus.trust_update"].return_value = {"success": False, "error": "denied"}
    result = incus_trust_mod.trust_present("salt-cloud", CERT_PEM)
    assert result["result"] is False
    assert result["comment"] == "Failed to update certificate salt-cloud: denied"


def test_trust_absent_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime
    _listed(salt_funcs)
    result = incus_trust_mod.trust_absent("salt-cloud", fingerprint=FINGERPRINT)
    assert result["result"] is True
    assert not result["changes"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fingerprint": FINGERPRINT},
        {"cert_pem": CERT_PEM},
        {},
    ],
)
def test_trust_absent_removes_by_supported_identity(state_runtime, kwargs):
    salt_funcs, _ = state_runtime
    _listed(salt_funcs, _cert())
    salt_funcs["incus.trust_remove"].return_value = {"success": True}
    result = incus_trust_mod.trust_absent("salt-cloud", **kwargs)
    assert result["result"] is True
    assert result["changes"]
    salt_funcs["incus.trust_remove"].assert_called_once_with(FINGERPRINT)


def test_trust_absent_rejects_mismatched_identity(state_runtime):
    salt_funcs, _ = state_runtime
    result = incus_trust_mod.trust_absent("salt-cloud", fingerprint="different", cert_pem=CERT_PEM)
    assert result["result"] is False
    assert result["comment"] == "fingerprint does not match cert_pem"
    salt_funcs["incus.trust_list"].assert_not_called()


def test_trust_absent_rejects_ambiguous_name(state_runtime):
    salt_funcs, _ = state_runtime
    _listed(salt_funcs, _cert(fingerprint="one"), _cert(fingerprint="two"))
    result = incus_trust_mod.trust_absent("salt-cloud")
    assert result["result"] is False
    assert "Multiple certificates" in result["comment"]
    salt_funcs["incus.trust_remove"].assert_not_called()


def test_trust_absent_test_mode(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    _listed(salt_funcs, _cert())
    result = incus_trust_mod.trust_absent("salt-cloud", fingerprint=FINGERPRINT)
    assert result["result"] is None
    assert result["changes"]
    salt_funcs["incus.trust_remove"].assert_not_called()


def test_trust_absent_reports_missing_fingerprint(state_runtime):
    salt_funcs, _ = state_runtime
    certificate = {"name": "salt-cloud"}
    _listed(salt_funcs, certificate)
    result = incus_trust_mod.trust_absent("salt-cloud")
    assert result["result"] is False
    assert result["comment"] == "Trusted certificate salt-cloud has no fingerprint"


def test_trust_absent_reports_remove_error(state_runtime):
    salt_funcs, _ = state_runtime
    _listed(salt_funcs, _cert())
    salt_funcs["incus.trust_remove"].return_value = {"success": False, "error": "denied"}
    result = incus_trust_mod.trust_absent("salt-cloud", fingerprint=FINGERPRINT)
    assert result["result"] is False
    assert result["comment"] == "Failed to remove certificate salt-cloud: denied"
