"""Profile management functions for the Incus Salt module."""

from urllib.parse import quote

__virtualname__ = "incus"


def __virtual__():
    from incus.modules import incus_mod

    return incus_mod.__virtual__()


def _client():
    from incus.modules.incus_mod import IncusClient

    return IncusClient(salt_funcs=__salt__)


# ========== Profile Management Functions ==========


def profile_list(recursion=0):
    """
    List all profiles

    Profiles are used to store configuration that can be applied to instances
    at creation time. They can contain both configuration options and devices.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.profile_list
        salt '*' incus.profile_list recursion=1

    :param recursion: Recursion level (0=URLs, 1=basic info, 2=full info)
    :return: Dictionary with 'success' status and 'profiles' list
    """
    client = _client()
    result = client._request("GET", "/profiles", params={"recursion": recursion})

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "profiles": result.get("metadata", [])}


def profile_get(name):
    """
    Get profile information

    Retrieve detailed information about a specific profile including
    its configuration, devices, and which instances are using it.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.profile_get default
        salt '*' incus.profile_get myprofile

    :param name: Profile name
    :return: Dictionary with 'success' status and 'profile' information
    """
    client = _client()
    result = client._request("GET", f"/profiles/{quote(name)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "profile": result.get("metadata", {})}


def profile_create(name, config=None, devices=None, description=""):
    """
    Create a new profile

    Profiles allow you to define common configurations that can be applied
    to multiple instances. This is useful for standardizing settings like
    CPU limits, memory limits, network devices, and disk devices.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.profile_create myprofile
        salt '*' incus.profile_create myprofile config="{'limits.cpu':'2','limits.memory':'4GB'}"
        salt '*' incus.profile_create webserver config="{'limits.cpu':'4'}" devices="{'eth0':{'type':'nic','network':'lxdbr0'}}"
        salt '*' incus.profile_create dbserver description="Database server profile" config="{'limits.memory':'8GB'}"

    :param name: Profile name
    :param config: Profile configuration (e.g., {'limits.cpu':'2','limits.memory':'4GB'})
    :param devices: Device configuration (e.g., {'eth0':{'type':'nic','network':'lxdbr0'}})
    :param description: Profile description
    :return: Dictionary with 'success' status and message
    """
    client = _client()

    data = {
        "name": name,
        "config": config or {},
        "devices": devices or {},
        "description": description,
    }

    result = client._sync_request("POST", "/profiles", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Profile {name} created successfully"}


def profile_update(name, config=None, devices=None, description=None):
    """
    Update profile configuration

    Modify an existing profile's configuration, devices, or description.
    The changes will affect all instances using this profile upon restart.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.profile_update myprofile config="{'limits.memory':'4GB'}"
        salt '*' incus.profile_update myprofile devices="{'root':{'path':'/','pool':'default','type':'disk'}}"
        salt '*' incus.profile_update myprofile description="Updated description"
        salt '*' incus.profile_update myprofile config="{'limits.cpu':'4'}" devices="{'eth0':{'type':'nic','network':'mybr0'}}"

    :param name: Profile name
    :param config: Configuration to update (merged with existing config)
    :param devices: Devices to update (merged with existing devices)
    :param description: Description to update (replaces existing description)
    :return: Dictionary with 'success' status and message
    """
    client = _client()

    # Get current profile config
    current = profile_get(name)
    if not current.get("success"):
        return current

    profile_data = current["profile"]

    # Update fields
    if config:
        profile_data["config"].update(config)

    if devices:
        # Deep merge devices: update properties within existing devices
        for dev_name, dev_conf in devices.items():
            if dev_name in profile_data["devices"]:
                # Device exists, merge properties
                profile_data["devices"][dev_name].update(dev_conf)
            else:
                # New device, add it
                profile_data["devices"][dev_name] = dev_conf

    if description is not None:
        profile_data["description"] = description

    result = client._sync_request("PUT", f"/profiles/{quote(name)}", data=profile_data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Profile {name} updated successfully"}


def profile_rename(name, new_name):
    """
    Rename a profile

    Rename an existing profile. All instances using this profile will
    automatically use the new name.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.profile_rename myprofile mynewprofile
        salt '*' incus.profile_rename old-web-profile web-profile

    :param name: Current profile name
    :param new_name: New profile name
    :return: Dictionary with 'success' status and message
    """
    client = _client()

    data = {"name": new_name}

    result = client._sync_request("POST", f"/profiles/{quote(name)}", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Profile {name} renamed to {new_name} successfully"}


def profile_copy(name, new_name, description=None):
    """
    Copy a profile to a new profile

    Create a duplicate of an existing profile with a new name.
    Optionally provide a new description.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.profile_copy default myprofile
        salt '*' incus.profile_copy webserver webserver-backup description="Backup of webserver profile"

    :param name: Source profile name
    :param new_name: New profile name
    :param description: Optional description for the new profile
    :return: Dictionary with 'success' status and message
    """
    client = _client()

    # Get source profile
    source = profile_get(name)
    if not source.get("success"):
        return source

    profile_data = source["profile"]

    # Prepare data for new profile
    data = {
        "name": new_name,
        "config": profile_data.get("config", {}),
        "devices": profile_data.get("devices", {}),
        "description": (
            description if description is not None else profile_data.get("description", "")
        ),
    }

    result = client._sync_request("POST", "/profiles", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Profile {name} copied to {new_name} successfully"}


def profile_delete(name):
    """
    Delete a profile

    Remove a profile from the system. The profile must not be in use
    by any instances before deletion.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.profile_delete myprofile
        salt '*' incus.profile_delete old-profile

    :param name: Profile name
    :return: Dictionary with 'success' status and message
    """
    client = _client()
    result = client._sync_request("DELETE", f"/profiles/{quote(name)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Profile {name} deleted successfully"}


__all__ = [
    "profile_list",
    "profile_get",
    "profile_create",
    "profile_update",
    "profile_rename",
    "profile_copy",
    "profile_delete",
]
