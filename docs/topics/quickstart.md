# Quickstart

## Prerequisites

- Incus installed and running on the target host
- Salt minion configured to connect (see [Configuration](configuration.md))

## Managing instances

### Ensure a container exists

```yaml
mycontainer:
  incus.instance_present:
    - source:
        type: image
        alias: images:ubuntu/22.04
    - config:
        limits.cpu: "2"
        limits.memory: 2GiB
    - profiles:
        - default
    - instance_type: container
```

### Start/stop instances

```yaml
mycontainer:
  incus.instance_running: []
```

```yaml
mycontainer:
  incus.instance_stopped:
    - force: true
```

## Managing networks

```yaml
mybr0:
  incus.network_present:
    - network_type: bridge
    - config:
        ipv4.address: 10.0.100.1/24
        ipv4.nat: "true"
        ipv6.address: none
```

## Managing storage pools

```yaml
default-pool:
  incus.storage_pool_present:
    - driver: dir
    - config:
        source: /var/lib/incus/storage-pools/default
```

## Managing profiles

```yaml
webserver-profile:
  incus.profile_present:
    - config:
        limits.cpu: "4"
        limits.memory: 4GiB
    - devices:
        eth0:
          name: eth0
          network: mybr0
          type: nic
```

## Snapshot management

```yaml
mycontainer/before-update:
  incus.instance_snapshot_present:
    - instance: mycontainer
    - name: before-update
    - description: Snapshot before apt upgrade
```

## PKI / TLS certificates

### Generate and trust a client certificate

```yaml
generate-incus-client-cert:
  incus_pki.keypair_present:
    - name: salt-master
    - storage:
        cert: /etc/salt/pki/incus/client.crt
        key: /etc/salt/pki/incus/client.key

trust-incus-client-cert:
  incus_pki.trust_present:
    - name: salt-master
    - storage:
        cert: /etc/salt/pki/incus/client.crt
        key: /etc/salt/pki/incus/client.key
    - require:
        - incus_pki: generate-incus-client-cert
```
