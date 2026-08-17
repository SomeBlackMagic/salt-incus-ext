"""Salt state functions for managing Incus profiles."""

__virtualname__ = "incus"


def __virtual__():
    """Load when the Incus profile execution functions are available."""
    if "incus.profile_list" in __salt__:
        return __virtualname__
    return False, "incus profile execution functions are not available"


def _normalize_config_value(value):
    """Normalize a profile configuration value for comparison."""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


# ======================================================================
# Profile States
# ======================================================================


def profile_present(name, config=None, devices=None, description=""):
    """
    Ensure a profile exists and matches all specified parameters.

    Profiles are used to store configuration that can be applied to instances
    at creation time. They can contain both configuration options and devices.

    :param name: Profile name
    :param config: Profile configuration (dict) - CPU limits, memory limits, etc.
    :param devices: Device configuration (dict) - NICs, disks, etc.
    :param description: Profile description

    Supports all profile configuration parameters including:
    - limits.cpu, limits.memory, limits.processes
    - security.nesting, security.privileged, security.idmap
    - boot.autostart, boot.host_shutdown_timeout
    - linux.kernel_modules
    - And many other profile-specific parameters

    The state will:
    1. Create the profile if it doesn't exist
    2. Update existing profiles to match the specified configuration
    3. Track all changes in config, devices, and description

    Example:

    .. code-block:: yaml

        webserver:
          incus.profile_present:
            - config:
                limits.cpu: "4"
                limits.memory: 4GB
                security.nesting: "true"
            - devices:
                eth0:
                  name: eth0
                  type: nic
                  nictype: bridged
                  parent: lxdbr0
                root:
                  path: /
                  pool: default
                  type: disk
            - description: Web server profile with resource limits

        database:
          incus.profile_present:
            - config:
                limits.cpu: "8"
                limits.memory: 16GB
                boot.autostart: "true"
            - devices:
                eth0:
                  name: eth0
                  type: nic
                  network: mybr0
                data:
                  path: /var/lib/mysql
                  pool: default
                  source: mysql-data
                  type: disk
            - description: Database server profile

        minimal:
          incus.profile_present:
            - config:
                limits.cpu: "1"
                limits.memory: 512MB
            - description: Minimal resources profile
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    profile_info = __salt__["incus.profile_get"](name)

    if profile_info.get("success"):
        # Profile exists, check for updates
        current_profile = profile_info.get("profile", {}) or {}
        changes = {}

        # Check config changes
        if config:
            current_config = current_profile.get("config", {}) or {}
            config_changes = {}
            for key, value in config.items():
                new_val = _normalize_config_value(value)
                current_val = _normalize_config_value(current_config.get(key, ""))
                if current_val != new_val:
                    config_changes[key] = {
                        "old": current_config.get(key),
                        "new": new_val,
                    }
            if config_changes:
                changes["config"] = config_changes

        # Check device changes
        if devices:
            current_devices = current_profile.get("devices", {}) or {}
            device_changes = {}
            for dev_name, dev_conf in devices.items():
                current_dev = current_devices.get(dev_name, {})
                # Deep comparison: check if device exists and all properties match
                if not current_dev:
                    # Device doesn't exist
                    device_changes[dev_name] = {
                        "old": None,
                        "new": dev_conf,
                    }
                else:
                    # Device exists, check if any property differs
                    property_changes = {}
                    for prop_key, prop_value in dev_conf.items():
                        current_value = current_dev.get(prop_key)
                        # Normalize values for comparison (convert to string)
                        normalized_new = str(prop_value) if prop_value is not None else None
                        normalized_current = (
                            str(current_value) if current_value is not None else None
                        )
                        if normalized_current != normalized_new:
                            property_changes[prop_key] = {
                                "old": current_value,
                                "new": prop_value,
                            }
                    if property_changes:
                        device_changes[dev_name] = property_changes
            if device_changes:
                changes["devices"] = device_changes

        # Check description changes
        if description is not None:
            current_desc = current_profile.get("description", "")
            if current_desc != description:
                changes["description"] = {
                    "old": current_desc,
                    "new": description,
                }

        if changes:
            if __opts__.get("test"):
                ret["result"] = None
                ret["comment"] = f"Profile {name} would be updated"
                ret["changes"] = changes
            else:
                update_result = __salt__["incus.profile_update"](
                    name,
                    config=config,
                    devices=devices,
                    description=description,
                )
                if update_result.get("success"):
                    ret["comment"] = f"Profile {name} updated"
                    ret["changes"] = changes
                else:
                    ret["result"] = False
                    ret["comment"] = (
                        f"Failed to update profile {name}: " f"{update_result.get('error')}"
                    )
        else:
            ret["comment"] = f"Profile {name} already in desired state"

    else:
        # Profile doesn't exist, create it
        if __opts__.get("test"):
            ret["result"] = None
            ret["comment"] = f"Profile {name} would be created"
            ret["changes"] = {
                "profile": {
                    "old": None,
                    "new": {
                        "name": name,
                        "config": config,
                        "devices": devices,
                        "description": description,
                    },
                }
            }
            return ret

        create_result = __salt__["incus.profile_create"](
            name,
            config=config,
            devices=devices,
            description=description,
        )

        if create_result.get("success"):
            ret["comment"] = f"Profile {name} created"
            ret["changes"] = {
                "profile": {
                    "old": None,
                    "new": name,
                }
            }
        else:
            ret["result"] = False
            ret["comment"] = f"Failed to create profile {name}: " f"{create_result.get('error')}"

    return ret


def profile_absent(name):
    """
    Ensure a profile does not exist.

    The profile must not be in use by any instances before deletion.
    If the profile is in use, the state will fail.

    :param name: Profile name

    Example:

    .. code-block:: yaml

        old_profile:
          incus.profile_absent

        temporary_profile:
          incus.profile_absent
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    profile_info = __salt__["incus.profile_get"](name)

    if not profile_info.get("success"):
        ret["comment"] = f"Profile {name} already absent"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Profile {name} would be deleted"
        ret["changes"] = {
            "profile": {
                "old": name,
                "new": None,
            }
        }
        return ret

    delete_result = __salt__["incus.profile_delete"](name)

    if delete_result.get("success"):
        ret["comment"] = f"Profile {name} deleted"
        ret["changes"] = {
            "profile": {
                "old": name,
                "new": None,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to delete profile {name}: " f"{delete_result.get('error')}"

    return ret


def profile_config(name, config, description=None):
    """
    Ensure a profile has specific configuration.

    This state function allows you to manage only the configuration
    of an existing profile without affecting its devices.

    :param name: Profile name
    :param config: Configuration dict to apply (merged with existing)
    :param description: Profile description to update (optional)

    Example:

    .. code-block:: yaml

        webserver:
          incus.profile_config:
            - config:
                limits.cpu: "4"
                limits.memory: 4GB
            - description: Updated web server profile

        database:
          incus.profile_config:
            - config:
                limits.memory: 16GB
                boot.autostart: "true"
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Get current profile info
    profile_info = __salt__["incus.profile_get"](name)
    if not profile_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to get profile {name}: {profile_info.get('error')}"
        return ret

    current_profile = profile_info.get("profile", {})
    current_config = current_profile.get("config", {})
    current_description = current_profile.get("description", "")

    # Check what needs to be updated
    config_changes = {}
    for key, value in (config or {}).items():
        new_val = _normalize_config_value(value)
        current_val = _normalize_config_value(current_config.get(key, ""))
        if current_val != new_val:
            config_changes[key] = {"old": current_config.get(key), "new": new_val}

    description_changed = description is not None and current_description != description

    if not config_changes and not description_changed:
        ret["comment"] = f"Profile {name} already has desired configuration"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Profile {name} configuration would be updated"
        if config_changes:
            ret["changes"]["config"] = config_changes
        if description_changed:
            ret["changes"]["description"] = {"old": current_description, "new": description}
        return ret

    # Apply updates
    update_result = __salt__["incus.profile_update"](name, config=config, description=description)

    if update_result.get("success"):
        ret["comment"] = f"Profile {name} configuration updated"
        if config_changes:
            ret["changes"]["config"] = config_changes
        if description_changed:
            ret["changes"]["description"] = {"old": current_description, "new": description}
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to update profile {name}: {update_result.get('error')}"

    return ret
