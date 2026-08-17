# """Integration tests for the Incus Salt module.
#
# These tests require a running Incus daemon accessible via Unix socket at
# /var/lib/incus/unix.socket (the default) or configured via minion pillar.
#
# A minimal Ubuntu image must be available under the alias ``ubuntu/22.04`` or
# reachable from https://images.linuxcontainers.org to allow container creation
# tests to pass.
# """
#
# import pytest
#
# pytestmark = [
#     pytest.mark.requires_salt_modules(
#         "incus.instance_list",
#         "incus.profile_list",
#         "incus.network_list",
#     ),
# ]
#
# # ---------------------------------------------------------------------------
# # Constants
# # ---------------------------------------------------------------------------
#
# TEST_CONTAINER_NAME = "salt-test-container"
# TEST_PROFILE_NAME = "salt-test-profile"
# TEST_NETWORK_NAME = "saltbr0"
# TEST_IMAGE_ALIAS = "images:ubuntu/22.04"
#
#
# # ---------------------------------------------------------------------------
# # Helpers
# # ---------------------------------------------------------------------------
#
#
# _CONNECTION_ERRORS = (
#     "Permission denied",
#     "Connection refused",
#     "No such file or directory",
#     "Connection aborted",
#     "FileNotFoundError",
# )
#
# _IMAGE_ERRORS = (
#     "Image not provided",
#     "not found",
#     "Failed to fetch",
#     "No source provided",
# )
#
#
# def _ok(ret):
#     """Assert that a salt_call_cli result succeeded and return its JSON."""
#     if ret.returncode == 255 and ret.stderr and "is not available" in ret.stderr:
#         pytest.skip(f"incus module not available: {ret.stderr.strip()}")
#
#     # Check the returned data before asserting returncode,
#     # because salt-call exits with code 1 when the function returns an error dict.
#     data = ret.data
#     if data is not None and not data.get("success"):
#         error = str(data.get("error", ""))
#         if any(msg in error for msg in _CONNECTION_ERRORS):
#             pytest.skip(f"Incus daemon not accessible: {error}")
#         if any(msg in error for msg in _IMAGE_ERRORS):
#             pytest.skip(f"Incus image not available: {error}")
#
#     assert ret.returncode == 0, f"salt-call failed: {ret.stderr}"
#     assert data is not None, "response is not JSON"
#     assert data.get("success") is True, f"incus call returned failure: {data}"
#     return data
#
#
# # ---------------------------------------------------------------------------
# # Fixtures
# # ---------------------------------------------------------------------------
#
#
# @pytest.fixture
# def incus_profile(salt_call_cli):
#     """Create a test profile and remove it after the test."""
#     ret = salt_call_cli.run(
#         "incus.profile_create",
#         TEST_PROFILE_NAME,
#         config={"limits.cpu": "1", "limits.memory": "256MiB"},
#         description="salt integration test profile",
#     )
#     _ok(ret)
#
#     yield TEST_PROFILE_NAME
#
#     salt_call_cli.run("incus.profile_delete", TEST_PROFILE_NAME)
#
#
# @pytest.fixture
# def incus_network(salt_call_cli):
#     """Create a test bridge network and remove it after the test."""
#     ret = salt_call_cli.run(
#         "incus.network_create",
#         TEST_NETWORK_NAME,
#         config={
#             "ipv4.address": "10.200.100.1/24",
#             "ipv4.nat": "true",
#             "ipv6.address": "none",
#         },
#     )
#     _ok(ret)
#
#     yield TEST_NETWORK_NAME
#
#     salt_call_cli.run("incus.network_delete", TEST_NETWORK_NAME)
#
#
# @pytest.fixture
# def incus_container(salt_call_cli):
#     """Create a stopped test container and remove it after the test."""
#     ret = salt_call_cli.run(
#         "incus.instance_create",
#         TEST_CONTAINER_NAME,
#         source={"type": "image", "alias": TEST_IMAGE_ALIAS},
#         instance_type="container",
#     )
#     _ok(ret)
#
#     yield TEST_CONTAINER_NAME
#
#     # Make sure the container is stopped before deletion
#     salt_call_cli.run("incus.instance_stop", TEST_CONTAINER_NAME, force=True)
#     salt_call_cli.run("incus.instance_delete", TEST_CONTAINER_NAME)
#
#
# # ---------------------------------------------------------------------------
# # Profile tests
# # ---------------------------------------------------------------------------
#
#
# class TestProfiles:
#     def test_profile_list_returns_success(self, salt_call_cli):
#         ret = salt_call_cli.run("incus.profile_list", recursion=1)
#         data = _ok(ret)
#         assert "profiles" in data
#         assert isinstance(data["profiles"], list)
#
#     def test_profile_lifecycle(self, salt_call_cli):
#         name = "salt-test-lifecycle-profile"
#         try:
#             # Create
#             ret = salt_call_cli.run(
#                 "incus.profile_create",
#                 name,
#                 config={"limits.cpu": "2"},
#                 description="lifecycle test",
#             )
#             data = _ok(ret)
#             assert name in data.get("message", "")
#
#             # Get
#             ret = salt_call_cli.run("incus.profile_get", name)
#             data = _ok(ret)
#             assert data["profile"]["name"] == name
#             assert data["profile"]["config"].get("limits.cpu") == "2"
#
#             # Update
#             ret = salt_call_cli.run(
#                 "incus.profile_update",
#                 name,
#                 config={"limits.cpu": "4"},
#                 description="updated",
#             )
#             _ok(ret)
#
#             ret = salt_call_cli.run("incus.profile_get", name)
#             data = _ok(ret)
#             assert data["profile"]["config"]["limits.cpu"] == "4"
#
#             # Rename
#             new_name = name + "-renamed"
#             ret = salt_call_cli.run("incus.profile_rename", name, new_name)
#             _ok(ret)
#
#             ret = salt_call_cli.run("incus.profile_get", new_name)
#             _ok(ret)
#
#             # Delete renamed profile
#             ret = salt_call_cli.run("incus.profile_delete", new_name)
#             _ok(ret)
#         finally:
#             # Best-effort cleanup for both original and renamed names
#             salt_call_cli.run("incus.profile_delete", name)
#             salt_call_cli.run("incus.profile_delete", name + "-renamed")
#
#     def test_profile_copy(self, salt_call_cli, incus_profile):
#         copy_name = incus_profile + "-copy"
#         try:
#             ret = salt_call_cli.run(
#                 "incus.profile_copy",
#                 incus_profile,
#                 copy_name,
#                 description="copy",
#             )
#             data = _ok(ret)
#             assert copy_name in data.get("message", "")
#
#             ret = salt_call_cli.run("incus.profile_get", copy_name)
#             data = _ok(ret)
#             assert data["profile"]["config"].get("limits.cpu") == "1"
#         finally:
#             salt_call_cli.run("incus.profile_delete", copy_name)
#
#
# # ---------------------------------------------------------------------------
# # Network tests
# # ---------------------------------------------------------------------------
#
#
# class TestNetworks:
#     def test_network_list_returns_success(self, salt_call_cli):
#         ret = salt_call_cli.run("incus.network_list", recursion=1)
#         data = _ok(ret)
#         assert "networks" in data
#         assert isinstance(data["networks"], list)
#
#     def test_network_lifecycle(self, salt_call_cli):
#         name = "salt-test-net0"
#         try:
#             # Create
#             ret = salt_call_cli.run(
#                 "incus.network_create",
#                 name,
#                 config={
#                     "ipv4.address": "10.200.200.1/24",
#                     "ipv4.nat": "true",
#                     "ipv6.address": "none",
#                 },
#             )
#             data = _ok(ret)
#             assert name in data.get("message", "")
#
#             # Get
#             ret = salt_call_cli.run("incus.network_get", name)
#             data = _ok(ret)
#             assert data["network"]["name"] == name
#
#             # Delete
#             ret = salt_call_cli.run("incus.network_delete", name)
#             _ok(ret)
#         finally:
#             salt_call_cli.run("incus.network_delete", name)
#
#
# # ---------------------------------------------------------------------------
# # Instance tests
# # ---------------------------------------------------------------------------
#
#
# class TestInstances:
#     def test_instance_list_returns_success(self, salt_call_cli):
#         ret = salt_call_cli.run("incus.instance_list", recursion=1)
#         data = _ok(ret)
#         assert "instances" in data
#         assert isinstance(data["instances"], list)
#
#     @pytest.mark.slow
#     def test_instance_lifecycle(self, salt_call_cli, incus_container):
#         """Full start → stop → snapshot → restore → delete lifecycle."""
#         name = incus_container
#
#         # Verify container exists and is stopped
#         ret = salt_call_cli.run("incus.instance_get", name)
#         data = _ok(ret)
#         assert data["instance"]["name"] == name
#
#         # Start
#         ret = salt_call_cli.run("incus.instance_start", name)
#         _ok(ret)
#
#         ret = salt_call_cli.run("incus.instance_get", name)
#         data = _ok(ret)
#         assert data["instance"]["status"] == "Running"
#
#         # Stop
#         ret = salt_call_cli.run("incus.instance_stop", name, timeout=60)
#         _ok(ret)
#
#         ret = salt_call_cli.run("incus.instance_get", name)
#         data = _ok(ret)
#         assert data["instance"]["status"] == "Stopped"
#
#     @pytest.mark.slow
#     def test_instance_snapshot_lifecycle(self, salt_call_cli, incus_container):
#         name = incus_container
#         snap_name = "snap1"
#
#         # Create snapshot
#         ret = salt_call_cli.run(
#             "incus.instance_snapshot_create",
#             name,
#             snap_name,
#             description="integration test snapshot",
#         )
#         data = _ok(ret)
#         assert snap_name in data.get("message", "")
#
#         # List snapshots
#         ret = salt_call_cli.run("incus.instance_snapshot_list", name, recursion=1)
#         data = _ok(ret)
#         snap_names = [s["name"] for s in data["snapshots"]]
#         assert snap_name in snap_names
#
#         # Get snapshot
#         ret = salt_call_cli.run("incus.instance_snapshot_get", name, snap_name)
#         data = _ok(ret)
#         assert data["snapshot"]["name"] == snap_name
#
#         # Update snapshot description
#         ret = salt_call_cli.run(
#             "incus.instance_snapshot_update",
#             name,
#             snap_name,
#             description="updated description",
#         )
#         _ok(ret)
#
#         # Restore snapshot
#         ret = salt_call_cli.run("incus.instance_snapshot_restore", name, snap_name)
#         _ok(ret)
#
#         # Delete snapshot
#         ret = salt_call_cli.run("incus.instance_snapshot_delete", name, snap_name)
#         _ok(ret)
#
#         ret = salt_call_cli.run("incus.instance_snapshot_list", name, recursion=1)
#         data = _ok(ret)
#         snap_names = [s["name"] for s in data["snapshots"]]
#         assert snap_name not in snap_names
#
#     @pytest.mark.slow
#     def test_instance_update_config(self, salt_call_cli, incus_container):
#         name = incus_container
#
#         ret = salt_call_cli.run(
#             "incus.instance_update",
#             name,
#             config={"limits.cpu": "1"},
#         )
#         _ok(ret)
#
#         ret = salt_call_cli.run("incus.instance_get", name)
#         data = _ok(ret)
#         assert data["instance"]["config"].get("limits.cpu") == "1"
