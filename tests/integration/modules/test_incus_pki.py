"""Integration tests for the PKI execution module through ``salt-call``."""

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_salt_modules("incus_pki.generate_keypair"),
]


def _ok(ret):
    assert ret.returncode == 0, f"salt-call failed: {ret.stderr or ret.data}"
    assert isinstance(ret.data, dict), f"response is not a mapping: {ret.data!r}"
    assert ret.data.get("success") is True, ret.data
    return ret.data


def test_generate_read_and_fingerprint_keypair(salt_call_cli, tmp_path):
    storage = {
        "cert": str(tmp_path / "client.crt"),
        "key": str(tmp_path / "client.key"),
    }

    generated = _ok(
        salt_call_cli.run(
            "incus_pki.generate_keypair",
            cn="salt-integration-test",
            days=1,
            storage=storage,
        )
    )
    assert generated["changed"] is True
    assert generated["fingerprint"]

    certificate = _ok(salt_call_cli.run("incus_pki.cert_get", storage=storage))
    assert "-----BEGIN CERTIFICATE-----" in certificate["cert"]

    fingerprint = _ok(salt_call_cli.run("incus_pki.cert_fingerprint", storage=storage))
    assert fingerprint["fingerprint"] == generated["fingerprint"]

    unchanged = _ok(salt_call_cli.run("incus_pki.generate_keypair", storage=storage))
    assert unchanged["changed"] is False
