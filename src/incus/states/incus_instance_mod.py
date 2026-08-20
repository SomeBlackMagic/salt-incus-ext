"""Salt state functions for managing Incus instances."""

import logging

from incus.utils import log_state_changes

log = logging.getLogger(__name__)

__virtualname__ = "incus"


def __virtual__():
    """Load when the Incus instance execution functions are available."""
    if "incus.instance_list" in __salt__:
        return __virtualname__
    return False, "incus execution module is not available"


def _normalize_config_value(value):
    """Normalize an instance configuration value for comparison."""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


# ======================================================================
# Instance States
# ======================================================================


@log_state_changes
def instance_present(
    name,
    source=None,
    instance_type="container",
    config=None,
    devices=None,
    profiles=None,
    ephemeral=False,
):
    """
    Ensure an instance exists and optionally matches given config.

    :param name: Instance name
    :param source: Source configuration for creating instance
                   (see exec-module incus.instance_create)
    :param instance_type: "container" or "virtual-machine"
    :param config: Instance config (dict)
    :param devices: Devices dict
    :param profiles: List of profiles
    :param ephemeral: Whether instance is ephemeral

    Example:

    .. code-block:: yaml

        mycontainer:
          incus.instance_present:
            - source:
                type: image
                alias: ubuntu/22.04
            - config:
                limits.cpu: "2"
                limits.memory: 2GB
            - profiles:
                - default
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    instance_info = __salt__["incus.instance_get"](name)

    if instance_info.get("success"):
        # Instance exists, check if update is needed
        instance = instance_info.get("instance", {})
        changes = {}

        # Config changes
        if config:
            current_config = instance.get("config", {}) or {}
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

        # Profiles
        if profiles is not None:
            current_profiles = instance.get("profiles", []) or []
            if set(current_profiles) != set(profiles):
                changes["profiles"] = {
                    "old": current_profiles,
                    "new": profiles,
                }

        # Devices
        if devices:
            current_devices = instance.get("devices", {}) or {}
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

        if changes:
            if __opts__.get("test"):
                ret["result"] = None
                ret["comment"] = f"Instance {name} would be updated"
                ret["changes"] = changes
            else:
                update_result = __salt__["incus.instance_update"](
                    name,
                    config=config,
                    devices=devices,
                    profiles=profiles,
                )
                if update_result.get("success"):
                    ret["comment"] = f"Instance {name} updated"
                    ret["changes"] = changes
                else:
                    ret["result"] = False
                    ret["comment"] = (
                        f"Failed to update instance {name}: " f"{update_result.get('error')}"
                    )
        else:
            ret["comment"] = f"Instance {name} already in desired state"
    else:
        # Instance doesn't exist, create it
        new_desc = {
            "name": name,
            "type": instance_type,
            "config": config,
            "devices": devices,
            "profiles": profiles,
            "ephemeral": ephemeral,
            "source": source,
        }

        if __opts__.get("test"):
            ret["result"] = None
            ret["comment"] = f"Instance {name} would be created"
            ret["changes"] = {"instance": {"old": None, "new": new_desc}}
        else:
            create_result = __salt__["incus.instance_create"](
                name,
                source=source,
                instance_type=instance_type,
                config=config,
                devices=devices,
                profiles=profiles,
                ephemeral=ephemeral,
            )

            if create_result.get("success"):
                ret["comment"] = f"Instance {name} created"
                ret["changes"] = {
                    "instance": {
                        "old": None,
                        "new": name,
                    }
                }
            else:
                ret["result"] = False
                ret["comment"] = (
                    f"Failed to create instance {name}: " f"{create_result.get('error')}"
                )

    return ret


@log_state_changes
def instance_absent(name, force=False):
    """
    Ensure an instance does not exist.

    :param name: Instance name
    :param force: Force deletion even if running

    Example:

    .. code-block:: yaml

        old_container:
          incus.instance_absent:
            - force: True
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    instance_info = __salt__["incus.instance_get"](name)

    if instance_info.get("success"):
        if __opts__.get("test"):
            ret["result"] = None
            ret["comment"] = f"Instance {name} would be deleted"
            ret["changes"] = {
                "instance": {
                    "old": name,
                    "new": None,
                }
            }
        else:
            delete_result = __salt__["incus.instance_delete"](name, force=force)
            if delete_result.get("success"):
                ret["comment"] = f"Instance {name} deleted"
                ret["changes"] = {
                    "instance": {
                        "old": name,
                        "new": None,
                    }
                }
            else:
                ret["result"] = False
                ret["comment"] = (
                    f"Failed to delete instance {name}: " f"{delete_result.get('error')}"
                )
    else:
        ret["comment"] = f"Instance {name} already absent"

    return ret


@log_state_changes
def instance_running(name, wait_is_ready=False, ready_timeout=300):
    """
    Ensure an instance is running.

    :param name: Instance name
    :param wait_is_ready: Wait for incus-agent to be ready after starting
    :param ready_timeout: Timeout in seconds for waiting (default: 300)

    Example:

    .. code-block:: yaml

        mycontainer:
          incus.instance_running

        myvm:
          incus.instance_running:
            - wait_is_ready: True
            - ready_timeout: 600
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    instance_info = __salt__["incus.instance_get"](name)

    if not instance_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Instance {name} does not exist"
        return ret

    instance = instance_info.get("instance", {}) or {}
    status = instance.get("status", "")

    if status == "Running":
        ret["comment"] = f"Instance {name} is already running"

        # If wait_is_ready is set, check if agent is ready even if already running
        if wait_is_ready:
            if not __opts__.get("test"):
                ready_result = __salt__["incus.instance_wait_ready"](name, timeout=ready_timeout)
                if not ready_result.get("success"):
                    ret["result"] = False
                    ret["comment"] = (
                        f"Instance {name} is running but agent is not ready: "
                        f"{ready_result.get('error')}"
                    )
                else:
                    ret["comment"] = (
                        f"Instance {name} is running and ready "
                        f"(waited {ready_result.get('elapsed_time', 0):.1f}s)"
                    )

        return ret

    if __opts__.get("test"):
        ret["result"] = None
        comment = f"Instance {name} would be started"
        if wait_is_ready:
            comment += " and wait for agent to be ready"
        ret["comment"] = comment
        ret["changes"] = {
            "state": {
                "old": status,
                "new": "Running",
            }
        }
        return ret

    start_result = __salt__["incus.instance_start"](name)
    if start_result.get("success"):
        ret["comment"] = f"Instance {name} started"
        ret["changes"] = {
            "state": {
                "old": status,
                "new": "Running",
            }
        }

        # Wait for instance to be ready if requested
        if wait_is_ready:
            ready_result = __salt__["incus.instance_wait_ready"](name, timeout=ready_timeout)
            if not ready_result.get("success"):
                ret["result"] = False
                ret["comment"] = (
                    f"Instance {name} started but agent is not ready: "
                    f"{ready_result.get('error')}"
                )
            else:
                ret["comment"] = (
                    f"Instance {name} started and ready "
                    f"(waited {ready_result.get('elapsed_time', 0):.1f}s)"
                )
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to start instance {name}: " f"{start_result.get('error')}"

    return ret


@log_state_changes
def instance_stopped(name, force=False):
    """
    Ensure an instance is stopped.

    :param name: Instance name
    :param force: Force stop

    Example:

    .. code-block:: yaml

        mycontainer:
          incus.instance_stopped:
            - force: True
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    instance_info = __salt__["incus.instance_get"](name)

    if not instance_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Instance {name} does not exist"
        return ret

    instance = instance_info.get("instance", {}) or {}
    status = instance.get("status", "")

    if status == "Stopped":
        ret["comment"] = f"Instance {name} is already stopped"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Instance {name} would be stopped"
        ret["changes"] = {
            "state": {
                "old": status,
                "new": "Stopped",
            }
        }
        return ret

    stop_result = __salt__["incus.instance_stop"](name, force=force)

    if stop_result.get("success"):
        ret["comment"] = f"Instance {name} stopped"
        ret["changes"] = {
            "state": {
                "old": status,
                "new": "Stopped",
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to stop instance {name}: " f"{stop_result.get('error')}"

    return ret


@log_state_changes
def instance_initialized(name, timeout=600, check_interval=5):
    """
    Ensure an instance has completed cloud-init initialization.

    This state checks if cloud-init is enabled on the instance. If cloud-init
    is not installed or available, the state is skipped. If cloud-init is
    enabled, the state waits for cloud-init to complete successfully.

    The state is idempotent and can be run multiple times safely.

    :param name: Instance name
    :param timeout: Maximum seconds to wait for cloud-init (default: 600)
    :param check_interval: Poll interval in seconds (default: 5)

    Example:

    .. code-block:: yaml

        myvm:
          incus.instance_initialized:
            - timeout: 900
            - check_interval: 10

        myvm-with-deps:
          incus.instance_initialized:
            - require:
              - incus: myvm

    Returns:
        dict: State return dictionary with result, changes, and comment
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # Check if instance exists
    instance_info = __salt__["incus.instance_get"](name)

    if not instance_info.get("success"):
        ret["result"] = False
        ret["comment"] = f"Instance {name} does not exist"
        return ret

    instance = instance_info.get("instance", {}) or {}
    status = instance.get("status", "")

    # Check if instance is running
    if status != "Running":
        ret["result"] = False
        ret["comment"] = (
            f"Instance {name} is not running (status: {status}). Cannot check cloud-init status."
        )
        return ret

    # Check if cloud-init is enabled/installed
    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Would check if cloud-init is enabled on instance {name}"
        return ret

    cloudinit_check = __salt__["incus.instance_check_cloudinit_enabled"](name)

    if not cloudinit_check.get("success"):
        ret["result"] = False
        ret["comment"] = (
            f"Failed to check cloud-init status on {name}: {cloudinit_check.get('error')}"
        )
        return ret

    if not cloudinit_check.get("enabled"):
        ret["comment"] = (
            f"Instance {name} does not have cloud-init installed. Skipping initialization check."
        )
        return ret

    # cloud-init is enabled, wait for it to complete
    log.info(f"cloud-init is enabled on {name}, waiting for completion...")

    wait_result = __salt__["incus.instance_wait_cloudinit"](
        name, timeout=timeout, interval=check_interval
    )

    if not wait_result.get("success"):
        status = wait_result.get("status", "unknown")
        error = wait_result.get("error", "Unknown error")

        if status == "error":
            # cloud-init completed but with errors
            ret["result"] = False
            ret["comment"] = f"cloud-init on instance {name} completed with errors: {error}"
            ret["changes"] = {
                "cloud-init": {
                    "status": "error",
                    "details": wait_result.get("details", {}),
                }
            }
        elif status == "timeout":
            # Timeout waiting for cloud-init
            ret["result"] = False
            ret["comment"] = f"Timeout waiting for cloud-init on instance {name}: {error}"
        else:
            # Other failure
            ret["result"] = False
            ret["comment"] = f"Failed to wait for cloud-init on instance {name}: {error}"

        return ret

    # cloud-init completed successfully
    status = wait_result.get("status", "unknown")
    elapsed_time = wait_result.get("elapsed_time", 0)

    if status == "done":
        ret["comment"] = (
            f"cloud-init completed successfully on instance {name} " f"(waited {elapsed_time:.1f}s)"
        )
        ret["changes"] = {
            "cloud-init": {
                "status": "done",
                "elapsed_time": f"{elapsed_time:.1f}s",
            }
        }
    elif status == "already_completed":
        ret["comment"] = f"cloud-init was already completed on instance {name}"
        # No changes - cloud-init was completed before this state run
    elif status == "disabled":
        ret["comment"] = f"cloud-init is disabled on instance {name}"
    else:
        ret["comment"] = f"cloud-init status on instance {name}: {status}"

    return ret
