# Storage

Storage pools define a backend; custom volumes live inside a pool and can be
attached to instances as disk devices. Common Incus pool drivers include
`dir`, `zfs`, `btrfs`, `lvm`, and `ceph`.

## Create a pool

```yaml
# Example: storage-pool.sls
application-pool:
  incus.storage_pool_present:
    - driver: zfs
    - description: Application storage
    - config:
        source: application-zpool
```

Backend packages and devices must exist before Incus creates the pool. Pool
configuration varies by driver; the saltext passes the dictionary to Incus.

## Create and attach a custom volume

```yaml
# Example: application-volume.sls
application-data:
  incus.volume_present:
    - pool: application-pool
    - volume_type: custom
    - config:
        size: 20GiB

application-data-device:
  incus.volume_attached:
    - pool: application-pool
    - instance: application-01
    - device_name: application-data
    - path: /srv/application
    - require:
        - incus: application-data
```

Alternatively, declare the disk under `devices` in `instance_present`. Use a
stable device name so updates and detach operations target the same entry.

## Snapshots, copies, and backup boundary

```yaml
# Example: volume-checkpoint.sls
pre-migration:
  incus.volume_snapshot_present:
    - pool: application-pool
    - volume: application-data
    - description: Before data migration
```

Execution functions support volume copy, move, snapshot, and restore
operations. The current saltext does not expose a volume export function;
perform off-host export with Incus tooling and verify restoration as part of
the backup procedure.

```bash
salt-call incus.volume_list application-pool recursion=1
salt-call incus.storage_pool_resources application-pool
```

Remove attachments before removing a volume or pool. Incus refuses deletion
while dependent resources remain, which protects against accidental data loss.

## Pool driver examples

Pool configuration is passed directly to Incus. Typical minimal forms are:

```yaml
# Example: pool-drivers.sls
local-dir:
  incus.storage_pool_present:
    - driver: dir
    - config:
        source: /srv/incus-pools/local-dir

local-btrfs:
  incus.storage_pool_present:
    - driver: btrfs
    - config:
        source: /dev/disk/by-id/example-btrfs-device

existing-zfs:
  incus.storage_pool_present:
    - driver: zfs
    - config:
        source: incus-zpool
```

LVM and Ceph require backend-specific host or cluster preparation. Confirm the
accepted `source` and driver keys against the target Incus version before
creating a production pool.

## Update and inspect pools

```yaml
# Example: pool-configuration.sls
application-pool:
  incus.storage_pool_config:
    - config:
        volume.size: 20GiB
    - description: Application storage
```

```bash
salt-call incus.storage_pool_list recursion=1
salt-call incus.storage_pool_get application-pool
salt-call incus.storage_pool_resources application-pool
salt-call incus.storage_pool_rename old-pool new-pool
```

Pool rename is imperative and has no matching state.

## Copy, move, and restore volumes

```bash
salt-call incus.volume_copy application-pool application-data \
  target_pool=application-pool target_volume=application-data-copy
salt-call incus.volume_move application-pool application-data archive-pool
salt-call incus.volume_create_from_snapshot application-pool application-data \
  pre-migration restored-data
```

Copy and create-from-snapshot preserve the source volume. Move changes its pool
and optionally its name. These operations have no idempotent state wrapper, so
check the target with `incus.volume_get` before calling them repeatedly.

## Volume snapshot lifecycle

```bash
salt-call incus.volume_snapshot_list application-pool application-data recursion=1
salt-call incus.volume_snapshot_rename application-pool application-data \
  pre-migration archived-checkpoint
salt-call incus.volume_snapshot_restore application-pool application-data \
  archived-checkpoint
salt-call incus.volume_snapshot_delete application-pool application-data \
  archived-checkpoint
```

Restore is disruptive because it replaces current volume contents. Stop or
quiesce writers and take an additional recovery snapshot first.

## Detach and remove

```yaml
# Example: retire-volume.sls
detach-application-data:
  incus.volume_detached:
    - name: application-data
    - pool: application-pool
    - instance: application-01
    - device_name: application-data

remove-application-data:
  incus.volume_absent:
    - name: application-data
    - pool: application-pool
    - require:
        - incus: detach-application-data
```

The detach state verifies that the named device points to the requested pool
and volume before attempting removal.
