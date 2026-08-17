# Plan: Добавить type hints во все модули

## Проблема

В кодовой базе полностью отсутствуют аннотации типов. Современные Salt extensions
(и рекомендации сообщества) используют type hints для:

1. Ранней диагностики ошибок через `mypy` / `pyright`
2. Улучшения автодополнения в IDE
3. Самодокументирования сигнатур функций

## Объём работы

- 11 execution-модулей (`src/incus/modules/`)
- 9+ state-модулей (`src/incus/states/`)
- 1 cloud-модуль (`src/incus/clouds/`)

Приоритет: execution-модули → state-модули → cloud-модуль.

## Стандарт аннотаций для Salt-модулей

### Execution-модуль (пример)

```python
# Было:
def instance_list(recursion=0):
    ...
    return {"success": True, "instances": result.get("metadata", [])}

# Стало:
def instance_list(recursion: int = 0) -> dict[str, object]:
    ...
    return {"success": True, "instances": result.get("metadata", [])}
```

### State-модуль (пример)

```python
# Было:
def instance_present(name, source=None, instance_type="container",
                     config=None, devices=None, profiles=None, ephemeral=False):
    ...
    return ret

# Стало:
def instance_present(
    name: str,
    source: dict[str, object] | None = None,
    instance_type: str = "container",
    config: dict[str, str] | None = None,
    devices: dict[str, dict[str, str]] | None = None,
    profiles: list[str] | None = None,
    ephemeral: bool = False,
) -> dict[str, object]:
    ...
    return ret
```

### Return type для state-функций

Все state-функции возвращают один и тот же тип:

```python
from typing import TypedDict

class StateResult(TypedDict):
    name: str
    result: bool | None   # None в test-режиме
    changes: dict[str, object]
    comment: str
```

Либо упрощённо: `dict[str, object]`.

## Шаги

### 1. Добавить `mypy` в dev-зависимости

В `pyproject.toml`:
```toml
dev_extra = [
    "black==...",
    "isort==...",
    "coverage==...",
    "mypy>=1.0",   ← добавить
]
```

### 2. Настроить `mypy` в `pyproject.toml`

```toml
[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true   # Salt не имеет stubs

# Salt dunder vars не видны mypy — отключаем строгость для них
[[tool.mypy.overrides]]
module = "incus.*"
disable_error_code = ["name-defined"]  # для __salt__, __opts__, etc.
```

### 3. Аннотировать по модулям (в порядке приоритета)

#### Приоритет 1: `incus_mod.py` (IncusClient)

Ключевые методы:
```python
def _request(
    self,
    method: str,
    path: str,
    data: dict[str, object] | None = None,
    params: dict[str, object] | None = None,
) -> dict[str, object]: ...

def _sync_request(
    self,
    method: str,
    path: str,
    data: dict[str, object] | None = None,
) -> dict[str, object]: ...
```

#### Приоритет 2: `incus_instance_mod.py` (execution)

Наиболее используемый модуль — аннотировать полностью.

#### Приоритет 3: остальные execution-модули

По убыванию сложности:
- `incus_network_mod.py`
- `incus_image_mod.py`
- `incus_volume_mod.py`
- `incus_profile_mod.py`
- `incus_settings_mod.py`
- `incus_storage_pool_mod.py`
- `incus_pki_mod.py`
- `incus_cluster_mod.py`
- `incus_trust_mod.py`

#### Приоритет 4: state-модули

Все state-функции возвращают `dict[str, object]`.

### 4. Добавить проверку в CI

В `.github/workflows/` добавить mypy-проверку или добавить в `noxfile.py`:

```python
@nox.session(name="mypy")
def mypy(session):
    session.install("-e", ".[dev_extra]")
    session.run("mypy", "src/incus/")
```

### 5. Добавить pre-commit hook для mypy (опционально)

В `.pre-commit-config.yaml`:
```yaml
- repo: https://github.com/pre-commit/mirrors-mypy
  rev: v1.x.x
  hooks:
    - id: mypy
      additional_dependencies: [types-requests]
```

## Пример полностью аннотированной функции

```python
def instance_create(
    name: str,
    source: dict[str, object],
    instance_type: str = "container",
    config: dict[str, str] | None = None,
    devices: dict[str, dict[str, str]] | None = None,
    profiles: list[str] | None = None,
    ephemeral: bool = False,
    wait: bool = True,
) -> dict[str, object]:
    """
    Create an instance.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.instance_create mycontainer \
            source='{"type": "image", "alias": "ubuntu/22.04"}'
    """
    client = _client()
    body: dict[str, object] = {
        "name": name,
        "type": instance_type,
        "source": source,
        "ephemeral": ephemeral,
    }
    if config:
        body["config"] = config
    if devices:
        body["devices"] = devices
    if profiles:
        body["profiles"] = profiles
    ...
```

## Критерий готовности

- [ ] `mypy` добавлен в `dev_extra` зависимости
- [ ] `[tool.mypy]` секция добавлена в `pyproject.toml`
- [ ] `src/incus/modules/incus_mod.py` полностью аннотирован
- [ ] `src/incus/modules/incus_instance_mod.py` полностью аннотирован
- [ ] Остальные execution-модули аннотированы
- [ ] State-модули аннотированы (минимум: параметры и return type)
- [ ] `nox -e mypy` проходит без ошибок
- [ ] pre-commit hook для mypy добавлен (опционально)
