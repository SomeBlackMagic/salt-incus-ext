# Plan: Раскомментировать и завершить integration-тесты

## Проблема

Файл `tests/integration/modules/test_incus.py` содержит полноценный набор тестов
(~350 строк), но **весь код закомментирован**. Integration-тесты принципиально
отличаются от functional:

| Аспект | Functional | Integration |
|--------|-----------|-------------|
| Запускают Salt-процессы | Нет, используют `Loaders` напрямую | Да, через `salt_call_cli` |
| Требуют полный minion | Нет | Да |
| Проверяют | Логику модулей | Интеграцию с Salt-инфраструктурой |
| CI-матрица | Всегда | При наличии Incus daemon |

## Текущее состояние закомментированного кода

Тесты хорошо написаны и покрывают:
- `TestProfiles` — lifecycle (create/get/update/rename/delete), copy
- `TestNetworks` — lifecycle (create/get/delete)
- `TestInstances` — lifecycle (start/stop), snapshot lifecycle, update config

## Причина комментирования

Вероятно, тесты были закомментированы при миграции кода из formula, т.к. требовали
адаптации под текущую инфраструктуру проекта.

## Шаги

### 1. Создать `tests/integration/conftest.py` с нужными fixtures

Файл `tests/integration/conftest.py` существует но пустой. Нужно добавить fixtures
по образцу functional `conftest.py`, но для `salt_call_cli`:

```python
import os
import pytest


@pytest.fixture(scope="session")
def salt_minion_config_overrides():
    """Configure Incus connection for integration tests."""
    incus_url = os.environ.get("INCUS_URL")
    if incus_url:
        return {
            "incus": {
                "connection": {
                    "type": "https",
                    "url": incus_url,
                    "cert_storage": {
                        "cert": os.environ.get("INCUS_CERT"),
                        "key": os.environ.get("INCUS_KEY"),
                        "verify": os.environ.get("INCUS_VERIFY", "true"),
                    },
                }
            }
        }
    return {
        "incus": {
            "connection": {
                "type": "unix",
                "socket": os.environ.get("INCUS_SOCKET", "/var/lib/incus/unix.socket"),
            }
        }
    }
```

### 2. Раскомментировать `tests/integration/modules/test_incus.py`

Снять комментарии (`# `) со всего содержимого файла. Адаптировать если нужно:

**Проверить и исправить:**
- `pytestmark` — убедиться, что правильные требования указаны
- `_ok()` helper — убедиться что работает с текущей структурой ответов (`{"success": True, ...}`)
- Fixtures `incus_profile`, `incus_network`, `incus_container` — проверить именa функций execution-модуля
- `TEST_IMAGE_ALIAS = "images:ubuntu/22.04"` — убедиться что образ доступен или параметризовать через env

**Пример адаптации fixture:**
```python
@pytest.fixture
def incus_container(salt_call_cli):
    ret = salt_call_cli.run(
        "incus.instance_create",
        TEST_CONTAINER_NAME,
        source={"type": "image", "alias": TEST_IMAGE_ALIAS},
        instance_type="container",
    )
    _ok(ret)
    yield TEST_CONTAINER_NAME
    salt_call_cli.run("incus.instance_stop", TEST_CONTAINER_NAME, force=True)
    salt_call_cli.run("incus.instance_delete", TEST_CONTAINER_NAME)
```

### 3. Создать `tests/integration/modules/test_incus_pki.py`

Пока закомментированный код не покрывает PKI. Добавить:

```python
"""Integration tests for incus_pki execution module."""

import os
import pytest

pytestmark = [
    pytest.mark.requires_salt_modules("incus_pki.cert_generate"),
]


class TestPkiIntegration:
    def test_cert_generate_and_fingerprint(self, salt_call_cli, tmp_path):
        storage = {
            "cert": str(tmp_path / "client.crt"),
            "key": str(tmp_path / "client.key"),
        }
        ret = salt_call_cli.run("incus_pki.cert_generate", storage=storage)
        assert ret.returncode == 0
        assert ret.data.get("success") is True

        ret = salt_call_cli.run("incus_pki.cert_fingerprint", storage=storage)
        assert ret.returncode == 0
        assert len(ret.data.get("fingerprint", "")) > 0
```

### 4. Добавить `slow` маркер к медленным тестам

В `pyproject.toml` маркер `slow` уже описан. Убедиться, что тесты создания
контейнера помечены:

```python
@pytest.mark.slow
def test_instance_lifecycle(self, salt_call_cli, incus_container):
    ...
```

### 5. Добавить integration-тесты в CI-матрицу

В `.github/workflows/test-action.yml` добавить отдельный job или параметр
для запуска integration-тестов при наличии Incus:

```yaml
- name: Run integration tests
  if: env.INCUS_SOCKET != ''
  run: |
    nox -e tests-integration
  env:
    INCUS_SOCKET: ${{ secrets.INCUS_SOCKET }}
```

### 6. Добавить nox-сессию `tests-integration` в `noxfile.py`

Проверить наличие и добавить если отсутствует:

```python
@nox.session(name="tests-integration")
def tests_integration(session):
    session.install("-e", ".[tests]")
    session.run(
        "pytest",
        "tests/integration/",
        "-v",
        "--tb=short",
        "-m", "not slow",
        *session.posargs,
    )
```

## Требования к среде для запуска

```bash
# Минимальная среда:
export INCUS_SOCKET=/var/lib/incus/unix.socket

# Или для HTTPS:
export INCUS_URL=https://myhost:8443
export INCUS_CERT=/path/to/client.crt
export INCUS_KEY=/path/to/client.key

# Запуск:
pytest tests/integration/ -v -m "not slow"
pytest tests/integration/ -v -m slow  # медленные тесты с созданием контейнеров
```

## Критерий готовности

- [ ] `tests/integration/modules/test_incus.py` раскомментирован и адаптирован
- [ ] `tests/integration/conftest.py` содержит нужные fixtures
- [ ] `tests/integration/modules/test_incus_pki.py` создан
- [ ] Быстрые integration-тесты проходят: `pytest tests/integration/ -m "not slow"`
- [ ] Медленные тесты проходят при наличии образа: `pytest tests/integration/ -m slow`
- [ ] `nox -e tests-integration` работает
