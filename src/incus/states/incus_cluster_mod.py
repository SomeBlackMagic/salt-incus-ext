"""Salt state functions for managing Incus cluster members."""

from incus.utils import log_state_changes

__virtualname__ = "incus"


def __virtual__():
    """Load when the Incus cluster execution functions are available."""
    if "incus.cluster_member_list" in __salt__:
        return __virtualname__
    return False, "incus cluster execution functions are not available"


# ======================================================================
# Cluster States
# ======================================================================


@log_state_changes
def cluster_member_present(name, address, cluster_password=None):
    """
    Ensure a cluster member exists.

    :param name: Member name
    :param address: Member address
    :param cluster_password: Cluster password

    Example:

    .. code-block:: yaml

        node2:
          incus.cluster_member_present:
            - address: 192.168.1.101
            - cluster_password: secret123
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    members = __salt__["incus.cluster_member_list"](recursion=1)
    if not members.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list cluster members: {members.get('error')}"
        return ret

    member_list = members.get("members", []) or []
    member_exists = any(m.get("server_name") == name for m in member_list)

    if member_exists:
        ret["comment"] = f"Cluster member {name} already exists"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Cluster member {name} would be added"
        ret["changes"] = {
            "member": {
                "old": None,
                "new": name,
            }
        }
        return ret

    add_result = __salt__["incus.cluster_member_add"](
        name,
        address,
        cluster_password=cluster_password,
    )

    if add_result.get("success"):
        ret["comment"] = f"Cluster member {name} added"
        ret["changes"] = {
            "member": {
                "old": None,
                "new": name,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to add cluster member {name}: " f"{add_result.get('error')}"

    return ret


@log_state_changes
def cluster_member_absent(name, force=False):
    """
    Ensure a cluster member does not exist.

    :param name: Member name
    :param force: Force removal

    Example:

    .. code-block:: yaml

        old_node:
          incus.cluster_member_absent:
            - force: True
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    members = __salt__["incus.cluster_member_list"](recursion=1)
    if not members.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list cluster members: {members.get('error')}"
        return ret

    member_list = members.get("members", []) or []
    member_exists = any(m.get("server_name") == name for m in member_list)

    if not member_exists:
        ret["comment"] = f"Cluster member {name} already absent"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Cluster member {name} would be removed"
        ret["changes"] = {
            "member": {
                "old": name,
                "new": None,
            }
        }
        return ret

    remove_result = __salt__["incus.cluster_member_remove"](name, force=force)

    if remove_result.get("success"):
        ret["comment"] = f"Cluster member {name} removed"
        ret["changes"] = {
            "member": {
                "old": name,
                "new": None,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to remove cluster member {name}: " f"{remove_result.get('error')}"

    return ret
