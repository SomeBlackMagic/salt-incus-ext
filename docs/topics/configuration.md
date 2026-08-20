# Configuration

## Connecting to Incus

The `incus` extension reads its connection settings from the Salt minion
configuration under the `incus:` key (or from pillar).

### Unix socket (default)

The simplest setup is used when Salt and Incus run on the same host:

```yaml
# /etc/salt/minion.d/incus.conf
incus:
  connection:
    type: unix
    socket: /var/lib/incus/unix.socket
```

The Salt minion process must have read/write access to the socket. Add the
`salt` user to the `incus` group and restart the minion:

```bash
usermod -aG incus salt
systemctl restart salt-minion
```

### HTTPS remote

Use HTTPS to manage a remote Incus host or cluster:

```yaml
incus:
  connection:
    type: https
    url: https://192.168.1.10:8443
    cert_storage:
      cert: /etc/salt/pki/incus/client.crt
      key: /etc/salt/pki/incus/client.key
      verify: true  # true | false | /path/to/ca.crt
```

Generate the client certificate using the `incus_pki` execution module:

```bash
salt myminion incus_pki.generate_keypair
```

Then add it to the Incus trust store on the target host.

### Pillar override

Connection settings can also be stored in pillar:

```yaml
# pillar/incus.sls
incus:
  connection:
    type: unix
    socket: /var/lib/incus/unix.socket
```

### Polling backoff

Polling keeps its fixed legacy intervals by default. Enable exponential
backoff independently for asynchronous operations and IP address discovery:

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

`jitter` is a fractional variation. For example, `0.2` varies an interval by
up to 20 percent in either direction. `max_interval` limits the base interval;
jitter is applied after that limit.

An Incus cloud profile can override IP polling settings with
`wait_for_ip_initial_interval`, `wait_for_ip_backoff_enabled`,
`wait_for_ip_backoff_factor`, `wait_for_ip_max_interval`, and
`wait_for_ip_jitter`. The existing `wait_for_ip_interval` setting remains
supported as a legacy alias for `wait_for_ip_initial_interval`.

## SDB-based certificate storage

Certificates and keys can be stored in Salt's SDB (Secure Data Backend)
instead of the filesystem. Pass `storage` with SDB URIs:

```bash
salt myminion incus_pki.generate_keypair \
  storage='{"cert": "sdb://incus/client.crt", "key": "sdb://incus/client.key"}'
```
