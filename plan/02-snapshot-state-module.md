# Plan: Вынести snapshot-состояния в отдельный state-модуль

**Статус: выполнен.** Snapshot state-модуль вынесен, документация добавлена,
unit-тесты проходят. План сохранён как историческое описание миграции.

## Проблема

Функции управления снапшотами (`instance_snapshot_present`, `instance_snapshot_absent`,
`instance_snapshot_restored`, `instance_snapshots_managed`) сейчас находятся в
`src/incus/states/incus_instance_mod.py`. Это нарушает принцип единственной
ответственности и затрудняет навигацию.

По аналогии с тем, как `incus_volume_mod.py` отделён от `incus_storage_pool_mod.py`,
снапшоты должны жить в своём файле.

## Текущее состояние

В `src/incus/states/incus_instance_mod.py` присутствуют:

```
# Строки 424–700+ (приблизительно)
def instance_snapshot_present(instance, name, stateful=False, description="")
def instance_snapshot_absent(instance, name)
def instance_snapshot_restored(instance, name)
def instance_snapshots_managed(instance, snapshots, ...)  # если есть
```

В `tests/functional/states/` уже есть `test_incus_snapshot.py`.
В `tests/unit/states/` **нет** `test_incus_snapshot.py`.

## Целевая структура

```
src/incus/states/
├── incus_instance_mod.py       # только lifecycle: present/absent/started/stopped/...
├── incus_instance_snapshot_mod.py  # NEW: snapshot states
├── ...

tests/unit/states/
├── test_incus_instance.py
├── test_incus_instance_snapshot.py  # NEW
```

## Шаги

### 1. Создать `src/incus/states/incus_instance_snapshot_mod.py`

Файл должен содержать стандартный заголовок:

```python
"""Salt state functions for managing Incus instance snapshots."""

import logging

log = logging.getLogger(__name__)

__virtualname__ = "incus"


def __virtual__():
    """Load when the Incus instance snapshot execution functions are available."""
    if "incus.instance_snapshot_list" in __salt__:
        return __virtualname__
    return False, "incus execution module is not available"
```

Затем перенести из `incus_instance_mod.py` блок начиная с комментария
`# Instance Snapshot States` до конца файла (или до следующего несвязанного блока).

### 2. Удалить snapshot-функции из `incus_instance_mod.py`

Удалить строки начиная с:
```python
# ======================================================================
# Instance Snapshot States
# ======================================================================
```
до конца блока снапшотов.

### 3. Обновить `docs/ref/states/index.rst`

Добавить новый модуль в список:

```rst
.. autosummary::
    :toctree:

    incus_cluster_mod
    incus_image_mod
    incus_instance_mod
    incus_instance_snapshot_mod   ← добавить
    incus_network_mod
    ...
```

### 4. Создать `docs/ref/states/incus.states.incus_instance_snapshot_mod.rst`

По аналогии с другими RST-файлами:

```rst
incus.states.incus_instance_snapshot_mod
=========================================

.. automodule:: incus.states.incus_instance_snapshot_mod
    :members:
```

### 5. Создать `tests/unit/states/test_incus_instance_snapshot.py`

Перенести/адаптировать unit-тесты снапшотов из `tests/unit/states/test_incus_instance.py`
(если они там есть) или написать новые по паттерну из `test_incus_cluster.py`.

Минимальный набор тестов:

```python
def test_virtual_loads_when_snapshot_execution_functions_available(monkeypatch): ...
def test_snapshot_present_creates_snapshot(state_runtime): ...
def test_snapshot_present_is_idempotent(state_runtime): ...
def test_snapshot_present_test_mode(state_runtime): ...
def test_snapshot_absent_deletes_snapshot(state_runtime): ...
def test_snapshot_absent_is_idempotent(state_runtime): ...
def test_snapshot_restored(state_runtime): ...
```

### 6. Убедиться что functional-тесты по-прежнему проходят

`tests/functional/states/test_incus_snapshot.py` уже существует и тестирует
функции через `states.incus.*`. После переноса между файлами эти тесты должны
продолжать работать без изменений, т.к. virtualname остался `"incus"`.

### 7. Обновить `tests/functional/data/snapshots.yml` при необходимости

Проверить, что тест-кейсы покрывают `instance_snapshot_restored`.

## Критерий готовности

- [ ] `src/incus/states/incus_instance_snapshot_mod.py` создан и содержит все snapshot-функции
- [ ] В `incus_instance_mod.py` нет блока `# Instance Snapshot States`
- [ ] `docs/ref/states/index.rst` содержит новый модуль
- [ ] `tests/unit/states/test_incus_instance_snapshot.py` создан с полным покрытием
- [ ] `pytest tests/unit/states/test_incus_instance_snapshot.py` — зелёный
- [ ] `pytest tests/functional/states/test_incus_snapshot.py` — зелёный (с Incus daemon)
