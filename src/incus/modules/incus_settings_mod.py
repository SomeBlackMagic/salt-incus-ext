"""Server settings functions for the Incus Salt module."""

__virtualname__ = "incus"


def __virtual__():
    from incus.modules import incus_mod

    return incus_mod.__virtual__()


def _client():
    from incus.modules.incus_mod import IncusClient

    return IncusClient(salt_funcs=__salt__)


# ========== Settings Management Functions ==========


def settings_get():
    """
    Get Incus server global configuration settings

    Retrieves the current global configuration for the Incus server.
    These settings control various aspects of server behavior including
    images auto-update, clustering, HTTPS address, and more.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.settings_get

    :return: Dictionary with 'success' status and 'settings' configuration

    Example return value:

    .. code-block:: python

        {
            "success": True,
            "settings": {
                "config": {
                    "core.https_address": "[::]:8443",
                    "core.trust_password": "secret",
                    "images.auto_update_cached": "true",
                    "images.auto_update_interval": "6",
                }
            },
        }
    """
    client = _client()
    result = client._request("GET", "")

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to get settings")}

    return {"success": True, "settings": result.get("metadata", {})}


def settings_update(config):
    """
    Update Incus server global configuration settings

    Modify global configuration options for the Incus server.
    This function merges the provided configuration with existing settings.

    Common configuration keys:
    - core.https_address: HTTPS address and port (e.g., ':8443', '[::]:8443')
    - core.trust_password: Password for adding new clients
    - images.auto_update_cached: Enable/disable automatic image updates ('true'/'false')
    - images.auto_update_interval: Hours between image update checks
    - images.compression_algorithm: Compression for images (e.g., 'gzip', 'zstd')
    - images.remote_cache_expiry: Days to cache remote images
    - cluster.https_address: Address for cluster communication
    - storage.backups_volume: Storage volume for backups
    - storage.images_volume: Storage volume for images

    CLI Example:

    .. code-block:: bash

        salt '*' incus.settings_update config="{'images.auto_update_interval':'12'}"
        salt '*' incus.settings_update config="{'core.https_address':'[::]:8443','images.auto_update_cached':'true'}"

    :param config: Dictionary of configuration key-value pairs to update
    :return: Dictionary with 'success' status and message

    Example usage:

    .. code-block:: python

        # Enable HTTPS on all interfaces
        incus.settings_update({"core.https_address": "[::]:8443"})

        # Configure image auto-update
        incus.settings_update(
            {"images.auto_update_cached": "true", "images.auto_update_interval": "12"}
        )

        # Set compression algorithm
        incus.settings_update({"images.compression_algorithm": "zstd"})
    """
    if not config or not isinstance(config, dict):
        return {"success": False, "error": "config parameter must be a dictionary"}

    client = _client()

    # Get current settings
    current = client._request("GET", "")
    if current.get("error_code") != 0:
        return {"success": False, "error": current.get("error", "Failed to get current settings")}

    settings_data = current.get("metadata", {})

    # Update config
    if "config" not in settings_data:
        settings_data["config"] = {}

    settings_data["config"].update(config)

    # Send update request
    result = client._sync_request("PUT", "", data=settings_data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to update settings")}

    return {"success": True, "message": "Server settings updated successfully"}


def settings_set(key, value):
    """
    Set a single Incus server configuration setting

    Convenience function to set a single configuration key without
    needing to provide a full configuration dictionary.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.settings_set core.https_address '[::]:8443'
        salt '*' incus.settings_set images.auto_update_interval 12
        salt '*' incus.settings_set images.compression_algorithm zstd

    :param key: Configuration key name
    :param value: Configuration value (will be converted to string)
    :return: Dictionary with 'success' status and message

    Example usage:

    .. code-block:: python

        # Enable HTTPS
        incus.settings_set("core.https_address", "[::]:8443")

        # Set auto-update interval
        incus.settings_set("images.auto_update_interval", "12")

        # Set trust password
        incus.settings_set("core.trust_password", "mysecret")
    """
    if not key or not isinstance(key, str):
        return {"success": False, "error": "key parameter must be a non-empty string"}

    return settings_update({key: str(value)})


def settings_unset(key):
    """
    Unset (remove) a single Incus server configuration setting

    Remove a configuration key from the server settings, reverting it
    to its default value.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.settings_unset core.trust_password
        salt '*' incus.settings_unset images.auto_update_interval

    :param key: Configuration key name to remove
    :return: Dictionary with 'success' status and message

    Example usage:

    .. code-block:: python

        # Remove trust password (disable password authentication)
        incus.settings_unset("core.trust_password")

        # Reset auto-update interval to default
        incus.settings_unset("images.auto_update_interval")
    """
    if not key or not isinstance(key, str):
        return {"success": False, "error": "key parameter must be a non-empty string"}

    client = _client()

    # Get current settings
    current = client._request("GET", "")
    if current.get("error_code") != 0:
        return {"success": False, "error": current.get("error", "Failed to get current settings")}

    settings_data = current.get("metadata", {})

    # Remove key from config
    if "config" in settings_data and key in settings_data["config"]:
        del settings_data["config"][key]
    else:
        return {"success": False, "error": f'Configuration key "{key}" not found'}

    # Send update request
    result = client._sync_request("PUT", "", data=settings_data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to update settings")}

    return {"success": True, "message": f'Configuration key "{key}" unset successfully'}


def settings_replace(config):
    """
    Replace entire Incus server configuration

    Replace the entire server configuration with the provided settings.
    Unlike settings_update(), this function does NOT merge with existing
    settings - it completely replaces them. Use with caution.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.settings_replace config="{'core.https_address':'[::]:8443','images.auto_update_cached':'true'}"

    :param config: Dictionary of configuration key-value pairs (replaces all settings)
    :return: Dictionary with 'success' status and message

    Example usage:

    .. code-block:: python

        # Replace all settings with minimal config
        incus.settings_replace(
            {"core.https_address": "[::]:8443", "images.auto_update_cached": "true"}
        )

    Warning:
        This function replaces ALL server configuration settings.
        Any settings not included in the config parameter will be
        removed and reverted to defaults. Use settings_update()
        instead if you want to modify specific settings.
    """
    if not config or not isinstance(config, dict):
        return {"success": False, "error": "config parameter must be a dictionary"}

    client = _client()

    # Get current settings structure
    current = client._request("GET", "")
    if current.get("error_code") != 0:
        return {"success": False, "error": current.get("error", "Failed to get current settings")}

    settings_data = current.get("metadata", {})

    # Replace config entirely
    settings_data["config"] = config

    # Send update request
    result = client._sync_request("PUT", "", data=settings_data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to replace settings")}

    return {"success": True, "message": "Server settings replaced successfully"}


__all__ = [
    "settings_get",
    "settings_update",
    "settings_set",
    "settings_unset",
    "settings_replace",
]
