import os

import pytest


def _verify_value(value):
    """Normalize INCUS_VERIFY while preserving a CA bundle path."""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


@pytest.fixture(scope="package")
def minion_config():  # pragma: no cover
    """Configure the Incus connection used by the integration minion."""
    incus_url = os.environ.get("INCUS_URL")
    if incus_url:
        cert = os.environ.get("INCUS_CERT")
        key = os.environ.get("INCUS_KEY")
        if bool(cert) != bool(key):
            pytest.fail("INCUS_CERT and INCUS_KEY must be set together")

        cert_storage = {
            "type": "local_files",
            "verify": _verify_value(os.environ.get("INCUS_VERIFY", "true")),
        }
        if cert and key:
            cert_storage.update({"cert": cert, "key": key})

        connection = {
            "type": "https",
            "url": incus_url,
            "cert_storage": cert_storage,
        }
    else:
        connection = {
            "type": "unix",
            "socket": os.environ.get("INCUS_SOCKET", "/var/lib/incus/unix.socket"),
        }

    return {"incus": {"connection": connection}}


@pytest.fixture(scope="package")
def master(master):  # pragma: no cover
    with master.started():
        yield master


@pytest.fixture(scope="package")
def minion(minion):  # pragma: no cover
    with minion.started():
        yield minion


@pytest.fixture
def salt_run_cli(master):  # pragma: no cover
    return master.salt_run_cli()


@pytest.fixture
def salt_cli(master):  # pragma: no cover
    return master.salt_cli()


@pytest.fixture
def salt_call_cli(minion):  # pragma: no cover
    return minion.salt_call_cli()


@pytest.fixture(scope="module")
def salt_ssh_cli(
    master, salt_ssh_roster_file, sshd_config_dir, known_hosts_file
):  # pylint: disable=unused-argument; pragma: no cover
    return master.salt_ssh_cli(
        timeout=180,
        roster_file=salt_ssh_roster_file,
        target_host="localhost",
        client_key=str(sshd_config_dir / "client_key"),
    )
