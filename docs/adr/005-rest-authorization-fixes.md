# ADR 005: Авторизаційні дірки в REST-шарі — знайдено й закрито

## Статус

Прийнято — 2026-08-19

---

## Контекст

Побічний продукт ADR 004: після mass-migration Phase 1 користувач попросив
проінвентаризувати **весь** `grunt/api/v1/` (96 ендпоінтів поза Phase 1) —
чи лишились кандидати на `roles=`/`find_doc`. Відповідь виявилась
негативною (0 нових кандидатів — Phase 1 справді покрив усе), але сам
прохід по всьому REST-шару заразом підсвітив шість речей, що **не мають
стосунку до API v2 примітивів взагалі** — реальні прогалини в авторизації
та один мертвий-код баг, знайдені лише тому, що хтось нарешті прочитав усі
файли поспіль.

Дослідження: 4 паралельні Explore-агенти, кожен покрив свій кластер
`api/v1/`. Два з них незалежно хибно позначили `except A, B:` (без дужок,
PEP 758, Python 3.14) як Python 2 баг — не так, репо на 3.14, це коректний
синтаксис. Відкинуто без змін коду.

---

## Знахідка 1: `docs/tree.py` — жодної перевірки прав узагалі

`get_tree`/`get_children`/`get_ancestors`/`move_node` (усі 4 ендпоінти)
викликали `tree_service.*` напряму з сирою сесією — ні `read_guard`, ні
`write_guard`, ні жодного виклику `permission_checker` ніде в самому
`document/tree.py` теж. Єдиний бар'єр — "залогінений" (`Depends(current_user)`
на рівні роутера). Будь-який автентифікований користувач міг читати й
переставляти tree-дані **будь-якого** doctype, незалежно від
`DocTypePermission`.

**Фікс:** `await read_guard(doctype)` на трьох read-ендпоінтах,
`await write_guard(doctype, "write")` на `move_node` — ті самі helper'и, що
скрізь інде в кодовій базі (`grunt/permissions/guards.py`).

**Тест:** `TreeCategory` (наявна фікстура) не годиться для доведення —
у неї взагалі немає `permissions`, а "немає permissions = відкрито" це
навмисна конвенція фреймворку. Додано `GuardedTreeCategory` з реальними
restrictive permissions (`role: TreeManager`) — 6 нових тестів у
`tests/test_tree_api.py`, deny/allow пара на кожен з 4 ендпоінтів (crunched
до 6, бо read/write розділено лише для `move_node`).

---

## Знахідка 2: `notifications.py` — без перевірки власності

`mark_as_read(notification_id)` робив `grunt.db.set_value(...)` напряму —
жодної перевірки, що сповіщення належить викликачу. Будь-який
автентифікований користувач міг позначити прочитаним **чуже** сповіщення
(id — не секрет, легко перебрати). Той самий присмак у
`unsubscribe_push(endpoint)` → `webpush_service.remove_subscription(endpoint)`
— видаляло підписку по `endpoint` без прив'язки до власника.

**Фікс:**
- `mark_as_read` — замість `db.set_value(id, ...)` тепер
  `grunt.db.bulk_update(filters={"name": id, "user": user.email}, ...)` —
  update матчиться лише якщо notification належить викликачу; повертає
  `bool`, чи щось реально оновилось (раніше завжди `True`).
- `webpush_service.remove_subscription(endpoint, user)` — новий обов'язковий
  параметр `user`, фільтр звужено до `{"endpoint": ..., "user": user}`.
  Єдиний caller (`unsubscribe_push`) оновлено.

**Тест:** `tests/test_notifications_ownership.py`, 3 тести — чуже
сповіщення не чіпається, своє оновлюється, чужа push-підписка не видаляється.

---

## Знахідка 3: `share.py: create_share` — **хибна тривога, вже виправлено**

Аудит-агент побачив відсутність read-перевірки перед створенням публічного
share-посилання й позначив як дірку. Виявилось — вже закрито, і краще, ніж
я збирався зробити: `DocumentShare.before_insert()`
(`grunt/document/doctypes/DocumentShare/document_share.py`) робить
`await grunt.get_doc(target_doctype, target_id)` на рівні **контролера**, не
лише в `create_share()` — тобто захищає й generic docs CRUD шлях
(`POST /api/v1/docs/DocumentShare`), не тільки whitelisted RPC. З докстрінга
контролера й наявного `tests/test_document_share_permissions.py` видно, що
це свідоме рішення з поясненням, чому саме тут, а не в `create_share()`.

Я спершу додав перевірку і в `create_share()` теж — зрозумів, що це дубль
одразу після прочитання контролера, відкотив. **Урок:** аудит агентів
дивився лише на endpoint-функції, не на doctype-контролери — для
`DocumentShare`-подібних кейсів (де реальний захист живе в
`before_insert`/`before_save` хуках) це дає хибні спрацювання. Наступного
разу перевіряти контролер доктайпу, а не лише виклик-сайт.

---

## Знахідка 4: `workflow.py: apply_transition` — обхід `write_guard`

Зміна стану документа йшла через `grunt.db.set_value(...)` — низькорівневий,
без перевірки прав виклик (задокументовано як такий у `grunt-app.md`).
Єдиний гейт — `read_guard` на початковому `get_doc` плюс workflow-специфічний
`allowed_roles`/`condition` на самому переході. Якщо конкретний перехід не
мав `allowed_roles` (типовий випадок — три з чотирьох переходів у наявних
тестах саме такі), користувач з правом лише на читання міг усе одно
протягнути документ через workflow, повністю оминаючи право на запис
доктайпу.

**Фікс:** один рядок — `grunt.db.set_value` → `grunt.set_value` (без
`.db`). Різниця: `grunt.set_value` (app-фасад) вже викликає
`write_guard(doctype, "write")` перед записом; `grunt.db.set_value` — ні.
Перевикористано наявний примітив, нової логіки не написано.

**Тест:** `test_apply_transition_requires_write_permission` у
`grunt/metadata/doctypes/DocType/tests/test_workflow.py` — новий doctype з
реальними permissions і transition без `allowed_roles`; read-only роль
отримує 403, write-роль проходить.

---

## Знахідка 5: `api_keys.py: list_api_keys` — мертвий код

```python
filters: dict[str, Any] = {"user_id": user.id}
if not user.is_superadmin:
    filters["user_id"] = user.id   # та сама умова, той самий результат
```

Обидві гілки ставили однакове значення — суперадмін ніколи не бачив чужих
ключів, хоча докстрінг ("Non-superadmins can only see their own keys")
явно натякає, що мав. Не дірка безпеки (звужує, не розширює доступ), а
зламана фіча.

**Фікс:** `filters = {}`, і лише в `not is_superadmin`-гілці додається
`user_id`.

**Тест:** `tests/test_api_keys_listing.py` — 2 тести. Обидва fake-користувачі
потребували ролі `"System Manager"` (реальний permission на `ApiKey.json`,
не сам баг) лише щоб пройти `read_guard` і дістатись до тестованої логіки.

---

## Знахідка 6: `method.py:84-86` — консистентність помилок

Сирий `HTTPException(403, detail=...)` для "метод не whitelisted" замість
`grunt.errors.forbidden()`, яким користується решта RBAC-шляху
(`permission_checker.require`, `whitelist(roles=)`-обгортка). Не баг — обидва
дають 403 — але інший JSON-конверт помилки (без `code`/`details`, яких
клієнт міг би очікувати). Вирівняно однорядковою заміною.

---

## Наслідки

| Знахідка | Файл(и) | Тип | Тестів |
|---|---|---|---|
| 1. Tree — без перевірки прав | `api/v1/docs/tree.py` | Авторизація | 6 нових |
| 2. Notifications — без ownership | `api/v1/notifications.py`, `webpush/service.py` | Авторизація | 3 нових |
| 3. Share create — вже було виправлено | — (хибна тривога) | — | наявні 2 пройшли |
| 4. Workflow — обхід write_guard | `workflow/engine.py` | Авторизація | 1 новий |
| 5. API keys listing — мертвий код | `api/v1/auth/api_keys.py` | Баг (не безпека) | 2 нових |
| 6. method.py — консистентність | `api/v1/method.py` | Стиль | — |

Результат: `ruff check grunt/` чистий, `pytest tests/ grunt/` — **837/837**
(12 нових regression-тестів, кожен напряму доводить конкретну знахідку),
`mypy grunt --ignore-missing-imports` — 56 помилок, без змін від ADR 004.

**Ширший висновок:** REST-шар вартий періодичного повного проходу — не по
одному doctype за раз (як `test_sensitive_doctype_permissions.py`,
`test_public_read_admin_write_doctypes.py` роблять для окремих doctype), а
по всьому `api/v1/` заразом. Три з п'яти реальних знахідок (tree, workflow,
api_keys) існували незалежно від будь-якого з цьогорічних рефакторингів —
не регресії, а давні прогалини, які просто ніхто не читав поспіль.
