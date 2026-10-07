# Instances

Incus manages system containers and virtual machines through one instances API.
Use `instance_type: container` for shared-kernel containers or
`instance_type: virtual-machine` when a separate guest kernel is required.

## Create from an image

```yaml
# Example: application-instance.sls
application-01:
  incus.instance_present:
    - source:
        type: image
        alias: ubuntu-24.04
    - instance_type: container
    - profiles:
        - default
    - config:
        limits.cpu: "2"
        limits.memory: 2GiB
    - devices:
        data:
          type: disk
          pool: default
          source: application-data
          path: /srv/application
```

`source` is passed to Incus and may describe an image, copy, or migration. For
copies and migrations, provide the complete source dictionary expected by the
target Incus API version. The saltext state currently exposes no separate
high-level migrate state.

The state reconciles the requested `config`, `profiles`, and supplied device
properties. It does not remove unspecified configuration or devices.

## Containers and virtual machines

The same state creates a VM:

```yaml
# Example: build-vm.sls
build-vm:
  incus.instance_present:
    - source:
        type: image
        alias: ubuntu-24.04
    - instance_type: virtual-machine
    - config:
        limits.cpu: "4"
        limits.memory: 8GiB
```

The alias must already exist locally on the target Incus server; see
[Images](images.md) for remote import. Image aliases must provide the requested
instance type. VM images, firmware, and host virtualisation support are Incus
prerequisites rather than saltext settings.

## Lifecycle

Use states for desired running/stopped state and execution calls for an
immediate restart:

```yaml
# Example: running-instance.sls
application-01:
  incus.instance_running:
    - wait_is_ready: true
    - ready_timeout: 300
    - require:
        - incus: application-instance
```

```bash
salt-call incus.instance_start application-01
salt-call incus.instance_restart application-01 timeout=30
salt-call incus.instance_stop application-01 timeout=30
salt-call incus.instance_wait_ready application-01 timeout=300 interval=2
```

`instance_initialized` can wait for cloud-init when it is enabled. Freeze and
unfreeze actions are not exported by the current execution module.

## Devices

Common device forms include:

```yaml
# Example: instance-devices.sls
device-demo:
  incus.instance_present:
    - source:
        type: image
        alias: ubuntu-24.04
    - devices:
        eth0:
          type: nic
          network: incusbr0
          name: eth0
        cache:
          type: disk
          pool: default
          source: cache-volume
          path: /var/cache/application
        gpu0:
          type: gpu
```

GPU passthrough depends on compatible host hardware, drivers, and Incus device
configuration. Keep host-specific devices in a profile when several instances
share them.

## Inspect, publish, and remove

```bash
salt-call incus.instance_list recursion=1
salt-call incus.instance_get application-01
salt-call incus.instance_snapshot_publish application-01 release-1 \
  properties='{"description":"application release 1"}' aliases='["application/release-1"]'
```

Publishing is currently exposed for snapshots. There is no standalone
`instance_publish` or high-level migration state. Use an image-backed workflow
or the complete `source` data accepted by Incus when those operations are
needed.

```yaml
# Example: retired-instance.sls
application-01:
  incus.instance_absent:
    - force: true
```

Preview any state with `salt-call state.apply <sls> test=True` before applying
high-impact device, profile, or deletion changes.
