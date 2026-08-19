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

## SDB-based certificate storage

Certificates and keys can be stored in Salt's SDB (Secure Data Backend)
instead of the filesystem. Pass `storage` with SDB URIs:

```bash
salt myminion incus_pki.generate_keypair \
  storage='{"cert": "sdb://incus/client.crt", "key": "sdb://incus/client.key"}'
```
