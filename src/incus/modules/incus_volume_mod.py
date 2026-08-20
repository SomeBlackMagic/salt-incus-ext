"""Storage volume management functions for the Incus Salt module."""

import logging
from urllib.parse import quote

log = logging.getLogger(__name__)

__virtualname__ = "incus"


def __virtual__():
    from incus.modules import incus_mod

    return incus_mod.__virtual__()


def _client():
    from incus.modules.incus_mod import IncusClient

    return IncusClient(salt_funcs=__salt__)


# ========== Storage Volume Management Functions ==========


def volume_list(pool, recursion=0):
    """
    List volumes in a storage pool

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_list default

    :param pool: Pool name
    :param recursion: Recursion level
    :return: List of volumes
    """
    client = _client()
    result = client._request(
        "GET", f"/storage-pools/{quote(pool)}/volumes", params={"recursion": recursion}
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "volumes": result.get("metadata", [])}


def volume_create(pool, name, volume_type="custom", config=None, description=""):
    """
    Create a storage volume

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_create default myvolume

    :param pool: Pool name
    :param name: Volume name
    :param volume_type: Volume type (custom, image, container, virtual-machine)
    :param config: Volume configuration
    :param description: Volume description
    :return: Result
    """
    log.info("Creating volume '%s' in pool '%s'", name, pool)
    client = _client()

    data = {"name": name, "type": volume_type, "config": config or {}, "description": description}

    result = client._sync_request(
        "POST", f"/storage-pools/{quote(pool)}/volumes/{volume_type}", data=data
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    log.info("Volume '%s' created in pool '%s'", name, pool)
    return {"success": True, "message": f"Volume {name} created successfully"}


def volume_get(pool, name, volume_type="custom"):
    """
    Get storage volume information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_get default myvolume

    :param pool: Pool name
    :param name: Volume name
    :param volume_type: Volume type
    :return: Volume information
    """
    client = _client()
    result = client._request(
        "GET", f"/storage-pools/{quote(pool)}/volumes/{volume_type}/{quote(name)}"
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "volume": result.get("metadata", {})}


def volume_update(pool, name, volume_type="custom", config=None, description=None):
    """
    Update storage volume configuration

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_update default myvolume config="{'size':'20GiB'}"

    :param pool: Pool name
    :param name: Volume name
    :param volume_type: Volume type
    :param config: Configuration to update
    :param description: Volume description to update
    :return: Result
    """
    client = _client()

    # Get current volume config
    current = client._request(
        "GET", f"/storage-pools/{quote(pool)}/volumes/{volume_type}/{quote(name)}"
    )
    if "error" in current:
        return {"success": False, "error": current["error"]}

    volume_data = current.get("metadata", {})

    # Update fields
    if config:
        volume_data["config"].update(config)

    if description is not None:
        volume_data["description"] = description

    result = client._sync_request(
        "PUT", f"/storage-pools/{quote(pool)}/volumes/{volume_type}/{quote(name)}", data=volume_data
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Volume {name} updated successfully"}


def volume_rename(pool, name, new_name, volume_type="custom"):
    """
    Rename a storage volume

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_rename default myvolume mynewvolume

    :param pool: Pool name
    :param name: Current volume name
    :param new_name: New volume name
    :param volume_type: Volume type
    :return: Result
    """
    client = _client()

    data = {"name": new_name}

    result = client._sync_request(
        "POST", f"/storage-pools/{quote(pool)}/volumes/{volume_type}/{quote(name)}", data=data
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Volume {name} renamed to {new_name} successfully"}


def volume_copy(
    source_pool,
    source_volume,
    target_pool=None,
    target_volume=None,
    volume_type="custom",
    config=None,
):
    """
    Copy a storage volume

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_copy default vol1 target_pool=default target_volume=vol2

    :param source_pool: Source pool name
    :param source_volume: Source volume name
    :param target_pool: Target pool name (defaults to source_pool)
    :param target_volume: Target volume name (defaults to source_volume)
    :param volume_type: Volume type
    :param config: Volume configuration for the copy
    :return: Result
    """
    client = _client()

    target_pool = target_pool or source_pool
    target_volume = target_volume or source_volume

    data = {
        "name": target_volume,
        "source": {"pool": source_pool, "name": source_volume, "type": volume_type},
        "config": config or {},
    }

    result = client._sync_request(
        "POST", f"/storage-pools/{quote(target_pool)}/volumes/{volume_type}", data=data
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {
        "success": True,
        "message": f"Volume {source_volume} copied to {target_volume} successfully",
    }


def volume_create_from_snapshot(
    pool, volume, snapshot_name, new_volume_name, volume_type="custom", config=None
):
    """
    Create a new volume from a snapshot

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_create_from_snapshot default myvolume snap1 restored_volume

    :param pool: Pool name
    :param volume: Source volume name
    :param snapshot_name: Snapshot name to create from
    :param new_volume_name: Name for the new volume
    :param volume_type: Volume type
    :param config: Volume configuration for the new volume
    :return: Result
    """
    client = _client()

    data = {
        "name": new_volume_name,
        "source": {"pool": pool, "name": volume, "type": volume_type, "snapshot": snapshot_name},
        "config": config or {},
    }

    result = client._sync_request(
        "POST", f"/storage-pools/{quote(pool)}/volumes/{volume_type}", data=data
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {
        "success": True,
        "message": f"Volume {new_volume_name} created from snapshot {snapshot_name} successfully",
    }


def volume_move(source_pool, source_volume, target_pool, target_volume=None, volume_type="custom"):
    """
    Move a storage volume to another pool

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_move pool1 vol1 pool2
        salt '*' incus.volume_move pool1 vol1 pool2 target_volume=vol2

    :param source_pool: Source pool name
    :param source_volume: Source volume name
    :param target_pool: Target pool name
    :param target_volume: Target volume name (defaults to source_volume)
    :param volume_type: Volume type
    :return: Result
    """
    client = _client()

    target_volume = target_volume or source_volume

    data = {"name": target_volume, "pool": target_pool}

    result = client._sync_request(
        "POST",
        f"/storage-pools/{quote(source_pool)}/volumes/{volume_type}/{quote(source_volume)}",
        data=data,
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {
        "success": True,
        "message": f"Volume {source_volume} moved to pool {target_pool} successfully",
    }


def volume_snapshot_list(pool, volume, volume_type="custom", recursion=0):
    """
    List snapshots of a storage volume

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_snapshot_list default myvolume
        salt '*' incus.volume_snapshot_list default myvolume recursion=1

    :param pool: Pool name
    :param volume: Volume name
    :param volume_type: Volume type
    :param recursion: Recursion level
    :return: List of snapshots
    """
    client = _client()
    result = client._request(
        "GET",
        f"/storage-pools/{quote(pool)}/volumes/{volume_type}/{quote(volume)}/snapshots",
        params={"recursion": recursion},
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "snapshots": result.get("metadata", [])}


def volume_snapshot_create(pool, volume, snapshot_name, volume_type="custom", description=""):
    """
    Create a snapshot of a storage volume

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_snapshot_create default myvolume snap1

    :param pool: Pool name
    :param volume: Volume name
    :param snapshot_name: Snapshot name
    :param volume_type: Volume type
    :param description: Snapshot description
    :return: Result
    """
    client = _client()

    data = {"name": snapshot_name, "description": description}

    result = client._sync_request(
        "POST",
        f"/storage-pools/{quote(pool)}/volumes/{volume_type}/{quote(volume)}/snapshots",
        data=data,
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {
        "success": True,
        "message": f"Snapshot {snapshot_name} of volume {volume} created successfully",
    }


def volume_snapshot_get(pool, volume, snapshot_name, volume_type="custom"):
    """
    Get information about a volume snapshot

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_snapshot_get default myvolume snap1

    :param pool: Pool name
    :param volume: Volume name
    :param snapshot_name: Snapshot name
    :param volume_type: Volume type
    :return: Snapshot information
    """
    client = _client()
    result = client._request(
        "GET",
        f"/storage-pools/{quote(pool)}/volumes/{volume_type}/{quote(volume)}/snapshots/{quote(snapshot_name)}",
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "snapshot": result.get("metadata", {})}


def volume_snapshot_rename(pool, volume, snapshot_name, new_name, volume_type="custom"):
    """
    Rename a volume snapshot

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_snapshot_rename default myvolume snap1 snap2

    :param pool: Pool name
    :param volume: Volume name
    :param snapshot_name: Current snapshot name
    :param new_name: New snapshot name
    :param volume_type: Volume type
    :return: Result
    """
    client = _client()

    data = {"name": new_name}

    result = client._sync_request(
        "POST",
        f"/storage-pools/{quote(pool)}/volumes/{volume_type}/{quote(volume)}/snapshots/{quote(snapshot_name)}",
        data=data,
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {
        "success": True,
        "message": f"Snapshot {snapshot_name} renamed to {new_name} successfully",
    }


def volume_snapshot_restore(pool, volume, snapshot_name, volume_type="custom"):
    """
    Restore a volume to a previous snapshot state

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_snapshot_restore default myvolume snap1

    :param pool: Pool name
    :param volume: Volume name
    :param snapshot_name: Snapshot name to restore from
    :param volume_type: Volume type
    :return: Result
    """
    client = _client()

    data = {"restore": snapshot_name}

    result = client._sync_request(
        "PUT", f"/storage-pools/{quote(pool)}/volumes/{volume_type}/{quote(volume)}", data=data
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {
        "success": True,
        "message": f"Volume {volume} restored from snapshot {snapshot_name} successfully",
    }


def volume_snapshot_delete(pool, volume, snapshot_name, volume_type="custom"):
    """
    Delete a volume snapshot

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_snapshot_delete default myvolume snap1

    :param pool: Pool name
    :param volume: Volume name
    :param snapshot_name: Snapshot name
    :param volume_type: Volume type
    :return: Result
    """
    client = _client()
    result = client._sync_request(
        "DELETE",
        f"/storage-pools/{quote(pool)}/volumes/{volume_type}/{quote(volume)}/snapshots/{quote(snapshot_name)}",
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {
        "success": True,
        "message": f"Snapshot {snapshot_name} of volume {volume} deleted successfully",
    }


def volume_delete(pool, name, volume_type="custom"):
    """
    Delete a storage volume

    CLI Example:

    .. code-block:: bash

        salt '*' incus.volume_delete default myvolume

    :param pool: Pool name
    :param name: Volume name
    :param volume_type: Volume type
    :return: Result
    """
    log.info("Deleting volume '%s' from pool '%s'", name, pool)
    client = _client()
    result = client._sync_request(
        "DELETE", f"/storage-pools/{quote(pool)}/volumes/{volume_type}/{quote(name)}"
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    log.info("Volume '%s' deleted from pool '%s'", name, pool)
    return {"success": True, "message": f"Volume {name} deleted successfully"}


__all__ = [
    "volume_list",
    "volume_create",
    "volume_get",
    "volume_update",
    "volume_rename",
    "volume_copy",
    "volume_create_from_snapshot",
    "volume_move",
    "volume_snapshot_list",
    "volume_snapshot_create",
    "volume_snapshot_get",
    "volume_snapshot_rename",
    "volume_snapshot_restore",
    "volume_snapshot_delete",
    "volume_delete",
]
