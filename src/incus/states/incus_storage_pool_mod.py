"""Salt state functions for managing Incus storage pools."""

__virtualname__ = "incus"


def __virtual__():
    """Load when the Incus storage-pool execution functions are available."""
    if "incus.storage_pool_list" in __salt__:
        return __virtualname__
    return False, "incus storage-pool execution functions are not available"


# ======================================================================
# Storage Pool States
# ======================================================================
# Storage Pools: storage_pool_present, storage_pool_absent, storage_pool_config


def storage_pool_present(name, driver, config=None, description=""):
    """
    Ensure a storage pool exists.

    :param name: Pool name
    :param driver: Storage driver (dir, zfs, btrfs, lvm, ceph)
    :param config: Pool configuration (dict)
    :param description: Pool description

    Example:

    .. code-block:: yaml

        mypool:
          incus.storage_pool_present:
            - driver: dir
            - config:
                source: /var/lib/incus/storage-pools/mypool
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    pools = __salt__["incus.storage_pool_list"](recursion=1)
    if not pools.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list storage pools: {pools.get('error')}"
        return ret

    pool_list = pools.get("pools", []) or []
    pool_exists = any(p.get("name") == name for p in pool_list)

    if pool_exists:
        ret["comment"] = f"Storage pool {name} already exists"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Storage pool {name} would be created"
        ret["changes"] = {
            "pool": {"old": None, "new": name},
        }
        return ret

    create_result = __salt__["incus.storage_pool_create"](
        name,
        driver,
        config=config,
        description=description,
    )

    if create_result.get("success"):
        ret["comment"] = f"Storage pool {name} created"
        ret["changes"] = {
            "pool": {"old": None, "new": name},
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to create storage pool {name}: " f"{create_result.get('error')}"

    return ret


def storage_pool_absent(name):
    """
    Ensure a storage pool does not exist.

    :param name: Pool name

    Example:

    .. code-block:: yaml

        old_pool:
          incus.storage_pool_absent
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    pools = __salt__["incus.storage_pool_list"](recursion=1)
    if not pools.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list storage pools: {pools.get('error')}"
        return ret

    pool_list = pools.get("pools", []) or []
    pool_exists = any(p.get("name") == name for p in pool_list)

    if not pool_exists:
        ret["comment"] = f"Storage pool {name} already absent"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Storage pool {name} would be deleted"
        ret["changes"] = {
            "pool": {
                "old": name,
                "new": None,
            }
        }
        return ret

    delete_result = __salt__["incus.storage_pool_delete"](name)

    if delete_result.get("success"):
        ret["comment"] = f"Storage pool {name} deleted"
        ret["changes"] = {
            "pool": {
                "old": name,
                "new": None,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to delete storage pool {name}: " f"{delete_result.get('error')}"

    return ret


def storage_pool_config(name, config, description=None):
    """
    Ensure a storage pool has specific configuration.

    :param name: Pool name
    :param config: Configuration dict to apply
    :param description: Pool description to update (optional)

    Example:

    .. code-block:: yaml

        mypool:
          incus.storage_pool_config:
            - config:
                rsync.bwlimit: "100"
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Get current pool info
    pool_info = __salt__["incus.storage_pool_get"](name)
    if not pool_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to get pool {name}: {pool_info.get('error')}"
        return ret

    current_pool = pool_info.get("pool", {})
    current_config = current_pool.get("config", {})
    current_description = current_pool.get("description", "")

    # Check what needs to be updated
    config_changes = {}
    for key, value in (config or {}).items():
        if current_config.get(key) != value:
            config_changes[key] = {"old": current_config.get(key), "new": value}

    description_changed = description is not None and current_description != description

    if not config_changes and not description_changed:
        ret["comment"] = f"Storage pool {name} already has desired configuration"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Storage pool {name} configuration would be updated"
        if config_changes:
            ret["changes"]["config"] = config_changes
        if description_changed:
            ret["changes"]["description"] = {"old": current_description, "new": description}
        return ret

    # Apply updates
    update_result = __salt__["incus.storage_pool_update"](
        name, config=config, description=description
    )

    if update_result.get("success"):
        ret["comment"] = f"Storage pool {name} configuration updated"
        if config_changes:
            ret["changes"]["config"] = config_changes
        if description_changed:
            ret["changes"]["description"] = {"old": current_description, "new": description}
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to update pool {name}: {update_result.get('error')}"

    return ret
