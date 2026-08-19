# Plan: Завершить integration-тесты

## Назначение

Integration-тесты запускают реальные Salt master/minion процессы и вызывают
execution-модули через `salt_call_cli`. В отличие от functional-тестов с прямой
загрузкой `Loaders`, они проверяют обнаружение extension-модулей, сериализацию
CLI-аргументов и прохождение вызова через Salt-инфраструктуру.

Набор отделён маркером `integration` от обычной Linux/Windows/macOS матрицы.
Тесты создания контейнеров дополнительно отмечены `slow`.

## Реализация

- [x] Раскомментировать и адаптировать lifecycle-тесты profiles, networks и
  instances в `tests/integration/modules/test_incus.py`.
- [x] Использовать уникальные имена ресурсов и учитывать лимит Linux IFNAMSIZ
  для bridge network.
- [x] Выполнять отдельный daemon preflight; после успешного preflight не
  преобразовывать ошибки lifecycle в `skip`.
- [x] Настроить integration minion через fixture `minion_config`.
- [x] Поддержать Unix socket и HTTPS connection.
- [x] Добавить PKI integration-сценарий для
  `incus_pki.generate_keypair`, `cert_get` и `cert_fingerprint`.
- [x] Добавить `cryptography` в test extras.
- [x] Зарегистрировать маркер `integration` и исключить его из стандартной
  nox-сессии.
- [x] Добавить nox-сессию `tests-integration`.
- [x] Добавить opt-in CI job для self-hosted Linux runner с настраиваемым
  runner label.

## Конфигурация окружения

Локальный Unix socket используется по умолчанию:

```bash
export INCUS_SOCKET=/var/lib/incus/unix.socket
```

Для HTTPS:

```bash
export INCUS_URL=https://incus.example:8443
export INCUS_CERT=/path/to/client.crt
export INCUS_KEY=/path/to/client.key
export INCUS_VERIFY=true  # false или путь к CA bundle также допустимы
```

`INCUS_CERT` и `INCUS_KEY` должны задаваться вместе.

Slow-тесты по умолчанию используют уже импортированный локальный alias
`ubuntu/22.04`. Его можно заменить:

```bash
export INCUS_TEST_IMAGE_ALIAS=alpine/3.22
```

Либо передать полный Incus API source как JSON:

```bash
export INCUS_TEST_IMAGE_SOURCE='{
  "type": "image",
  "mode": "pull",
  "server": "https://images.linuxcontainers.org",
  "protocol": "simplestreams",
  "alias": "alpine/3.22"
}'
```

`INCUS_INTEGRATION_REQUIRED=true` превращает отсутствие daemon или образа в
ошибку. Без этой переменной локальный запуск пропускает недоступную часть набора.

## Запуск

```bash
# Быстрые integration-тесты
nox -e tests-integration

# Только slow lifecycle-тесты контейнеров
nox -e tests-integration -- -m "integration and slow"

# Напрямую через pytest
pytest tests/integration -m "integration and not slow"
pytest tests/integration -m "integration and slow"
```

Обычная `nox -e tests` использует `-m "not integration"` и не требует Incus.

## CI

Integration job запускается только не для pull request и только когда repository
variable `INCUS_INTEGRATION_ENABLED=true`. Runner должен иметь доступ к daemon.

Поддерживаемые repository variables:

- `INCUS_SOCKET` — путь к socket; по умолчанию `/var/lib/incus/unix.socket`;
- `INCUS_RUNNER_LABEL` — дополнительный label Incus-capable runner, например
  `incus`;
- `INCUS_TEST_IMAGE_ALIAS` — включает slow job step и задаёт локальный alias.

Запрет запуска на pull request защищает self-hosted runner от выполнения
непроверенного кода.

## Критерии готовности

- [x] Pytest собирает 10 integration-сценариев.
- [x] Быстрый набор проходит с доступным Incus daemon.
- [x] Slow-набор проходит с доступным container image.
- [x] `nox -e tests-integration` проходит.
- [x] Обычная тестовая матрица не выполняет integration-набор.
