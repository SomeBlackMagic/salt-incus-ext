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

1. Verify the URL and port: `curl -k https://HOST:8443/1.0`.
2. Check that the client certificate is in the trust store with
   `incus config trust list`.
3. Verify that the `verify:` setting matches the server's TLS configuration.

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
