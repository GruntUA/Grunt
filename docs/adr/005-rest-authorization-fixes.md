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

---

## Доповнення: той самий метод за межами `api/v1/` (2026-08-19, того ж дня)

Той самий "прочитати все поспіль" підхід застосовано ще у двох місцях: (A)
doctype-колоковані `@grunt.whitelist(...)`-методи в самому grunt (7 файлів,
поза `api/v1/`, тому не покриті вище) і (B) whitelisted-методи/роути в усіх
застосунках монорепо, побудованих на grunt (`hrm`, `tsnap`, `car_ua`,
`letter`, `ua_tools` — `inventory`/`cms` без жодного, пропущені). 2 паралельні
Explore-агенти, з явною інструкцією звіряти doctype-контролер
(`before_insert`/`before_save`) перед тим, як позначати щось діркою — саме
той урок, що коштував відкоченого фіксу в `share.py` вище.

**(A) grunt doctypes/ — чисто.** Усі 7 файлів (`ActivityLog`, `AssignmentLog`,
`AssignmentRule`, `User`, `GruntInstalledApp`, `File`, `auth/user_utils.py`)
прочитано повністю, жодної реальної дірки. Побічно підтверджено важливий
факт про архітектуру: `write_guard`/`read_guard` — це лише **грубий**,
doctype-рівневий гейт (без конкретного doc — `match`-вирази типу
`"owner == user"` там пропускаються); **рядковий** enforcement того самого
`match` відбувається окремо, вже всередині `update_document`/`delete_document`
(`document/mixins/write.py`), коли реальний документ уже на руках. Тобто
`grunt.save_doc`/`delete_doc`/`new_doc` дають подвійний захист (грубий +
рядковий), а не один шар, що виглядає неповним.

**(B) Сестринські застосунки — 1 реальна діра, 2 "міни уповільненої дії".**

- **`tsnap/tsnap/api.py: find_applicant` — реальна, exploitable.** Пошук по
  `Applicant` через сирий `grunt.db.get_all(...)` (без прав) замість
  `grunt.get_list`. `Applicant.json` має **справжні** обмежувальні права
  (лише `System Manager`/`Реєстратор ЦНАП`/`Адміністратор ЦНАП`/`Керівник
  ЦНАП`, без `"All"`). Будь-який автентифікований користувач сайту — **з
  будь-якого застосунку на тому самому логіні**, не лише tsnap — міг
  дістати РНОКПП (податковий номер), ЄДРПОУ, телефон і email будь-якого
  заявника за 3+ символами запиту. **Фікс:** `await read_guard("Applicant")`
  перед запитом — `grunt.get_list` не годився напряму, бо ендпоінт потребує
  `or_filters` (пошук по 4 полях одразу), якого немає на рівні
  `get_list`-фасаду.
- **`hrm/hrm/api.py` — 7 функцій, 7 сирих `grunt.db.get_all` викликів на
  `Department`/`Employee`/`Position`/`DepartmentPosition` (ЗП, надбавки,
  ПІБ, email).** Наразі НЕ exploitable — усі відповідні doctype мають
  `permissions: None` (за конвенцією фреймворку — відкрито для будь-кого
  залогіненого), тож guarded-шлях віддав би те саме. Але це стає живою
  дірою в момент, коли хтось додасть `DocTypePermission` для `Employee`
  (цілком імовірно для зарплатних даних) — і ніхто про це не згадає, бо
  код "уже працював". Замінено всі 7 на `grunt.get_list` (прямий заміняч,
  жоден виклик не використовував `or_filters`).
- **`car_ua/.../start_import.py: reset_status`** — той самий патерн, що
  Знахідка 4 в ADR 005: `grunt.db.set_value` (без прав) замість
  `grunt.set_value`. `RegistryImport.json` теж без `permissions` — не
  exploitable сьогодні, та сама "міна". Замінено обидва виклики.

**Тести:** жоден з трьох застосунків (`tsnap`, `hrm`, `car_ua`) не має
тестової інфраструктури з БД/контекстом — `car_ua` має лише чисті unit-тести
без фікстур, `tsnap`/`hrm` не мають тестів узагалі. Регресійні тести не
додано — фікси звірено напряму читанням коду проти реальних `*.json`
permissions, не покрито автоматично. Якщо ці застосунки почнуть отримувати
активну розробку — налаштування test harness (за зразком
`apps/grunt/conftest.py`) варте окремого заходу.

**Синтаксис:** `py_compile` + ізольований `ruff check` на всіх трьох
змінених файлах — чисто (2 попередження в `car_ua`/`hrm` — `except
Exception`/`try-except-pass` — не мої рядки, поза межами цього заходу).

## Доповнення 2: test harness для tsnap/hrm/car_ua (2026-08-19, того ж дня)

Заплановане вище "варте окремого заходу" зроблено того ж дня.

**Новий `grunt/testkit.py`** — переносний pytest-плагін-модуль (не
`conftest.py`, щоб уникнути подвійного імпорту, той самий урок, що й
`tests/support.py`). Один виклик `make_app_fixtures(app_dir, app_name)`
будує повний набір fixture'ів (`setup_db`, `db_session`, `engine`, `ctx`,
`client`) — той самий движок, що й у `apps/grunt/tests/conftest.py`
(single-engine SQLite, SA_METADATA bootstrap/teardown), плюс:
- завантажує doctype JSON застосунку (`{app}/{module}/doctypes/`, модулі —
  з `app.json`) поруч із core-doctype'ами grunt, а не замість них;
- ставить `app_dir` на `sys.path` **при виклику conftest** (не всередині
  fixture) — тестові модулі імпортуються під час collection, до першого
  fixture, тож `from car_ua.services... import ...` на рівні модуля
  інакше падав би;
- викликає `document_registry.index_external_app_controllers(app_dir)`, щоб
  ледачий контролер-резолвер (`get_doc(Class, id)` тощо) working для
  doctype'ів застосунку так само, як для core;
- `setup_db` навмисно **не** `autouse` (на відміну від grunt-own conftest):
  теки тестів застосунків змішують DB-тести з чистими sync unit-тестами
  (`car_ua`'s `test_registry_import_parsing.py`), і pytest-asyncio жорстко
  падає, коли sync-тест отримує autouse async fixture. Підтягується
  транзитивно через `db_session`/`engine`/`ctx`/`client` — запитуй один із
  них у тестах, яким потрібна БД.

Кожен застосунок отримав дволанковий `tests/conftest.py`
(`globals().update(make_app_fixtures(Path(__file__).parent.parent, "<app>"))`)
і `pytest.ini`/`[tool.pytest.ini_options]` з `asyncio_mode = "auto"`
(`car_ua`, `tsnap` — новий `pytest.ini`; `hrm` — додано в наявний
`pyproject.toml`) — узгоджено з конвенцією grunt, щоб не треба було
`@pytest.mark.asyncio` на кожному тесті вручну (хоча `testkit.py`'s fixture
все одно явно `pytest_asyncio.fixture`, а не голий `@pytest.fixture`, —
робить незалежним від того, чи застосунок сам налаштував asyncio_mode).

**Знахідка під час перевірки harness (не баг цього заходу, довідково):**
`DocumentWriteMixin._resolve_dt()` (`document/mixins/write.py:73`)
безумовно робить `doctype_registry._lazy_load(doctype_name)` на кожен
`new_doc`/`save_doc` — "форсований lazy-reload" для live-picked-up змін
схеми. `_lazy_load` резолвить сайт через
`site_manager.get_active_site()` → фолбек на `sites/currentsite.txt` →
реальний dev-сайт (`dev2.itmlt.win`), **ігноруючи** сесію/engine, встановлені
через `grunt.context(...)` у тесті. Перевірено емпірично (traceback-трасування
через тимчасовий monkey-patch): це лише `SELECT` (best-effort, `try/except
Exception: return None`), без записів — і це поведінка, що вже існує в
**усьому** наявному grunt-тестовому наборі (будь-який тест з `new_doc`/
`save_doc` вже це робить), не щось нове від `testkit.py`. Тому нові
регресійні тести нижче навмисно побудовані на `write_guard`-шляху
(`grunt.set_value`/`grunt.get_list`/`read_guard`), який іде через
безпечний `doctype_registry.get()`, а не `new_doc`/`save_doc` — щоб не
покладатись на доступність реального сайту в CI. Вартий окремого фіксу
колись (передавати активний контекст у `_resolve_dt`, а не завжди йти через
`site_manager`), але поза обсягом цього заходу.

**Регресійні тести (усі нові, усі проходять):**
- `apps/tsnap/tests/test_applicant_search_permissions.py` (3) — `find_applicant`:
  403 без ролі, `{"items": [...]}`  з роллю "Реєстратор ЦНАП", і що
  short-circuit на запиті <3 символів не оминає guard для реального пошуку.
- `apps/hrm/tests/test_department_list_permissions.py` (2) — `get_first_level_departments`:
  оскільки `Department.json` сьогодні без `permissions` (guard відкритий
  для всіх), фікстура тимчасово вішає `DocTypePermission` на вже
  завантажений у registry doctype, щоб довести, що ендпоінт реально піде
  через `read_guard`, щойно права з'являться — а не мовчки їх ігноруватиме,
  як робив сирий `grunt.db.get_all`.
- `apps/car_ua/tests/test_reset_status_permissions.py` (2) — `reset_status`:
  та сама тактика тимчасових прав на `RegistryImport`, плюс реальний "застряглий"
  рядок (`grunt.db.insert_one`, повз lifecycle hooks — свідомо, щоб не
  чіпати `_resolve_dt`) зі статусом "Виконується"; юзер лише з `read`
  дістає 403 на `write_guard`, юзер з `write` — `{"ok": True}`.

**Перевірка:** `pytest apps/{car_ua,tsnap,hrm}/tests/` — 49+3+2=54 passed
(49 = 47 наявних чистих unit-тестів `car_ua` без жодної регресії + 2 нових).
Повний grunt-own набір (`pytest tests/ grunt/`) — і далі 841 passed, без
жодного впливу від `testkit.py`.
