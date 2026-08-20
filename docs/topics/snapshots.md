# Instance snapshots

Snapshots capture an instance at a point in time for rollback and controlled
change workflows. They are not a substitute for an off-host backup: a pool or
host failure can remove both an instance and its snapshots.

## Create and inspect

```yaml
# Example: before-upgrade.sls
before-upgrade:
  incus.instance_snapshot_present:
    - instance: application-01
    - name: before-upgrade
    - description: Before operating system upgrade
```

```bash
salt-call incus.instance_snapshot_list application-01 recursion=1
salt-call incus.instance_snapshot_get application-01 before-upgrade
```

Set `stateful: true` only when Incus and the instance support a stateful
snapshot. Stateful VM snapshots have additional hypervisor and storage
requirements; ordinary stateless snapshots are more portable.

## Restore and delete

```yaml
# Example: rollback.sls
restore-application-before-upgrade:
  incus.instance_snapshot_restored:
    - instance: application-01
    - name: before-upgrade
```

Restoring replaces the instance's current state and is therefore disruptive.
Stop application traffic and preview the state where appropriate.

```yaml
# Example: remove-old-snapshot.sls
before-upgrade:
  incus.instance_snapshot_absent:
    - instance: application-01
    - name: before-upgrade
```

## Retention and scheduling

`instance_snapshots_managed` and `instance_snapshots_rotated` provide managed
sets and retention-oriented workflows. A simple Salt scheduler can apply a
snapshot SLS periodically:

```yaml
# /etc/salt/minion.d/schedule.conf
schedule:
  incus-nightly-snapshot:
    function: state.apply
    args:
      - snapshots.nightly
    hours: 24
```

```yaml
# Example: snapshots/nightly.sls
nightly:
  incus.instance_snapshot_present:
    - instance: application-01
    - name: nightly
    - description: Managed nightly checkpoint
```

A fixed name is idempotent and will not create a new snapshot every night. For
dated names, render a controlled date value and combine it with
`instance_snapshots_rotated` so retention remains bounded.
