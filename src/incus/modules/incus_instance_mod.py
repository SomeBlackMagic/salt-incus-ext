"""Instance management functions for the Incus Salt module."""

import logging
import time
from urllib.parse import quote

log = logging.getLogger(__name__)

__virtualname__ = "incus"


def __virtual__():
    from incus.modules import incus_mod

    return incus_mod.__virtual__()


def _client():
    from incus.modules.incus_mod import IncusClient

    return IncusClient(salt_funcs=__salt__)

# ========== Instance Management Functions ==========

def instance_list(recursion=0):
    """
    List all instances (containers and VMs)

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_list
        salt '*' incus.instance_list recursion=1

    :param recursion: Recursion level (0=URLs, 1=basic info, 2=full info)
    :return: List of instances
    """
    client = _client()
    result = client._request('GET', '/instances', params={'recursion': recursion})

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'instances': result.get('metadata', [])}


def instance_get(name):
    """
    Get instance information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_get mycontainer

    :param name: Instance name
    :return: Instance information
    """
    client = _client()
    result = client._request('GET', f'/instances/{quote(name)}')

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'instance': result.get('metadata', {})}


def instance_create(name, source=None, instance_type='container', config=None, devices=None, profiles=None, ephemeral=False):
    """
    Create a new instance

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_create mycontainer source="{'type':'image','alias':'ubuntu/22.04'}"
        salt '*' incus.instance_create myvm instance_type=virtual-machine source="{'type':'image','alias':'ubuntu/22.04'}"

    :param name: Instance name
    :param source: Source configuration (image, copy, migration, none)
    :param instance_type: Instance type (container or virtual-machine)
    :param config: Instance configuration
    :param devices: Device configuration
    :param profiles: List of profiles to apply
    :param ephemeral: Whether instance is ephemeral
    :return: Result
    """
    client = _client()

    data = {
        'name': name,
        'type': instance_type,
        'ephemeral': ephemeral
    }

    if source:
        data['source'] = source

    if config:
        data['config'] = config

    if devices:
        data['devices'] = devices

    if profiles:
        data['profiles'] = profiles

    result = client._sync_request('POST', '/instances', data=data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Instance {name} created successfully'}


def instance_delete(name, force=False):
    """
    Delete an instance

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_delete mycontainer
        salt '*' incus.instance_delete mycontainer force=True

    :param name: Instance name
    :param force: Force deletion
    :return: Result
    """
    client = _client()

    # Stop instance if running and force is True
    if force:
        instance_info = instance_get(name)
        if instance_info.get('success') and instance_info.get('instance', {}).get('status') == 'Running':
            instance_stop(name, force=True)

    result = client._sync_request('DELETE', f'/instances/{quote(name)}')

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Instance {name} deleted successfully'}


def instance_update(name, config=None, devices=None, profiles=None):
    """
    Update instance configuration

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_update mycontainer config="{'limits.cpu':'2'}"

    :param name: Instance name
    :param config: Configuration to update
    :param devices: Devices to update
    :param profiles: Profiles to apply
    :return: Result
    """
    client = _client()

    # Get current instance config
    current = instance_get(name)
    if not current.get('success'):
        return current

    instance_data = current['instance']

    # Update fields
    if config:
        instance_data['config'].update(config)

    if devices:
        # Deep merge devices: update properties within existing devices
        for dev_name, dev_conf in devices.items():
            if dev_name in instance_data['devices']:
                # Device exists, merge properties
                instance_data['devices'][dev_name].update(dev_conf)
            else:
                # New device, add it
                instance_data['devices'][dev_name] = dev_conf

    if profiles is not None:
        instance_data['profiles'] = profiles

    result = client._sync_request('PUT', f'/instances/{quote(name)}', data=instance_data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Instance {name} updated successfully'}


def instance_start(name, force=False, stateful=False):
    """
    Start an instance

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_start mycontainer

    :param name: Instance name
    :param force: Force start
    :param stateful: Restore state
    :return: Result
    """
    client = _client()

    data = {
        'action': 'start',
        'force': force,
        'stateful': stateful
    }

    result = client._sync_request('PUT', f'/instances/{quote(name)}/state', data=data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Instance {name} started successfully'}


def instance_stop(name, force=False, stateful=False, timeout=30):
    """
    Stop an instance

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_stop mycontainer
        salt '*' incus.instance_stop mycontainer force=True

    :param name: Instance name
    :param force: Force stop
    :param stateful: Save state
    :param timeout: Timeout in seconds
    :return: Result
    """
    client = _client()

    data = {
        'action': 'stop',
        'force': force,
        'stateful': stateful,
        'timeout': timeout
    }

    result = client._sync_request('PUT', f'/instances/{quote(name)}/state', data=data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Instance {name} stopped successfully'}


def instance_restart(name, force=False, timeout=30):
    """
    Restart an instance

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_restart mycontainer

    :param name: Instance name
    :param force: Force restart
    :param timeout: Timeout in seconds
    :return: Result
    """
    client = _client()

    data = {
        'action': 'restart',
        'force': force,
        'timeout': timeout
    }

    result = client._sync_request('PUT', f'/instances/{quote(name)}/state', data=data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Instance {name} restarted successfully'}


def instance_wait_ready(name, timeout=300, interval=2):
    """
    Wait for instance to be fully ready (incus-agent is responsive)

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_wait_ready myvm
        salt '*' incus.instance_wait_ready myvm timeout=600

    :param name: Instance name
    :param timeout: Maximum seconds to wait (default: 300)
    :param interval: Poll interval in seconds (default: 2)
    :return: Result dict with success status
    """
    client = _client()
    started = time.time()

    log.info(f"Waiting for instance '{name}' to become ready (timeout: {timeout}s)")

    while time.time() - started < timeout:
        # Try to execute a simple command to check if incus-agent is ready
        data = {
            'command': ['/bin/true'],
            'wait-for-websocket': False,
            'interactive': False
        }

        result = client._sync_request('POST', f'/instances/{quote(name)}/exec', data=data)

        # If exec succeeds, the agent is ready
        if result.get('error_code') == 0:
            elapsed = time.time() - started
            log.info(f"Instance '{name}' is ready after {elapsed:.1f}s")
            return {
                'success': True,
                'message': f'Instance {name} is ready',
                'elapsed_time': elapsed
            }

        # Log the error for debugging
        error_msg = result.get('error', 'Unknown error')
        log.debug(f"Instance '{name}' not ready yet: {error_msg}")

        # Wait before next check
        time.sleep(interval)

    # Timeout reached
    elapsed = time.time() - started
    log.warning(f"Timeout waiting for instance '{name}' to become ready ({elapsed:.1f}s)")
    return {
        'success': False,
        'error': f'Timeout waiting for instance to become ready after {elapsed:.1f}s'
    }


# ========== Instance Snapshot Management Functions ==========

def instance_snapshot_list(instance, recursion=0):
    """
    List snapshots of an instance

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_snapshot_list mycontainer
        salt '*' incus.instance_snapshot_list mycontainer recursion=1

    :param instance: Instance name
    :param recursion: Recursion level (0=URLs, 1=basic info, 2=full info)
    :return: List of snapshots
    """
    client = _client()
    result = client._request('GET', f'/instances/{quote(instance)}/snapshots',
                            params={'recursion': recursion})

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'snapshots': result.get('metadata', [])}


def instance_snapshot_get(instance, snapshot_name):
    """
    Get information about an instance snapshot

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_snapshot_get mycontainer snap1

    :param instance: Instance name
    :param snapshot_name: Snapshot name
    :return: Snapshot information
    """
    client = _client()
    result = client._request('GET', f'/instances/{quote(instance)}/snapshots/{quote(snapshot_name)}')

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'snapshot': result.get('metadata', {})}


def instance_snapshot_create(instance, snapshot_name, stateful=False, description=''):
    """
    Create a snapshot of an instance

    Snapshots capture the state of an instance at a point in time.
    They can be stateless (filesystem only) or stateful (includes runtime state/memory).

    Stateless snapshots:
    - Support both containers and VMs
    - Only capture filesystem state
    - Fast to create and restore
    - Smaller storage footprint
    - Instance can be stopped or running

    Stateful snapshots:
    - Only supported for virtual machines
    - Include memory and runtime state
    - VM must be running for stateful snapshot
    - Larger size than stateless snapshots
    - Slower to create and restore

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_snapshot_create mycontainer snap1
        salt '*' incus.instance_snapshot_create mycontainer before-update description="Before system update"
        salt '*' incus.instance_snapshot_create myvm running-state stateful=True description="VM with running state"

    :param instance: Instance name
    :param snapshot_name: Snapshot name
    :param stateful: Whether to include runtime state (only for VMs)
    :param description: Snapshot description
    :return: Result
    """
    client = _client()

    data = {
        'name': snapshot_name,
        'stateful': stateful
    }

    if description:
        data['description'] = description

    result = client._sync_request('POST', f'/instances/{quote(instance)}/snapshots', data=data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Snapshot {snapshot_name} of instance {instance} created successfully'}


def instance_snapshot_rename(instance, snapshot_name, new_name):
    """
    Rename an instance snapshot

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_snapshot_rename mycontainer snap1 snap2

    :param instance: Instance name
    :param snapshot_name: Current snapshot name
    :param new_name: New snapshot name
    :return: Result
    """
    client = _client()

    data = {
        'name': new_name
    }

    result = client._sync_request('POST', f'/instances/{quote(instance)}/snapshots/{quote(snapshot_name)}',
                                  data=data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Snapshot {snapshot_name} renamed to {new_name} successfully'}


def instance_snapshot_restore(instance, snapshot_name, stateful=None):
    """
    Restore an instance to a previous snapshot state

    This operation will revert the instance to the state captured in the snapshot.
    The instance is typically stopped during restoration.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_snapshot_restore mycontainer snap1
        salt '*' incus.instance_snapshot_restore myvm running-state stateful=True

    :param instance: Instance name
    :param snapshot_name: Snapshot name to restore from
    :param stateful: Whether to restore runtime state (only for stateful snapshots)
    :return: Result
    """
    client = _client()

    data = {
        'restore': snapshot_name
    }

    if stateful is not None:
        data['stateful'] = stateful

    result = client._sync_request('PUT', f'/instances/{quote(instance)}', data=data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Instance {instance} restored from snapshot {snapshot_name} successfully'}


def instance_snapshot_delete(instance, snapshot_name):
    """
    Delete an instance snapshot

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_snapshot_delete mycontainer snap1

    :param instance: Instance name
    :param snapshot_name: Snapshot name
    :return: Result
    """
    client = _client()
    result = client._sync_request('DELETE', f'/instances/{quote(instance)}/snapshots/{quote(snapshot_name)}')

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Snapshot {snapshot_name} of instance {instance} deleted successfully'}


def instance_snapshot_update(instance, snapshot_name, description=None, expires_at=None):
    """
    Update instance snapshot metadata

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_snapshot_update mycontainer snap1 description="Updated description"
        salt '*' incus.instance_snapshot_update mycontainer snap1 expires_at="2024-12-31T23:59:59Z"

    :param instance: Instance name
    :param snapshot_name: Snapshot name
    :param description: New description
    :param expires_at: Expiry date in ISO format (YYYY-MM-DDTHH:MM:SSZ)
    :return: Result
    """
    client = _client()

    # Get current snapshot config
    current = client._request('GET', f'/instances/{quote(instance)}/snapshots/{quote(snapshot_name)}')
    if current.get('error_code') != 0:
        return {'success': False, 'error': current.get('error', 'Failed to get snapshot')}

    snapshot_data = current.get('metadata', {})

    # Update fields
    if description is not None:
        snapshot_data['description'] = description

    if expires_at is not None:
        snapshot_data['expires_at'] = expires_at

    result = client._sync_request('PUT', f'/instances/{quote(instance)}/snapshots/{quote(snapshot_name)}',
                                  data=snapshot_data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Snapshot {snapshot_name} updated successfully'}


def instance_snapshot_publish(instance, snapshot_name, properties=None, public=False, aliases=None):
    """
    Publish an instance snapshot as an image

    Create a reusable image from an instance snapshot. This allows you to
    create templates from configured instances.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_snapshot_publish mycontainer snap1
        salt '*' incus.instance_snapshot_publish mycontainer snap1 properties="{'os':'ubuntu','release':'22.04'}" public=True
        salt '*' incus.instance_snapshot_publish mycontainer snap1 aliases="['ubuntu-configured','web-template']"

    :param instance: Instance name
    :param snapshot_name: Snapshot name
    :param properties: Image properties dictionary
    :param public: Whether the image should be public
    :param aliases: List of image aliases
    :return: Result with image fingerprint
    """
    client = _client()

    data = {
        'public': public,
        'source': {
            'type': 'snapshot',
            'name': f'{instance}/{snapshot_name}'
        }
    }

    if properties:
        data['properties'] = properties

    if aliases:
        data['aliases'] = [{'name': a} if isinstance(a, str) else a for a in aliases]

    result = client._sync_request('POST', '/images', data=data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    # Extract fingerprint from result
    metadata = result.get('metadata', {})
    fingerprint = metadata.get('fingerprint', 'unknown')

    return {
        'success': True,
        'message': f'Snapshot {snapshot_name} published as image successfully',
        'fingerprint': fingerprint
    }


# ========== Cloud-init Status Functions ==========

def instance_check_cloudinit_enabled(name):
    """
    Check if cloud-init is enabled in the instance.

    This function checks if cloud-init package is installed by trying to execute
    'cloud-init --version' command inside the instance.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_check_cloudinit_enabled myvm

    :param name: Instance name
    :return: Result dict with success status and enabled flag
    """
    client = _client()

    # Try to execute cloud-init --version command
    data = {
        'command': ['cloud-init', '--version'],
        'wait-for-websocket': False,
        'interactive': False,
        'environment': {}
    }

    try:
        result = client._sync_request('POST', f'/instances/{quote(name)}/exec', data=data)

        # If command succeeds (exit code 0), cloud-init is installed
        if result.get('error_code') == 0:
            return {
                'success': True,
                'enabled': True,
                'message': 'cloud-init is installed and available'
            }
        else:
            # Command failed, cloud-init is not available
            return {
                'success': True,
                'enabled': False,
                'message': 'cloud-init is not installed or not available'
            }
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to check cloud-init status: {str(e)}'
        }


def _check_cloudinit_boot_finished(client, name):
    """
    Internal helper to check if a cloud-init boot-finished marker exists.

    :param client: Incus client instance
    :param name: Instance name
    :return: Tuple (completed: bool, error: str or None)
    """
    try:
        check_data = {
            'command': ['test', '-f', '/var/lib/cloud/instance/boot-finished'],
            'wait-for-websocket': False,
            'interactive': False,
            'environment': {}
        }

        check_result = client._sync_request('POST', f'/instances/{quote(name)}/exec', data=check_data)

        # DEBUG: Log API response
        log.debug(f"API error_code={check_result.get('error_code')}, metadata_present={check_result.get('metadata') is not None}")

        if check_result.get('error_code') != 0:
            error_msg = f"Failed to check cloud-init marker: {check_result.get('error')}"
            log.debug(f"Failed to check cloud-init marker on '{name}': {check_result.get('error')}")
            return (False, error_msg)

        # Get the return code from metadata
        # Note: Incus API returns nested structure: result['metadata']['metadata']['return']
        metadata = check_result.get('metadata', {})
        inner_metadata = metadata.get('metadata', {})
        return_code = inner_metadata.get('return', -1)

        # DEBUG: Log metadata details
        log.debug(f"return_code={return_code}, inner_metadata_keys={list(inner_metadata.keys()) if inner_metadata else []}")

        # Return code 0 means file exists (cloud-init completed)
        return (return_code == 0, None)

    except Exception as e:
        log.debug(f"Exception while checking cloud-init status on '{name}': {str(e)}")
        return (False, str(e))


def instance_get_cloudinit_status(name):
    """
    Get cloud-init status from the instance.

    This function checks if cloud-init has completed by checking the boot-finished marker file.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_get_cloudinit_status myvm

    :param name: Instance name
    :return: Result dict with success status and cloud-init completion status
    """
    client = _client()

    completed, error = _check_cloudinit_boot_finished(client, name)

    if error:
        return {
            'success': False,
            'error': error
        }

    return {
        'success': True,
        'completed': completed,
        'status': 'done' if completed else 'running'
    }


def instance_wait_cloudinit(name, timeout=600, interval=5):
    """
    Wait for cloud-init to complete in the instance.

    This function polls cloud-init completion by checking marker files,
    avoiding potentially blocking commands.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_wait_cloudinit myvm
        salt '*' incus.instance_wait_cloudinit myvm timeout=900 interval=10

    :param name: Instance name
    :param timeout: Maximum seconds to wait (default: 600)
    :param interval: Poll interval in seconds (default: 5)
    :return: Result dict with success status and cloud-init result
    """
    client = _client()

    # First, check if cloud-init was already completed before we started waiting
    completed, error = _check_cloudinit_boot_finished(client, name)

    if completed:
        log.info(f"cloud-init was already completed on instance '{name}' (boot-finished file exists)")
        return {
            'success': True,
            'status': 'already_completed',
            'message': f'cloud-init was already completed on {name}',
            'elapsed_time': 0
        }

    # cloud-init is not yet complete, start waiting loop
    log.info(f"Waiting for cloud-init to complete on instance '{name}' (timeout: {timeout}s)")
    started = time.time()

    while time.time() - started < timeout:
        completed, error = _check_cloudinit_boot_finished(client, name)

        if error:
            log.debug(f"Error checking cloud-init on '{name}': {error}")
            time.sleep(interval)
            continue

        if completed:
            elapsed = time.time() - started
            log.info(f"cloud-init completed on '{name}' after {elapsed:.1f}s (boot-finished file exists)")
            return {
                'success': True,
                'status': 'done',
                'message': f'cloud-init completed on {name}',
                'elapsed_time': elapsed
            }

        # boot-finished doesn't exist yet - still running
        log.debug(f"cloud-init still running on '{name}', waiting...")
        time.sleep(interval)

    # Timeout reached
    elapsed = time.time() - started
    log.warning(f"Timeout waiting for cloud-init on instance '{name}' ({elapsed:.1f}s)")
    return {
        'success': False,
        'status': 'timeout',
        'error': f'Timeout waiting for cloud-init to complete after {elapsed:.1f}s'
    }


__all__ = [
    'instance_list',
    'instance_get',
    'instance_create',
    'instance_delete',
    'instance_update',
    'instance_start',
    'instance_stop',
    'instance_restart',
    'instance_wait_ready',
    'instance_snapshot_list',
    'instance_snapshot_get',
    'instance_snapshot_create',
    'instance_snapshot_rename',
    'instance_snapshot_restore',
    'instance_snapshot_delete',
    'instance_snapshot_update',
    'instance_snapshot_publish',
    'instance_check_cloudinit_enabled',
    'instance_get_cloudinit_status',
    'instance_wait_cloudinit',
]
