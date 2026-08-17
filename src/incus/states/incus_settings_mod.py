"""Salt state functions for managing Incus server settings."""

__virtualname__ = "incus"


def __virtual__():
    """Load when the Incus settings execution functions are available."""
    if "incus.settings_get" in __salt__:
        return __virtualname__
    return False, "incus settings execution functions are not available"


# ======================================================================
# Server Settings States
# ======================================================================


def settings_present(name, config):
    """
    Ensure Incus server has specific global configuration settings.

    This state merges the provided configuration with existing settings,
    updating only the specified keys while preserving others.

    :param name: State name (descriptive identifier)
    :param config: Dictionary of configuration key-value pairs to apply

    Common configuration keys:
    - core.https_address: HTTPS address and port (e.g., '[::]:8443')
    - core.trust_password: Password for adding new clients
    - images.auto_update_cached: Enable/disable automatic image updates ('true'/'false')
    - images.auto_update_interval: Hours between image update checks
    - images.compression_algorithm: Compression for images (e.g., 'gzip', 'zstd')
    - cluster.https_address: Address for cluster communication
    - storage.backups_volume: Storage volume for backups
    - storage.images_volume: Storage volume for images

    Example:

    .. code-block:: yaml

        incus_basic_config:
          incus.settings_present:
            - config:
                images.auto_update_cached: "true"
                images.auto_update_interval: "12"

        incus_https_config:
          incus.settings_present:
            - config:
                core.https_address: "[::]:8443"
                core.trust_password: "mysecret"

        incus_image_compression:
          incus.settings_present:
            - config:
                images.compression_algorithm: "zstd"
                images.remote_cache_expiry: "10"

        incus_cluster_config:
          incus.settings_present:
            - config:
                cluster.https_address: "192.168.1.100:8443"
                cluster.offline_threshold: "120"
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Get current settings
    settings_info = __salt__["incus.settings_get"]()
    if not settings_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to get server settings: {settings_info.get('error')}"
        return ret

    current_settings = settings_info.get("settings", {}) or {}
    current_config = current_settings.get("config", {}) or {}

    # Check what needs to be updated
    config_changes = {}
    for key, value in (config or {}).items():
        new_val = str(value)
        current_val = current_config.get(key)
        if current_val != new_val:
            config_changes[key] = {
                "old": current_val,
                "new": new_val,
            }

    if not config_changes:
        ret["comment"] = "Server settings already in desired state"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = "Server settings would be updated"
        ret["changes"] = {"config": config_changes}
        return ret

    # Apply updates
    update_result = __salt__["incus.settings_update"](config)

    if update_result.get("success"):
        ret["comment"] = "Server settings updated"
        ret["changes"] = {"config": config_changes}
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to update server settings: {update_result.get('error')}"

    return ret


def settings_config(name, key, value):
    """
    Ensure a single Incus server configuration setting has a specific value.

    This is a convenience state for managing individual configuration keys
    without needing to provide a full configuration dictionary.

    :param name: State name (descriptive identifier, typically the config key)
    :param key: Configuration key name
    :param value: Configuration value (will be converted to string)

    Example:

    .. code-block:: yaml

        https_address:
          incus.settings_config:
            - key: core.https_address
            - value: "[::]:8443"

        auto_update_interval:
          incus.settings_config:
            - key: images.auto_update_interval
            - value: "12"

        compression_algorithm:
          incus.settings_config:
            - key: images.compression_algorithm
            - value: "zstd"

        trust_password:
          incus.settings_config:
            - key: core.trust_password
            - value: "mysecret"
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Get current settings
    settings_info = __salt__["incus.settings_get"]()
    if not settings_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to get server settings: {settings_info.get('error')}"
        return ret

    current_settings = settings_info.get("settings", {}) or {}
    current_config = current_settings.get("config", {}) or {}

    # Check current value
    new_val = str(value)
    current_val = current_config.get(key)

    if current_val == new_val:
        ret["comment"] = f"Setting {key} already has value {new_val}"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Setting {key} would be updated"
        ret["changes"] = {
            key: {
                "old": current_val,
                "new": new_val,
            }
        }
        return ret

    # Apply update
    update_result = __salt__["incus.settings_set"](key, value)

    if update_result.get("success"):
        ret["comment"] = f"Setting {key} updated to {new_val}"
        ret["changes"] = {
            key: {
                "old": current_val,
                "new": new_val,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to update setting {key}: {update_result.get('error')}"

    return ret


def settings_absent(name, key):
    """
    Ensure a specific Incus server configuration setting is not present.

    This state removes a configuration key, reverting it to its default value.

    :param name: State name (descriptive identifier, typically the config key)
    :param key: Configuration key name to remove

    Example:

    .. code-block:: yaml

        remove_trust_password:
          incus.settings_absent:
            - key: core.trust_password

        reset_auto_update:
          incus.settings_absent:
            - key: images.auto_update_interval

        remove_https_address:
          incus.settings_absent:
            - key: core.https_address
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Get current settings
    settings_info = __salt__["incus.settings_get"]()
    if not settings_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to get server settings: {settings_info.get('error')}"
        return ret

    current_settings = settings_info.get("settings", {}) or {}
    current_config = current_settings.get("config", {}) or {}

    # Check if key exists
    if key not in current_config:
        ret["comment"] = f"Setting {key} already absent"
        return ret

    current_val = current_config.get(key)

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Setting {key} would be removed"
        ret["changes"] = {
            key: {
                "old": current_val,
                "new": None,
            }
        }
        return ret

    # Remove setting
    unset_result = __salt__["incus.settings_unset"](key)

    if unset_result.get("success"):
        ret["comment"] = f"Setting {key} removed"
        ret["changes"] = {
            key: {
                "old": current_val,
                "new": None,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to remove setting {key}: {unset_result.get('error')}"

    return ret


def settings_managed(name, config):
    """
    Ensure Incus server configuration exactly matches the specified settings.

    Unlike settings_present which merges with existing settings, this state
    REPLACES the entire configuration. Any settings not specified will be
    removed and reverted to defaults.

    WARNING: This is a destructive operation. Use with caution!

    :param name: State name (descriptive identifier)
    :param config: Dictionary of ALL desired configuration key-value pairs

    Example:

    .. code-block:: yaml

        incus_exact_config:
          incus.settings_managed:
            - config:
                core.https_address: "[::]:8443"
                images.auto_update_cached: "true"
                images.auto_update_interval: "12"
                images.compression_algorithm: "zstd"

    Note:
        This state will remove ALL settings not specified in the config
        parameter. For incremental updates, use settings_present instead.
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Get current settings
    settings_info = __salt__["incus.settings_get"]()
    if not settings_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to get server settings: {settings_info.get('error')}"
        return ret

    current_settings = settings_info.get("settings", {}) or {}
    current_config = current_settings.get("config", {}) or {}

    # Compare entire configuration
    desired_config = {str(k): str(v) for k, v in (config or {}).items()}

    # Find all changes
    all_changes = {}

    # Keys that need to be added or updated
    for key, value in desired_config.items():
        current_val = current_config.get(key)
        if current_val != value:
            all_changes[key] = {
                "old": current_val,
                "new": value,
            }

    # Keys that need to be removed
    for key, current_val in current_config.items():
        if key not in desired_config:
            all_changes[key] = {
                "old": current_val,
                "new": None,
            }

    if not all_changes:
        ret["comment"] = "Server settings already match desired state exactly"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = "Server settings would be replaced"
        ret["changes"] = {"config": all_changes}
        return ret

    # Replace configuration
    replace_result = __salt__["incus.settings_replace"](desired_config)

    if replace_result.get("success"):
        ret["comment"] = "Server settings replaced"
        ret["changes"] = {"config": all_changes}
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to replace server settings: {replace_result.get('error')}"

    return ret
