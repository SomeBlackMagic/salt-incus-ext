# Plan: Добавить functional-тесты для PKI и Trust модулей

## Проблема

Существующее покрытие тестами:

| Модуль               | Unit tests | Functional tests |
|----------------------|------------|------------------|
| `incus_pki_mod` (exec) | ✓ `tests/unit/modules/test_incus_pki.py` | ✗ отсутствуют |
| `incus_pki_mod` (state) | ✓ `tests/unit/states/test_incus_pki.py` | ✗ отсутствуют |
| `incus_trust_mod` (exec) | ✓ `tests/unit/modules/test_incus_trust.py` | ✗ отсутствуют |
| `incus_trust_mod` (state) | планируется (план 03) | ✗ |

Functional-тесты нужны для:
1. Проверки реального взаимодействия с Incus API
2. Гарантии, что PKI-функции работают с реальным криптографическим стеком
3. E2E проверки жизненного цикла: сгенерировать → добавить в trust store → проверить → удалить

## Целевая структура

```
tests/functional/states/
├── test_incus_pki.py      ← NEW

tests/functional/data/
├── pki.yml                ← NEW
```

## Что тестировать

### PKI execution module (`incus_pki_mod`)

Ключевые функции для тестирования:

```python
# Генерация ключевой пары
incus_pki.cert_generate(storage=None)

# Получение fingerprint существующего сертификата
incus_pki.cert_fingerprint(storage=None)

# Чтение PEM-содержимого сертификата
incus_pki.cert_get(storage=None)
```

### PKI state module (`incus_pki_mod`)

Состояния для тестирования:

```python
# Обеспечить, что клиентский сертификат существует
incus_pki.client_cert_present(name, storage=None)

# Обеспечить, что сертификат добавлен в trust store Incus
incus_pki.cert_trusted(name, storage=None)

# Обеспечить, что сертификат удалён из trust store
incus_pki.cert_untrusted(name, storage=None)
```

## Шаги

### 1. Создать `tests/functional/data/pki.yml`

```yaml
cases:
  - name: generate_client_certificate
    description: Generate a new client certificate and verify fingerprint
    requires:
      - cmd: "python3 -c 'import cryptography'"
        message: "python-cryptography is required"
    storage:
      cert: /tmp/salt-incus-test-client.crt
      key: /tmp/salt-incus-test-client.key
    cleanup_commands:
      - "rm -f /tmp/salt-incus-test-client.crt /tmp/salt-incus-test-client.key"

  - name: cert_lifecycle_with_trust_store
    description: Generate cert, add to trust store, verify, remove from trust store
    requires:
      - cmd: "python3 -c 'import cryptography'"
        message: "python-cryptography is required"
      - cmd: "test -S ${INCUS_SOCKET:-/var/lib/incus/unix.socket}"
        message: "Incus daemon is not accessible"
    storage:
      cert: /tmp/salt-incus-trust-test.crt
      key: /tmp/salt-incus-trust-test.key
    cleanup_commands:
      - "rm -f /tmp/salt-incus-trust-test.crt /tmp/salt-incus-trust-test.key"
```

### 2. Создать `tests/functional/states/test_incus_pki.py`

Файл должен следовать паттерну из `test_incus_settings.py`.

Структура тестов:

```python
import pytest
from tests.functional.conftest import check_requirements, load_yaml_cases

pytestmark = [
    pytest.mark.requires_salt_states("incus_pki"),
]


class TestPkiStateCertGeneration:
    """Tests for PKI certificate generation states."""

    def test_client_cert_present_creates_certificate(self, modules, tmp_path):
        """Generates a new cert when storage path is empty."""
        storage = {
            "cert": str(tmp_path / "client.crt"),
            "key": str(tmp_path / "client.key"),
        }
        result = modules.incus_pki.cert_generate(storage=storage)
        assert result.get("success") is True

        # Fingerprint should be retrievable
        fp_result = modules.incus_pki.cert_fingerprint(storage=storage)
        assert fp_result.get("success") is True
        assert len(fp_result.get("fingerprint", "")) > 0

    def test_client_cert_present_is_idempotent(self, states, tmp_path):
        """Second call does not regenerate an existing cert."""
        storage = {
            "cert": str(tmp_path / "client.crt"),
            "key": str(tmp_path / "client.key"),
        }
        # First call — creates
        result1 = states.incus_pki.client_cert_present(
            name="test-cert", storage=storage
        )
        assert result1.result is True
        assert result1.changes

        # Second call — no changes
        result2 = states.incus_pki.client_cert_present(
            name="test-cert", storage=storage
        )
        assert result2.result is True
        assert not result2.changes


class TestPkiStateTrustStore:
    """Tests for adding/removing certs from Incus trust store."""

    @pytest.fixture(autouse=True)
    def skip_without_incus(self):
        import os, socket as s
        sock_path = os.environ.get("INCUS_SOCKET", "/var/lib/incus/unix.socket")
        if not os.path.exists(sock_path):
            pytest.skip(f"Incus daemon not accessible at {sock_path}")

    def test_cert_trusted_adds_to_trust_store(self, states, modules, tmp_path):
        storage = {
            "cert": str(tmp_path / "client.crt"),
            "key": str(tmp_path / "client.key"),
        }
        # Generate cert first
        modules.incus_pki.cert_generate(storage=storage)

        result = states.incus_pki.cert_trusted(
            name="salt-functional-test", storage=storage
        )
        assert result.result is True

        # Cleanup
        try:
            fp = modules.incus_pki.cert_fingerprint(storage=storage)
            if fp.get("success"):
                modules.incus.trust_remove(fp["fingerprint"])
        except Exception:
            pass
```

### 3. Добавить `pytest.mark` для пропуска без реального демона

Использовать уже существующий паттерн из `conftest.py`:

```python
@pytest.fixture(autouse=True)
def require_incus_daemon():
    """Skip tests if Incus daemon is not accessible."""
    import os
    sock = os.environ.get("INCUS_SOCKET", "/var/lib/incus/unix.socket")
    if not os.path.exists(sock):
        pytest.skip(f"Incus daemon socket not found: {sock}")
```

### 4. Добавить `slow` маркер

PKI-тесты с реальным демоном помечать `@pytest.mark.slow` по аналогии с другими
functional-тестами.

### 5. Проверить что `cryptography` добавлен в тестовые зависимости

В `pyproject.toml`, секция `[project.optional-dependencies]`:

```toml
tests = [
    "pytest>=7.2.0",
    "pytest-salt-factories[docker]>=1.0.0; sys_platform != 'win32'",
    "pytest-instafail",
    "cryptography",   ← добавить, если отсутствует
]
```

## Критерий готовности

- [ ] `tests/functional/data/pki.yml` создан
- [ ] `tests/functional/states/test_incus_pki.py` создан
- [ ] Тесты без демона (cert generation) проходят: `pytest tests/functional/states/test_incus_pki.py -k "not trust_store"`
- [ ] Тесты с демоном проходят при наличии Incus: `pytest tests/functional/states/test_incus_pki.py -m slow`
- [ ] `cryptography` присутствует в тестовых зависимостях
