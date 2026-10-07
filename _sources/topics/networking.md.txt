# Networking

Incus network types include `bridge`, `macvlan`, `sriov`, `ovn`, and
`physical`. Available options depend on the Incus version, host networking, and
whether the server is clustered.

## Managed bridge with NAT

```yaml
# Example: bridge-network.sls
incusbr1:
  incus.network_present:
    - network_type: bridge
    - description: Application bridge
    - config:
        ipv4.address: 10.80.0.1/24
        ipv4.nat: "true"
        ipv6.address: none
```

Attach the managed network in a profile:

```yaml
# Example: network-profile.sls
application-network:
  incus.profile_present:
    - devices:
        eth0:
          type: nic
          name: eth0
          network: incusbr1
```

The same device dictionary can be supplied to `incus.instance_present` for a
single instance.

## Other network types

An OVN network normally references an existing uplink network:

```yaml
# Example: ovn-network.sls
tenant-ovn:
  incus.network_present:
    - network_type: ovn
    - config:
        network: uplink0
        ipv4.address: 10.90.0.1/24
```

`macvlan`, `sriov`, and `physical` networks require a suitable parent interface
or device configuration. Validate those requirements with Incus before
applying the state across a cluster.

## State and diagnostics

```bash
salt-call incus.network_list recursion=1
salt-call incus.network_get incusbr1
salt-call incus.network_state incusbr1
salt-call incus.network_lease_list incusbr1
```

The current function is `incus.network_state`, not `network_state_get`. It reads
runtime state; the state module manages existence and configuration rather than
an explicit up/down action.

```yaml
# Example: obsolete-network.sls
obsolete-bridge:
  incus.network_absent: []
```

## Network ACLs

ACL rules are ordered lists. Declare the complete ingress or egress list when
managing it with a state.

```yaml
# Example: network-acl.sls
application-acl:
  incus.network_acl_present:
    - description: Permit HTTPS from the service network
    - ingress:
        - action: allow
          source: 10.80.0.0/24
          protocol: tcp
          destination_port: "443"
        - action: drop
    - egress:
        - action: allow
```

Attach the ACL through the appropriate Incus network or NIC configuration for
the network type in use. Rule ordering and supported selectors depend on the
Incus version.

## Network forwards

```yaml
# Example: network-forward.sls
application-forward:
  incus.network_forward_present:
    - network: incusbr1
    - listen_address: 10.80.0.10
    - description: Public application endpoint
    - ports:
        - protocol: tcp
          listen_port: "443"
          target_address: 10.80.0.20
          target_port: "8443"
```

The listen address must be usable by the managed network. Forward states
compare the complete `ports` list when it is supplied.

## Network peers

```yaml
# Example: network-peer.sls
application-peer:
  incus.network_peer_present:
    - network: tenant-a
    - peer_name: tenant-b
    - target_network: tenant-b
    - target_project: default
    - description: Tenant network peering
```

Peering availability and project permissions are enforced by Incus. Although
this state accepts `target_project`, ordinary saltext resource requests do not
currently expose project selection.

## DNS zones and records

```yaml
# Example: network-dns.sls
example.internal:
  incus.network_zone_present:
    - description: Internal application zone

application-record:
  incus.network_zone_record_present:
    - zone: example.internal
    - record_name: application
    - entries:
        - type: A
          value: 10.80.0.20
    - require:
        - incus: example.internal
```

Use the matching `*_absent` states for removal. Execution functions additionally
provide list/get/update operations and ACL rename. Preview list replacement and
deletion with Salt test mode.
