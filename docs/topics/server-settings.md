# Server settings

Server settings modify the global Incus API configuration. They can expose the
HTTPS listener, change image policy, or alter cluster behaviour, so preview
changes and apply them to a controlled target set.

## Merge selected settings

```yaml
# Example: server-settings.sls
incus-image-policy:
  incus.settings_present:
    - config:
        images.auto_update_cached: "true"
        images.auto_update_interval: "12"
        images.compression_algorithm: zstd
```

`settings_present` merges only the requested keys and preserves other server
configuration. `settings_config` is the single-key equivalent:

```yaml
# Example: enable-incus-https.sls
incus-https-listener:
  incus.settings_config:
    - key: core.https_address
    - value: "[::]:8443"
```

Enabling the listener does not configure firewall rules, server certificate
distribution, or client trust. Complete those steps before switching remote
automation to HTTPS.

## Revert a setting

```yaml
# Example: remove-trust-password.sls
remove-incus-trust-password:
  incus.settings_absent:
    - key: core.trust_password
```

Removing a key reverts it to the Incus default. The execution
`settings_unset` function reports an error for a missing key; the state is
idempotent and treats an already absent key as success.

## Exact management is destructive

:::{warning}
`incus.settings_managed` and `incus.settings_replace` replace the entire
configuration mapping. Every existing key omitted from the desired mapping is
removed. Prefer `settings_present` for normal incremental management.
:::

```yaml
# Example: exact-settings.sls
incus-exact-settings:
  incus.settings_managed:
    - config:
        core.https_address: "[::]:8443"
        images.auto_update_cached: "true"
```

Always run the exact-management state with test mode first:

```bash
salt-call state.apply server-settings.exact test=True
salt-call incus.settings_get
```

Review every `old -> null` change before applying. Sensitive values such as
`core.trust_password` are redacted from client error logging, but state output
and pillar access should still be restricted.
