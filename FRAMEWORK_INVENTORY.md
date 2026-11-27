# Інвентаризація частин фреймворку Ґрунт

Знімок: 2026-11-21, гілка `feat/prepared-report` (589933b4).
Мета — карта «з чого складається ядро» для подальшого аналізу: межі частин, розмір, ключові
елементи, публічні точки входу. Оцінок і рішень тут немає — лише інвентар.

## Загальні цифри

| Що | Кількість |
|---|---|
| Python-пакетів у `grunt/` | 41 + 19 модулів верхнього рівня |
| Рядків Python (без тестів) | ~81 000 у 697 файлах |
| Рядків фронтенду (Vue/TS, без тестів) | ~62 000 у 784 файлах |
| Core DocType | 114 |
| Типів полів (плагіни `frontend/src/components/fields/*`) | 38 + запасний `Default` |
| Alembic-міграцій ядра | 28 |
| `@whitelist()`-методів (RPC) | 224, з них 115 у `api/` |
| Класичних REST-маршрутів | ~28 |
| Ключів `hooks.py` для додатків | 22 |
| CLI-команд | ~70 у 13 групах |
| Тестів: pytest-файлів / vitest-файлів | 299 / 75 |

## Зведена карта

| # | Частина | Пакети | ~Рядків |
|---|---|---|---|
| 1 | Фасад API і життєвий цикл застосунку | `__init__`, `app/`, `startup/`, `config`, `local`, `main`, `errors` | 2 800 |
| 2 | Робота з БД | `db/`, `store/`, `query/`, `cache/` | 9 000 |
| 3 | Метадані (моделі, DocType, поля) | `metadata/`, `naming/`, `validators/`, `geo/` | 4 500 |
| 4 | Документи (ORM-рівень, CRUD, життєвий цикл) | `document/`, `activity/` | 8 900 |
| 5 | Дозволи й автентифікація | `permissions/`, `auth/` | 7 900 |
| 6 | API фреймворку й інтеграції | `api/`, `middleware/`, `mcp/`, `webhook/`, `integrations/` | 9 500 |
| 7 | Розширюваність (додатки, хуки, скрипти) | `apps/`, `hooks`, `events`, `core_*`, `actions/`, `scripting/` | 3 800 |
| 8 | Бізнес-процеси й фонові задачі | `workflow/`, `assignment/`, `notification/`, `tasks/` | 6 500 |
| 9 | Файли, імпорт/експорт, друк, бекапи | `storage/`, `io/`, `data_import/`, `print/`, `backups/` | 7 100 |
| 10 | Комунікації й realtime | `email/`, `webpush/`, `publish`, `outbox`, `progress` | 3 400 |
| 11 | Звіти й пошук | `reports/`, `search/` | 2 300 |
| 12 | Сайт і робоче місце (desk) | `website/`, `site/` | 2 600 |
| 13 | Інтернаціоналізація | `i18n/` | 1 600 |
| 14 | Моніторинг і логування | `monitoring/`, `log`, `logging_config` | 3 300 |
| 15 | Інструменти розробника | `cli/`, `testkit`, `utils/`, `fixtures`, `standard_records` | 7 700 |
| 16 | UI (фронтенд) | `frontend/src/` | 62 000 (TS/Vue) |

---

## 1. Фасад API і життєвий цикл застосунку

**Що це:** єдиний простір імен `import grunt` для коду додатків і запуск FastAPI-застосунку.

- `grunt/__init__.py` — публічний фасад: `get_doc`, `new_doc`, `save_doc`, `delete_doc`,
  `rename_doc`, `copy_doc`, `get_list`, `get_all`, `count`, `aggregate`, `exists`,
  `get_value`/`set_value`, `get_single`, `bulk_insert`/`bulk_update`/`bulk_delete_docs`,
  `get_meta`, `has_permission`/`has_perm`, `submit`, `notify`, `publish`, `enqueue`,
  `enqueue_doc`, `render_template`, `throw`, `msgprint`, `log`, `log_error`, `_`, `whitelist`,
  контекст (`context`, `get_user`, `sudo`, `system_context`, `set_context`…), `db`, кеші.
- `app/` — `GruntApp` як сума міксинів: `ContextAPI`, `RealtimeAPI`, `PermissionAPI`,
  `WorkflowAPI`, `UtilityAPI`.
- `startup/` — lifespan, завантаження core DocType, сидування, встановлення додатків
  (`GruntInstalledApp`), фікстури, workspace, dev-режим, валідація налаштувань.
- `config.py`, `local.py` (контекст запиту), `main.py` (точка входу ASGI), `errors.py`,
  `version.py` (версія з git-тегів).

## 2. Робота з БД

**Шари** (за `DB_LAYERS_PLAN.md`): сесія → діалект → схема → store → query.

- `db/session.py` — async SQLAlchemy, engine/session factory, мульти-БД (сайти).
- `db/dialects/` — **єдине місце, що розрізняє бекенди**: `sqlite` (типовий), `postgresql`,
  `mysql`; `fulltext` (FTS5/нативний FTS), `archive` (дампи).
- `db/schema/` — `diff` (що треба змінити в таблиці під DocType) → `changes` → `apply`
  (`check` проти даних, потім застосування). Автосинхронізація схеми з метаданих.
- `db/migrations/` + `alembic_utils.py`, `rename_doctype.py` — 28 міграцій ядра, міграції
  додатків, `db rollback/history`.
- `db/api.py` — `GruntDB` (`grunt.db`), `list_query`, `aggregate_query`, сортування.
- `db/commit.py` (`on_commit`), `write_intent.py` (SQLite `BEGIN IMMEDIATE`), `buckets.py`
  (групування за датою), `errors.py` (БД-помилки → HTTP), `profiler.py`, `types.py`.
- `store/` — де живуть рядки DocType: `SqlStore` (таблиця), `VirtualStore` (ring buffer,
  зовнішні джерела), `lookup.store_for()`.
- `query/` — запит як дані: AST (`nodes`), парсер фільтр-dict → AST (`parse`), компіляція в
  SQL (`compile_sql`), обчислення в пам’яті (`evaluate`), агрегати, `run` проти store.
- `cache/` — `document_cache`, `query_cache`, `bus` (інвалідація між процесами).

## 3. Метадані: моделі, DocType, поля

- `metadata/doctype.py` — модель DocType (центральна сутність), `field.py` — `DocField` і
  базовий клас `FieldType` з **трейтами** (споживачі питають трейт, а не ім’я типу).
- `metadata/registry.py` — in-memory реєстр DocType з лінивим завантаженням; `store.py` —
  визначення DocType у таблиці самого DocType; `loader.py`, `compiler.py`, `dump.py` (JSON для
  форм/списків/білдерів).
- `metadata/extensions.py` — поля, які один додаток додає до DocType іншого.
- `metadata/permission.py`, `permission_layers.py` — метадані дозволів і шар сайту над ними.
- `metadata/dynamic_options.py` (динамічні Select), `widget.py` (типи віджетів дашборду),
  `scaffold.py` (генерація файлів DocType).
- Метадані-DocType: `DocType`, `DocField`, `DocPermission`, `DocTypeAction`,
  `DocTypeCalendarSource`, `DocTypeLink`, `DocTypeStatusIndicator`, `Workflow`,
  `WorkflowState`, `WorkflowTransition`.
- **Типи полів (38)** — плагіни «Python + Vue + manifest.json» у
  `frontend/src/components/fields/<Type>/`: Data, Int, Float, Currency, Percent, Check,
  Select, MultiSelect, Link, DynamicLink, MultiLink, Table, EmbeddedForm, Date, Datetime, Time,
  Duration, LongText, RichText, Code, JSON, HTML, HTMLView, Password, Attach, Image, Signature,
  BarCode, Color, Icon, Rating, Geolocation, Button, RowCondition, ColumnMapping, Tab, Section,
  Column; `Default` — запасні ListCell/FilterInput для типів без власних.
- `naming/` — автоіменування: `NamingSeries`, шаблони, токени дат.
- `validators/` — валідатори полів: email, phone, url, IBAN/IBAN-UA, ЄДРПОУ, РНОКПП.
- `geo/` — довідники: Country, Region, City, Address, Currency, Language, Timezone.

## 4. Документи

**Що це:** «ORM-рівень» над метаданими — контролери, CRUD із дозволами, конвеєр запису.

- `document/base.py` — `Document`, базовий клас контролера; `mixins/lifecycle.py` —
  життєвий цикл (validate → before/after insert/save/delete…); `pipeline.py` — точки
  розширення конвеєра запису; `payload.py`.
- `document/api.py` — `DocumentAPI`: CRUD і запити з перевіркою дозволів (те, що за
  `grunt.get_doc` та ін.); `collection.py`, `bulk_ops.py`, `document_list.py`.
- `document/queryset.py` — fluent-типізований query builder; `query.py` (`__child_of`).
- Зв’язки: `relations.py` (child table, MultiLink), `multi_link.py` (junction-таблиці),
  `links.py` (автоматичні backlinks), `connections.py` (вкладка «Зв’язки»), `tree.py`
  (is_tree), `fetch.py` (fetch_from), `titles.py` (масове розв’язання заголовків).
- Обчислення й перевірки: `validation.py`, `validators.py`, `formula.py`, `aggregate.py`,
  `guards.py` (вето на зміну/видалення), `update_side_effects.py`.
- `versioning.py` — JSON-diff версій; `serde.py`, `schema.py` (серіалізація), `meta.py`,
  `sidebar.py`, `registry.py`.
- DocType: `Comment`, `DocLink`, `DocTag`, `DocVersion`, `DocumentShare`.
- `activity/` — соціальний шар: стрічка (`ActivityLog`), лайки, реакції, підписки
  (`DocFollow`), кошик (`DeletedDocument`), `ViewLog`, віхи (`Milestone`, `MilestoneTracker`).

## 5. Дозволи й автентифікація

### 5.1 Дозволи (`permissions/`)
- `rbac.py`, `access.py` — рольовий доступ для (doctype, user); `roles.py`, `role_props.py`.
- `query.py` — **row-level security як один предикат на дію** (єдине джерело істини);
  `reads.py` — читання від імені користувача (рядки + поля); `match.py` — вирази
  `DocPermission.match`.
- `scopes.py` — ролі, обмежені записом (scoped roles); `trees.py` — успадкування по піддереву;
  `shares.py` (`SharedWith`); `groups.py` (`UserGroup`).
- `perms.py` — іменовані дозволи (те, що код перевіряє замість назв ролей; декларуються в
  `hooks.permissions`).
- Аудит і пояснення: `explain.py` (трасування «чому можна/не можна»), `audit.py`
  (`PermissionLog`), `access_log.py` (`AccessLog`), `warnings.py` (підозрілі налаштування),
  `doc_perms.py` (`__perms` для форми), `guards.py`.
- API: `permission_inspector`, `permission_layers`, `permission_matrix`,
  `permission_warnings`, `role_scopes`, `share`.

### 5.2 Автентифікація (`auth/`)
- `login.py`, `service.py`, `session_cookie.py`, `current.py`, `dependencies.py` (FastAPI deps).
- Провайдери (`providers/`): email-посилання, OAuth, WebAuthn (passkeys), реєстр провайдерів
  (розширюється через `hooks.auth_providers`).
- `mfa.py`, `password_policy.py`, `passwords.py`, `login_policy.py`, `ip_policy.py`,
  `impersonation.py`, `api_key_service.py`.
- DocType: `User`, `Role`, `UserRole`, `RoleProfile`(+Role), `UserRoleProfile`, `UserGroup`
  (+Member), `UserSession`, `UserSessionLogin`, `ApiKey`(+Role), `EmailLoginToken`,
  `WebAuthnCredential`.

## 6. API фреймворку й інтеграції

- `api/context.py` — `whitelist()` (RPC-методи), `get_session`, `get_engine`;
  `messages.py` (`msgprint`), `results.py`, `typegen.py` (генерація TS-типів методів).
- `api/v1/` — HTTP-поверхня:
  - документи: `docs/crud.py` (REST `/{doctype}/{id}`), `document/*` (meta, history, links,
    tree, workflow, export, collaboration), `documents.py`, `method.py` (виклик whitelist);
  - метадані/налаштування: `meta`, `site_config`, `view_settings`, `saved_filters`,
    `workspace`, `pages`, `dashboard(_data)`, `translations`;
  - дозволи: див. 5.1; автентифікація: `auth_methods`, `oauth`;
  - інше: `files`, `email`, `notifications`, `search`, `data_import`, `webhooks`, `scripting`,
    `mcp`, `health`, `dev`, `ws` (WebSocket).
- `middleware/` — `security` (заголовки), `rate_limit`, `idempotency`, `logging`.
- `mcp/` — MCP-сервер: протокол, реєстр інструментів (розширюється `hooks.mcp_tools`).
- `webhook/` — вихідні (`OutgoingWebhook`, `WebhookLog`) і вхідні (`IncomingWebhook`,
  `IncomingWebhookLog`) вебхуки.
- `integrations/` — OAuth-клієнт до зовнішніх сервісів (`ConnectedApp`, `OAuthToken`).

## 7. Розширюваність: додатки, хуки, скрипти

- `apps/` — виявлення й завантаження додатків: `manifest.py` (`[tool.grunt]` у pyproject:
  `depends_on`, `extends`, `adopts`, `required_grunt`, `modules`, `workspace`), `deps.py`,
  `required.py`, `loader.py`, `consumers.py`.
- **Ключі `hooks.py` додатку (22):** `doc_events`, `doctype_js`, `write_guards`,
  `auth_providers`, `rate_limits`, `override_doctype_class`, `doctype_mixins`,
  `scheduler_events`, `io_exporters`, `io_importers`, `website_templates`, `website_globals`,
  `website_context`, `website_resolvers`, `website_sitemap`, `tree_title_resolvers`,
  `doc_actions`, `mcp_tools`, `notification_channels`, `notification_events`, `permissions`,
  `sidebar_sections`.
- `hooks.py` (`@on`, `@on_doc`, `dispatch`), `events.py` (`subscribe`/`fire`),
  `core_events.py`, `core_hooks.py`, `core_pipeline.py` — шина подій і стадії ядра.
- `actions/` — кастомні кнопки документа, зареєстровані в коді й прив’язані до метаданих.
- `scripting/` — `ServerScript` (sandbox `safe_globals`), `ClientScript`, `Hook` (DocType),
  `file_scripts.py` (скрипти з файлів додатку).

## 8. Бізнес-процеси й фонові задачі

- `workflow/` — рушій: стани/переходи, `guard`, `actors`, `inbox` (вхідні на погодження).
- `assignment/` — правила призначення (`AssignmentRule`, `AssignmentRuleUser`,
  `AssignmentLog`, умови).
- `notification/` — правила (`Notification`) + канали (`NotificationChannel`) + доставка
  (`NotificationDelivery`) + дзвоник (`NotificationLog`); отримувачі, дати-правила, індекс
  правил, події коду; SLA (`ServiceLevel`, `ServiceLevelStatus`); 12 стандартних правил у
  `records/`.
- `tasks/` — брокер, `enqueue`, worker, scheduler (`ScheduledJob`, `ScheduledJobState`,
  `ScheduledJobLog`), `BackgroundJob`/`BackgroundWorker`, `AutoRepeat`, `Reminder`, `ToDo`,
  обслуговування БД, retention, інтроспекція Redis.

## 9. Файли, імпорт/експорт, друк, бекапи

- `storage/` — content-addressed сховище файлів (`File`, `FileFolder`), бекенди, підписані
  URL, квоти, «простори», посилання на файли, GC, мініатюри, оптимізація зображень;
  `cloud/` — віддалені сховища через rclone (`StorageRemote`), хмарні бекапи.
- `io/` — реєстри експортерів (CSV, XLSX, HTML, санітизація) та імпортерів (CSV, XLSX);
  DocType `DataImport`, `DataExport`; `data_import/` — сервіс і задачі імпорту.
- `print/` — `PrintFormat`, `LetterHead`, рендер, PDF, фільтри шаблонів.
- `backups/` — бекап БД + файлів + конфігу за розкладом (`Backup`).

## 10. Комунікації й realtime

- `email/` — `EmailAccount`, `EmailQueue`, `EmailMessage`, `EmailAttachment`,
  `EmailTemplate`, `EmailUnsubscribe`; compose, вхідна пошта (`inbound`), маршрутизація.
- `webpush/` — push-повідомлення в браузер (`PushSubscription`).
- `publish.py` (realtime-події), `outbox.py` (відкладена доставка після коміту),
  `progress.py` (прогрес довгих операцій), `api/v1/ws.py` (WebSocket).

## 11. Звіти й пошук

- `reports/` — рушій звітів (`Report`), joins, опції списку, обчислення віджетів,
  підготовлені звіти (`PreparedReport` — поточна гілка), доступ і доставка.
- `search/` — глобальний пошук (FTS5 через діалект), токени, терміни.

## 12. Сайт і робоче місце

- `website/` — публічні сторінки: роутер, генератор, домени/хости, SPA-обгортка, превʼю,
  сторінки `www/` (login, signup, share).
- `site/` — мультисайт (`manager`, `bench`, middleware), `SystemSettings`, меню додатків
  (`AppMenu`), workspace (`WorkspaceSection`, `WorkspaceSidebarItem`), сторінки й віджети
  (`Page`, `PageWidget`), `Bookmark`, `SavedFilter`, `UserViewSettings`, онбординг
  (`ModuleOnboarding`, `OnboardingStep`, `OnboardingProgress`), тури форм (`FormTour`).

## 13. Інтернаціоналізація

- `i18n/` — gettext PO/POT, екстракція рядків, множини, Jinja-розширення, переклад
  метаданих, middleware мови; API `translations`; каталог `translations/`.

## 14. Моніторинг і логування

- `monitoring/` — `ErrorLog`, перф-статистика (`PerfStat`, `PerfTrend`), SQL-профайлер
  (`SqlProfilerRequest`/`Query`/`Span`), `SystemHealthReport`, перевірка оновлень.
- `log.py`, `logging_config.py` — файлове логування з маршрутизацією по модулях.
- `middleware/logging.py`, `db/profiler.py`, `api/v1/health.py`.

## 15. Інструменти розробника

- `cli/` — групи команд: `site`, `app`, `db`, `doctype`, `fixtures`, `data`, `files`,
  `users`, `ui`, `skills`, `i18n`; окремі `migrate`, `test`, `lint`, `shell`, `release`,
  `worker`, `version`.
- `testkit.py` — фікстури/хелпери для тестів додатків; `utils/testgen.py`, `codegen.py`,
  `boilerplate.py`, `import_graph.py`.
- `fixtures.py`, `standard_records.py` — стандартні записи з `records/` і фікстури додатків.
- `utils/` — дрібні хелпери (рядки, числа, slug, sanitize, http, redis, captcha, шаблони).

## 16. UI (фронтенд, `frontend/src/`)

Vue 3 + TypeScript + shadcn-vue, Pinia, Vue Router, Vite.

| Частина | Де | Файлів |
|---|---|---|
| UI-кіт (shadcn-vue, не правиться вручну) | `components/ui/` | 315 |
| Поля (38 плагінів: редактор, ListCell, FilterInput, manifest) | `components/fields/` | 113 |
| Подання: list, form, report, kanban, calendar, gantt, gallery, tree, map, explorer | `components/views/` | 64 |
| Дашборди й віджети | `components/dashboard/` | 38 |
| Каркас: сайдбар, брендинг, layout, мобільне, PWA | `components/app/`, `layout/`, `mobile/`, `pwa/` | ~14 |
| Ядро клієнта: API-клієнт (15 модулів), WebSocket, рендерер форм, client scripts, io | `core/` | 70 |
| Composables (форма, список, мапа, сповіщення, presence, offline-черга, WebAuthn…) | `core/composables/` | 70 |
| Реєстри розширення: поля, подання, фільтри, клітинки списку, віджети, секції властивостей | `core/*Registry.ts` | 7 |
| Сторінки: desk, app, auth, reports, errors | `pages/` | 20 |
| Studio — візуальний конструктор DocType/вебформ | `pages/studio/builder/` | 27 |
| Сховища Pinia: app, auth, builder, doctype, pages, ui | `stores/` | 6 |

---

## Наскрізні механізми (перетинають кілька частин)

| Механізм | Де живе | Хто користується |
|---|---|---|
| Контекст запиту (user, site, sudo) | `local.py`, `app/context_api.py` | усі частини |
| Трейти типів полів | `metadata/field.py` | дозволи, fetch_from, зв’язки, пошук, схема |
| Конвеєр запису документа | `document/pipeline.py`, `core_pipeline.py`, `hooks` | документи, версії, сповіщення, вебхуки, пошук |
| `on_commit` / outbox | `db/commit.py`, `outbox.py` | realtime, сповіщення, кеш |
| Реєстри «код → метадані» | actions, field types, widgets, io, mcp, auth providers, channels | розширюваність додатків |
| Стандартні записи `records/` | `standard_records.py` | ролі, сповіщення, онбординг |
| Генерація типів | `api/typegen.py`, `doctype sync-types` | фронтенд (`methods.generated.d.ts`) |

## Пов’язані плани (контекст для аналізу)

`DB_LAYERS_PLAN.md` (частина 2), `PERMISSIONS_PLAN.md` (5), `NOTIFICATIONS_PLAN.md` (8),
`EXTENSIONS_PLAN.md` (7), `IMPORT_CYCLES_PLAN.md` (DAG імпортів, усе ядро),
`FRAPPE_GAP_PLAN.md` (порівняння з Frappe), `REFACTOR_PLAN.md`, `IDEAS.md`.
