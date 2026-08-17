"""Cluster management functions for the Incus Salt module."""

from urllib.parse import quote

__virtualname__ = "incus"


def __virtual__():
    from incus.modules import incus_mod

    return incus_mod.__virtual__()


def _client():
    from incus.modules.incus_mod import IncusClient

    return IncusClient(salt_funcs=__salt__)


# ========== Cluster Management Functions ==========


def cluster_info():
    """
    Get cluster information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.cluster_info

    :return: Cluster information
    """
    client = _client()
    result = client._request("GET", "/cluster")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "cluster": result.get("metadata", {})}


def cluster_member_list(recursion=0):
    """
    List cluster members

    CLI Example:

    .. code-block:: bash

        salt '*' incus.cluster_member_list

    :param recursion: Recursion level
    :return: List of cluster members
    """
    client = _client()
    result = client._request("GET", "/cluster/members", params={"recursion": recursion})

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "members": result.get("metadata", [])}


def cluster_member_add(name, address, cluster_password=None):
    """
    Add a cluster member

    CLI Example:

    .. code-block:: bash

        salt '*' incus.cluster_member_add node2 192.168.1.101

    :param name: Member name
    :param address: Member address
    :param cluster_password: Cluster password
    :return: Result
    """
    client = _client()

    data = {"server_name": name, "server_address": address}

    if cluster_password:
        data["cluster_password"] = cluster_password

    result = client._sync_request("POST", "/cluster/members", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Cluster member {name} added successfully"}


def cluster_member_remove(name, force=False):
    """
    Remove a cluster member

    CLI Example:

    .. code-block:: bash

        salt '*' incus.cluster_member_remove node2

    :param name: Member name
    :param force: Force removal
    :return: Result
    """
    client = _client()

    params = {}
    if force:
        params["force"] = "1"

    result = client._sync_request("DELETE", f"/cluster/members/{quote(name)}", params=params)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Cluster member {name} removed successfully"}


__all__ = [
    "cluster_info",
    "cluster_member_list",
    "cluster_member_add",
    "cluster_member_remove",
]
