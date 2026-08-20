"""Salt state functions for managing Incus storage volumes."""

from incus.utils import log_state_changes

__virtualname__ = "incus"


def __virtual__():
    """Load when the Incus volume execution functions are available."""
    if "incus.volume_list" in __salt__:
        return __virtualname__
    return False, "incus volume execution functions are not available"


# ======================================================================
# Storage Volume States
# ======================================================================


@log_state_changes
def volume_present(name, pool, volume_type="custom", config=None, description=""):
    """
    Ensure a storage volume exists.

    :param name: Volume name
    :param pool: Pool name
    :param volume_type: Volume type (custom, image, container, virtual-machine)
    :param config: Volume configuration
    :param description: Volume description

    Example:

    .. code-block:: yaml

        myvolume:
          incus.volume_present:
            - pool: default
            - config:
                size: 10GB
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    volumes = __salt__["incus.volume_list"](pool, recursion=1)
    if not volumes.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list volumes in pool {pool}: " f"{volumes.get('error')}"
        return ret

    volume_list = volumes.get("volumes", []) or []
    volume_exists = any(v.get("name") == name and v.get("type") == volume_type for v in volume_list)

    if volume_exists:
        ret["comment"] = f"Volume {name} already exists in pool {pool}"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Volume {name} would be created in pool {pool}"
        ret["changes"] = {
            "volume": {
                "old": None,
                "new": name,
            }
        }
        return ret

    create_result = __salt__["incus.volume_create"](
        pool,
        name,
        volume_type=volume_type,
        config=config,
        description=description,
    )

    if create_result.get("success"):
        ret["comment"] = f"Volume {name} created in pool {pool}"
        ret["changes"] = {
            "volume": {
                "old": None,
                "new": name,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to create volume {name}: " f"{create_result.get('error')}"

    return ret


@log_state_changes
def volume_absent(name, pool, volume_type="custom"):
    """
    Ensure a storage volume does not exist.

    :param name: Volume name
    :param pool: Pool name
    :param volume_type: Volume type

    Example:

    .. code-block:: yaml

        old_volume:
          incus.volume_absent:
            - pool: default
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    volumes = __salt__["incus.volume_list"](pool, recursion=1)
    if not volumes.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list volumes in pool {pool}: " f"{volumes.get('error')}"
        return ret

    volume_list = volumes.get("volumes", []) or []
    volume_exists = any(v.get("name") == name and v.get("type") == volume_type for v in volume_list)

    if not volume_exists:
        ret["comment"] = f"Volume {name} already absent from pool {pool}"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Volume {name} would be deleted from pool {pool}"
        ret["changes"] = {
            "volume": {
                "old": name,
                "new": None,
            }
        }
        return ret

    delete_result = __salt__["incus.volume_delete"](pool, name, volume_type)

    if delete_result.get("success"):
        ret["comment"] = f"Volume {name} deleted from pool {pool}"
        ret["changes"] = {
            "volume": {
                "old": name,
                "new": None,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to delete volume {name}: " f"{delete_result.get('error')}"

    return ret


@log_state_changes
def volume_config(name, pool, volume_type="custom", config=None, description=None):
    """
    Ensure a storage volume has specific configuration.

    :param name: Volume name
    :param pool: Pool name
    :param volume_type: Volume type
    :param config: Configuration dict to apply
    :param description: Volume description to update (optional)

    Example:

    .. code-block:: yaml

        myvolume:
          incus.volume_config:
            - pool: default
            - config:
                size: 20GiB
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Get current volume info
    volume_info = __salt__["incus.volume_get"](pool, name, volume_type)
    if not volume_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to get volume {name}: {volume_info.get('error')}"
        return ret

    current_volume = volume_info.get("volume", {})
    current_config = current_volume.get("config", {})
    current_description = current_volume.get("description", "")

    # Check what needs to be updated
    config_changes = {}
    for key, value in (config or {}).items():
        if current_config.get(key) != value:
            config_changes[key] = {"old": current_config.get(key), "new": value}

    description_changed = description is not None and current_description != description

    if not config_changes and not description_changed:
        ret["comment"] = f"Volume {name} already has desired configuration"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Volume {name} configuration would be updated"
        if config_changes:
            ret["changes"]["config"] = config_changes
        if description_changed:
            ret["changes"]["description"] = {"old": current_description, "new": description}
        return ret

    # Apply updates
    update_result = __salt__["incus.volume_update"](
        pool, name, volume_type=volume_type, config=config, description=description
    )

    if update_result.get("success"):
        ret["comment"] = f"Volume {name} configuration updated"
        if config_changes:
            ret["changes"]["config"] = config_changes
        if description_changed:
            ret["changes"]["description"] = {"old": current_description, "new": description}
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to update volume {name}: {update_result.get('error')}"

    return ret


@log_state_changes
def volume_snapshot_present(name, pool, volume, volume_type="custom", description=""):
    """
    Ensure a volume snapshot exists.

    :param name: Snapshot name
    :param pool: Pool name
    :param volume: Volume name
    :param volume_type: Volume type
    :param description: Snapshot description

    Example:

    .. code-block:: yaml

        snap1:
          incus.volume_snapshot_present:
            - pool: default
            - volume: myvolume
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Check if snapshot exists
    snapshots = __salt__["incus.volume_snapshot_list"](pool, volume, volume_type, recursion=1)
    if not snapshots.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list snapshots: {snapshots.get('error')}"
        return ret

    snapshot_list = snapshots.get("snapshots", []) or []
    snapshot_exists = any(s.get("name") == name for s in snapshot_list)

    if snapshot_exists:
        ret["comment"] = f"Snapshot {name} already exists for volume {volume}"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Snapshot {name} would be created for volume {volume}"
        ret["changes"] = {"snapshot": {"old": None, "new": name}}
        return ret

    # Create snapshot
    create_result = __salt__["incus.volume_snapshot_create"](
        pool, volume, name, volume_type=volume_type, description=description
    )

    if create_result.get("success"):
        ret["comment"] = f"Snapshot {name} created for volume {volume}"
        ret["changes"] = {"snapshot": {"old": None, "new": name}}
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to create snapshot {name}: {create_result.get('error')}"

    return ret


@log_state_changes
def volume_snapshot_absent(name, pool, volume, volume_type="custom"):
    """
    Ensure a volume snapshot does not exist.

    :param name: Snapshot name
    :param pool: Pool name
    :param volume: Volume name
    :param volume_type: Volume type

    Example:

    .. code-block:: yaml

        old_snap:
          incus.volume_snapshot_absent:
            - pool: default
            - volume: myvolume
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Check if snapshot exists
    snapshots = __salt__["incus.volume_snapshot_list"](pool, volume, volume_type, recursion=1)
    if not snapshots.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list snapshots: {snapshots.get('error')}"
        return ret

    snapshot_list = snapshots.get("snapshots", []) or []
    snapshot_exists = any(s.get("name") == name for s in snapshot_list)

    if not snapshot_exists:
        ret["comment"] = f"Snapshot {name} already absent from volume {volume}"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Snapshot {name} would be deleted from volume {volume}"
        ret["changes"] = {"snapshot": {"old": name, "new": None}}
        return ret

    # Delete snapshot
    delete_result = __salt__["incus.volume_snapshot_delete"](pool, volume, name, volume_type)

    if delete_result.get("success"):
        ret["comment"] = f"Snapshot {name} deleted from volume {volume}"
        ret["changes"] = {"snapshot": {"old": name, "new": None}}
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to delete snapshot {name}: {delete_result.get('error')}"

    return ret


@log_state_changes
def volume_attached(  # pylint: disable=unused-argument
    name, pool, instance, device_name=None, path=None, volume_type="custom"
):
    """
    Ensure a volume is attached to an instance.

    :param name: Volume name
    :param pool: Pool name
    :param instance: Instance name
    :param device_name: Device name (defaults to volume name)
    :param path: Mount path inside instance
    :param volume_type: Volume type

    Example:

    .. code-block:: yaml

        myvolume:
          incus.volume_attached:
            - pool: default
            - instance: mycontainer
            - path: /mnt/data
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    device_name = device_name or name

    # Get instance info
    instance_info = __salt__["incus.instance_get"](instance)
    if not instance_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to get instance {instance}: {instance_info.get('error')}"
        return ret

    current_devices = instance_info.get("instance", {}).get("devices", {})

    # Check if device already attached
    if device_name in current_devices:
        device = current_devices[device_name]
        if (
            device.get("type") == "disk"
            and device.get("pool") == pool
            and device.get("source") == name
        ):
            ret["comment"] = f"Volume {name} already attached to instance {instance}"
            return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Volume {name} would be attached to instance {instance}"
        ret["changes"] = {
            "device": {
                "old": current_devices.get(device_name),
                "new": {
                    "type": "disk",
                    "pool": pool,
                    "source": name,
                    "path": path,
                },
            }
        }
        return ret

    # Attach volume
    new_devices = {
        device_name: {
            "type": "disk",
            "pool": pool,
            "source": name,
        }
    }
    if path:
        new_devices[device_name]["path"] = path

    update_result = __salt__["incus.instance_update"](instance, devices=new_devices)

    if update_result.get("success"):
        ret["comment"] = f"Volume {name} attached to instance {instance}"
        ret["changes"] = {
            "device": {
                "old": current_devices.get(device_name),
                "new": new_devices[device_name],
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to attach volume {name}: {update_result.get('error')}"

    return ret


@log_state_changes
def volume_detached(name, pool, instance, device_name=None):
    """
    Ensure a volume is detached from an instance.

    :param name: Volume name
    :param pool: Pool name
    :param instance: Instance name
    :param device_name: Device name (defaults to volume name)

    Example:

    .. code-block:: yaml

        myvolume:
          incus.volume_detached:
            - pool: default
            - instance: mycontainer
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    device_name = device_name or name

    # Get instance info
    instance_info = __salt__["incus.instance_get"](instance)
    if not instance_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to get instance {instance}: {instance_info.get('error')}"
        return ret

    current_devices = instance_info.get("instance", {}).get("devices", {})

    # Check if device is attached
    if device_name not in current_devices:
        ret["comment"] = f"Volume {name} already detached from instance {instance}"
        return ret

    device = current_devices[device_name]
    if device.get("pool") != pool or device.get("source") != name:
        ret["comment"] = f"Device {device_name} is not volume {name} from pool {pool}"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Volume {name} would be detached from instance {instance}"
        ret["changes"] = {"device": {"old": device, "new": None}}
        return ret

    # Detach volume by updating instance without this device
    remaining_devices = {k: v for k, v in current_devices.items() if k != device_name}

    # Get full instance config to update
    instance_data = instance_info.get("instance", {})
    instance_data["devices"] = remaining_devices

    # We need to use a different approach - remove the device
    # Using instance_update with empty devices dict for the specific device
    update_result = __salt__["incus.instance_update"](
        instance, devices={device_name: {}}  # Empty dict removes the device
    )

    if update_result.get("success"):
        ret["comment"] = f"Volume {name} detached from instance {instance}"
        ret["changes"] = {"device": {"old": device, "new": None}}
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to detach volume {name}: {update_result.get('error')}"

    return ret
