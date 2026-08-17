# Plan: Аудит `__virtualname__` и `__func_alias__` во всех модулях

## Проблема

Все state-модули используют `__virtualname__ = "incus"`, кроме `incus_pki_mod.py`
(`__virtualname__ = "incus_pki"`). Нужно убедиться, что:

1. Паттерн мёрджа функций из нескольких файлов в одно пространство имён работает корректно.
2. `__func_alias__` добавлен там, где имя функции конфликтует с Python-зарезервированными
   словами или требует альтернативного имени в SLS.
3. Все execution-модули также последовательны.

## Текущее состояние

### State-модули (`src/incus/states/`)

| Файл                      | `__virtualname__` | `__func_alias__` | `__virtual__()` проверяет |
|---------------------------|-------------------|-------------------|---------------------------|
| `incus_cluster_mod.py`    | `"incus"`         | отсутствует       | `incus.cluster_member_list` in `__salt__` |
| `incus_image_mod.py`      | `"incus"`         | отсутствует       | `incus.image_list` in `__salt__` |
| `incus_instance_mod.py`   | `"incus"`         | отсутствует       | `incus.instance_list` in `__salt__` |
| `incus_network_mod.py`    | `"incus"`         | отсутствует       | проверить |
| `incus_pki_mod.py`        | `"incus_pki"`     | отсутствует       | `incus_pki.cert_get` in `__salt__` |
| `incus_profile_mod.py`    | `"incus"`         | отсутствует       | проверить |
| `incus_settings_mod.py`   | `"incus"`         | отсутствует       | проверить |
| `incus_storage_pool_mod.py` | `"incus"`       | отсутствует       | проверить |
| `incus_volume_mod.py`     | `"incus"`         | отсутствует       | проверить |

### Execution-модули (`src/incus/modules/`)

Все используют `__virtualname__ = "incus"`, кроме `incus_pki_mod.py` (`"incus_pki"`).

## Стандарт Salt для этого паттерна

Из документации Salt и исходников (`salt/loader.py`):

- Несколько файлов с одинаковым `__virtualname__` **мёрджатся** в один модуль.
  Это легитимный паттерн для разбивки большого модуля на файлы.
- Порядок: если два файла экспортируют **одинаковую функцию**, побеждает тот,
  что загружен позже (алфавитный порядок файлов).
- `__func_alias__` нужен, если имя Python-функции ≠ желаемое имя в Salt.
  Например: `__func_alias__ = {"present_": "present"}` если функция названа
  `present_` (из-за конфликта с ключевым словом).

## Шаги

### 1. Верифицировать отсутствие конфликтов имён функций

Проверить, что ни один файл не объявляет функцию с тем же именем, что другой файл
в том же пространстве имён:

```bash
grep -h "^def " src/incus/states/incus_cluster_mod.py \
                 src/incus/states/incus_image_mod.py \
                 src/incus/states/incus_instance_mod.py \
                 src/incus/states/incus_network_mod.py \
                 src/incus/states/incus_profile_mod.py \
                 src/incus/states/incus_settings_mod.py \
                 src/incus/states/incus_storage_pool_mod.py \
                 src/incus/states/incus_volume_mod.py \
  | sort | uniq -d
```

Ожидаемый результат: пустой вывод (нет дублей).

### 2. Верифицировать, что `__virtual__()` каждого state-модуля проверяет именно свои функции

**Стандарт:** `__virtual__()` должен проверять наличие execution-функции из
**того же домена**, не общей `incus.instance_list` для всех.

Текущий пример (`incus_cluster_mod.py`) — корректный:
```python
def __virtual__():
    if "incus.cluster_member_list" in __salt__:
        return __virtualname__
    return False, "incus cluster execution functions are not available"
```

Проверить остальные файлы по тому же паттерну. Каждый файл должен проверять
свою "ключевую" функцию, а не чужую.

### 3. Добавить `__func_alias__` только при реальной необходимости

В текущей кодовой базе функции не используют зарезервированные Python-имена,
поэтому `__func_alias__` **не требуется** и добавлять его не надо.

Если в будущем появится функция `from_` или `import_` — добавить алиас:
```python
__func_alias__ = {
    "from_": "from",
}
```

### 4. Зафиксировать паттерн в CONTRIBUTING или docs

Добавить раздел в `docs/topics/contributing.md` (создать если нет):

```markdown
## Module naming convention

All execution and state modules under the `incus` namespace share
`__virtualname__ = "incus"`. Salt merges them at load time.
The exception is `incus_pki_mod`, which requires the `cryptography`
package and therefore lives in its own `incus_pki` namespace.
```

## Критерий готовности

- [ ] `grep -h "^def "` не возвращает дублей имён функций среди state-модулей с `__virtualname__ = "incus"`
- [ ] Каждый state-модуль проверяет в `__virtual__()` свои execution-функции
- [ ] Нет лишних `__func_alias__` добавленных без причины
- [ ] Паттерн задокументирован в `docs/topics/`
