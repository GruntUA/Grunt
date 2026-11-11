# Циклічні імпорти ядра — план

Живий план. Оновлюється після кожного кроку: що зроблено, що далі, які рішення прийняті.
Новий чат з Claude починає звідси.

**Рішення власника (2026-11-09):** доводимо ядро до справжнього DAG імпортів — 0 алертів
`py/unsafe-cyclic-import` і 0 `py/cyclic-import`, включно з циклом через фасад `grunt/__init__`.
Виключення запитів CodeQL не розглядаємо: алерт = неправильно розкладені залежності.

Оновлено: 2026-11-11 — злито #120–#136 (кроки 0–7, 9); злито #137 (крок 8: базовий список порожній, CodeQL 0 і локально, і в CI); злито #138 (крок 10). План виконано: ядро — DAG імпортів, храповик і CodeQL — 0. Далі — оновлення додатків під нові API.

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
| 6 | Документ: `document.base` ↔ mixins ↔ `collection` / `queryset` / `registry`; mixins без `api.v1.ws`, `workflow`, `website` — через події | злито (#126–#128, #131–#133) |
| 7 | Auth-сервіси: `User` ↔ `users` ↔ `user_api` (прибрати реекспорти внизу `user.py`), `login`, `service`, `UserSession` | злито (#134) |
| 8 | Решта: storage (`files` ↔ `images` ↔ `tasks`, `cloud.*`), monitoring (`health` ↔ `updates`), workflow (`engine` ↔ `notify` ↔ `events`), `apps.loader` ↔ `consumers` ↔ `website.router`, `progress` → `ws` | злито (#137) |
| 9 | Фасад: ядро не імпортує `grunt` (`_`, `log`, `grunt.db`, `throw`, `whitelist`…) — прямі імпорти з модулів; правило в ruff/тесті; `grunt/__init__` лінивий | злито (#129–#131, #135, #136) |
| 10 | Храповик рахує й неявні імпорти батьківських пакетів; базовий список порожній; CodeQL локально і в CI — 0 | злито (#138) |

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

### 2026-11-10 — крок 9a: сервіси під документом без низькорівневого фасаду

- `workflow.engine / guard / registry`, `storage.references / signing`, `naming.service`,
  `website.generator`: `get_meta`, `grunt.db.*` (зокрема `bulk_update`), `get_session`, `_` / `log`
  — напряму. Базовий список 111 → 106 (`naming`, `naming.service`, `storage.references`,
  `storage.signing`, `workflow.registry`).
- **Вузол, що лишився.** Сервіси (workflow-переходи, коментарі й журнал, сторінки сайту, формули)
  кличуть `grunt.get_doc / new_doc / save_doc / count / get_list` — повний конвеєр із правами з
  `app.document_api`, а він сам імпортує ці сервіси (`workflow_engine`). Рішення: високорівневий
  CRUD із правами — у шар документа (`document/api.py`), фасад делегує; сервіси кличуть його.
  Порядок: 9b — `document/api.py` (поведінка та сама); 9c — сервіси на нього; потім 6b-3 (події
  для `api.v1.ws`, вебхуків, `events`) і 6b-4 (HTTP-методи з `Document` в API, нові шляхи —
  рішення власника 2026-11-10).

### 2026-11-10 — крок 9b: `document/api.py` і шина подій без підсистем

- **Високорівневий CRUD із правами — у шарі документа.** `app/document_api.py` → `document/api.py`
  (`git mv`, поведінка та сама): один екземпляр `documents` зі своїм `db` і кешами (запитів,
  документів); `GruntApp` і фасад (`grunt.get_doc`, `get_list`, `new_doc`, ...) делегують у нього
  — один набір кешів. `grunt.submit` (workflow) лишився в `app` — `app/workflow_api.py`.
- **Шина подій без підсистем.** `grunt.events` — лише шина (`fire`, `subscribe`); основні етапи
  (серверні скрипти, зв'язки, файли, правила сповіщень і призначень) — `grunt/core_events.py`,
  який шина імпортує за шляхом перед першою подією (не можуть загубитися через порядок
  імпорту). `grunt.hooks` — без фасаду.
- Базовий список 106 → 101 (−7: `events`, `scripting`, `notification.rule_index / tasks`,
  `AssignmentLog`, `ToDo`, старий `app.document_api`; +2: `document.api` — це перейменований
  `app.document_api`, `app.workflow_api` — виділений з нього `submit`; обидва в циклі через
  `collection` / `workflow.engine` → фасад — 9c).

### 2026-11-10 — крок 9c: сервіси на `documents` і `grunt.local`

- `workflow.engine`, `website.generator` — `documents.get_doc / save_doc / new_doc` замість
  `grunt.*`; `grunt.system_context` → `grunt.local.as_system(session, engine)` (документ
  `SYSTEM_USER` реєструє `auth.doctypes.User.user` — `local.use_system_user`; без нього
  `as_system` відмовляє, а не працює як «ніхто»).
- `collection`, `update_side_effects` — `grunt.set_context / context` з поточним користувачем →
  `grunt.local.rebound(session, engine)`.
- **Формули** (`count` / `sum_docs`) — без `document.api` (реальний цикл імпорту `formula →
  document.api → collection → formula`): `count` — сирий підрахунок, як `grunt.count`;
  `sum_docs` — перевірка права читання + `permissions.reads` по всіх рядках. **Виправлено:**
  `sum_docs` через `grunt.get_list` підсумовував лише першу сторінку (20 рядків) —
  `tests/test_formula_aggregates.py` падає на старому коді.
- Базовий список 101 → 100 (`document.formula`). Решту тримають: `document.base` → фасад
  (`grunt.context` для хуків), `base` / `lifecycle` → `api.v1.ws`, `webhook.service`,
  `website.generator`, workflow — це 6b-3; `workflow.engine ↔ workflow.notify`.
- Результат: 2260 passed, pyright 0.

### 2026-11-10 — крок 6b-3: точки розширення конвеєра запису

- `grunt/document/pipeline.py` — `WriteExtension` з точками `prepare_insert`, `before_store`,
  `begin_update` (→ `UpdateScope`: `active()` навколо збереження, `finish()` після),
  `check_delete`, `after_write`, `changes_recorded`, `doc_progress`. Конвеєр (`lifecycle`,
  `update_side_effects`, `base`) кличе їх замість workflow, `website.generator`, вебхуків,
  активності/підписників і WebSocket.
- Реалізації — `grunt/core_pipeline.py` (workflow-охоронці й переходи, маршрут веб-сторінки,
  вебхуки, активність, realtime); конвеєр імпортує його за шляхом перед першим записом.
  `REQUIRED = {"workflow"}`: без охоронця workflow `pipeline.extensions()` відмовляє —
  запис не проходить без перевірки (`tests/test_write_pipeline_extensions.py`).
- Функціонально-локальні імпорти `activity` / `follow` в `update_side_effects` прибрано.
- Базовий список 100 → 93 (`lifecycle`, `collection`, `update_side_effects`, `webhook.service`,
  `OutgoingWebhook`, `workflow.guard`, `activity.follow`).
- Результат: 2262 passed, pyright 0; CodeQL локально 257 → 224, нових 0. З алертів після #131
  лишились 2 (`documents` у `workflow.engine` / `website.generator`) — їх тримають HTTP-методи
  в `Document` (6b-4).

### 2026-11-10 — крок 6b-4: HTTP-методи документа — з `Document` у `grunt.api.v1.document`

- Рішення власника (2026-11-10): винести, нові шляхи, сумісність не зберігаємо.
- 7 міксинів `grunt/document/mixins/*_rpc.py` (27 методів-`@staticmethod`) → модулі
  `grunt/api/v1/document/{tree,links,export,history,collaboration,workflow,meta}.py` (функції
  модуля). Шлях `grunt.document.base.Document.<m>` → `grunt.api.v1.document.<модуль>.<m>`.
  `Document` = `DocumentLifecycleMixin` + сам документ, без HTTP-методів.
- Оновлено: фронтенд (`core/api/docs.ts`, `DocSidebarBody.vue`, `executor.ts`, експортери),
  `methods.generated.d.ts` (перегенеровано), тести, `docs/api/grunt-app.md`, skill
  `grunt-dev` (`references/api.md`, обидві копії). Інші додатки bench
  старих шляхів не використовують.
- Базовий список 93 → 70 (23 модулі: усі `*_rpc`, `activity`, `activity.reactions /
  milestones`, `print.renderer`, `website.preview`, `document.tree / titles`, `metadata.scaffold`,
  ...).
- Результат: 2262 passed, vitest 335, vue-tsc і pyright 0; CodeQL локально 224 → 147;
  алерти `documents` після #131 зникли; 3 «нові» — ті самі цикли `auth`, перекласифіковані з
  `unsafe-cyclic-import` на `cyclic-import`.

### 2026-11-10 — крок 7: auth-сервіси

- **Реекспорти внизу `User/user.py` прибрано.** HTTP-методи входу — за власним шляхом
  `grunt.auth.user_api.<name>` (було `grunt.auth.doctypes.User.user.<name>`); імпорти сервісів —
  з `grunt.auth.users`. Оновлено фронтенд (`stores/auth.ts`, `api/client.ts`, `auth-admin.ts`,
  `browserHealth.ts`, тести), `User.js`, `rate_limit`, `dependencies`, `document_cache`, тести,
  `methods.generated.d.ts`. Інші додатки bench цих шляхів не використовують.
- **Хешування паролів** — лист `auth/passwords.py`; контролер `User` більше не імпортує
  `auth.users`.
- **`UserSession ↔ service`:** `session_ttl_minutes` (налаштування сесій) — у `UserSession`.
- Низькорівневий фасад прибрано з `auth.*`.
- Базовий список 70 → 64 (`user_api`, `login`, `mfa`, `impersonation`, `session_cookie`,
  `password_policy`). Решту `auth` (`User`, `UserRole`, `Role`, `users`, `UserSession`,
  `service`, `ip_policy`) тримає високорівневий фасад (`grunt.*` у контролерах, `document.base`)
  — крок 9.
- Результат: 2262 passed, vitest 335, vue-tsc і pyright 0; CodeQL локально 147 → 38, нових 0.

### 2026-11-10 — крок 9d: ядро без фасаду (механічний прохід)

- 196 модулів ядра (крім `grunt/__init__`, `grunt/app/*`, `document.api`, `local`): `grunt.get_meta /
  get_session / get_engine / throw / whitelist / log`, `grunt.db.*` (`GruntDB()`),
  `grunt.system_context` (новий асинхронний `grunt.local.system_context` поверх `as_system`) і
  CRUD (`grunt.get_doc / get_list / new_doc / save_doc / delete_doc / count / ...` →
  `documents.*`, імпорт `lazy` — модулі, які `document.api` тягне під час завантаження,
  кличуть його назад).
- `Document.objects` (`queryset`) — без імпорту `document.api`: той реєструє себе
  (`queryset.use_document_api`).
- Лишилось у ядрі: `grunt.get_user` (89), `grunt.context` (24), `notify` / `publish` /
  `render_template` — живуть у шарі `app` (документ `User`, пошук користувача за email) — 9e.
- Базовий список 64 → 63; цикли тепер видно прямими ребрами (`documents`) замість фасаду.
- Результат: 2262 passed, pyright 0; CodeQL локально 38 → 38, нових 0.

### 2026-11-11 — крок 9e: ядро без фасаду, тест-правило

- `grunt.get_user()` → `grunt.local.user_email()` (лише email, 401 без користувача) або
  `grunt.auth.current.acting_user()` (документ `User`, вище шару auth). `grunt.context(...)`
  (з пошуком за email) → `grunt.auth.current.user_context(...)`; фасад (`ContextAPI`) делегує
  туди. `set_context` / `reset_context` → `grunt.local.bind` / `unbind`.
- `render_template` → `grunt.utils.templates.render` (фасад реєструє себе — `use_app`, бо
  шаблон отримує його глобальною `grunt`); `notify` → `grunt.publish.notify`; кеші →
  `documents.doc_cache / query_cache`; `__version__` → `framework_version()`; `__file__` → шлях
  від модуля; `from grunt import log / _ / whitelist / log_error / outbox / hooks` — напряму.
- `Document.grunt` (для контролерів додатків, `self.grunt.db...`) — `sys.modules["grunt"]`;
  контролери ядра кличуть `throw` з `grunt.errors` (типізований `NoReturn`).
  `DataImport.export_doctype` — без невикористаного параметра-фасаду.
- **Правило:** `tests/test_no_facade_in_core.py` — ядро не імпортує `grunt` (крім самого
  фасаду `grunt/__init__`, `grunt/app`, а також `testkit` і `utils/shell`, що віддають фасад
  коду додатків навмисно).
- Базовий список 63 → 38 (вся `auth`, `document.base / api`, `api.v1.ws`, `publish`,
  `progress`, `outbox`, `tasks.broker / middleware`, `app.*`, ...).
- Результат: 2263 passed, vitest 335, pyright 0; CodeQL локально 38 → 38, нових 0.

### 2026-11-11 — крок 8: решта циклів

Базовий список 38 → 0, CodeQL локально 38 → 0 (обидва запити). По вузлах:

- **Фасад.** `api.messages` без невикористаних `notify_all` / `queue_email` (тягнули email і
  сповіщення); `app.permission_api` і `scripting.server_script` — прямі імпорти замість `grunt`.
- **workflow.** `ActiveTransition`, `current_transition()`, `user_may_take` — у новий
  `workflow/transition.py`; `engine`, `guard`, `notify`, `core_pipeline` беруть звідти.
- **assignment.** Перегляд правила — метод контролера `AssignmentRule.preview()`;
  `AssignmentService.preview_rule` прибрано, контролер не імпортує сервіс.
- **storage.cloud.** `RemoteError` і `obscure` — у `providers` (rclone імпортує їх звідти).
  Сповіщення System Manager про збій сховища — через шину: `record_status` кидає подію
  `storage_remote_failed`, підписник у `core_events` надсилає сповіщення (додатки теж можуть
  підписатися).
- **actions / reports.** `metadata/dump.py: dump_doctype` — серіалізація DocType без збагачення
  `actions`; `api.v1.meta._dump_doctype` додає actions зверху, звіти (`reports.joins`) читають
  лише поля.
- **apps / website.** `website.*` бере головний веб-додаток із `site_manager.get_primary_web_app()`,
  `CORE_APP` — з `apps.required` (дублікат у `apps.loader` прибрано).
- **email / scheduler.** `broker.by_name("module:function")` — задача за назвою без імпорту її
  модуля (зареєстрована — з мітками, інакше `AsyncKicker` за назвою). `email.service` штовхає
  `process_email_queue` так. Дайджести планувальник ставить за шляхом
  (`_add_scheduled_job(path, cron, *args, job_id=...)`), id `grunt.digest.daily/weekly` збережено.
- **monitoring.** Рядок звіту (`OK`…`INFO`, `Row`, `row`) — `monitoring/rows.py`;
  `human_size` — `grunt/utils/sizes.py`.
- **storage.** Оптимізатор зображень — `storage/optimize.py` (його імпортує `files`);
  `images.py` — лише стиснення вже збережених (`compress_existing`, `start_compression` за тим
  самим шляхом методу), задачу ставить через `by_name`.
- **Ламає:** `grunt.workflow.engine.current_transition` → `grunt.workflow.transition` (застосунок
  `esign` імпортує старий шлях — оновити разом з рештою додатків);
  `grunt.storage.cloud.rclone.RemoteError/obscure` → `providers`;
  `grunt.monitoring.health.human_size` → `grunt.utils.sizes`; `grunt.storage.images.optimize_image`
  / `ImageOptions` / `renamed` → `grunt.storage.optimize`; `AssignmentService.preview_rule` →
  `AssignmentRule.preview`.
- Результат: 2265 passed, 2 skipped; pyright 0; ruff чисто.
- **Далі — крок 10:** храповик рахує й неявні імпорти батьківських пакетів; перевірити CodeQL
  у CI.

### 2026-11-11 — крок 10: неявні імпорти батьківських пакетів

- `grunt/utils/import_graph.py`: імпорт `a.b.c` — ще й ребро до кожного пакета над ним
  (`a/__init__`, `a/b/__init__` виконуються першими), крім пакетів самого імпортера — вони
  вже імпортуються. Так рахує й храповик.
- З таким підрахунком у циклах було 136 модулів — одна компонента через `__init__.py`, що
  реекспортують підмодулі. Порожні тепер (лише docstring): `apps`, `auth.providers`, `db`
  (і без проксі `__getattr__` — фасад сам задає `grunt.db`), `io`, `io.exporters`, `metadata`,
  `naming`, `scripting`, `startup`, `storage`, `store`, `website`. Імпортери ядра (78 файлів)
  беруть імена з модулів, що їх визначають. `naming_service` → `grunt.naming.service`,
  `server_script_runner` → `grunt.scripting.server_script`.
- `__init__` з кодом (`actions`, `activity`, `startup.doctypes`, `storage.cloud`) у цикли не
  потрапили — лишаються, шляхи методів не змінюються.
- Базовий список порожній і за суворим підрахунком; CodeQL локально 0.
- **Ламає (додатки):** `from grunt.storage import store, read, FileTooLargeError` →
  `grunt.storage.files` / `grunt.storage.backends` (esign, mlt_portal, official_documents,
  inventory, tsnap, letter, hromada_it, cms); `from grunt.store import …` →
  `grunt.store.base` / `virtual` (translate); так само решта пакетів вище.
- Результат: 2265 passed, 2 skipped; pyright 0; ruff чисто.
