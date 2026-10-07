# PKI and TLS

Remote Incus HTTPS connections authenticate both sides. Salt verifies the
Incus server certificate, and Incus accepts the Salt client only after the
client certificate is in its trust store. Never send the client private key to
the Incus server.

## Generate an EC P-384 keypair

The PKI execution module creates a self-signed client certificate with an EC
P-384 key, SHA-384 signature, and an unencrypted PKCS8 PEM private key. The
state is idempotent unless `force: true` is requested.

```yaml
# Example: incus-client-pki.sls
salt-incus-client:
  incus_pki.keypair_present:
    - storage:
        cert: /etc/salt/pki/incus/client.crt
        key: /etc/salt/pki/incus/client.key
    - generate:
        cn: salt-incus-client
        days: 730
```

EC P-384 gives a strong, broadly supported EC key with smaller key material
than a comparably strong RSA key. The certificate and private key are stored as
PEM. Incus identifies trust entries with the lowercase SHA-256 digest of the
certificate's DER encoding, not a digest of the PEM text.

```bash
salt-call incus_pki.cert_fingerprint \
  storage='{"cert":"/etc/salt/pki/incus/client.crt","key":"/etc/salt/pki/incus/client.key"}'
```

## Register trust

Run trust registration through a minion that already has access to Incus,
typically through the local Unix socket. The combined state generates missing
material and adds the public certificate:

```yaml
# Example: trust-local-client.sls
salt-incus-client:
  incus_pki.client_trusted:
    - storage:
        cert: /etc/salt/pki/incus/client.crt
        key: /etc/salt/pki/incus/client.key
    - generate:
        cn: salt-incus-client
        days: 730
    - restricted: false
```

For an already distributed certificate, `incus.trust_present` supports project
restrictions:

```jinja
# Example: restricted-client.sls
project-automation:
  incus.trust_present:
    - cert_pem: {{ pillar['incus_project_client_cert'] | yaml_encode }}
    - restricted: true
    - projects:
        - automation
```

Use a unique display name and the smallest useful project set. The
`incus_pki.trust_present` convenience state supports `restricted` but not a
project list; use `incus.trust_present` when project scoping is required.

## Files or SDB

Local storage writes certificates with mode `0644` and private keys with mode
`0600`; parent directories are restricted to `0700`. SDB keeps both values in a
configured secure backend such as Vault. `salt://` may be read for imports but
is read-only and cannot receive generated keys.

```yaml
# Example: Vault-backed keypair
vault-incus-client:
  incus_pki.keypair_present:
    - storage:
        cert: sdb://incus-vault/pki/client.crt
        key: sdb://incus-vault/pki/client.key
```

Limit SDB read access to the minions that initiate HTTPS connections. The cloud
driver requires local certificate files on the Salt master and rejects
`sdb://` provider values.

## Configure server verification

Prefer `verify: true` when the Incus certificate chains to a CA in the system
trust store. Otherwise set `verify` to the issuing CA certificate path or an
SDB URI containing it. A self-signed Incus server certificate can be used as
that trust anchor when appropriate.

```yaml
incus:
  connection:
    type: https
    url: https://incus.example.net:8443
    cert_storage:
      cert: /etc/salt/pki/incus/client.crt
      key: /etc/salt/pki/incus/client.key
      verify: /etc/salt/pki/incus/server-ca.crt
```

Set `verify: false` only during controlled development. It still encrypts the
connection but does not establish that Salt reached the intended server.

## Revoke or rotate a client

The generic trust state removes by fingerprint or public certificate:

```yaml
# Example: revoke-client.sls
retired-incus-client:
  incus.trust_absent:
    - fingerprint: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

When rotating, create and trust the replacement first, switch clients to the
new keypair, verify connectivity, and then revoke the old fingerprint. The PKI
convenience state `incus_pki.trust_absent` instead derives the fingerprint from
its configured certificate storage.
