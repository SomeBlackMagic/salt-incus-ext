# Clusters

An Incus cluster presents several servers as one API endpoint. Incus owns Raft
membership, distributed database roles, storage, and network prerequisites;
saltext-incus exposes member inspection and basic add/remove operations.

## Inspect members

```bash
salt-call incus.cluster_info
salt-call incus.cluster_member_list recursion=1
salt-cloud --list-locations my-incus
```

The cloud driver's `avail_locations` maps cluster members to salt-cloud
locations. On a non-clustered server it returns a synthetic `local` location.

## Add or remove a member

```jinja
# Example: cluster-member.sls
incus-node-03:
  incus.cluster_member_present:
    - address: 10.20.0.13:8443
    - cluster_password: {{ pillar['incus_cluster_password'] | yaml_encode }}
```

The joining server must already satisfy Incus version, network, storage, name
resolution, and trust prerequisites. Protect the join password in pillar or an
external secret backend.

```yaml
# Example: retire-cluster-member.sls
incus-node-03:
  incus.cluster_member_absent:
    - force: false
```

Use graceful removal after moving instances and any member-local data. Reserve
`force: true` for recovery when the member cannot participate.

## Place cloud instances

```yaml
# /etc/salt/cloud.profiles.d/incus.conf
incus-node-02-container:
  provider: my-incus
  image: ubuntu-24.04
  instance_type: container
  profiles:
    - default
  location: incus-node-02
```

The execution `instance_create` function has no separate `location` argument;
member targeting is implemented by the cloud driver. Incus may later move
workloads according to explicit administrator actions.

## Availability considerations

Production HA design is an Incus responsibility. A three-member cluster is a
common minimum for maintaining database quorum after one voter fails, but the
required number and database roles depend on the Incus release and failure
model. Shared or replicated storage and network availability must be designed
separately; clustering alone does not make local instance data highly
available.
