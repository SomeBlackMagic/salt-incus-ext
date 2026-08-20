# Configuration

The execution modules read `incus` from Salt configuration through
`config.get`. Put the data in a minion configuration fragment, pillar, or
another source supported by Salt's configuration system.

## Complete option reference

The following table covers every field in `incus.modules.incus_mod.DEFAULT_CFG`.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `incus.connection.type` | string | `unix` | Transport: `unix` or `https`. |
| `incus.connection.socket` | string | `/var/lib/incus/unix.socket` | Incus Unix socket path. |
| `incus.connection.url` | string/null | `null` | Remote server base URL; required for HTTPS. |
| `incus.connection.cert_storage.type` | string | `local_files` | Descriptive storage type: `local_files` or `sdb`. Resolution is selected by each value's URI. |
| `incus.connection.cert_storage.cert` | string/null | `null` | Client certificate path or `sdb://` URI. |
| `incus.connection.cert_storage.key` | string/null | `null` | Client private-key path or `sdb://` URI. |
| `incus.connection.cert_storage.verify` | boolean/string | `true` | Use system CAs, disable verification, or name a CA file/SDB URI. |
| `incus.connection.polling.operation.backoff_enabled` | boolean | `false` | Enable exponential delay for async operations. |
| `incus.connection.polling.operation.initial_interval` | number | `1.0` | First operation polling delay in seconds. |
| `incus.connection.polling.operation.backoff_factor` | number | `1.5` | Operation delay multiplier. |
| `incus.connection.polling.operation.max_interval` | number | `30.0` | Maximum base operation delay. |
| `incus.connection.polling.operation.jitter` | number | `0.2` | Fractional random delay variation. |
| `incus.connection.polling.ip.backoff_enabled` | boolean | `false` | Enable exponential delay while salt-cloud waits for an IP. |
| `incus.connection.polling.ip.initial_interval` | number | `2.0` | First IP polling delay in seconds. |
| `incus.connection.polling.ip.backoff_factor` | number | `1.5` | IP polling delay multiplier. |
| `incus.connection.polling.ip.max_interval` | number | `15.0` | Maximum base IP polling delay. |
| `incus.connection.polling.ip.jitter` | number | `0.2` | Fractional random delay variation. |

The PKI module also recognises these optional values outside `DEFAULT_CFG`:

| Option | Default | Purpose |
| --- | --- | --- |
| `incus.api_client.generate.cn` | `salt-cloud` | Generated certificate common name. |
| `incus.api_client.generate.days` | `3650` | Generated certificate lifetime. |
| `incus.api_client.generate_storage` | none | Default writable `cert`/`key` storage. |
| `incus.api_client.import_storage` | none | Fallback readable `cert`/`key` storage. |
| `incus.api_client.salt_cloud_storage` | none | Fallback certificate/key for the execution client's HTTPS connection. |

## Local Unix socket

```yaml
# /etc/salt/minion.d/incus.conf
incus:
  connection:
    type: unix
    socket: /var/lib/incus/unix.socket
```

The minion account must be able to open the socket. After changing group
membership, restart the minion so it receives the new supplementary groups.

```bash
usermod -aG incus salt
systemctl restart salt-minion
salt-call incus.cluster_info
```

`incus.ping` is not exported by the current extension. `incus.cluster_info` is
a small read-only connectivity check; `incus.instance_list` is another useful
check on a non-clustered server.

## Remote HTTPS

```yaml
incus:
  connection:
    type: https
    url: https://incus.example.net:8443
    cert_storage:
      type: local_files
      cert: /etc/salt/pki/incus/client.crt
      key: /etc/salt/pki/incus/client.key
      verify: /etc/salt/pki/incus/server-ca.crt
```

Both `cert` and `key` must be set together. `verify: true` uses the normal CA
bundle, while a path uses that CA certificate. Reserve `verify: false` for a
short-lived development environment: it authenticates neither the server nor a
man-in-the-middle endpoint.

```bash
salt 'incus-client' incus.instance_list recursion=1
```

## SDB certificate storage

Configure an SDB profile using the selected backend's Salt documentation, then
refer to its values by URI. For example, a profile named `incus-vault` can back
these paths:

```yaml
incus:
  connection:
    type: https
    url: https://incus.example.net:8443
    cert_storage:
      type: sdb
      cert: sdb://incus-vault/incus/client.crt
      key: sdb://incus-vault/incus/client.key
      verify: sdb://incus-vault/incus/server-ca.crt
  api_client:
    generate_storage:
      cert: sdb://incus-vault/incus/client.crt
      key: sdb://incus-vault/incus/client.key
```

```yaml
# Example: generate-client-keypair.sls
incus-api-client:
  incus_pki.keypair_present:
    - storage:
        cert: sdb://incus-vault/incus/client.crt
        key: sdb://incus-vault/incus/client.key
    - generate:
        cn: salt-minion-incus
        days: 730
```

The execution client resolves SDB data in memory and materialises protected
temporary files for Requests. The salt-cloud driver does not support SDB URIs;
use local files on the Salt master for cloud providers.

## Polling

```yaml
incus:
  connection:
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

`jitter: 0.2` varies later delays by up to 20 percent. salt-cloud profiles may
override the IP settings with `wait_for_ip_initial_interval`,
`wait_for_ip_backoff_enabled`, `wait_for_ip_backoff_factor`,
`wait_for_ip_max_interval`, and `wait_for_ip_jitter`. The legacy
`wait_for_ip_interval` aliases the initial interval.

## Clusters and environment variables

An Incus cluster has one API endpoint from the client's perspective. Configure
one Unix socket or HTTPS URL; select the target member per salt-cloud profile
with `location`. Multiple independent servers require separate cloud providers
or separate minion targets rather than a list under one `connection` block.

The execution client has no saltext-specific environment variables. Unix mode
explicitly ignores proxy and CA environment variables. HTTPS mode uses
Requests' standard environment behaviour, including `HTTPS_PROXY`, `NO_PROXY`,
`REQUESTS_CA_BUNDLE`, and `CURL_CA_BUNDLE`; explicit connection settings remain
the clearest and most reproducible choice.
