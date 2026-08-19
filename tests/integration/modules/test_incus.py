"""Integration tests for the Incus execution modules through ``salt-call``.

The tests use a real Salt minion and require a reachable Incus daemon. Slow
instance tests additionally require a local image alias. Set
``INCUS_TEST_IMAGE_ALIAS`` to select it, or provide the complete API source as
JSON through ``INCUS_TEST_IMAGE_SOURCE``.
"""

import json
import os
import uuid

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_salt_modules(
        "incus.instance_list",
        "incus.profile_list",
        "incus.network_list",
    ),
]


def _required():
    return os.environ.get("INCUS_INTEGRATION_REQUIRED", "false").lower() == "true"


def _data(ret):
    return ret.data if isinstance(ret.data, dict) else None


def _ok(ret):
    """Assert that a salt-call result succeeded and return its data."""
    data = _data(ret)
    assert ret.returncode == 0, f"salt-call failed: {ret.stderr or data}"
    assert data is not None, f"response is not a mapping: {ret.data!r}"
    assert data.get("success") is True, f"Incus call returned failure: {data}"
    return data


def _name(kind):
    if kind == "network":
        # A managed bridge name is also a Linux interface name (IFNAMSIZ=16).
        return f"sit-{uuid.uuid4().hex[:11]}"
    return f"salt-it-{kind}-{uuid.uuid4().hex[:10]}"


def _image_source():
    raw_source = os.environ.get("INCUS_TEST_IMAGE_SOURCE")
    if raw_source:
        try:
            source = json.loads(raw_source)
        except ValueError as exc:
            pytest.fail(f"INCUS_TEST_IMAGE_SOURCE is not valid JSON: {exc}")
        if not isinstance(source, dict):
            pytest.fail("INCUS_TEST_IMAGE_SOURCE must contain a JSON object")
        return source

    return {
        "type": "image",
        "alias": os.environ.get("INCUS_TEST_IMAGE_ALIAS", "ubuntu/22.04"),
    }


@pytest.fixture(autouse=True)
def require_incus_daemon(salt_call_cli):
    """Skip optional local runs, but fail a required integration environment."""
    ret = salt_call_cli.run("incus.instance_list")
    data = _data(ret)
    if ret.returncode == 0 and data and data.get("success") is True:
        return

    detail = (data or {}).get("error") or ret.stderr or repr(ret.data)
    message = f"Incus integration environment is unavailable: {detail}"
    if _required():
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture
def incus_profile(salt_call_cli):
    """Create a uniquely named profile and remove it after the test."""
    name = _name("profile")
    ret = salt_call_cli.run(
        "incus.profile_create",
        name,
        config={"limits.cpu": "1", "limits.memory": "256MiB"},
        description="salt integration test profile",
    )
    _ok(ret)
    try:
        yield name
    finally:
        salt_call_cli.run("incus.profile_delete", name)


@pytest.fixture
def incus_container(salt_call_cli):
    """Create a stopped container and force-remove it after the test."""
    name = _name("container")
    ret = salt_call_cli.run(
        "incus.instance_create",
        name,
        source=_image_source(),
        instance_type="container",
    )
    data = _data(ret)
    if not data or data.get("success") is not True:
        detail = (data or {}).get("error") or ret.stderr or repr(ret.data)
        message = f"Incus test image is unavailable: {detail}"
        if _required():
            pytest.fail(message)
        pytest.skip(message)
    _ok(ret)
    try:
        yield name
    finally:
        salt_call_cli.run("incus.instance_delete", name, force=True)


class TestProfiles:
    def test_profile_list_returns_success(self, salt_call_cli):
        data = _ok(salt_call_cli.run("incus.profile_list", recursion=1))
        assert isinstance(data["profiles"], list)

    def test_profile_lifecycle(self, salt_call_cli):
        name = _name("profile")
        renamed = f"{name}-renamed"
        try:
            data = _ok(
                salt_call_cli.run(
                    "incus.profile_create",
                    name,
                    config={"limits.cpu": "2"},
                    description="lifecycle test",
                )
            )
            assert name in data["message"]

            data = _ok(salt_call_cli.run("incus.profile_get", name))
            assert data["profile"]["name"] == name
            assert data["profile"]["config"].get("limits.cpu") == "2"

            _ok(
                salt_call_cli.run(
                    "incus.profile_update",
                    name,
                    config={"limits.cpu": "4"},
                    description="updated",
                )
            )
            data = _ok(salt_call_cli.run("incus.profile_get", name))
            assert data["profile"]["config"]["limits.cpu"] == "4"

            _ok(salt_call_cli.run("incus.profile_rename", name, renamed))
            data = _ok(salt_call_cli.run("incus.profile_get", renamed))
            assert data["profile"]["name"] == renamed

            _ok(salt_call_cli.run("incus.profile_delete", renamed))
        finally:
            salt_call_cli.run("incus.profile_delete", name)
            salt_call_cli.run("incus.profile_delete", renamed)

    def test_profile_copy(self, salt_call_cli, incus_profile):
        copy_name = f"{incus_profile}-copy"
        try:
            data = _ok(
                salt_call_cli.run(
                    "incus.profile_copy",
                    incus_profile,
                    copy_name,
                    description="copy",
                )
            )
            assert copy_name in data["message"]

            data = _ok(salt_call_cli.run("incus.profile_get", copy_name))
            assert data["profile"]["config"].get("limits.cpu") == "1"
        finally:
            salt_call_cli.run("incus.profile_delete", copy_name)


class TestNetworks:
    def test_network_list_returns_success(self, salt_call_cli):
        data = _ok(salt_call_cli.run("incus.network_list", recursion=1))
        assert isinstance(data["networks"], list)

    def test_network_lifecycle(self, salt_call_cli):
        name = _name("network")
        try:
            data = _ok(
                salt_call_cli.run(
                    "incus.network_create",
                    name,
                    config={"ipv4.address": "none", "ipv6.address": "none"},
                )
            )
            assert name in data["message"]

            data = _ok(salt_call_cli.run("incus.network_get", name))
            assert data["network"]["name"] == name

            _ok(salt_call_cli.run("incus.network_delete", name))
        finally:
            salt_call_cli.run("incus.network_delete", name)


class TestInstances:
    def test_instance_list_returns_success(self, salt_call_cli):
        data = _ok(salt_call_cli.run("incus.instance_list", recursion=1))
        assert isinstance(data["instances"], list)

    @pytest.mark.slow
    def test_instance_lifecycle(self, salt_call_cli, incus_container):
        name = incus_container
        data = _ok(salt_call_cli.run("incus.instance_get", name))
        assert data["instance"]["name"] == name

        _ok(salt_call_cli.run("incus.instance_start", name))
        data = _ok(salt_call_cli.run("incus.instance_get", name))
        assert data["instance"]["status"] == "Running"

        _ok(salt_call_cli.run("incus.instance_stop", name, timeout=60))
        data = _ok(salt_call_cli.run("incus.instance_get", name))
        assert data["instance"]["status"] == "Stopped"

    @pytest.mark.slow
    def test_instance_snapshot_lifecycle(self, salt_call_cli, incus_container):
        name = incus_container
        snap_name = _name("snapshot")

        data = _ok(
            salt_call_cli.run(
                "incus.instance_snapshot_create",
                name,
                snap_name,
                description="integration test snapshot",
            )
        )
        assert snap_name in data["message"]

        data = _ok(salt_call_cli.run("incus.instance_snapshot_list", name, recursion=1))
        assert snap_name in [snapshot["name"] for snapshot in data["snapshots"]]

        data = _ok(salt_call_cli.run("incus.instance_snapshot_get", name, snap_name))
        assert data["snapshot"]["name"] == snap_name

        _ok(
            salt_call_cli.run(
                "incus.instance_snapshot_update",
                name,
                snap_name,
                description="updated description",
            )
        )
        _ok(salt_call_cli.run("incus.instance_snapshot_restore", name, snap_name))
        _ok(salt_call_cli.run("incus.instance_snapshot_delete", name, snap_name))

        data = _ok(salt_call_cli.run("incus.instance_snapshot_list", name, recursion=1))
        assert snap_name not in [snapshot["name"] for snapshot in data["snapshots"]]

    @pytest.mark.slow
    def test_instance_update_config(self, salt_call_cli, incus_container):
        name = incus_container
        _ok(
            salt_call_cli.run(
                "incus.instance_update",
                name,
                config={"limits.cpu": "1"},
            )
        )

        data = _ok(salt_call_cli.run("incus.instance_get", name))
        assert data["instance"]["config"].get("limits.cpu") == "1"
