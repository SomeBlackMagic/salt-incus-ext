"""Salt state functions for managing Incus networking resources."""

__virtualname__ = "incus"


def __virtual__():
    """Load when the Incus network execution functions are available."""
    if "incus.network_list" in __salt__:
        return __virtualname__
    return False, "incus network execution functions are not available"


# ======================================================================
# Helpers
# ======================================================================


def _format_error_message(operation, resource_name, result, extra_info=None):
    """
    Format enhanced error message with troubleshooting information.

    :param operation: Operation being performed (e.g., "create", "update", "delete")
    :param resource_name: Name of the resource
    :param result: Result dict from execution module
    :param extra_info: Additional information dict (config, params, etc.)
    :return: Formatted error message string
    """
    error_msg = result.get("error", "Unknown error")
    error_code = result.get("error_code")

    msg = f"Failed to {operation} {resource_name}: {error_msg}"

    # Add enhanced details for server errors (5xx)
    if error_code and 500 <= error_code < 600:
        msg += (
            f"\n\nServer Error (HTTP {error_code}). "
            f"Check Salt minion logs for detailed request/response information."
        )

        if extra_info:
            msg += "\n\nConfiguration sent:"
            for key, value in extra_info.items():
                msg += f"\n  - {key}: {value}"

        msg += (
            "\n\nTroubleshooting:"
            "\n  1. Verify all configuration values are valid for Incus"
            "\n  2. Remove optional parameters one by one to isolate the issue"
            "\n  3. Check detailed logs: /var/log/salt/minion"
            "\n  4. Check Incus server logs: journalctl -u incus -n 50"
            "\n  5. Test the API directly: incus query -X POST /1.0/... --data '{}'"
        )

    return msg


def _normalize_config_value(value):
    """
    Normalize configuration value to string for comparison.
    Converts Python boolean to lowercase string to match Incus API format.

    :param value: Configuration value (can be str, bool, int, etc.)
    :return: Normalized string value
    """
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


# ======================================================================
# Network States
# ======================================================================


def network_present(name, network_type="bridge", config=None, description=""):
    """
    Ensure a network exists with all specified parameters.

    :param name: Network name
    :param network_type: Network type (bridge, macvlan, sriov, ovn, physical)
    :param config: Network configuration (dict)
    :param description: Network description

    Supports all network configuration parameters including:
    - ipv4.address, ipv4.nat, ipv4.dhcp, ipv4.routing
    - ipv6.address, ipv6.nat, ipv6.dhcp, ipv6.routing
    - dns.domain, dns.mode, dns.search
    - bridge.driver, bridge.external_interfaces, bridge.hwaddr, bridge.mtu
    - network, parent, mtu, vlan
    - And many other network-specific parameters

    Example:

    .. code-block:: yaml

        mybr0:
          incus.network_present:
            - network_type: bridge
            - config:
                ipv4.address: 10.0.0.1/24
                ipv4.nat: "true"
                ipv4.dhcp: "true"
                ipv4.dhcp.ranges: 10.0.0.100-10.0.0.200
                ipv6.address: none
                dns.domain: incus
                dns.mode: managed
            - description: Main bridge network
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    network_info = __salt__["incus.network_get"](name)

    if network_info.get("success"):
        # Network exists, check for updates
        current_network = network_info.get("network", {}) or {}
        changes = {}

        # Check config changes
        if config:
            current_config = current_network.get("config", {}) or {}
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

        # Check description changes
        if description is not None:
            current_desc = current_network.get("description", "")
            if current_desc != description:
                changes["description"] = {
                    "old": current_desc,
                    "new": description,
                }

        if changes:
            if __opts__.get("test"):
                ret["result"] = None
                ret["comment"] = f"Network {name} would be updated"
                ret["changes"] = changes
            else:
                # Update config if needed
                if "config" in changes:
                    update_result = __salt__["incus.network_update"](name, config)
                    if not update_result.get("success"):
                        ret["result"] = False
                        ret["comment"] = (
                            f"Failed to update network {name}: " f"{update_result.get('error')}"
                        )
                        return ret

                ret["comment"] = f"Network {name} updated"
                ret["changes"] = changes
        else:
            ret["comment"] = f"Network {name} already in desired state"
    else:
        # Network doesn't exist, create it
        if __opts__.get("test"):
            ret["result"] = None
            ret["comment"] = f"Network {name} would be created"
            ret["changes"] = {
                "network": {
                    "old": None,
                    "new": {
                        "name": name,
                        "type": network_type,
                        "config": config,
                        "description": description,
                    },
                }
            }
            return ret

        create_result = __salt__["incus.network_create"](
            name,
            network_type=network_type,
            config=config,
            description=description,
        )

        if create_result.get("success"):
            ret["comment"] = f"Network {name} created"
            ret["changes"] = {
                "network": {
                    "old": None,
                    "new": name,
                }
            }
        else:
            ret["result"] = False
            ret["comment"] = _format_error_message(
                "create",
                f"network {name}",
                create_result,
                extra_info={
                    "type": network_type,
                    "description": description or "(empty)",
                    "config": config or {},
                },
            )

    return ret


def network_absent(name):
    """
    Ensure a network does not exist.

    :param name: Network name

    Example:

    .. code-block:: yaml

        old_network:
          incus.network_absent
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    network_info = __salt__["incus.network_get"](name)

    if not network_info.get("success"):
        ret["comment"] = f"Network {name} already absent"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Network {name} would be deleted"
        ret["changes"] = {
            "network": {
                "old": name,
                "new": None,
            }
        }
        return ret

    delete_result = __salt__["incus.network_delete"](name)

    if delete_result.get("success"):
        ret["comment"] = f"Network {name} deleted"
        ret["changes"] = {
            "network": {
                "old": name,
                "new": None,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to delete network {name}: " f"{delete_result.get('error')}"

    return ret


# ======================================================================
# Network ACL States
# ======================================================================


def network_acl_present(name, config=None, description="", egress=None, ingress=None):
    """
    Ensure a network ACL exists and matches configuration.

    :param name: ACL name
    :param config: ACL configuration (dict)
    :param description: ACL description
    :param egress: List of egress rules
    :param ingress: List of ingress rules

    Example:

    .. code-block:: yaml

        myacl:
          incus.network_acl_present:
            - ingress:
                - action: allow
                  source: 10.0.0.0/24
                  destination: ""
                  protocol: tcp
                  destination_port: "22"
                - action: drop
                  source: ""
            - egress:
                - action: allow
            - description: SSH access from internal network
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    acl_info = __salt__["incus.network_acl_get"](name)

    if acl_info.get("success"):
        # ACL exists, check for updates
        current_acl = acl_info.get("acl", {}) or {}
        changes = {}

        # Check config
        if config:
            current_config = current_acl.get("config", {}) or {}
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

        # Check description
        if description is not None:
            current_desc = current_acl.get("description", "")
            if current_desc != description:
                changes["description"] = {
                    "old": current_desc,
                    "new": description,
                }

        # Check egress rules
        if egress is not None:
            current_egress = current_acl.get("egress", [])
            if current_egress != egress:
                changes["egress"] = {
                    "old": current_egress,
                    "new": egress,
                }

        # Check ingress rules
        if ingress is not None:
            current_ingress = current_acl.get("ingress", [])
            if current_ingress != ingress:
                changes["ingress"] = {
                    "old": current_ingress,
                    "new": ingress,
                }

        if changes:
            if __opts__.get("test"):
                ret["result"] = None
                ret["comment"] = f"Network ACL {name} would be updated"
                ret["changes"] = changes
            else:
                update_result = __salt__["incus.network_acl_update"](
                    name,
                    config=config,
                    description=description,
                    egress=egress,
                    ingress=ingress,
                )
                if update_result.get("success"):
                    ret["comment"] = f"Network ACL {name} updated"
                    ret["changes"] = changes
                else:
                    ret["result"] = False
                    ret["comment"] = (
                        f"Failed to update network ACL {name}: " f"{update_result.get('error')}"
                    )
        else:
            ret["comment"] = f"Network ACL {name} already in desired state"
    else:
        # ACL doesn't exist, create it
        if __opts__.get("test"):
            ret["result"] = None
            ret["comment"] = f"Network ACL {name} would be created"
            ret["changes"] = {
                "acl": {
                    "old": None,
                    "new": name,
                }
            }
            return ret

        create_result = __salt__["incus.network_acl_create"](
            name,
            config=config,
            description=description,
            egress=egress,
            ingress=ingress,
        )

        if create_result.get("success"):
            ret["comment"] = f"Network ACL {name} created"
            ret["changes"] = {
                "acl": {
                    "old": None,
                    "new": name,
                }
            }
        else:
            ret["result"] = False
            ret["comment"] = (
                f"Failed to create network ACL {name}: " f"{create_result.get('error')}"
            )

    return ret


def network_acl_absent(name):
    """
    Ensure a network ACL does not exist.

    :param name: ACL name

    Example:

    .. code-block:: yaml

        old_acl:
          incus.network_acl_absent
    """
    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    acl_info = __salt__["incus.network_acl_get"](name)

    if not acl_info.get("success"):
        ret["comment"] = f"Network ACL {name} already absent"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Network ACL {name} would be deleted"
        ret["changes"] = {
            "acl": {
                "old": name,
                "new": None,
            }
        }
        return ret

    delete_result = __salt__["incus.network_acl_delete"](name)

    if delete_result.get("success"):
        ret["comment"] = f"Network ACL {name} deleted"
        ret["changes"] = {
            "acl": {
                "old": name,
                "new": None,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to delete network ACL {name}: " f"{delete_result.get('error')}"

    return ret


# ======================================================================
# Network Forward States
# ======================================================================


def network_forward_present(network, listen_address, config=None, description="", ports=None):
    """
    Ensure a network forward exists and matches configuration.

    :param network: Network name
    :param listen_address: Listen address
    :param config: Forward configuration (dict)
    :param description: Forward description
    :param ports: List of port forwards

    Example:

    .. code-block:: yaml

        mybr0_forward:
          incus.network_forward_present:
            - network: mybr0
            - listen_address: 10.0.0.1
            - ports:
                - listen_port: "80"
                  protocol: tcp
                  target_address: 10.0.0.2
                  target_port: "8080"
                - listen_port: "443"
                  protocol: tcp
                  target_address: 10.0.0.2
                  target_port: "8443"
            - description: Web traffic forward
    """
    ret = {
        "name": f"{network}_{listen_address}",
        "result": True,
        "changes": {},
        "comment": "",
    }

    forward_info = __salt__["incus.network_forward_get"](network, listen_address)

    if forward_info.get("success"):
        # Forward exists, check for updates
        current_forward = forward_info.get("forward", {}) or {}
        changes = {}

        # Check config
        if config:
            current_config = current_forward.get("config", {}) or {}
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

        # Check description
        if description is not None:
            current_desc = current_forward.get("description", "")
            if current_desc != description:
                changes["description"] = {
                    "old": current_desc,
                    "new": description,
                }

        # Check ports
        if ports is not None:
            current_ports = current_forward.get("ports", [])
            if current_ports != ports:
                changes["ports"] = {
                    "old": current_ports,
                    "new": ports,
                }

        if changes:
            if __opts__.get("test"):
                ret["result"] = None
                ret["comment"] = f"Network forward {listen_address} would be updated"
                ret["changes"] = changes
            else:
                update_result = __salt__["incus.network_forward_update"](
                    network,
                    listen_address,
                    config=config,
                    description=description,
                    ports=ports,
                )
                if update_result.get("success"):
                    ret["comment"] = f"Network forward {listen_address} updated"
                    ret["changes"] = changes
                else:
                    ret["result"] = False
                    ret["comment"] = (
                        f"Failed to update network forward {listen_address}: "
                        f"{update_result.get('error')}"
                    )
        else:
            ret["comment"] = f"Network forward {listen_address} already in desired state"
    else:
        # Forward doesn't exist, create it
        if __opts__.get("test"):
            ret["result"] = None
            ret["comment"] = f"Network forward {listen_address} would be created"
            ret["changes"] = {
                "forward": {
                    "old": None,
                    "new": listen_address,
                }
            }
            return ret

        create_result = __salt__["incus.network_forward_create"](
            network,
            listen_address,
            config=config,
            description=description,
            ports=ports,
        )

        if create_result.get("success"):
            ret["comment"] = f"Network forward {listen_address} created"
            ret["changes"] = {
                "forward": {
                    "old": None,
                    "new": listen_address,
                }
            }
        else:
            ret["result"] = False
            ret["comment"] = (
                f"Failed to create network forward {listen_address}: "
                f"{create_result.get('error')}"
            )

    return ret


def network_forward_absent(network, listen_address):
    """
    Ensure a network forward does not exist.

    :param network: Network name
    :param listen_address: Listen address

    Example:

    .. code-block:: yaml

        mybr0_forward:
          incus.network_forward_absent:
            - network: mybr0
            - listen_address: 10.0.0.1
    """
    ret = {
        "name": f"{network}_{listen_address}",
        "result": True,
        "changes": {},
        "comment": "",
    }

    forward_info = __salt__["incus.network_forward_get"](network, listen_address)

    if not forward_info.get("success"):
        ret["comment"] = f"Network forward {listen_address} already absent"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Network forward {listen_address} would be deleted"
        ret["changes"] = {
            "forward": {
                "old": listen_address,
                "new": None,
            }
        }
        return ret

    delete_result = __salt__["incus.network_forward_delete"](network, listen_address)

    if delete_result.get("success"):
        ret["comment"] = f"Network forward {listen_address} deleted"
        ret["changes"] = {
            "forward": {
                "old": listen_address,
                "new": None,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = (
            f"Failed to delete network forward {listen_address}: " f"{delete_result.get('error')}"
        )

    return ret


# ======================================================================
# Network Peer States
# ======================================================================


def network_peer_present(
    network, peer_name, config=None, description="", target_network=None, target_project=None
):
    """
    Ensure a network peer exists and matches configuration.

    :param network: Network name
    :param peer_name: Peer name
    :param config: Peer configuration (dict)
    :param description: Peer description
    :param target_network: Target network name
    :param target_project: Target project name

    Example:

    .. code-block:: yaml

        mybr0_peer:
          incus.network_peer_present:
            - network: mybr0
            - peer_name: peer1
            - target_network: othernet
            - target_project: otherproject
            - description: Peer to other network
    """
    ret = {
        "name": f"{network}_{peer_name}",
        "result": True,
        "changes": {},
        "comment": "",
    }

    peer_info = __salt__["incus.network_peer_get"](network, peer_name)

    if peer_info.get("success"):
        # Peer exists, check for updates
        current_peer = peer_info.get("peer", {}) or {}
        changes = {}

        # Check config
        if config:
            current_config = current_peer.get("config", {}) or {}
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

        # Check description
        if description is not None:
            current_desc = current_peer.get("description", "")
            if current_desc != description:
                changes["description"] = {
                    "old": current_desc,
                    "new": description,
                }

        # Check target_network
        if target_network is not None:
            current_target = current_peer.get("target_network", "")
            if current_target != target_network:
                changes["target_network"] = {
                    "old": current_target,
                    "new": target_network,
                }

        # Check target_project
        if target_project is not None:
            current_project = current_peer.get("target_project", "")
            if current_project != target_project:
                changes["target_project"] = {
                    "old": current_project,
                    "new": target_project,
                }

        if changes:
            if __opts__.get("test"):
                ret["result"] = None
                ret["comment"] = f"Network peer {peer_name} would be updated"
                ret["changes"] = changes
            else:
                update_result = __salt__["incus.network_peer_update"](
                    network,
                    peer_name,
                    config=config,
                    description=description,
                    target_network=target_network,
                    target_project=target_project,
                )
                if update_result.get("success"):
                    ret["comment"] = f"Network peer {peer_name} updated"
                    ret["changes"] = changes
                else:
                    ret["result"] = False
                    ret["comment"] = (
                        f"Failed to update network peer {peer_name}: "
                        f"{update_result.get('error')}"
                    )
        else:
            ret["comment"] = f"Network peer {peer_name} already in desired state"
    else:
        # Peer doesn't exist, create it
        if __opts__.get("test"):
            ret["result"] = None
            ret["comment"] = f"Network peer {peer_name} would be created"
            ret["changes"] = {
                "peer": {
                    "old": None,
                    "new": peer_name,
                }
            }
            return ret

        create_result = __salt__["incus.network_peer_create"](
            network,
            peer_name,
            config=config,
            description=description,
            target_network=target_network,
            target_project=target_project,
        )

        if create_result.get("success"):
            ret["comment"] = f"Network peer {peer_name} created"
            ret["changes"] = {
                "peer": {
                    "old": None,
                    "new": peer_name,
                }
            }
        else:
            ret["result"] = False
            ret["comment"] = (
                f"Failed to create network peer {peer_name}: " f"{create_result.get('error')}"
            )

    return ret


def network_peer_absent(network, peer_name):
    """
    Ensure a network peer does not exist.

    :param network: Network name
    :param peer_name: Peer name

    Example:

    .. code-block:: yaml

        mybr0_peer:
          incus.network_peer_absent:
            - network: mybr0
            - peer_name: peer1
    """
    ret = {
        "name": f"{network}_{peer_name}",
        "result": True,
        "changes": {},
        "comment": "",
    }

    peer_info = __salt__["incus.network_peer_get"](network, peer_name)

    if not peer_info.get("success"):
        ret["comment"] = f"Network peer {peer_name} already absent"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Network peer {peer_name} would be deleted"
        ret["changes"] = {
            "peer": {
                "old": peer_name,
                "new": None,
            }
        }
        return ret

    delete_result = __salt__["incus.network_peer_delete"](network, peer_name)

    if delete_result.get("success"):
        ret["comment"] = f"Network peer {peer_name} deleted"
        ret["changes"] = {
            "peer": {
                "old": peer_name,
                "new": None,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = (
            f"Failed to delete network peer {peer_name}: " f"{delete_result.get('error')}"
        )

    return ret


# ======================================================================
# Network Zone States
# ======================================================================


def network_zone_present(zone, config=None, description=""):
    """
    Ensure a network zone exists and matches configuration.

    :param zone: Zone name (e.g., example.com)
    :param config: Zone configuration (dict)
    :param description: Zone description

    Example:

    .. code-block:: yaml

        example.com:
          incus.network_zone_present:
            - config:
                dns.nameservers: ns1.example.com
            - description: Main DNS zone
    """
    ret = {
        "name": zone,
        "result": True,
        "changes": {},
        "comment": "",
    }

    zone_info = __salt__["incus.network_zone_get"](zone)

    if zone_info.get("success"):
        # Zone exists, check for updates
        current_zone = zone_info.get("zone", {}) or {}
        changes = {}

        # Check config
        if config:
            current_config = current_zone.get("config", {}) or {}
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

        # Check description
        if description is not None:
            current_desc = current_zone.get("description", "")
            if current_desc != description:
                changes["description"] = {
                    "old": current_desc,
                    "new": description,
                }

        if changes:
            if __opts__.get("test"):
                ret["result"] = None
                ret["comment"] = f"Network zone {zone} would be updated"
                ret["changes"] = changes
            else:
                update_result = __salt__["incus.network_zone_update"](
                    zone,
                    config=config,
                    description=description,
                )
                if update_result.get("success"):
                    ret["comment"] = f"Network zone {zone} updated"
                    ret["changes"] = changes
                else:
                    ret["result"] = False
                    ret["comment"] = (
                        f"Failed to update network zone {zone}: " f"{update_result.get('error')}"
                    )
        else:
            ret["comment"] = f"Network zone {zone} already in desired state"
    else:
        # Zone doesn't exist, create it
        if __opts__.get("test"):
            ret["result"] = None
            ret["comment"] = f"Network zone {zone} would be created"
            ret["changes"] = {
                "zone": {
                    "old": None,
                    "new": zone,
                }
            }
            return ret

        create_result = __salt__["incus.network_zone_create"](
            zone,
            config=config,
            description=description,
        )

        if create_result.get("success"):
            ret["comment"] = f"Network zone {zone} created"
            ret["changes"] = {
                "zone": {
                    "old": None,
                    "new": zone,
                }
            }
        else:
            ret["result"] = False
            ret["comment"] = (
                f"Failed to create network zone {zone}: " f"{create_result.get('error')}"
            )

    return ret


def network_zone_absent(zone):
    """
    Ensure a network zone does not exist.

    :param zone: Zone name

    Example:

    .. code-block:: yaml

        old-zone.com:
          incus.network_zone_absent
    """
    ret = {
        "name": zone,
        "result": True,
        "changes": {},
        "comment": "",
    }

    zone_info = __salt__["incus.network_zone_get"](zone)

    if not zone_info.get("success"):
        ret["comment"] = f"Network zone {zone} already absent"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Network zone {zone} would be deleted"
        ret["changes"] = {
            "zone": {
                "old": zone,
                "new": None,
            }
        }
        return ret

    delete_result = __salt__["incus.network_zone_delete"](zone)

    if delete_result.get("success"):
        ret["comment"] = f"Network zone {zone} deleted"
        ret["changes"] = {
            "zone": {
                "old": zone,
                "new": None,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to delete network zone {zone}: " f"{delete_result.get('error')}"

    return ret


def network_zone_record_present(zone, record_name, config=None, description="", entries=None):
    """
    Ensure a network zone record exists and matches configuration.

    :param zone: Zone name
    :param record_name: Record name
    :param config: Record configuration (dict)
    :param description: Record description
    :param entries: List of DNS entries

    Example:

    .. code-block:: yaml

        www_record:
          incus.network_zone_record_present:
            - zone: example.com
            - record_name: www
            - entries:
                - type: A
                  value: 192.168.1.1
                - type: AAAA
                  value: "2001:db8::1"
            - description: Web server record
    """
    ret = {
        "name": f"{zone}_{record_name}",
        "result": True,
        "changes": {},
        "comment": "",
    }

    record_info = __salt__["incus.network_zone_record_get"](zone, record_name)

    if record_info.get("success"):
        # Record exists, check for updates
        current_record = record_info.get("record", {}) or {}
        changes = {}

        # Check config
        if config:
            current_config = current_record.get("config", {}) or {}
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

        # Check description
        if description is not None:
            current_desc = current_record.get("description", "")
            if current_desc != description:
                changes["description"] = {
                    "old": current_desc,
                    "new": description,
                }

        # Check entries
        if entries is not None:
            current_entries = current_record.get("entries", [])
            if current_entries != entries:
                changes["entries"] = {
                    "old": current_entries,
                    "new": entries,
                }

        if changes:
            if __opts__.get("test"):
                ret["result"] = None
                ret["comment"] = f"Network zone record {record_name} would be updated"
                ret["changes"] = changes
            else:
                update_result = __salt__["incus.network_zone_record_update"](
                    zone,
                    record_name,
                    config=config,
                    description=description,
                    entries=entries,
                )
                if update_result.get("success"):
                    ret["comment"] = f"Network zone record {record_name} updated"
                    ret["changes"] = changes
                else:
                    ret["result"] = False
                    ret["comment"] = (
                        f"Failed to update network zone record {record_name}: "
                        f"{update_result.get('error')}"
                    )
        else:
            ret["comment"] = f"Network zone record {record_name} already in desired state"
    else:
        # Record doesn't exist, create it
        if __opts__.get("test"):
            ret["result"] = None
            ret["comment"] = f"Network zone record {record_name} would be created"
            ret["changes"] = {
                "record": {
                    "old": None,
                    "new": record_name,
                }
            }
            return ret

        create_result = __salt__["incus.network_zone_record_create"](
            zone,
            record_name,
            config=config,
            description=description,
            entries=entries,
        )

        if create_result.get("success"):
            ret["comment"] = f"Network zone record {record_name} created"
            ret["changes"] = {
                "record": {
                    "old": None,
                    "new": record_name,
                }
            }
        else:
            ret["result"] = False
            ret["comment"] = (
                f"Failed to create network zone record {record_name}: "
                f"{create_result.get('error')}"
            )

    return ret


def network_zone_record_absent(zone, record_name):
    """
    Ensure a network zone record does not exist.

    :param zone: Zone name
    :param record_name: Record name

    Example:

    .. code-block:: yaml

        old_record:
          incus.network_zone_record_absent:
            - zone: example.com
            - record_name: old
    """
    ret = {
        "name": f"{zone}_{record_name}",
        "result": True,
        "changes": {},
        "comment": "",
    }

    record_info = __salt__["incus.network_zone_record_get"](zone, record_name)

    if not record_info.get("success"):
        ret["comment"] = f"Network zone record {record_name} already absent"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["comment"] = f"Network zone record {record_name} would be deleted"
        ret["changes"] = {
            "record": {
                "old": record_name,
                "new": None,
            }
        }
        return ret

    delete_result = __salt__["incus.network_zone_record_delete"](zone, record_name)

    if delete_result.get("success"):
        ret["comment"] = f"Network zone record {record_name} deleted"
        ret["changes"] = {
            "record": {
                "old": record_name,
                "new": None,
            }
        }
    else:
        ret["result"] = False
        ret["comment"] = (
            f"Failed to delete network zone record {record_name}: " f"{delete_result.get('error')}"
        )

    return ret
