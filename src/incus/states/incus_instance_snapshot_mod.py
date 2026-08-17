"""Salt state functions for managing Incus instance snapshots."""

import logging

log = logging.getLogger(__name__)

__virtualname__ = "incus"


def __virtual__():
    """Load when the Incus instance snapshot execution functions are available."""
    if "incus.instance_snapshot_list" in __salt__:
        return __virtualname__
    return False, "incus snapshot execution functions are not available"


# ======================================================================
# Instance Snapshot States
# ======================================================================


def instance_snapshot_present(instance, name, stateful=False, description=""):
    """
    Ensure an instance snapshot exists.

    :param instance: Instance name
    :param name: Snapshot name
    :param stateful: Whether to create a stateful snapshot (includes memory/runtime state)
    :param description: Snapshot description

    Example:

    .. code-block:: yaml

        mycontainer/before-update:
          incus.instance_snapshot_present:
            - instance: mycontainer
            - name: before-update
            - stateful: False
            - description: Snapshot before system update

        myvm/running-state:
          incus.instance_snapshot_present:
            - instance: myvm
            - name: running-state
            - stateful: True
            - description: Snapshot with VM running state
    """
    ret = {
        "name": f"{instance}/{name}",
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Check if instance exists
    instance_info = __salt__["incus.instance_get"](instance)
    if not instance_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Instance {instance} does not exist"
        return ret

    # Check if snapshot exists
    snapshots = __salt__["incus.instance_snapshot_list"](instance, recursion=1)
    if not snapshots.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list snapshots: {snapshots.get('error')}"
        return ret

    snapshot_list = snapshots.get("snapshots", []) or []
    snapshot_exists = any(s.get("name") == name for s in snapshot_list)

    if snapshot_exists:
        ret["comment"] = f"Snapshot {name} already exists for instance {instance}"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Snapshot {name} would be created for instance {instance}"
        ret["changes"] = {"snapshot": {"old": None, "new": name}}
        return ret

    # Create snapshot
    create_result = __salt__["incus.instance_snapshot_create"](
        instance, name, stateful=stateful, description=description
    )

    if create_result.get("success"):
        ret["comment"] = f"Snapshot {name} created for instance {instance}"
        ret["changes"] = {"snapshot": {"old": None, "new": name}}
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to create snapshot {name}: {create_result.get('error')}"

    return ret


def instance_snapshot_absent(instance, name):
    """
    Ensure an instance snapshot does not exist.

    :param instance: Instance name
    :param name: Snapshot name

    Example:

    .. code-block:: yaml

        mycontainer/old-snap:
          incus.instance_snapshot_absent:
            - instance: mycontainer
            - name: old-snap
    """
    ret = {
        "name": f"{instance}/{name}",
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Check if instance exists
    instance_info = __salt__["incus.instance_get"](instance)
    if not instance_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Instance {instance} does not exist"
        return ret

    # Check if snapshot exists
    snapshots = __salt__["incus.instance_snapshot_list"](instance, recursion=1)
    if not snapshots.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list snapshots: {snapshots.get('error')}"
        return ret

    snapshot_list = snapshots.get("snapshots", []) or []
    snapshot_exists = any(s.get("name") == name for s in snapshot_list)

    if not snapshot_exists:
        ret["comment"] = f"Snapshot {name} already absent from instance {instance}"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Snapshot {name} would be deleted from instance {instance}"
        ret["changes"] = {"snapshot": {"old": name, "new": None}}
        return ret

    # Delete snapshot
    delete_result = __salt__["incus.instance_snapshot_delete"](instance, name)

    if delete_result.get("success"):
        ret["comment"] = f"Snapshot {name} deleted from instance {instance}"
        ret["changes"] = {"snapshot": {"old": name, "new": None}}
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to delete snapshot {name}: {delete_result.get('error')}"

    return ret


def instance_snapshot_restored(instance, name):
    """
    Ensure an instance is restored to a specific snapshot state.

    WARNING: This will restore the instance to the snapshot state,
    losing any changes made after the snapshot was created.

    :param instance: Instance name
    :param name: Snapshot name to restore

    Example:

    .. code-block:: yaml

        mycontainer/before-update:
          incus.instance_snapshot_restored:
            - instance: mycontainer
            - name: before-update
    """
    ret = {
        "name": f"{instance}/{name}",
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Check if instance exists
    instance_info = __salt__["incus.instance_get"](instance)
    if not instance_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Instance {instance} does not exist"
        return ret

    # Check if snapshot exists
    snapshots = __salt__["incus.instance_snapshot_list"](instance, recursion=1)
    if not snapshots.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list snapshots: {snapshots.get('error')}"
        return ret

    snapshot_list = snapshots.get("snapshots", []) or []
    snapshot_exists = any(s.get("name") == name for s in snapshot_list)

    if not snapshot_exists:
        ret["result"] = False
        ret["comment"] = f"Snapshot {name} does not exist for instance {instance}"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Instance {instance} would be restored to snapshot {name}"
        ret["changes"] = {
            "restored": {
                "old": "current state",
                "new": f"snapshot {name}",
            }
        }
        return ret

    # Restore snapshot
    restore_result = __salt__["incus.instance_snapshot_restore"](instance, name)

    if restore_result.get("success"):
        ret["comment"] = f"Instance {instance} restored to snapshot {name}"
        ret["changes"] = {
            "restored": {
                "old": "current state",
                "new": f"snapshot {name}",
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to restore snapshot {name}: {restore_result.get('error')}"

    return ret


def instance_snapshots_managed(  # pylint: disable=unused-argument
    instance, snapshots_config, name=None
):
    """
    Manage multiple snapshots for an instance with rotation policy.

    This state ensures that specified snapshots exist and automatically
    rotates old snapshots based on retention policies. It supports:
    - Creating multiple snapshots with different configurations
    - Automatic snapshot rotation based on keep count
    - Pattern-based snapshot management (e.g., daily-*, weekly-*)
    - Expiry date management

    :param instance: Instance name
    :param snapshots_config: Dictionary of snapshot configurations
    :param name: Salt state ID (automatically supplied by Salt)

    Each snapshot configuration can include:
    - name: Snapshot name (required)
    - stateful: Whether to create stateful snapshot (default: False)
    - description: Snapshot description
    - keep: Number of snapshots to keep for this pattern (rotation)
    - pattern: Name pattern for rotation (e.g., "daily-*")
    - expires_at: Expiry date in ISO format

    Example:

    .. code-block:: yaml

        web-container-snapshots:
          incus.instance_snapshots_managed:
            - instance: web-container
            - snapshots_config:
                daily:
                  name: daily-{{ salt['cmd.run']('date +%Y%m%d') }}
                  stateful: False
                  description: Daily automated snapshot
                  pattern: daily-*
                  keep: 7
                weekly:
                  name: weekly-{{ salt['cmd.run']('date +%YW%V') }}
                  stateful: False
                  description: Weekly automated snapshot
                  pattern: weekly-*
                  keep: 4
                before-update:
                  name: before-update
                  stateful: False
                  description: Pre-update snapshot
                  keep: 3
    """
    ret = {
        "name": f"{instance}_snapshots",
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Check if instance exists
    instance_info = __salt__["incus.instance_get"](instance)
    if not instance_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Instance {instance} does not exist"
        return ret

    # Get current snapshots
    snapshots_result = __salt__["incus.instance_snapshot_list"](instance, recursion=1)
    if not snapshots_result.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list snapshots: {snapshots_result.get('error')}"
        return ret

    current_snapshots = snapshots_result.get("snapshots", []) or []
    current_snapshot_names = [s.get("name") for s in current_snapshots]

    changes = {}
    snapshots_created = []
    snapshots_rotated = []

    # Process each snapshot configuration
    for snap_id, snap_config in snapshots_config.items():
        snap_name = snap_config.get("name")
        if not snap_name:
            ret["result"] = False
            ret["comment"] = f"Snapshot configuration '{snap_id}' missing 'name' field"
            return ret

        stateful = snap_config.get("stateful", False)
        description = snap_config.get("description", "")
        keep = snap_config.get("keep")
        pattern = snap_config.get("pattern")
        expires_at = snap_config.get("expires_at")

        # Check if snapshot needs to be created
        if snap_name not in current_snapshot_names:
            if __opts__.get("test"):
                snapshots_created.append(snap_name)
            else:
                # Create snapshot
                create_result = __salt__["incus.instance_snapshot_create"](
                    instance, snap_name, stateful=stateful, description=description
                )
                if not create_result.get("success"):
                    ret["result"] = False
                    ret["comment"] = (
                        f"Failed to create snapshot {snap_name}: {create_result.get('error')}"
                    )
                    return ret

                snapshots_created.append(snap_name)

                # Update expires_at if specified
                if expires_at:
                    update_result = __salt__["incus.instance_snapshot_update"](
                        instance, snap_name, expires_at=expires_at
                    )
                    if not update_result.get("success"):
                        log.warning(
                            "Failed to set expiry for snapshot %s: %s",
                            snap_name,
                            update_result.get("error"),
                        )

        # Handle rotation if pattern and keep are specified
        if pattern and keep is not None:
            import fnmatch

            # Find all snapshots matching the pattern
            matching_snapshots = [
                s for s in current_snapshots if fnmatch.fnmatch(s.get("name", ""), pattern)
            ]

            # Sort by creation time (oldest first)
            matching_snapshots.sort(key=lambda s: s.get("created_at", ""))

            # If we have more than 'keep' snapshots, delete the oldest ones
            if len(matching_snapshots) > keep:
                to_delete = matching_snapshots[: len(matching_snapshots) - keep]

                for snap_to_delete in to_delete:
                    del_name = snap_to_delete.get("name")
                    if __opts__.get("test"):
                        snapshots_rotated.append(del_name)
                    else:
                        delete_result = __salt__["incus.instance_snapshot_delete"](
                            instance, del_name
                        )
                        if delete_result.get("success"):
                            snapshots_rotated.append(del_name)
                        else:
                            log.warning(
                                "Failed to delete snapshot %s during rotation: %s",
                                del_name,
                                delete_result.get("error"),
                            )

    # Build changes dict
    if snapshots_created:
        changes["created"] = {"old": None, "new": snapshots_created}

    if snapshots_rotated:
        changes["rotated"] = {"old": snapshots_rotated, "new": None}

    if changes:
        if __opts__.get("test"):
            ret["result"] = None
            ret["comment"] = f"Instance {instance} snapshots would be managed"
        else:
            ret["comment"] = f"Instance {instance} snapshots managed successfully"
        ret["changes"] = changes
    else:
        ret["comment"] = f"Instance {instance} snapshots already in desired state"

    return ret


def instance_snapshots_rotated(  # pylint: disable=unused-argument
    instance, pattern, keep, name=None
):
    """
    Ensure snapshots matching a pattern are rotated, keeping only the newest N.

    This state is useful for implementing snapshot retention policies.
    It will delete the oldest snapshots that match the specified pattern,
    keeping only the specified number of the most recent ones.

    :param instance: Instance name
    :param pattern: Snapshot name pattern (supports wildcards like "daily-*")
    :param keep: Number of snapshots to keep
    :param name: Salt state ID (automatically supplied by Salt)

    Example:

    .. code-block:: yaml

        rotate-daily-snapshots:
          incus.instance_snapshots_rotated:
            - instance: web-container
            - pattern: daily-*
            - keep: 7

        rotate-weekly-snapshots:
          incus.instance_snapshots_rotated:
            - instance: web-container
            - pattern: weekly-*
            - keep: 4

        rotate-backup-snapshots:
          incus.instance_snapshots_rotated:
            - instance: database
            - pattern: backup-*
            - keep: 10
    """
    import fnmatch

    ret = {
        "name": f"{instance}_rotate_{pattern}",
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Check if instance exists
    instance_info = __salt__["incus.instance_get"](instance)
    if not instance_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Instance {instance} does not exist"
        return ret

    # Get current snapshots
    snapshots_result = __salt__["incus.instance_snapshot_list"](instance, recursion=1)
    if not snapshots_result.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list snapshots: {snapshots_result.get('error')}"
        return ret

    current_snapshots = snapshots_result.get("snapshots", []) or []

    # Find all snapshots matching the pattern
    matching_snapshots = [
        s for s in current_snapshots if fnmatch.fnmatch(s.get("name", ""), pattern)
    ]

    # Sort by creation time (oldest first)
    matching_snapshots.sort(key=lambda s: s.get("created_at", ""))

    # Check if rotation is needed
    if len(matching_snapshots) <= keep:
        ret["comment"] = (
            f"Snapshot rotation not needed: {len(matching_snapshots)} snapshots (keeping {keep})"
        )
        return ret

    # Calculate which snapshots to delete
    to_delete = matching_snapshots[: len(matching_snapshots) - keep]
    to_delete_names = [s.get("name") for s in to_delete]

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Would delete {len(to_delete)} old snapshots matching pattern '{pattern}'"
        ret["changes"] = {
            "deleted": {
                "old": to_delete_names,
                "new": None,
            }
        }
        return ret

    # Delete old snapshots
    deleted = []
    failed = []

    for snap in to_delete:
        snap_name = snap.get("name")
        delete_result = __salt__["incus.instance_snapshot_delete"](instance, snap_name)
        if delete_result.get("success"):
            deleted.append(snap_name)
        else:
            failed.append({"name": snap_name, "error": delete_result.get("error")})

    # Build result
    if deleted:
        ret["changes"] = {
            "deleted": {
                "old": deleted,
                "new": None,
            }
        }

    if failed:
        ret["result"] = False
        ret["comment"] = f"Failed to delete some snapshots: {failed}"
    else:
        ret["comment"] = f"Deleted {len(deleted)} old snapshots matching pattern '{pattern}'"

    return ret
