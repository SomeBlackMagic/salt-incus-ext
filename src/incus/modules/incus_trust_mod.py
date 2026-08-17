"""Trust management functions for the Incus Salt module."""

from urllib.parse import quote

__virtualname__ = "incus"


def __virtual__():
    from incus.modules import incus_mod

    return incus_mod.__virtual__()


def _client():
    from incus.modules.incus_mod import IncusClient

    return IncusClient(salt_funcs=__salt__)

# ========== Trust Management Functions ==========

def trust_list(recursion=1):
    """
    List trusted client certificates.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.trust_list
    """
    client = _client()
    result = client._request('GET', '/certificates', params={'recursion': recursion})

    if result.get('error_code') != 0:
        return {'success': False, 'error': result.get('error', 'Failed to list trusted certificates')}

    return {'success': True, 'certificates': result.get('metadata', [])}


def trust_get(fingerprint):
    """
    Get trusted certificate details by fingerprint.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.trust_get <fingerprint>
    """
    if not fingerprint:
        return {'success': False, 'error': 'fingerprint is required'}

    client = _client()
    result = client._request('GET', f'/certificates/{quote(fingerprint)}')

    if result.get('error_code') != 0:
        return {'success': False, 'error': result.get('error', 'Failed to get trusted certificate')}

    return {'success': True, 'certificate': result.get('metadata', {})}


def trust_add(cert_pem, name=None, restricted=False):
    """
    Add a client certificate to the Incus trust store.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.trust_add cert_pem="$(cat /path/client.crt)" name=salt-cloud restricted=False
    """
    if not cert_pem:
        return {'success': False, 'error': 'cert_pem is required'}

    data = {
        'type': 'client',
        'certificate': cert_pem,
        'name': name or 'salt-cloud',
        'restricted': bool(restricted),
    }

    client = _client()
    result = client._sync_request('POST', '/certificates', data=data)

    if result.get('error_code') != 0:
        return {'success': False, 'error': result.get('error', 'Failed to add trusted certificate')}

    return {'success': True, 'message': 'Certificate added to trust store'}


def trust_remove(fingerprint):
    """
    Remove a trusted certificate by fingerprint.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.trust_remove <fingerprint>
    """
    if not fingerprint:
        return {'success': False, 'error': 'fingerprint is required'}

    client = _client()
    result = client._sync_request('DELETE', f'/certificates/{quote(fingerprint)}')

    if result.get('error_code') != 0:
        return {'success': False, 'error': result.get('error', 'Failed to remove trusted certificate')}

    return {'success': True, 'message': f'Certificate {fingerprint} removed from trust store'}

__all__ = [
    'trust_list',
    'trust_get',
    'trust_add',
    'trust_remove',
]
