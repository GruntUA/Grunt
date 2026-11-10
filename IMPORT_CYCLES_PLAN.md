# Циклічні імпорти ядра — план

Живий план. Оновлюється після кожного кроку: що зроблено, що далі, які рішення прийняті.
Новий чат з Claude починає звідси.

**Рішення власника (2026-11-09):** доводимо ядро до справжнього DAG імпортів — 0 алертів
`py/unsafe-cyclic-import` і 0 `py/cyclic-import`, включно з циклом через фасад `grunt/__init__`.
Виключення запитів CodeQL не розглядаємо: алерт = неправильно розкладені залежності.

Оновлено: 2026-11-10 — кроки 0–6b-1 злито (#120–#127); 6b-2 (`base` ↔ `registry` / `schema` / `queryset`) — у PR.

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
   search.tokens, site.bench, db.dialects (+ archive)
1  контекст: local (користувач — `session_user()` email і `session_roles()`), site.manager,
   cache.bus, db.commit
2  метадані: metadata.compiler / store / registry, document.meta
3  дані: db, store, query, site.settings (рядок SystemSettings — через метадані)
4  права: permissions.*
5  документ: document.base + mixins (без імпорту api/ws/workflow — через події)
6  сервіси: auth (User, users, login), workflow, notification, storage, email, search.service…
7  вхідні точки: api/v1, website, apps.loader / consumers, main, cli
—  фасад grunt/__init__ і grunt.app — лише для коду додатків; ядро його не імпортує
```

## Кроки

| # | Що | Стан |
|---|---|---|
| 0 | Тест-храповик, граф, локальний CodeQL, цей план | злито (#120) |
| 1 | Малі цикли: auth.providers ↔ registry, dialects.fulltext ↔ search.terms, standard_records ↔ startup.fixtures, tasks.auto_repeat ↔ AutoRepeat | злито (#120) |
| 2 | Користувач за моделлю Frappe: нижче auth — email і ролі (`get_roles`), `Document.user` — email сесії, API прав `check(doctype, action, doc, *, user=None)`; документ `User` — лише `grunt.get_user()` | злито (#121, #122) |
| 3 | Контекстний шар-лист: `site.manager` без `db.profiler`/`monitoring.perf`, `site.settings`, `cache.bus`, `db.commit` | злито (#123) |
| 4 | Метадані: `document.meta` ↔ `metadata.compiler` ↔ `metadata.registry` ↔ `search.service` | злито (#124) |
| 5 | Права всередині: `rbac` ↔ `query` ↔ `child` ↔ `shares` ↔ `user_permissions` ↔ `reference` | злито (#125) |
| 6 | Документ: `document.base` ↔ mixins ↔ `collection` / `queryset` / `registry`; mixins без `api.v1.ws`, `workflow`, `website` — через події | 6a злито (#126); 6b-1 злито (#127); 6b-2 (`base` ↔ `registry` / `schema` / `queryset`) — у PR; 6b-3 (mixins → сервіси вище — через події) — далі |
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

### 2026-11-10 — крок 3: контекстний шар

- `local`, `site.manager`, `cache.bus`, `db.commit` — поза циклами; разом з ними `i18n`,
  діалекти й ще 15 модулів. Базовий список 178 → 156.
- **site.manager → perf / profiler:** `site_manager.on_engine(setup)` — налаштування рушія
  застосовується до наявних і нових; `monitoring.perf` (лічильник SQL) і `db.profiler` (якщо
  `sql_profiler_enabled`) реєструються самі. Менеджер не знає реалізацій.
- **dialects → backups:** `BackupError`, рівні стиснення, `zstd_options` — у листі
  `db/dialects/archive.py`; `backups`, `cli`, тести імпортують звідти. `current_dialect()`
  (не використовувався, тягнув фасад) прибрано.
- **i18n → site.manager:** тека bench — лист `site/bench.py`; `SiteManager.bench_dir` —
  властивість над ним (заміна в тестах діє). Джерело опцій мов `grunt.i18n.language` реєструє
  `metadata.dynamic_options` (i18n не знає метаданих).
- **`language_of`** — з `i18n.service` у `auth/language.py`, шукає за email (не за
  `User.name`). Модуль додано в базовий список: читає через `grunt.db.api`, а той у циклі через
  `store.sql → document.update_side_effects → activity.follow` — вийде на кроках 5–6. Функція й
  раніше сиділа в циклі (у `i18n.service`).
- **cache.bus:** асинхронний обробник отримує сесію й рушій сайту через `grunt.local`, без
  фасаду й без користувача.
- **site.settings:** читає рядок `SystemSettings` напряму з таблиці (`doctype_registry` +
  сесія) — налаштування нижче запитів і прав, які їх читають. Переїхав у шар даних; у циклі
  через `metadata.registry → grunt` (кроки 4, 9).
- Результат: 2250 passed, pyright 0; CodeQL локально 325 → 311, нових 0.

### 2026-11-10 — крок 4: метадані

- `metadata.compiler / registry / store`, `document.meta`, `search.service`, `db.schema.apply`,
  `site.settings` — поза циклами (разом 11 модулів). Базовий список 156 → 145.
- **compiler → registry:** ключ сайту для кешів (`_resolve_site_key`) — `site_cache_key()` у
  `site.manager`; `compiler` більше не імпортує реєстр.
- **registry → search.service:** реєстр кличе обробники `on_doctype_updated(session, doctype,
  previous)`; пошуковий індекс підписується сам (`search.service._follow_doctype_update`).
- **registry, db.schema.apply, compiler → фасад:** `_` / `log` — з `grunt.i18n` / `grunt.log`.
- Результат: 2253 passed, pyright 0; CodeQL локально 311 → 295, нових 0.

### 2026-11-10 — крок 5: права всередині

- **Рекурсія `rbac ↔ query ↔ child ↔ reference`.** Доступ справді рекурсивний (дочірній рядок —
  за батьком, коментар — за документом), тому `child.py` і `reference.py` злито в
  `permissions/query.py` разом із тілом перевірки (`query.allowed`). `rbac.permission_checker` —
  тонке API над ним (`check` → `allowed`, `require` з 403, `hidden_fields`).
- **`query.run` без прав.** Читання від імені користувача (предикат прав, приховані поля, 403 на
  фільтр за прихованим полем) — новий `permissions/reads.py` (`fetch / count / page / aggregate(
  query, *, user=email)`). `query.run.*` — лише з `ignore_permissions=True` (обов'язковий
  keyword, `Literal[True]`); явність «чиїми правами читаємо» збережено сигнатурами.
- **Без фасаду** в `permissions.*`, `query.run`, `query.sql`, `store.base / sql`, `db.api`:
  `doctype_registry.get_meta`, `local.require_session`, `GruntDB()` з `grunt.db.api`, `whitelist`
  з `grunt.api.context`, `_` / `log` напряму.
- Базовий список 145 → 141 (`child` / `reference` злито; `match`, `query.sql`, `store.base` поза
  циклами). `permissions/reads.py` додано в список — код переїхав із `query.run`, що й так був у
  циклі. Права, `query.run`, `store`, `db.api` лишаються в циклі через `store → document.registry`
  і `store.sql → document.update_side_effects / aggregate` — крок 6.
- Результат: 2257 passed, pyright 0; CodeQL локально 295 → 285, нових 0.

### 2026-11-10 — крок 6a: шар даних поза циклами

Крок 6 поділено: 6a — сховище, запити, `db.*` і права виходять із циклу; 6b — сам документ.

- **store → document.registry:** `store_class` бере контролер через `use_controllers(lookup)`;
  `document.registry` реєструє `document_registry.get` сам. Пошук сховища (`store_for`,
  `store_class`, `supports`) — модуль `store/lookup.py`; `store.virtual` бере з нього сховище
  цільового DocType для Link-вузла (замість `query.run`).
- **store.sql → document.update_side_effects:** `delete_child_rows` і `delete_row_and_links` —
  операції над таблицями — переїхали в `store.sql`.
- **db.session → api.context:** контекст сесії/рушія — напряму через `grunt.local`;
  `clear_context()` — у `grunt.local`. Новий `local.bound_session(session, engine)` — сесія без
  користувача для службової роботи (`cache.bus`, запис метрик у `monitoring.perf`).
- **Без фасаду:** `db.errors`, `document.aggregate`, `monitoring.perf`, `document.registry`.
- Базовий список 141 → 121 (−20): `store*`, `query.run`, `db.*`, усі `permissions.*`,
  `api.context`, `monitoring.perf`; обидва винятки (`auth.language`, `permissions.reads`) теж
  вийшли.
- Результат: 2257 passed, pyright 0; CodeQL локально 285 → 285, нових 0 (його алерти тримає
  велика компонента через фасад і документ — 6b, 9).

### 2026-11-10 — крок 6b-1: документ без низькорівневого фасаду

- `throw` — з `api.messages` (тягне email і сповіщення) у `grunt.errors` (шар 0); фасад і
  `auth.*` імпортують звідти.
- У `grunt/document/**` низькорівневі звернення до фасаду замінено прямими імпортами:
  `get_meta` → `doctype_registry`, `get_session` → `local.require_session`, `whitelist` →
  `api.context`, `throw` → `errors`, `grunt.db.*` (читання) → `GruntDB()`, `_` / `log` напряму.
  Високорівневі (`get_doc`, `get_list`, `new_doc`, `context`) лишились — крок 9.
- Базовий список 121 → 115: `document.fetch / links / query / validation / validators /
  versioning`.
- Що тримає решту документа: `base` імпортує всі mixins, а mixins (`lifecycle`, `collection`,
  `tree`, `queryset`, `registry`) — `base` назад (фабрики `load_document` / `new_document`,
  клас за замовчуванням). Це 6b-2.
- Результат: 2257 passed, pyright 0; CodeQL локально 285 → 281, нових 0 (алерт `publish →
  api.v1.ws` змінив клас з `unsafe-cyclic-import` на `cyclic-import` — той самий цикл).

### 2026-11-10 — крок 6b-2: `base` ↔ `registry` / `schema` / `queryset`

- **Базовий клас реєструється сам:** `document.base` викликає `document_registry.use_base(Document)`;
  `document_registry.base` — для DocType без контролера і для перевірок «контролер перевизначив
  хук» (`collection`, `tree`). `document.registry` більше не імпортує `base`.
- Фабрики — через клас: `lifecycle` — `self.load(...)`, `update_side_effects` / `collection` —
  `document_registry.base.new(...)` / `.load(...)` (новий classmethod `Document.new`).
- `DocumentList` — окремий лист `document/document_list.py` (`collection`, `query_cache`,
  `document_api` імпортують звідти).
- `schema` / `queryset` — без імпорту `Document` (лише анотації); `collaboration_rpc` — без
  імпорту контролера `Comment` (за назвою DocType).
- Базовий список 115 → 111: `document.registry`, `document.schema`, `Comment`, `cache.query_cache`.
- Що лишилось у документі: високорівневий фасад у ядрі (`grunt.get_doc / get_list / new_doc /
  context` → `app.document_api` → документ) — крок 9; mixins / `base` імпортують сервіси вище
  (`api.v1.ws`, `webhook.service`, `workflow`, `auth.users`), а ті — контролери DocType → `base`
  — 6b-3 (події).
- Результат: 2258 passed, pyright 0; CodeQL локально 281 → 256, нових 0.
