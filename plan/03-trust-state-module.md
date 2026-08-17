# Plan: Создать state-модуль для trust management

## Проблема

Execution-модуль `src/incus/modules/incus_trust_mod.py` существует и предоставляет:
- `trust_list` — список доверенных сертификатов
- `trust_get` — получить сертификат по fingerprint
- `trust_add` — добавить сертификат в trust store
- `trust_remove` — удалить сертификат по fingerprint

**State-модуль отсутствует**. Пользователь не может описать желаемое состояние trust
в SLS-файле — только вызывать execution-функции напрямую.

## Целевая структура

```
src/incus/states/
├── incus_trust_mod.py   ← NEW

tests/unit/states/
├── test_incus_trust.py  ← NEW (unit/modules уже есть)

tests/functional/states/
├── test_incus_trust.py  ← NEW (functional/states)

tests/functional/data/
├── trust.yml            ← NEW (YAML test cases)

docs/ref/states/
├── incus.states.incus_trust_mod.rst  ← NEW
```

## Функции state-модуля

### `trust_present(name, cert_pem, restricted=False)`

Обеспечить, что сертификат (идентифицируемый по `name`) присутствует в trust store.

**Логика:**
1. Вызвать `incus.trust_list()` — получить список.
2. Найти сертификат с совпадающим `name`.
3. Если найден — вернуть без изменений (idempotent).
4. Если не найден — вызвать `incus.trust_add(cert_pem, name, restricted)`.
5. Поддержать `test`-режим.

```yaml
# Пример SLS:
salt-master-cert:
  incus.trust_present:
    - cert_pem: |
        -----BEGIN CERTIFICATE-----
        ...
        -----END CERTIFICATE-----
    - restricted: false
```

### `trust_absent(name)`

Обеспечить, что сертификат с данным `name` отсутствует в trust store.

**Логика:**
1. Вызвать `incus.trust_list(recursion=1)`.
2. Найти сертификат с совпадающим `name`, получить его `fingerprint`.
3. Если не найден — вернуть без изменений.
4. Если найден — вызвать `incus.trust_remove(fingerprint)`.

```yaml
old-salt-master:
  incus.trust_absent: []
```

## Шаги

### 1. Создать `src/incus/states/incus_trust_mod.py`

```python
"""Salt state functions for managing Incus trust store (client certificates)."""

__virtualname__ = "incus"


def __virtual__():
    """Load when the Incus trust execution functions are available."""
    if "incus.trust_list" in __salt__:
        return __virtualname__
    return False, "incus execution module is not available"


def trust_present(name, cert_pem, restricted=False):
    """
    Ensure a client certificate is present in the Incus trust store.

    :param name: Certificate name (used for identification)
    :param cert_pem: PEM-encoded certificate string
    :param restricted: Whether to restrict the certificate

    Example:

    .. code-block:: yaml

        salt-master-cert:
          incus.trust_present:
            - cert_pem: |
                -----BEGIN CERTIFICATE-----
                ...
                -----END CERTIFICATE-----
            - restricted: false
    """
    ...


def trust_absent(name):
    """
    Ensure a client certificate is absent from the Incus trust store.

    :param name: Certificate name to remove

    Example:

    .. code-block:: yaml

        old-salt-master:
          incus.trust_absent: []
    """
    ...
```

### 2. Добавить модуль в `docs/ref/states/index.rst`

```rst
    incus_trust_mod
```

### 3. Создать `docs/ref/states/incus.states.incus_trust_mod.rst`

```rst
incus.states.incus_trust_mod
============================

.. automodule:: incus.states.incus_trust_mod
    :members:
```

### 4. Создать `tests/unit/states/test_incus_trust.py`

По паттерну из `tests/unit/states/test_incus_cluster.py`.

Минимальный набор:

```python
def test_virtual_loads(): ...
def test_virtual_rejects_missing_functions(): ...

def test_trust_present_is_idempotent(): ...
def test_trust_present_adds_certificate(): ...
def test_trust_present_test_mode(): ...
def test_trust_present_reports_list_error(): ...
def test_trust_present_reports_add_error(): ...

def test_trust_absent_is_idempotent(): ...
def test_trust_absent_removes_certificate(): ...
def test_trust_absent_test_mode(): ...
def test_trust_absent_reports_list_error(): ...
def test_trust_absent_reports_remove_error(): ...
```

### 5. Создать `tests/functional/data/trust.yml`

```yaml
cases:
  - name: add_and_remove_certificate
    description: Add a self-signed certificate to the trust store and remove it
    setup: []
    cleanup: []
```

### 6. Создать `tests/functional/states/test_incus_trust.py`

По паттерну из `tests/functional/states/test_incus_profile.py`.

## Важные нюансы

### Идентификация сертификата

`trust_list(recursion=1)` возвращает объекты вида:
```json
{
  "name": "salt-master",
  "fingerprint": "abc123...",
  "type": "client",
  ...
}
```

Идентифицируем по полю `name`. Это позволяет сделать состояние idempotent
без хранения fingerprint.

### Сравнение для idempotency

Для `trust_present`: проверяем только наличие сертификата с данным `name`.
Изменение `restricted` или замена `cert_pem` — это отдельный вопрос (update).
В v1 можно не поддерживать update (только add/remove).

## Критерий готовности

- [ ] `src/incus/states/incus_trust_mod.py` создан с `trust_present` и `trust_absent`
- [ ] `docs/ref/states/index.rst` обновлён
- [ ] `docs/ref/states/incus.states.incus_trust_mod.rst` создан
- [ ] `tests/unit/states/test_incus_trust.py` — зелёный
- [ ] `tests/functional/states/test_incus_trust.py` — зелёный (с Incus daemon)
