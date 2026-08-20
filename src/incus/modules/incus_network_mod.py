"""Network management functions for the Incus Salt module."""

import logging
from urllib.parse import quote

log = logging.getLogger(__name__)

__virtualname__ = "incus"


def __virtual__():
    from incus.modules import incus_mod

    return incus_mod.__virtual__()


def _client():
    from incus.modules.incus_mod import IncusClient

    return IncusClient(salt_funcs=__salt__)


# ========== Network Management Functions ==========


def network_list(recursion=0):
    """
    List all networks

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_list

    :param recursion: Recursion level
    :return: List of networks
    """
    client = _client()
    result = client._request("GET", "/networks", params={"recursion": recursion})

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "networks": result.get("metadata", [])}


def network_create(name, network_type="bridge", config=None, description=""):
    """
    Create a network

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_create mybr0 config="{'ipv4.address':'10.0.0.1/24','ipv4.nat':'true'}"

    :param name: Network name
    :param network_type: Network type (bridge, macvlan, sriov, ovn, physical)
    :param config: Network configuration
    :param description: Network description
    :return: Result
    """
    log.info("Creating Incus network '%s' (type=%s)", name, network_type)
    client = _client()

    data = {"name": name, "type": network_type, "config": config or {}, "description": description}

    result = client._sync_request("POST", "/networks", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    log.info("Incus network '%s' created", name)
    return {"success": True, "message": f"Network {name} created successfully"}


def network_get(name):
    """
    Get network information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_get mybr0

    :param name: Network name
    :return: Network information
    """
    client = _client()
    result = client._request("GET", f"/networks/{quote(name)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "network": result.get("metadata", {})}


def network_delete(name):
    """
    Delete a network

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_delete mybr0

    :param name: Network name
    :return: Result
    """
    log.info("Deleting Incus network '%s'", name)
    client = _client()
    result = client._sync_request("DELETE", f"/networks/{quote(name)}")

    if result.get("error_code") != 0:
        if result.get("error_code") == 404:
            log.warning("Network '%s' not found", name)
        return {"success": False, "error": result["error"]}

    log.info("Incus network '%s' deleted", name)
    return {"success": True, "message": f"Network {name} deleted successfully"}


def network_update(name, config):
    """
    Update network configuration

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_update mybr0 config="{'ipv4.nat':'false'}"

    :param name: Network name
    :param config: Configuration to update
    :return: Result
    """
    log.info("Updating Incus network '%s'", name)
    client = _client()

    # Get current network config
    current = client._request("GET", f"/networks/{quote(name)}")
    if "error" in current:
        return {"success": False, "error": current["error"]}

    network_data = current.get("metadata", {})
    network_data["config"].update(config)

    result = client._sync_request("PUT", f"/networks/{quote(name)}", data=network_data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    log.info("Incus network '%s' updated", name)
    return {"success": True, "message": f"Network {name} updated successfully"}


def network_rename(name, new_name):
    """
    Rename a network

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_rename mybr0 mybr1

    :param name: Current network name
    :param new_name: New network name
    :return: Result
    """
    client = _client()

    data = {"name": new_name}

    result = client._sync_request("POST", f"/networks/{quote(name)}", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network {name} renamed to {new_name} successfully"}


def network_state(name):
    """
    Get network state information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_state mybr0

    :param name: Network name
    :return: Network state information
    """
    client = _client()
    result = client._request("GET", f"/networks/{quote(name)}/state")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "state": result.get("metadata", {})}


def network_lease_list(name):
    """
    List DHCP leases for a network

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_lease_list mybr0

    :param name: Network name
    :return: List of DHCP leases
    """
    client = _client()
    result = client._request("GET", f"/networks/{quote(name)}/leases")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "leases": result.get("metadata", [])}


# ========== Network ACL Management Functions ==========


def network_acl_list(recursion=0):
    """
    List all network ACLs

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_acl_list
        salt '*' incus.network_acl_list recursion=1

    :param recursion: Recursion level
    :return: List of network ACLs
    """
    client = _client()
    result = client._request("GET", "/network-acls", params={"recursion": recursion})

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "acls": result.get("metadata", [])}


def network_acl_get(name):
    """
    Get network ACL information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_acl_get myacl

    :param name: ACL name
    :return: ACL information
    """
    client = _client()
    result = client._request("GET", f"/network-acls/{quote(name)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "acl": result.get("metadata", {})}


def network_acl_create(name, config=None, description="", egress=None, ingress=None):
    """
    Create a network ACL

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_acl_create myacl
        salt '*' incus.network_acl_create myacl ingress="[{'action':'allow','source':'10.0.0.0/24'}]"

    :param name: ACL name
    :param config: ACL configuration
    :param description: ACL description
    :param egress: List of egress rules
    :param ingress: List of ingress rules
    :return: Result
    """
    client = _client()

    data = {
        "name": name,
        "config": config or {},
        "description": description,
        "egress": egress or [],
        "ingress": ingress or [],
    }

    result = client._sync_request("POST", "/network-acls", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network ACL {name} created successfully"}


def network_acl_update(name, config=None, description=None, egress=None, ingress=None):
    """
    Update network ACL

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_acl_update myacl ingress="[{'action':'deny','source':'192.168.1.0/24'}]"

    :param name: ACL name
    :param config: Configuration to update
    :param description: Description to update
    :param egress: Egress rules to update
    :param ingress: Ingress rules to update
    :return: Result
    """
    client = _client()

    # Get current ACL config
    current = network_acl_get(name)
    if not current.get("success"):
        return current

    acl_data = current["acl"]

    if config:
        acl_data["config"].update(config)

    if description is not None:
        acl_data["description"] = description

    if egress is not None:
        acl_data["egress"] = egress

    if ingress is not None:
        acl_data["ingress"] = ingress

    result = client._sync_request("PUT", f"/network-acls/{quote(name)}", data=acl_data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network ACL {name} updated successfully"}


def network_acl_delete(name):
    """
    Delete a network ACL

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_acl_delete myacl

    :param name: ACL name
    :return: Result
    """
    client = _client()
    result = client._sync_request("DELETE", f"/network-acls/{quote(name)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network ACL {name} deleted successfully"}


def network_acl_rename(name, new_name):
    """
    Rename a network ACL

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_acl_rename myacl myacl2

    :param name: Current ACL name
    :param new_name: New ACL name
    :return: Result
    """
    client = _client()

    data = {"name": new_name}

    result = client._sync_request("POST", f"/network-acls/{quote(name)}", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network ACL {name} renamed to {new_name} successfully"}


# ========== Network Forward Management Functions ==========


def network_forward_list(network, recursion=0):
    """
    List network forwards

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_forward_list mybr0

    :param network: Network name
    :param recursion: Recursion level
    :return: List of forwards
    """
    client = _client()
    result = client._request(
        "GET", f"/networks/{quote(network)}/forwards", params={"recursion": recursion}
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "forwards": result.get("metadata", [])}


def network_forward_get(network, listen_address):
    """
    Get network forward information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_forward_get mybr0 10.0.0.1

    :param network: Network name
    :param listen_address: Listen address
    :return: Forward information
    """
    client = _client()
    result = client._request("GET", f"/networks/{quote(network)}/forwards/{quote(listen_address)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "forward": result.get("metadata", {})}


def network_forward_create(network, listen_address, config=None, description="", ports=None):
    """
    Create a network forward

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_forward_create mybr0 10.0.0.1 ports="[{'listen_port':'80','protocol':'tcp','target_address':'10.0.0.2','target_port':'8080'}]"

    :param network: Network name
    :param listen_address: Listen address
    :param config: Forward configuration
    :param description: Forward description
    :param ports: List of port forwards
    :return: Result
    """
    client = _client()

    data = {
        "listen_address": listen_address,
        "config": config or {},
        "description": description,
        "ports": ports or [],
    }

    result = client._sync_request("POST", f"/networks/{quote(network)}/forwards", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network forward {listen_address} created successfully"}


def network_forward_update(network, listen_address, config=None, description=None, ports=None):
    """
    Update network forward

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_forward_update mybr0 10.0.0.1 ports="[{'listen_port':'443','protocol':'tcp','target_address':'10.0.0.3','target_port':'8443'}]"

    :param network: Network name
    :param listen_address: Listen address
    :param config: Configuration to update
    :param description: Description to update
    :param ports: Ports to update
    :return: Result
    """
    client = _client()

    # Get current forward config
    current = network_forward_get(network, listen_address)
    if not current.get("success"):
        return current

    forward_data = current["forward"]

    if config:
        forward_data["config"].update(config)

    if description is not None:
        forward_data["description"] = description

    if ports is not None:
        forward_data["ports"] = ports

    result = client._sync_request(
        "PUT", f"/networks/{quote(network)}/forwards/{quote(listen_address)}", data=forward_data
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network forward {listen_address} updated successfully"}


def network_forward_delete(network, listen_address):
    """
    Delete a network forward

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_forward_delete mybr0 10.0.0.1

    :param network: Network name
    :param listen_address: Listen address
    :return: Result
    """
    client = _client()
    result = client._sync_request(
        "DELETE", f"/networks/{quote(network)}/forwards/{quote(listen_address)}"
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network forward {listen_address} deleted successfully"}


# ========== Network Peer Management Functions ==========


def network_peer_list(network, recursion=0):
    """
    List network peers

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_peer_list mybr0

    :param network: Network name
    :param recursion: Recursion level
    :return: List of peers
    """
    client = _client()
    result = client._request(
        "GET", f"/networks/{quote(network)}/peers", params={"recursion": recursion}
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "peers": result.get("metadata", [])}


def network_peer_get(network, peer_name):
    """
    Get network peer information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_peer_get mybr0 peer1

    :param network: Network name
    :param peer_name: Peer name
    :return: Peer information
    """
    client = _client()
    result = client._request("GET", f"/networks/{quote(network)}/peers/{quote(peer_name)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "peer": result.get("metadata", {})}


def network_peer_create(
    network, peer_name, config=None, description="", target_network=None, target_project=None
):
    """
    Create a network peer

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_peer_create mybr0 peer1 target_network=othernet target_project=otherproject

    :param network: Network name
    :param peer_name: Peer name
    :param config: Peer configuration
    :param description: Peer description
    :param target_network: Target network name
    :param target_project: Target project name
    :return: Result
    """
    client = _client()

    data = {"name": peer_name, "config": config or {}, "description": description}

    if target_network:
        data["target_network"] = target_network

    if target_project:
        data["target_project"] = target_project

    result = client._sync_request("POST", f"/networks/{quote(network)}/peers", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network peer {peer_name} created successfully"}


def network_peer_update(
    network, peer_name, config=None, description=None, target_network=None, target_project=None
):
    """
    Update network peer

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_peer_update mybr0 peer1 description="Updated peer"

    :param network: Network name
    :param peer_name: Peer name
    :param config: Configuration to update
    :param description: Description to update
    :param target_network: Target network to update
    :param target_project: Target project to update
    :return: Result
    """
    client = _client()

    # Get current peer config
    current = network_peer_get(network, peer_name)
    if not current.get("success"):
        return current

    peer_data = current["peer"]

    if config:
        peer_data["config"].update(config)

    if description is not None:
        peer_data["description"] = description

    if target_network is not None:
        peer_data["target_network"] = target_network

    if target_project is not None:
        peer_data["target_project"] = target_project

    result = client._sync_request(
        "PUT", f"/networks/{quote(network)}/peers/{quote(peer_name)}", data=peer_data
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network peer {peer_name} updated successfully"}


def network_peer_delete(network, peer_name):
    """
    Delete a network peer

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_peer_delete mybr0 peer1

    :param network: Network name
    :param peer_name: Peer name
    :return: Result
    """
    client = _client()
    result = client._sync_request("DELETE", f"/networks/{quote(network)}/peers/{quote(peer_name)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network peer {peer_name} deleted successfully"}


# ========== Network Zone Management Functions ==========


def network_zone_list(recursion=0):
    """
    List all network zones

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_zone_list
        salt '*' incus.network_zone_list recursion=1

    :param recursion: Recursion level
    :return: List of network zones
    """
    client = _client()
    result = client._request("GET", "/network-zones", params={"recursion": recursion})

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "zones": result.get("metadata", [])}


def network_zone_get(zone):
    """
    Get network zone information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_zone_get example.com

    :param zone: Zone name
    :return: Zone information
    """
    client = _client()
    result = client._request("GET", f"/network-zones/{quote(zone)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "zone": result.get("metadata", {})}


def network_zone_create(zone, config=None, description=""):
    """
    Create a network zone

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_zone_create example.com
        salt '*' incus.network_zone_create example.com config="{'dns.nameservers':'ns1.example.com'}"

    :param zone: Zone name
    :param config: Zone configuration
    :param description: Zone description
    :return: Result
    """
    client = _client()

    data = {"name": zone, "config": config or {}, "description": description}

    result = client._sync_request("POST", "/network-zones", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network zone {zone} created successfully"}


def network_zone_update(zone, config=None, description=None):
    """
    Update network zone

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_zone_update example.com config="{'dns.nameservers':'ns2.example.com'}"

    :param zone: Zone name
    :param config: Configuration to update
    :param description: Description to update
    :return: Result
    """
    client = _client()

    # Get current zone config
    current = network_zone_get(zone)
    if not current.get("success"):
        return current

    zone_data = current["zone"]

    if config:
        zone_data["config"].update(config)

    if description is not None:
        zone_data["description"] = description

    result = client._sync_request("PUT", f"/network-zones/{quote(zone)}", data=zone_data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network zone {zone} updated successfully"}


def network_zone_delete(zone):
    """
    Delete a network zone

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_zone_delete example.com

    :param zone: Zone name
    :return: Result
    """
    client = _client()
    result = client._sync_request("DELETE", f"/network-zones/{quote(zone)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network zone {zone} deleted successfully"}


# ========== Network Zone Record Management Functions ==========


def network_zone_record_list(zone, recursion=0):
    """
    List network zone records

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_zone_record_list example.com

    :param zone: Zone name
    :param recursion: Recursion level
    :return: List of zone records
    """
    client = _client()
    result = client._request(
        "GET", f"/network-zones/{quote(zone)}/records", params={"recursion": recursion}
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "records": result.get("metadata", [])}


def network_zone_record_get(zone, record_name):
    """
    Get network zone record information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_zone_record_get example.com www

    :param zone: Zone name
    :param record_name: Record name
    :return: Record information
    """
    client = _client()
    result = client._request("GET", f"/network-zones/{quote(zone)}/records/{quote(record_name)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "record": result.get("metadata", {})}


def network_zone_record_create(zone, record_name, config=None, description="", entries=None):
    """
    Create a network zone record

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_zone_record_create example.com www entries="[{'type':'A','value':'192.168.1.1'}]"

    :param zone: Zone name
    :param record_name: Record name
    :param config: Record configuration
    :param description: Record description
    :param entries: List of DNS entries
    :return: Result
    """
    client = _client()

    data = {
        "name": record_name,
        "config": config or {},
        "description": description,
        "entries": entries or [],
    }

    result = client._sync_request("POST", f"/network-zones/{quote(zone)}/records", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network zone record {record_name} created successfully"}


def network_zone_record_update(zone, record_name, config=None, description=None, entries=None):
    """
    Update network zone record

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_zone_record_update example.com www entries="[{'type':'A','value':'192.168.1.2'}]"

    :param zone: Zone name
    :param record_name: Record name
    :param config: Configuration to update
    :param description: Description to update
    :param entries: Entries to update
    :return: Result
    """
    client = _client()

    # Get current record config
    current = network_zone_record_get(zone, record_name)
    if not current.get("success"):
        return current

    record_data = current["record"]

    if config:
        record_data["config"].update(config)

    if description is not None:
        record_data["description"] = description

    if entries is not None:
        record_data["entries"] = entries

    result = client._sync_request(
        "PUT", f"/network-zones/{quote(zone)}/records/{quote(record_name)}", data=record_data
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network zone record {record_name} updated successfully"}


def network_zone_record_delete(zone, record_name):
    """
    Delete a network zone record

    CLI Example:

    .. code-block:: bash

        salt '*' incus.network_zone_record_delete example.com www

    :param zone: Zone name
    :param record_name: Record name
    :return: Result
    """
    client = _client()
    result = client._sync_request(
        "DELETE", f"/network-zones/{quote(zone)}/records/{quote(record_name)}"
    )

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Network zone record {record_name} deleted successfully"}


__all__ = [
    "network_list",
    "network_create",
    "network_get",
    "network_delete",
    "network_update",
    "network_rename",
    "network_state",
    "network_lease_list",
    "network_acl_list",
    "network_acl_get",
    "network_acl_create",
    "network_acl_update",
    "network_acl_delete",
    "network_acl_rename",
    "network_forward_list",
    "network_forward_get",
    "network_forward_create",
    "network_forward_update",
    "network_forward_delete",
    "network_peer_list",
    "network_peer_get",
    "network_peer_create",
    "network_peer_update",
    "network_peer_delete",
    "network_zone_list",
    "network_zone_get",
    "network_zone_create",
    "network_zone_update",
    "network_zone_delete",
    "network_zone_record_list",
    "network_zone_record_get",
    "network_zone_record_create",
    "network_zone_record_update",
    "network_zone_record_delete",
]
