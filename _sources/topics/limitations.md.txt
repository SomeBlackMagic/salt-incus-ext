# Known limitations

The following boundaries describe the current implementation rather than all
capabilities of Incus itself.

## Projects

The client does not expose a project parameter or a global project setting.
Resource requests therefore use the server's default project. Restricted trust
certificates may list projects, but the saltext cannot currently select one of
those projects for an operation.

## Cluster targeting

The cloud driver supports `location` during instance creation. The execution
`instance_create` function and instance states do not expose a cluster-member
target. Migration and evacuation have no dedicated execution or state API.

## Cloud IP discovery

Salt Cloud waits only for global IPv4 addresses. IPv6-only instances may start
successfully but return no address and skip Salt-minion deployment. A timeout
leaves the created instance running for diagnosis; it does not roll back.

## Timeouts and retries

Normal REST requests use a fixed 30-second HTTP timeout. Image upload/export
uses 600 seconds. Asynchronous operations normally wait up to 300 seconds.
Polling intervals and backoff are configurable, but these operation and HTTP
deadlines are not global configuration options.

## TLS storage

Execution modules can resolve local paths and `sdb://` certificate material.
The cloud driver accepts local paths or inline PEM and rejects SDB URIs. It must
run where the private-key files are available.

## Incomplete high-level workflows

There is no dedicated state for instance migration, instance publication
without a snapshot, image alias rename/copy, profile rename/copy, volume move,
or storage export. The corresponding execution function can be used where it
exists, but repeated orchestration must add its own existence checks.

Volume export is not implemented. Image export is implemented. Instance
freeze/unfreeze actions are not exposed.

## Reconciliation scope

Most `present` states reconcile only explicitly supplied fields and preserve
unspecified configuration. They are not complete authoritative replacements.
The notable exception is `settings_managed`, which deliberately replaces all
server configuration and removes omitted keys.
