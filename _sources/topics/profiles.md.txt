# Profiles

Incus profiles group configuration and devices that can be applied to many
instances. Use profiles for shared policy and instance-local `config` or
`devices` for exceptions.

## Create a profile

```yaml
# Example: application-profile.sls
application:
  incus.profile_present:
    - description: Standard application workload
    - config:
        limits.cpu: "4"
        limits.memory: 4GiB
        boot.autostart: "true"
    - devices:
        eth0:
          type: nic
          name: eth0
          network: incusbr1
        root:
          type: disk
          path: /
          pool: default
```

```yaml
# Example: instance-with-profile.sls
application-01:
  incus.instance_present:
    - source:
        type: image
        alias: ubuntu-24.04
    - profiles:
        - application
```

`profile_present` reconciles requested config keys and device properties but
does not remove unspecified keys or devices. Its `description` default is an
empty string, so omit ambiguity by always declaring the intended description
or passing `description: null` when it must remain untouched.

## Update only configuration

```yaml
# Example: profile-resource-update.sls
application:
  incus.profile_config:
    - config:
        limits.cpu: "6"
        limits.memory: 8GiB
    - description: Expanded application workload
```

This state does not modify devices. Changes to a profile affect all instances
using it; some device or resource changes require an instance restart before
the guest observes them.

## Inspect, copy, and rename

```bash
salt-call incus.profile_list recursion=1
salt-call incus.profile_get application
salt-call incus.profile_copy application application-canary \
  description='Canary application workload'
salt-call incus.profile_rename application-canary application-next
```

Copy and rename are imperative execution operations. There are no matching
copy/rename states, so guard repeated orchestration calls explicitly.

## Remove a profile

```yaml
# Example: retired-profile.sls
application-old:
  incus.profile_absent: []
```

Incus refuses to remove a profile while instances still reference it. Move
those instances to replacement profiles before applying the absent state.
