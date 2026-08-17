"""Storage pool management functions for the Incus Salt module."""

from urllib.parse import quote

__virtualname__ = "incus"


def __virtual__():
    from incus.modules import incus_mod

    return incus_mod.__virtual__()


def _client():
    from incus.modules.incus_mod import IncusClient

    return IncusClient(salt_funcs=__salt__)


# ========== Storage Pool Management Functions ==========


def storage_pool_list(recursion=0):
    """
    List all storage pools

    CLI Example:

    .. code-block:: bash

        salt '*' incus.storage_pool_list

    :param recursion: Recursion level
    :return: List of storage pools
    """
    client = _client()
    result = client._request('GET', '/storage-pools', params={'recursion': recursion})

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'pools': result.get('metadata', [])}


def storage_pool_create(name, driver, config=None, description=''):
    """
    Create a storage pool

    CLI Example:

    .. code-block:: bash

        salt '*' incus.storage_pool_create mypool dir config="{'source':'/var/lib/incus/storage-pools/mypool'}"

    :param name: Pool name
    :param driver: Storage driver (dir, zfs, btrfs, lvm, ceph)
    :param config: Pool configuration
    :param description: Pool description
    :return: Result
    """
    client = _client()

    data = {
        'name': name,
        'driver': driver,
        'config': config or {},
        'description': description
    }

    result = client._sync_request('POST', '/storage-pools', data=data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Storage pool {name} created successfully'}


def storage_pool_get(name):
    """
    Get storage pool information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.storage_pool_get mypool

    :param name: Pool name
    :return: Storage pool information
    """
    client = _client()
    result = client._request('GET', f'/storage-pools/{quote(name)}')

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'pool': result.get('metadata', {})}


def storage_pool_update(name, config=None, description=None):
    """
    Update storage pool configuration

    CLI Example:

    .. code-block:: bash

        salt '*' incus.storage_pool_update mypool config="{'rsync.bwlimit':'100'}"

    :param name: Pool name
    :param config: Configuration to update
    :param description: Pool description to update
    :return: Result
    """
    client = _client()

    # Get current pool config
    current = client._request('GET', f'/storage-pools/{quote(name)}')
    if 'error' in current:
        return {'success': False, 'error': current['error']}

    pool_data = current.get('metadata', {})

    # Update fields
    if config:
        pool_data['config'].update(config)

    if description is not None:
        pool_data['description'] = description

    result = client._sync_request('PUT', f'/storage-pools/{quote(name)}', data=pool_data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Storage pool {name} updated successfully'}


def storage_pool_rename(name, new_name):
    """
    Rename a storage pool

    CLI Example:

    .. code-block:: bash

        salt '*' incus.storage_pool_rename mypool mynewpool

    :param name: Current pool name
    :param new_name: New pool name
    :return: Result
    """
    client = _client()

    data = {
        'name': new_name
    }

    result = client._sync_request('POST', f'/storage-pools/{quote(name)}', data=data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Storage pool {name} renamed to {new_name} successfully'}


def storage_pool_resources(name):
    """
    Get storage pool resource usage information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.storage_pool_resources mypool

    :param name: Pool name
    :return: Storage pool resource information
    """
    client = _client()
    result = client._request('GET', f'/storage-pools/{quote(name)}/resources')

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'resources': result.get('metadata', {})}


def storage_pool_delete(name):
    """
    Delete a storage pool

    CLI Example:

    .. code-block:: bash

        salt '*' incus.storage_pool_delete mypool

    :param name: Pool name
    :return: Result
    """
    client = _client()
    result = client._sync_request('DELETE', f'/storage-pools/{quote(name)}')

    if result.get('error_code') != 0:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'message': f'Storage pool {name} deleted successfully'}


__all__ = [
    'storage_pool_list',
    'storage_pool_create',
    'storage_pool_get',
    'storage_pool_update',
    'storage_pool_rename',
    'storage_pool_resources',
    'storage_pool_delete',
]
