# Plan: Trust state для Salt Cloud HTTPS bootstrap

## Назначение

Salt Cloud driver `src/incus/clouds/incus_mod.py` использует клиентские TLS
`cert` и `key` для подключения к удалённому Incus API. До первого HTTPS-запроса
публичный сертификат Salt Cloud должен быть зарегистрирован в trust store
Incus через локальный Unix socket или уже авторизованное соединение.

State-модуль `incus_pki` остаётся storage-oriented интерфейсом для генерации и
хранения ключевых пар. Новый `incus.trust_*` интерфейс принимает публичный PEM
напрямую, не требует передачи приватного ключа на Incus server и не зависит от
`cryptography`.

## Публичный интерфейс

```python
trust_present(name, cert_pem, restricted=False, projects=None)
trust_absent(name, fingerprint=None, cert_pem=None)
```

- Идентичность сертификата определяется по SHA-256 fingerprint DER-содержимого,
  а не по отображаемому `name`.
- `name`, `restricted` и `projects` синхронизируются через PATCH существующей
  trust-записи.
- `trust_absent` предпочитает `fingerprint` или `cert_pem`. Поиск только по
  имени разрешён лишь при единственном точном совпадении.
- Оба состояния поддерживают Salt test mode.

## Реализация

- [x] Расширить `incus.trust_add` параметром `projects`.
- [x] Добавить execution-функцию `incus.trust_update` на основе
  `PATCH /certificates/{fingerprint}`.
- [x] Создать `src/incus/states/incus_trust_mod.py`.
- [x] Проверять полный набор execution-функций в `__virtual__`.
- [x] Добавить unit-тесты execution- и state-слоёв.
- [x] Добавить functional lifecycle с уникальным сертификатом и cleanup по
  fingerprint.
- [x] Добавить HTTPS integration-сценарий, активируемый при наличии
  `INCUS_URL`.
- [x] Добавить state reference и руководство по Salt Cloud bootstrap.
- [x] Добавить changelog fragment.

## Пример

```yaml
salt-cloud-client:
  incus.trust_present:
    - cert_pem: |
        -----BEGIN CERTIFICATE-----
        ...
        -----END CERTIFICATE-----
    - restricted: false
```

После успешного применения state соответствующая пара `cert`/`key` на Salt
master может использоваться cloud provider через `connection.type: https`.

## Проверки

- [x] `pytest tests/unit/modules/test_incus_trust.py tests/unit/states/test_incus_trust.py`
- [x] `pytest tests/functional/states/test_incus_trust.py` через локальный Unix socket
- [ ] HTTPS integration-кейс выполнен в окружении с `INCUS_URL`, `INCUS_CERT`,
  `INCUS_KEY` и корректным `INCUS_VERIFY`
