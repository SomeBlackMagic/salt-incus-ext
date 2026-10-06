# Salt Cloud driver

The Incus cloud driver creates, starts, queries, deploys to, and removes Incus
instances. Configure providers and profiles on the Salt master.

## Provider configuration

```yaml
# /etc/salt/cloud.providers.d/incus.conf
my-incus:
  driver: incus
  connection:
    type: unix
    socket: /var/lib/incus/unix.socket
    polling:
      operation:
        backoff_enabled: true
        initial_interval: 1.0
        backoff_factor: 1.5
        max_interval: 30.0
        jitter: 0.2
      ip:
        backoff_enabled: true
        initial_interval: 2.0
        backoff_factor: 1.5
        max_interval: 15.0
        jitter: 0.2
```

For a remote provider, bootstrap the public client certificate through an
already trusted path, such as a minion using the Incus Unix socket. Keep the
private key only on the Salt master.

```yaml
# /etc/salt/cloud.providers.d/incus-remote.conf
my-incus-remote:
  driver: incus
  connection:
    type: https
    url: https://incus.example.net:8443
    cert_storage:
      type: local_files
      cert: /etc/salt/pki/incus/client.crt
      key: /etc/salt/pki/incus/client.key
      verify: /etc/salt/pki/incus/server-ca.crt
```

The cloud driver accepts local paths or inline PEM data but deliberately
rejects `sdb://` values.

## Profile configuration

```yaml
# /etc/salt/cloud.profiles.d/incus.conf
incus-ubuntu-container:
  provider: my-incus
  image: ubuntu-24.04
  instance_type: container
  profiles:
    - default
  config:
    limits.cpu: "2"
    limits.memory: 2GiB
  devices:
    eth0:
      type: nic
      network: incusbr0
      name: eth0
  location: incus-node-02
  wait_for_ip_timeout: 180
  wait_for_ip_initial_interval: 2.0
  wait_for_ip_backoff_enabled: true
  wait_for_ip_backoff_factor: 1.5
  wait_for_ip_max_interval: 15.0
  wait_for_ip_jitter: 0.2
  deploy: true
```

| Profile option | Default | Description |
| --- | --- | --- |
| `provider` | required | Provider name. |
| `image` | required | Local Incus image alias; import remote images first. |
| `instance_type` | `container` | `container` or `virtual-machine`. |
| `profiles` | `[default]` | Incus profiles attached at creation. |
| `config` | `{}` | Instance configuration. |
| `devices` | `{}` | Instance-local devices. |
| `location` | empty | Target cluster member. |
| `wait_for_ip_timeout` | `120` | Maximum seconds to wait for a global IPv4 address. |
| `wait_for_ip_interval` | none | Legacy alias for the initial interval. |
| `wait_for_ip_initial_interval` | provider/default | First polling interval. |
| `wait_for_ip_backoff_enabled` | provider/default | Enable exponential delay. |
| `wait_for_ip_backoff_factor` | provider/default | Polling multiplier. |
| `wait_for_ip_max_interval` | provider/default | Maximum base interval. |
| `wait_for_ip_jitter` | provider/default | Fractional random variation. |
| `deploy` | `true` | Deploy a Salt minion after obtaining an IP. |

Standard Salt Cloud deployment options such as the deploy script, SSH user,
authentication, and master address may also be set in the profile.

The image alias must already exist on the provider's Incus server. CLI remote
notation such as `images:ubuntu/24.04` is not resolved by the REST client. Use
the [Images](images.md) guide to import and maintain a local alias first.

## Query and lifecycle commands

```bash
salt-cloud -Q
salt-cloud -F
salt-cloud -S
salt-cloud --list-images my-incus
salt-cloud --list-sizes my-incus
salt-cloud --list-locations my-incus
salt-cloud -p incus-ubuntu-container application-01
salt-cloud -d application-01
```

`-Q` returns standard node summaries, `-F` returns full Incus objects, and `-S`
uses the fields in Salt's `query.selection`. Profiles are exposed as cloud
sizes, and cluster members are exposed as locations.

## Creation and IP discovery

`create` posts the image-backed instance, waits for its asynchronous operation,
starts it, and polls `/instances/<name>/state`. `_wait_for_ip` returns global
IPv4 addresses from non-loopback interfaces. A timeout does not delete the
running instance; creation returns the node with an empty private address list
and skips minion deployment.

When `deploy` is true and an address is found, the driver calls Salt Cloud's
normal Linux deployment path. Set `deploy: false` for images that already run a
configured minion or for instances managed without Salt SSH bootstrap.

## Events

Creation emits these event tags:

- `salt/cloud/<name>/creating`
- `salt/cloud/<name>/requesting`
- `salt/cloud/<name>/created`

Deletion emits `salt/cloud/<name>/destroying` and
`salt/cloud/<name>/destroyed`. The creation events contain filtered name,
profile, provider, and driver fields; deletion events contain the instance
name.

## Trust bootstrap example

```jinja
# Example: register-cloud-client.sls
salt-cloud-client:
  incus.trust_present:
    - cert_pem: {{ pillar['incus_cloud_client_certificate'] | yaml_encode }}
    - restricted: false
```

After this state succeeds through a trusted local connection, the corresponding
private key and certificate can be used by the HTTPS provider above. Revoke the
client with `incus.trust_absent` by fingerprint when it is retired.
