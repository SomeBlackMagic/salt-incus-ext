# Architecture

saltext-incus translates declarative Salt states and imperative Salt calls into
requests to the Incus REST API. The extension deliberately keeps transport,
resource operations, and orchestration separate.

## Request path

```text
Salt SLS / salt-call / salt-cloud
            |
            v
state module or cloud driver
            |
            v
execution module -> IncusClient -> Incus REST API
```

The three public layers have different responsibilities:

- **Execution modules** under `incus.modules` expose individual operations such
  as `incus.instance_get` and `incus.network_create`.
- **State modules** under `incus.states` compare current and desired values,
  support Salt test mode, and call execution functions only when a change is
  required.
- **The cloud driver** implements the salt-cloud create, query, deployment, and
  destroy interfaces.

Most execution and state modules share the `incus` virtual name. The PKI
modules use `incus_pki` because they have an additional `cryptography`
dependency.

## From SLS to Incus

This state first asks `incus.instance_get` for the current object. If it is
missing, the state calls `incus.instance_create`; if selected configuration,
profiles, or devices differ, it calls `incus.instance_update`.

```yaml
# Example: web-container.sls
web-01:
  incus.instance_present:
    - source:
        type: image
        alias: ubuntu-24.04
    - profiles:
        - default
    - config:
        limits.cpu: "2"
        limits.memory: 2GiB
```

With `test=True`, the state returns `result: null` and the planned `changes`
without sending the mutating request.

## Client and transport

`IncusClient` owns a `requests.Session` and supports two transports:

- `unix` mounts `UnixHTTPAdapter` for both HTTP schemes. The adapter replaces
  the normal TCP connection with an `AF_UNIX` socket while keeping an ordinary
  `http://localhost/1.0` URL for request construction.
- `https` uses the normal Requests HTTPS adapter, a client certificate/key
  pair, and either platform CA verification, a specified CA certificate, or
  explicitly disabled verification.

Unix transport ignores proxy environment variables by setting
`session.trust_env` to false. HTTPS follows Requests' normal environment
behaviour.

## Synchronous and asynchronous responses

Incus may return a completed synchronous response or an asynchronous operation
URL. `_sync_request` returns synchronous data immediately. For an asynchronous
response it polls the operation until a terminal state:

| Status code | Meaning | Client action |
| --- | --- | --- |
| `100` | Created | Continue polling |
| `101` | Started | Continue polling |
| `103` | Running | Continue polling |
| `200` | Success | Return the operation result |
| `400` | Failure | Return the operation error |

The operation timeout defaults to 300 seconds at the call site. Polling can use
a fixed delay or exponential backoff with a maximum interval and jitter. An
unknown operation status is treated as an error rather than as success.

## Configuration resolution

The execution client deep-copies `DEFAULT_CFG`, then recursively overlays the
value returned by Salt's `config.get('incus')`. Salt's normal `config.get`
resolution makes minion configuration and pillar available at this point.
Explicit dictionaries passed to `IncusClient` bypass that lookup; the cloud
driver uses this path after merging its active provider's `connection` block.

For execution modules, certificate, key, and CA values may be local paths or
`sdb://` values. Resolved SDB contents are written to temporary files because
Requests requires paths for TLS material; the client removes those files when
it closes. The cloud driver intentionally accepts local files or inline PEM but
does not resolve SDB URIs.

See [Configuration](configuration.md) for every default and [PKI and TLS](pki-guide.md)
for certificate lifecycle guidance.
