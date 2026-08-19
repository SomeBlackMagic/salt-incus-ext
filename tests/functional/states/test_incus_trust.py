"""Functional tests for Salt Cloud certificate trust bootstrap."""

import os
import uuid

import pytest

from incus.clouds import incus_mod as incus_cloud_mod

pytestmark = [
    pytest.mark.requires_salt_modules("incus_pki.generate_keypair"),
    pytest.mark.requires_salt_states("incus.trust_present"),
]


def test_salt_cloud_certificate_trust_lifecycle(modules, states, tmp_path):
    certificate_name = f"salt-cloud-functional-{uuid.uuid4().hex}"
    storage = {
        "cert": str(tmp_path / "salt-cloud.crt"),
        "key": str(tmp_path / "salt-cloud.key"),
    }
    generated = modules.incus_pki.generate_keypair(
        cn=certificate_name,
        days=1,
        storage=storage,
    )
    assert generated.get("success") is True, generated.get("comment")

    cert_pem = (tmp_path / "salt-cloud.crt").read_text(encoding="utf-8")
    fingerprint = generated["fingerprint"]

    try:
        added = states["incus.trust_present"](
            certificate_name,
            cert_pem=cert_pem,
            restricted=False,
        )
        assert added.result is True, added.comment
        assert added.changes

        unchanged = states["incus.trust_present"](
            certificate_name,
            cert_pem=cert_pem,
            restricted=False,
        )
        assert unchanged.result is True, unchanged.comment
        assert not unchanged.changes

        updated_name = f"{certificate_name}-updated"
        updated = states["incus.trust_present"](
            updated_name,
            cert_pem=cert_pem,
            restricted=True,
            projects=["default"],
        )
        assert updated.result is True, updated.comment
        assert updated.changes

        trusted = modules.incus.trust_get(fingerprint)
        assert trusted.get("success") is True, trusted.get("error")
        assert trusted["certificate"]["name"] == updated_name
        assert trusted["certificate"]["restricted"] is True
        assert trusted["certificate"]["projects"] == ["default"]

        removed = states["incus.trust_absent"](
            updated_name,
            fingerprint=fingerprint,
        )
        assert removed.result is True, removed.comment
        assert removed.changes

        absent = states["incus.trust_absent"](
            updated_name,
            fingerprint=fingerprint,
        )
        assert absent.result is True, absent.comment
        assert not absent.changes
    finally:
        existing = modules.incus.trust_get(fingerprint)
        if existing.get("success"):
            modules.incus.trust_remove(fingerprint)


@pytest.mark.skipif(
    not os.environ.get("INCUS_URL"),
    reason="INCUS_URL is required for the Salt Cloud HTTPS bootstrap test",
)
def test_cloud_driver_connects_after_trust_bootstrap(modules, states, tmp_path):
    certificate_name = f"salt-cloud-https-{uuid.uuid4().hex}"
    cert_path = tmp_path / "salt-cloud.crt"
    key_path = tmp_path / "salt-cloud.key"
    storage = {"cert": str(cert_path), "key": str(key_path)}
    generated = modules.incus_pki.generate_keypair(
        cn=certificate_name,
        days=1,
        storage=storage,
    )
    assert generated.get("success") is True, generated.get("comment")

    fingerprint = generated["fingerprint"]
    cert_pem = cert_path.read_text(encoding="utf-8")
    client = None
    try:
        trusted = states["incus.trust_present"](
            certificate_name,
            cert_pem=cert_pem,
            restricted=False,
        )
        assert trusted.result is True, trusted.comment

        verify = incus_cloud_mod._coerce_verify_value(os.environ.get("INCUS_VERIFY", "true"))
        client = incus_cloud_mod.IncusClient(
            {
                "connection": {
                    "type": "https",
                    "url": os.environ["INCUS_URL"],
                    "cert_storage": {
                        "type": "local_files",
                        "cert": str(cert_path),
                        "key": str(key_path),
                        "verify": verify,
                    },
                }
            }
        )
        response = client._request("GET", "")
        assert response.get("error_code") in (None, 0), response.get("error")
        assert response.get("metadata", {}).get("auth") == "trusted"
    finally:
        if client is not None:
            client.close()
        existing = modules.incus.trust_get(fingerprint)
        if existing.get("success"):
            modules.incus.trust_remove(fingerprint)
