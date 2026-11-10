# Циклічні імпорти ядра — план

Живий план. Оновлюється після кожного кроку: що зроблено, що далі, які рішення прийняті.
Новий чат з Claude починає звідси.

**Рішення власника (2026-11-09):** доводимо ядро до справжнього DAG імпортів — 0 алертів
`py/unsafe-cyclic-import` і 0 `py/cyclic-import`, включно з циклом через фасад `grunt/__init__`.
Виключення запитів CodeQL не розглядаємо: алерт = неправильно розкладені залежності.

Оновлено: 2026-11-10 — кроки 0–1 злито (#120), 2a злито (#121); 2b (email замість об'єкта) — PR #122.

---

## Стан на старті (develop, 251da7a1)

- CodeQL: **594** алерти — 536 `py/unsafe-cyclic-import` (error, валять PR) і 58
  `py/cyclic-import` (recommendation) у ~130 модулях.
- Власний граф (`grunt.utils.import_graph`, усі імпорти): 637 модулів, 2090 ребер,
  **187 модулів у циклах**: одна компонента на 179 модулів + три малі.
- Без ребер до пакетів (як рахує CodeQL) велика компонента — 105 модулів; евристика
  feedback-arc-set — ~48 ребер розрізати. З фасадом — ~78.

## Як рахує CodeQL (перевірено на тестовому проєкті)

| Імпорт | `unsafe-cyclic-import` | `cyclic-import` |
|---|---|---|
| рівня модуля | так | так |
| `lazy from …` (PEP 810) | **так** — для CodeQL це звичайний імпорт | так |
| `if TYPE_CHECKING:` | **так** | так |
| усередині функції | ні | **так** |
| пакет (`from grunt import x`, `__init__`) | ні | ні |

Звідси: ні `lazy`, ні `TYPE_CHECKING`, ні імпорт у функції цикл не прибирають — лише
змінюють, як його класифікує CodeQL. Тому ціль — DAG усіх імпортів.

## Інструменти

- **Тест-храповик** `tests/test_import_cycles.py` + `tests/import_cycles_baseline.txt` —
  модулі, що ще в циклі. Новий модуль у циклі → тест падає й показує найкоротший цикл з
  номерами рядків; модуль, що вийшов з циклів, треба викреслити. Список лише скорочується.
  Рахує всі імпорти (функції, `TYPE_CHECKING`, `lazy`) і ребра до пакетів.
- **Граф** `grunt/utils/import_graph.py` — `build(root, "grunt")`, `.cycles()`; без
  залежностей, нічого не імпортує.
- **CodeQL локально** (лише для звірки з CI): бандл 2.27.4 у
  `~/.local/share/codeql-v2.27.4/`; `cycles.sh [repo] [work]` будує базу з файлів git (без
  `.venv`/`node_modules`) і рахує обидва запити; `graph.py` — прототип аналізу (`--no-pkg`
  як CodeQL, `--all`, `--hubs N`, `--fas`, `--packages`).

## Правила розплутування

1. **Лист знизу.** Модуль, від якого залежать багато інших, не імпортує нічого «вище» за
   себе. Спільне виносимо в листовий модуль без залежностей від grunt (`search/tokens.py`,
   `tasks/repeat_schedule.py`, `auth/providers/declarations.py`).
2. **Реєстр не знає реалізацій.** Реалізації оголошуються в `hooks.py` рядком шляху
   (споживач у `grunt.apps.consumers`), реєстр імпортує їх під час першого звернення.
3. **Без дублікатів сутностей.** Нижчий шар не заводить «свою версію» класу вищого
   (протокол-копію полів) — він оперує значеннями: користувач нижче auth — це email і
   ролі, як у Frappe. Протокол — лише для опису DocType (`permissions.access.Target`).
4. **Реакція — подією.** Коли нижчий шар має «повідомити» вищий (документ → workflow,
   websocket), нижчий публікує подію / викликає зареєстрований обробник.
5. Імпорт у функцію, `lazy`, `TYPE_CHECKING`, реекспорт через `__init__` — **не**
   виправлення.
6. Сумісність внутрішніх шляхів не зберігаємо (DB_LAYERS_PLAN): переносимо — правимо
   виклики, без реекспортів «щоб старе працювало».

## Цільові шари (знизу вгору)

```
0  листи: errors, log, i18n (каталоги), config, version, auth.constants, utils.*,
   search.tokens
1  контекст: local (користувач — `session_user()` email і `session_roles()`), site.manager,
   site.settings, cache.bus, db.commit
2  метадані: metadata.compiler / store / registry, document.meta
3  дані: db, store, query
4  права: permissions.*
5  документ: document.base + mixins (без імпорту api/ws/workflow — через події)
6  сервіси: auth (User, users, login), workflow, notification, storage, email, search.service…
7  вхідні точки: api/v1, website, apps.loader / consumers, main, cli
—  фасад grunt/__init__ і grunt.app — лише для коду додатків; ядро його не імпортує
```

## Кроки

| # | Що | Стан |
|---|---|---|
| 0 | Тест-храповик, граф, локальний CodeQL, цей план | у PR |
| 1 | Малі цикли: auth.providers ↔ registry, dialects.fulltext ↔ search.terms, standard_records ↔ startup.fixtures, tasks.auto_repeat ↔ AutoRepeat | у PR |
| 2 | Користувач за моделлю Frappe: нижче auth — email і ролі (`get_roles`), `Document.user` — email сесії, API прав `check(doctype, action, doc, *, user=None)`; документ `User` — лише `grunt.get_user()` | 2a злито (#121); 2b — PR #122 |
| 3 | Контекстний шар-лист: `site.manager` без `db.profiler`/`monitoring.perf`, `site.settings`, `cache.bus`, `db.commit` | |
| 4 | Метадані: `document.meta` ↔ `metadata.compiler` ↔ `metadata.registry` ↔ `search.service` | |
| 5 | Права всередині: `rbac` ↔ `query` ↔ `child` ↔ `shares` ↔ `user_permissions` ↔ `reference` | |
| 6 | Документ: `document.base` ↔ mixins ↔ `collection` / `queryset` / `registry`; mixins без `api.v1.ws`, `workflow`, `website` — через події | |
| 7 | Auth-сервіси: `User` ↔ `users` ↔ `user_api` (прибрати реекспорти внизу `user.py`), `login`, `service`, `UserSession` | |
| 8 | Решта: storage (`files` ↔ `images` ↔ `tasks`, `cloud.*`), monitoring (`health` ↔ `updates`), workflow (`engine` ↔ `notify` ↔ `events`), `apps.loader` ↔ `consumers` ↔ `website.router`, `progress` → `ws` | |
| 9 | Фасад: ядро не імпортує `grunt` (`_`, `log`, `grunt.db`, `throw`, `whitelist`…) — прямі імпорти з модулів; правило в ruff/тесті; `grunt/__init__` лінивий | |
| 10 | Храповик рахує й неявні імпорти батьківських пакетів; базовий список порожній; CodeQL локально і в CI — 0 | |

Кожен крок — окремий PR у `develop`; великий крок ділиться (ліміт CodeRabbit 100 файлів).

## Рішення

- **2026-11-09** Ціль — справжній DAG разом із фасадом (власник). Імпорт у функцію не
  вважається виправленням.
- **2026-11-09** Захист від регресій — власний тест на `ast`, а не CodeQL: працює в pytest
  без 2 ГБ бандла, рахує суворіше (функції, пакети).
- **2026-11-10** Користувач — за моделлю Frappe (власник: протокол `Identity` дублював
  `User`, відкинуто). Нижче auth користувач — email: `local.session_user()`,
  `permissions.roles.get_roles(user=None)` / `has_roles(roles, *, user=None)` (поточний — з
  контексту, системний і гість — константи, інші — `UserRole` через рядок `User` за email).
  Документ `User` — лише `grunt.get_user()` (метод фасаду, `app.context_api`).
- **2026-11-10** API прав як `frappe.has_permission`: `permission_checker.check / require(
  doctype, action, doc=None, *, user=None)`, `await hidden_fields(doctype, *, user=None)`;
  `user` — email, `None` — поточний. `RoleAccess(doctype, email, roles)`, ролі підтягує
  `roles.role_access()`; протокол `Principal` прибрано. Сумісність не зберігаємо, додатки — потім.
- **2026-11-10** `Document` не тримає користувача: `doc.user` — email користувача сесії, життєвий
  цикл діє від імені контексту (як у Frappe); `user=` прибрано з конструктора,
  `load_document` / `new_document`. Події (`fire`, `doc_events`) передають `user` = email.
- **2026-11-10** `grunt.context(session, engine, user)` приймає й email — фасад сам дістає
  документ (`get_auth_context_user`, кеш), як `frappe.set_user`. `SYSTEM_USER` — документ у
  контролері; нижче auth: `system_context(...)` і `SYSTEM_USER_EMAIL`.
- **2026-11-10** Параметри whitelisted-методів, що мають бути лише для Python (`create_api_key(
  user=...)`), анотуються `User` — диспетчер відхиляє їх з HTTP (підробка через JSON).
- **2026-11-09** Провайдери входу — хук `auth_providers` у `hooks.py` (шляхи класів); старі
  `register_provider(s)()` прибрано. `registry.register()` лишився для готових екземплярів.

## Журнал

### 2026-11-09 — кроки 0–1

- `grunt/utils/import_graph.py`, `tests/test_import_cycles.py`, базовий список (187 → 178).
- **auth.providers:** реєстр більше не імпортує провайдерів, провайдери — реєстр. Вбудовані
  оголошено в `core_hooks.auth_providers`; новий споживач хука пише в лист
  `providers/declarations.py`, реєстр імпортує класи під час першого звернення. Документація:
  `docs/guide/auth-providers.md`, таблиця хуків у `docs/guide/create-app.md`.
- **search:** розбиття запиту й рендерери FTS5 / tsquery / MySQL — у листі
  `search/tokens.py`; `terms` лишився SQL-хелперами над діалектами.
- **fixtures:** запис фікстур (`apply_doctype_fixture` і помічники) переїхав із
  `startup/fixtures.py` у `grunt/fixtures.py` поруч з експортом.
- **auto_repeat:** арифметика розкладу — лист `tasks/repeat_schedule.py`.
- Лишається на кроці 2: `providers.base` тягне `User` лише заради анотацій.

### 2026-11-10 — крок 2: користувач за моделлю Frappe

Розбито на два PR через ліміт CodeRabbit: 2a — ролі за email (`get_roles` / `has_roles`,
`User.has_role`), `grunt.get_user` на фасаді, тестові хелпери `tests/support.py`;
2b — email замість об'єкта в правах, `Document` і подіях.

Перша версія (протокол `Identity`) відкинута — дублювала `User`. Подивились Frappe:
`frappe.session.user` — рядок, `get_roles(user)`, `has_permission(..., user=None)`,
`Document` без користувача. Зроблено так само.

- `local`: `session_user()`, `require_session_user()`, `session_roles()`; `require_user` прибрано.
- `permissions.roles`: `get_roles`, `has_roles`, `role_access`; `user_has_roles` прибрано — код із
  документом користується `User.has_role(*roles)`. `permissions.*` — email замість об'єкта.
- `rbac`: новий порядок аргументів (`user=` в кінці), `hidden_fields` асинхронний.
- `Document.user` → властивість (email сесії); `_set_grunt_context()` перев'язує лише
  сесію/рушій. Ручні анотації поля `user` (ErrorLog, WebAuthnCredential) — коментар, як
  у генератора.
- `get_user()` — метод `ContextAPI` (`grunt.get_user`); `api.context.get_user/set_user` прибрано.
- Знайдено pyright-невидимі місця (через `Any` / `getattr`), що мовчки ламалися б від email
  замість об'єкта: ключ кешу запитів (ролі й email → порожні — змішав би видачу різних
  користувачів), ролі переходів workflow, автор коментаря для підписників, автор ToDo,
  `entered_by` у milestones, підпис файлів, маска SMTP-пароля, масове видалення. Усі —
  через `get_roles` / email.
- `User.name` не завжди email (ім'я можна задати) — ролі інших користувачів шукаються через
  рядок `User` за email.
- `page_visible(page, roles)`; онбординг передає ролі явно (працює під `system_context`).
- Тести: `tests/support.py` — `acting_as`, `check_as`, `require_as`, `hidden_fields_as`,
  `read_predicate_as`, `access_of`; виклики переписано через AST.
- Skill `grunt-dev` (`references/hooks.md`, обидві копії): `user` в обробнику — email.
- Результат: 2240 passed, pyright 0. CodeQL локально 590 → 325 (у представленні CodeQL
  велика компонента 105 → 57 модулів). Базовий список 178: `permissions.roles` повернуто
  (був на develop; тримає фасад — крок 9).
- Додатки не оновлено (рішення власника — спершу фреймворк): ламаються виклики
  `permission_checker.check(user, …)`, `user_has_roles`, `Document(..., user=)`,
  хуки з `user.email`.
