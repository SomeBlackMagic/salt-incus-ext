# Images

Incus instances are created from images already available to the target Incus
server. The REST API does not resolve CLI remote notation such as
`images:ubuntu/24.04`; import the remote image first and then use a local alias.

## Import a remote image

```yaml
# Example: images/ubuntu.sls
ubuntu-24.04:
  incus.image_present:
    - source:
        server: https://images.linuxcontainers.org
        alias: ubuntu/24.04
        protocol: simplestreams
    - auto_update: true
    - properties:
        description: Managed Ubuntu 24.04 image
```

The state name becomes the primary local alias. Additional aliases can be
provided with `aliases`. Subsequent instance and cloud profiles should use
`ubuntu-24.04`, not `images:ubuntu/24.04`.

```yaml
# Example: instance-from-managed-image.sls
include:
  - images.ubuntu

application-01:
  incus.instance_present:
    - source:
        type: image
        alias: ubuntu-24.04
    - require:
        - incus: ubuntu-24.04
```

`image_present` searches by an explicit fingerprint, the state-name alias,
additional aliases, and finally the source alias. When an image already exists,
it can reconcile public/auto-update flags, aliases, properties, expiry, and
compression. The requested alias list is authoritative for that image; preview
alias changes with `test=True`.

## Import a local file

The file path is resolved on the Salt minion running the execution module.

```yaml
# Example: local-image.sls
application-base:
  incus.image_present:
    - source: /srv/incus-images/application-rootfs.tar.xz
    - public: false
    - properties:
        os: Ubuntu
        release: "24.04"
```

The execution API accepts tar archives and VM image formats supported by the
target Incus version. Local upload and image export use a 600-second HTTP
timeout.

## Inspect and manage aliases

```bash
salt-call incus.image_list recursion=1
salt-call incus.image_get <fingerprint>
salt-call incus.image_alias_list recursion=1
salt-call incus.image_alias_get ubuntu-24.04
salt-call incus.image_alias_create application-stable <fingerprint>
salt-call incus.image_alias_rename application-stable application-old
salt-call incus.image_alias_delete application-old
```

Alias execution functions are imperative. For an idempotent workflow, prefer
the `aliases` argument of `incus.image_present`.

## Copy, refresh, export, and share

```bash
salt-call incus.image_copy <fingerprint> aliases='["application-copy"]'
salt-call incus.image_refresh <fingerprint>
salt-call incus.image_export <fingerprint> target_path=/srv/backups/image.tar.gz
salt-call incus.image_secret_create <fingerprint>
```

`image_refresh` is useful only for an image retaining a remote source.
`image_secret_create` returns temporary access data for a private image; treat
it as a secret and do not place it in logs or pillar. Cross-server image copy
may additionally require the target certificate and a source secret.

## Remove an image

```yaml
# Example: retired-image.sls
application-old:
  incus.image_absent:
    - alias: application-old
```

Removing an image does not remove instances already created from it. Confirm
that no deployment workflow still uses its aliases before deletion.
