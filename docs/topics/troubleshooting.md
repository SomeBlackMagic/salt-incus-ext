# Troubleshooting

## "incus execution module is not available"

Salt cannot find the `incus` execution module. Check that:

1. The package is installed in Salt's Python environment:

   ```bash
   salt myminion pip.show incus
   ```

2. Modules are synced:

   ```bash
   salt myminion saltutil.sync_all
   ```

## "Permission denied" on Unix socket

The Salt minion user does not have access to `/var/lib/incus/unix.socket`:

```bash
usermod -aG incus salt
systemctl restart salt-minion
```

## "Connection refused" on HTTPS

1. Verify the configured URL, DNS, and port.
2. Check that Incus listens on the expected address with `incus config get
   core.https_address` on the server.
3. Test network reachability separately from client authentication.

```bash
curl --cacert /etc/salt/pki/incus/server-ca.crt \
  https://incus.example.net:8443/1.0
```

For Unix transport, confirm the configured path exists and that the minion can
open it:

```bash
curl --unix-socket /var/lib/incus/unix.socket http://localhost/1.0
```

## "Certificate is not trusted"

The server reached the TLS client-certificate stage but did not find that
certificate's fingerprint in its trust store. Add only the public certificate
through a trusted local connection:

```jinja
# Example: trust-debug-client.sls
debug-client:
  incus.trust_present:
    - cert_pem: {{ pillar['debug_client_certificate'] | yaml_encode }}
    - restricted: false
```

Compare `incus_pki.cert_fingerprint` on the client with `incus config trust
list` on the server. Do not solve a client-trust failure by disabling server
verification; they are independent checks.

## "Timeout waiting for operation"

Image imports, copies, and storage operations may outlast the client's
operation timeout. Check the Incus daemon log and operation list before
retrying: the server-side operation may still have completed. Slow polling does
not extend the fixed deadline. Confirm storage and network throughput and avoid
launching duplicate imports under new names.

## "Instance already exists"

Use `incus.instance_present` for idempotent SLS management. Direct
`incus.instance_create` calls are imperative and return an error for an
existing name. If the state still attempts creation, run
`incus.instance_get <name>` with the same minion and connection configuration
to check project and endpoint selection.

## "No IP obtained"

The cloud driver created and started the instance but found no global IPv4
address before `wait_for_ip_timeout`.

```bash
salt-cloud -f list_nodes_full my-incus
incus list application-01
incus network list-leases incusbr0
```

Check that the attached NIC references an available network, DHCP is enabled,
the image configures its interface, and the selected cluster member can reach
that network. Increase the timeout for slow VM boots; increasing it will not
repair a missing NIC or DHCP service.

## Test mode gives the wrong diff

Run with `test=True` first to preview changes:

```bash
salt myminion state.apply mystate test=True
```

## Module not loading after install

Force a module refresh:

```bash
salt myminion saltutil.refresh_modules
salt myminion sys.doc incus
```

The `incus_pki` namespace additionally requires `cryptography` in Salt's Python
environment.

## Debug logging

Run a single call at debug level before changing daemon-wide logging:

```bash
salt-call -l debug incus.instance_get application-01
salt-cloud -l debug -Q
```

The client logs method, endpoint, operation status, and redacted server errors.
Do not publish debug logs without reviewing URLs, instance configuration, and
certificate paths for sensitive data.
