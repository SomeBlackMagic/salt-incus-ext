# Plan: Документация — руководства, примеры SLS, troubleshooting

## Проблема

Текущее состояние документации:
- `docs/topics/installation.md` — есть, базовый
- `docs/index.rst` — ссылается только на installation и API reference
- API reference (autosummary) — есть, но только docstrings из кода
- **Нет**: конфигурационного руководства, примеров SLS, troubleshooting

Без документации пользователи не могут:
1. Понять, как настроить подключение (Unix socket vs HTTPS)
2. Найти примеры реального использования в SLS
3. Диагностировать типичные проблемы

## Целевая структура документации

```
docs/
├── index.rst                        ← обновить toctree
├── topics/
│   ├── installation.md              ← существует, дополнить
│   ├── configuration.md             ← NEW: подключение к Incus
│   ├── quickstart.md                ← NEW: первые шаги с примерами SLS
│   └── troubleshooting.md           ← NEW: типичные проблемы
├── ref/
│   ├── modules/index.rst            ← существует
│   └── states/index.rst             ← существует
```

## Шаги

### 1. Создать `docs/topics/configuration.md`

**Содержание:**

```markdown
# Configuration

## Connecting to Incus

The `incus` extension reads its connection settings from the Salt minion
configuration under the `incus:` key (or from pillar).

### Unix socket (default)

The simplest setup — used when Salt and Incus run on the same host:

    # /etc/salt/minion.d/incus.conf
    incus:
      connection:
        type: unix
        socket: /var/lib/incus/unix.socket

The Salt minion process must have read/write access to the socket.
Add the `salt` user to the `incus` group:

    usermod -aG incus salt

### HTTPS remote

For managing a remote Incus host or cluster:

    incus:
      connection:
        type: https
        url: https://192.168.1.10:8443
        cert_storage:
          cert: /etc/salt/pki/incus/client.crt
          key: /etc/salt/pki/incus/client.key
          verify: true        # true | false | /path/to/ca.crt

Generate the client certificate using the `incus_pki` module:

    salt myminion incus_pki.cert_generate

Then add it to the Incus trust store on the target host.

### Pillar override

Connection settings can also be stored in pillar:

    # pillar/incus.sls
    incus:
      connection:
        type: unix
        socket: /var/lib/incus/unix.socket

## SDB-based certificate storage

Certificates and keys can be stored in Salt's SDB (Secure Data Backend)
instead of the filesystem. Pass `storage` with SDB URIs:

    salt myminion incus_pki.cert_generate \
      storage='{"cert": "sdb://incus/client.crt", "key": "sdb://incus/client.key"}'
```

### 2. Создать `docs/topics/quickstart.md`

**Содержание:**

```markdown
# Quickstart

## Prerequisites

- Incus installed and running on the target host
- Salt minion configured to connect (see [Configuration](configuration.md))

## Managing instances

### Ensure a container exists

    mycontainer:
      incus.instance_present:
        - source:
            type: image
            alias: images:ubuntu/22.04
        - config:
            limits.cpu: "2"
            limits.memory: 2GiB
        - profiles:
            - default
        - instance_type: container

### Start/stop instances

    mycontainer:
      incus.instance_started: []

    mycontainer:
      incus.instance_stopped:
        - force: True

## Managing networks

    mybr0:
      incus.network_present:
        - network_type: bridge
        - config:
            ipv4.address: 10.0.100.1/24
            ipv4.nat: "true"
            ipv6.address: none

## Managing storage pools

    default-pool:
      incus.storage_pool_present:
        - driver: dir
        - config:
            source: /var/lib/incus/storage-pools/default

## Managing profiles

    webserver-profile:
      incus.profile_present:
        - config:
            limits.cpu: "4"
            limits.memory: 4GiB
        - devices:
            eth0:
              name: eth0
              network: mybr0
              type: nic

## Snapshot management

    mycontainer/before-update:
      incus.instance_snapshot_present:
        - instance: mycontainer
        - name: before-update
        - description: Snapshot before apt upgrade

## PKI / TLS certificates

### Generate and trust a client certificate

    generate-incus-client-cert:
      incus_pki.client_cert_present:
        - name: salt-master
        - storage:
            cert: /etc/salt/pki/incus/client.crt
            key: /etc/salt/pki/incus/client.key

    trust-incus-client-cert:
      incus_pki.cert_trusted:
        - name: salt-master
        - storage:
            cert: /etc/salt/pki/incus/client.crt
            key: /etc/salt/pki/incus/client.key
        - require:
            - incus_pki: generate-incus-client-cert
```

### 3. Создать `docs/topics/troubleshooting.md`

**Содержание:**

```markdown
# Troubleshooting

## "incus execution module is not available"

Salt cannot find the `incus` execution module. Check:

1. The package is installed in Salt's Python environment:

       salt myminion pip.show incus

2. Modules are synced:

       salt myminion saltutil.sync_all

## "Permission denied" on Unix socket

The Salt minion user doesn't have access to `/var/lib/incus/unix.socket`:

    usermod -aG incus salt
    systemctl restart salt-minion

## "Connection refused" on HTTPS

1. Verify the URL and port: `curl -k https://HOST:8443/1.0`
2. Check the client certificate is in the trust store:
   `incus config trust list`
3. Verify `verify:` setting matches the server's TLS configuration.

## Test mode gives wrong diff

Run with `test=True` first to preview changes:

    salt myminion state.apply mystate test=True

## Module not loading after install

Force a module sync:

    salt myminion saltutil.refresh_modules
    salt myminion sys.doc incus
```

### 4. Обновить `docs/index.rst`

Добавить новые guides в toctree:

```rst
.. toctree::
  :maxdepth: 2
  :caption: Guides
  :hidden:

  topics/installation
  topics/configuration   ← добавить
  topics/quickstart      ← добавить
  topics/troubleshooting ← добавить
```

### 5. Дополнить `docs/topics/installation.md`

Добавить раздел про зависимости для HTTPS-режима:

```markdown
## Optional dependencies

For HTTPS connections with TLS certificate management:

    pip install cryptography

This is required for the `incus_pki` module.
```

### 6. Добавить ref для cloud-модуля в `docs/index.rst`

```rst
.. toctree::
  :maxdepth: 2
  :caption: Provided Modules
  :hidden:

  ref/modules/index
  ref/states/index
  ref/clouds/index    ← добавить если отсутствует
```

## Критерий готовности

- [ ] `docs/topics/configuration.md` создан (Unix socket, HTTPS, SDB)
- [ ] `docs/topics/quickstart.md` создан (примеры для instance, network, profile, snapshot, PKI)
- [ ] `docs/topics/troubleshooting.md` создан (типичные ошибки и решения)
- [ ] `docs/index.rst` ссылается на все новые страницы
- [ ] `make -C docs html` не выдаёт ошибок (только warnings допустимы)
- [ ] Sphinx spell-check проходит для новых файлов
