# План реалізації пропущеного функціоналу (Gap Closure: Grunt vs Frappe)

Цей документ описує етапи реалізації функцій, які зараз присутні у Frappe, але відсутні в Ґрунті, для досягнення зрілості корпоративного рівня.

---

## 1. Кастомні контролери документів (Python Classes) ✅
**Мета:** Дозволити розробникам створювати класи Python для специфічних DocType з перевизначенням бізнес-логіки.

- [x] Створити базовий клас `Document` у `backend/grunt/core/document/base.py`.
- [x] Реалізувати механізм автоматичного завантаження (discovery) класів з `grunt_apps/*/controllers/`.
- [x] Оновити `DocumentService` для виклику хуків контролера під час CRUD.
- [x] Стандартні хуки: `before_insert`, `after_insert`, `before_save`, `after_save`, `validate`, `before_delete`, `after_delete`.

## 2. Глобальна система хуків (App Interoperability) ✅
**Мета:** Механізм взаємодії між різними додатками (apps).

- [x] Розширити `core/hooks.py`: реєстрація через `doc_events` у `hooks.py` додатків.
- [x] Підтримка wildcard `*` — хук на всі DocType (використовується для `ActivityLog`).
- [x] Підтримка черговості виконання хуків (`priority`).
- [x] Перевизначення контролерів (`override_doctype_class`) іншими додатками.

## 3. Фонові завдання та Планувальник (Background Jobs & Scheduler) ✅
**Мета:** Виконання асинхронних та регламентних робіт.

- [x] Інтегровано **TaskIQ** з `RedisStreamBroker` (in-memory fallback без Redis).
- [x] Декоратор `@task` для маркування фонових функцій.
- [x] Модуль `Scheduler` на базі `APScheduler` з підтримкою `cron` та `interval`.
- [x] Системний DocType `BackgroundTaskLog` + `TaskiqMiddleware` для автоматичного логування статусів (Started / Success / Error).

## 4. Поштова підсистема (Email Engine) ✅
**Мета:** Комунікація з користувачами через Email.

- [x] `EmailAccount` DocType для налаштування SMTP/IMAP.
- [x] `EmailQueue` DocType — черга листів зі статусами `Pending / Sent / Error`.
- [x] Асинхронна відправка через `aiosmtplib`.
- [x] Фонові завдання: `process_email_queue` (щохвилини), `pull_from_accounts` (кожні 10 хв).
- [x] Хук `inbound_email` для обробки вхідних листів (інтеграція з іншими додатками).

## 5. Інструменти управління даними (Import/Export) ✅
**Мета:** Масове завантаження та вивантаження даних.

- [x] `DataImport` DocType з підтримкою операцій `Insert / Update / Upsert`.
- [x] `DataImportService` на базі `pandas` для парсингу CSV/XLSX.
- [x] Фонова обробка через `TaskIQ` — великі файли не блокують сервер.
- [x] Ендпоінт `GET /api/v1/{doctype}/export` — потоковий CSV-експорт з фільтрами.

## 6. Колаборація та соціальні функції ✅
**Мета:** Покращення взаємодії користувачів.

- [x] `Comment` DocType — обговорення під кожним документом.
- [x] `ToDo` DocType — призначення задач з пріоритетом та дедлайном.
- [x] `ActivityLog` DocType — глобальний журнал аудиту (Create / Update / Delete), автоматично наповнюється через wildcard-хук.
- [x] `SharedWith` DocType — фундамент Row-level security для гнучкого обмеження доступу.

## 7. Мультиорендність (Multi-tenancy) ✅
**Мета:** Підтримка сотень незалежних сайтів на одному екземплярі бекенду.

- [x] `SiteManager` (`core/site/manager.py`) — читає `.env` з `my-bench/sites/<site>/`, сумісних з `grunt-cli`. Динамічно створює та кешує `AsyncEngine` для кожного сайту.
- [x] `SiteContextMiddleware` — визначає активний сайт за `X-Grunt-Site` або `Host`.
- [x] `get_session()` / `get_engine()` — FastAPI-залежності, завжди звертаються до БД поточного сайту.
- [x] Startup у `main.py` — ітерує всі сайти з `my-bench/sites/`, ініціалізує БД та синхронізує таблиці.
- [x] Фонові завдання (`email/tasks.py`, `data_import/tasks.py`, `middleware.py`) оновлені — використовують `site_manager` замість глобального `engine`.

---

## Фаза 5: Core Missing Features (Frappe Parity)

Порівняльний аналіз Frappe vs Ґрунт виявив критичні прогалини. Нижче — план їх закриття.

### 5.1 — Система нотифікацій ✅
**Мета:** Email/system/push нотифікації на основі подій документів.

**Створені файли:**
- `backend/grunt/core/notification/__init__.py` — модуль, singleton `notification_service`
- `backend/grunt/core/notification/service.py` — `NotificationService` (evaluate_rules, get/mark_read)
- `backend/grunt/api/v1/notifications.py` — `GET /notifications`, `PATCH /{id}/read`, `POST /read-all`
- `backend/tests/test_notifications.py` — 12 тестів

**Змінені файли:**
- `backend/grunt/core/db/system_tables.py` — додано `GruntNotificationRule`, `GruntNotification`
- `backend/grunt/core/hooks.py` — інтеграція evaluate_rules після after_insert/after_save/on_transition
- `backend/grunt/api/v1/router.py` — підключено notifications_router

**Логіка:**
- `NotificationRule` — doctype + event + recipients + condition + subject/message templates
- Recipients: `"owner"`, `"role:Manager"`, `"{field:assigned_to}"`, literal email
- Канали: system (WebSocket) + email (через EmailQueue)
- Condition: sandboxed eval Python-виразів (`doc.get('status') == 'Overdue'`)

### 5.2 — Версіювання документів ✅
**Мета:** JSON diff кожної зміни, відкат до будь-якої версії.

**Створені файли:**
- `backend/grunt/core/document/versioning.py` — `VersionService` (create_version, get_versions, build_restore_data)
- `backend/tests/test_versioning.py` — 9 тестів

**Змінені файли:**
- `backend/grunt/core/db/system_tables.py` — додано `GruntDocVersion` (doctype, doc_id, version, changes JSON, user)
- `backend/grunt/core/document/service.py` — автоматичне створення версії в `update_document()` якщо `dt.track_changes`
- `backend/grunt/api/v1/docs.py` — `GET /{doctype}/{doc_id}/versions`, `POST /{doctype}/{doc_id}/restore/{version_id}`

**Логіка:**
- `_compute_diff()` — field-level diff (old_value → new_value), пропускає modified_at/modified_by
- `build_restore_data()` — застосовує зворотні diff від найновішої версії до цільової
- Інтеграція: автоматично після flush в `DocumentService.update()`

### 5.3 — Naming Series ✅
**Мета:** Повноцінні паттерни нумерації документів (CONTR-.YYYY.-.####).

**Створені файли:**
- `backend/grunt/core/naming/__init__.py` — модуль, singleton `naming_service`
- `backend/grunt/core/naming/patterns.py` — `parse_pattern()`, `build_prefix()`, `format_name()`, `has_counter()`, `resolve_simple()`
- `backend/grunt/core/naming/service.py` — `NamingService.generate()`, `_next_counter()` (atomic SELECT...FOR UPDATE)
- `backend/tests/test_naming.py` — 19 тестів

**Змінені файли:**
- `backend/grunt/core/db/system_tables.py` — додано `GruntNamingSeries` (prefix + counter)
- `backend/grunt/core/document/service.py` — замінено `_apply_autoname()` на `NamingService.generate()`

**Підтримувані паттерни:**
- `PREFIX-.YYYY.-.MM.-.####` — дата-токени + лічильник
- `field:title` — значення поля як ім'я
- `hash` — UUID4
- `prompt` — ручне введення (з поля `name` в даних)

### 5.4 — i18n (інтернаціоналізація) ✅
**Мета:** Повна система перекладу на основі GNU gettext PO/POT.

**Створені файли:**
- `backend/grunt/core/i18n/__init__.py` — convenience functions `_()`, `ngettext()`, `pgettext()`
- `backend/grunt/core/i18n/service.py` — `TranslationService` з PO-парсером, plural forms, msgctxt, DB overrides
- `backend/grunt/core/i18n/locales/grunt.pot` — шаблон перекладу (всі рядки фреймворку)
- `backend/grunt/core/i18n/locales/uk/LC_MESSAGES/grunt.po` — українські переклади
- `backend/grunt/api/v1/translations.py` — `GET /translations/{locale}` (PO→JSON для фронтенду)
- `frontend/src/plugins/i18n.ts` — vue-i18n setup з lazy-load з бекенду
- `frontend/src/locales/uk.json`, `en.json` — fallback переклади
- `backend/tests/test_i18n.py` — 13 тестів

**Змінені файли:**
- `backend/grunt/core/db/system_tables.py` — додано `GruntTranslation` (source, language, translated, context)
- `backend/grunt/api/v1/router.py` — підключено translations_router

**Логіка:**
- Кастомний PO-парсер (без babel залежності): msgid/msgstr/msgctxt/plural forms
- Українські plural forms: 3 форми (1 документ, 2 документи, 5 документів)
- `ContextVar` для per-request мови
- DB overrides через `GruntTranslation` таблицю (пріоритет над PO-файлами)

### 5.5 — Print Formats / Генерація документів ✅
**Мета:** Генерація PDF/DOCX/XLSX з Jinja2 шаблонів.

**Створені файли:**
- `backend/grunt/core/print/templates/standard.html` — Jinja2 шаблон (секції, типи полів, стиль #2D6A4F)
- `backend/tests/test_print.py` — 32 тести

**Змінені файли:**
- `backend/grunt/core/db/system_tables.py` — додано `GruntPrintFormat` (doctype, template_type, template, is_default)
- `backend/grunt/core/print/renderer.py` — `render_standard()`, `render_from_string()`, `get_print_format_template()`, `render_docx()`, `_render_fallback()`
- `backend/grunt/api/v1/docs.py` — `GET /{doctype}/{doc_id}/print?fmt=html|pdf|xlsx|docx&print_format=...`

**Логіка:**
- HTML: Jinja2 шаблон → стандартний або кастомний PrintFormat з БД
- PDF: HTML → WeasyPrint
- DOCX: docxtpl шаблон (шлях зберігається в PrintFormat)
- XLSX: openpyxl (стилізована таблиця з полів DocType)
- Fallback: inline HTML якщо `standard.html` не знайдено

---

## Фаза 6: Advanced Features (план)

### 6.1 — Client Script / Server Script ✅
**Мета:** Написання логіки прямо в UI без деплою.

**Створені файли:**
- `backend/grunt/core/scripting/__init__.py` — модуль, singleton `server_script_runner`
- `backend/grunt/core/scripting/safe_globals.py` — sandbox: safe builtins, validation, blocked patterns
- `backend/grunt/core/scripting/server_script.py` — `ServerScriptRunner` (execute, load from DB, run events/API)
- `backend/grunt/core/scripting/client_script.py` — `get_client_scripts()` (load from DB per DocType)
- `backend/grunt/api/v1/scripting.py` — `GET /client-script/{doctype}`, `POST /method/{method}`
- `frontend/src/core/scripting/executor.ts` — Client Script runtime (FormProxy, GruntProxy, executeClientScripts)
- `backend/tests/test_scripting.py` — 28 тестів

**Змінені файли:**
- `backend/grunt/core/db/system_tables.py` — додано `GruntServerScript`, `GruntClientScript`
- `backend/grunt/core/hooks.py` — інтеграція Server Script виконання для DocType Events
- `backend/grunt/api/v1/router.py` — підключено scripting_router

**Логіка:**
- **Server Script** типи: DocType Event, API, Scheduler Event
- Sandbox: safe builtins (datetime, json, math, re), blocked (import, os, subprocess, eval, open)
- `grunt.response`, `grunt.throw()`, `grunt.flags`, `grunt.log()` — доступні в скриптах
- **Client Script**: JS виконується через `new Function()` з `cur_frm` і `grunt` proxy
- Events: `on_load`, `on_change`, `validate`, `before_save`, `after_save`

### 6.2 — Web Form ✅
**Мета:** Публічні форми для анонімних користувачів.

**Створені файли:**
- `backend/grunt/core/webform/__init__.py` — модуль, singleton `web_form_service`
- `backend/grunt/core/webform/service.py` — `WebFormService` (get_form, get_form_fields, submit, _validate_submission)
- `backend/grunt/api/v1/webform.py` — `GET /webform/{route}`, `POST /webform/{route}/submit` (без auth)
- `backend/tests/test_webform.py` — 10 тестів

**Змінені файли:**
- `backend/grunt/core/db/system_tables.py` — додано `GruntWebForm`
- `backend/grunt/api/v1/router.py` — підключено webform_router

**Логіка:**
- `GruntWebForm`: route, doctype, fields (JSON — вибрані поля), login_required, max_submissions
- Публічні endpoints без auth: `GET /webform/{route}`, `POST /webform/{route}/submit`
- Optional auth через Bearer token parsing (не обов'язково)
- Валідація: required fields, allowed fields filter, non-physical fields skip
- Submission створює документ в target DocType від імені user або guest

### 6.3 — Document Links / Backlinks ✅
**Мета:** Автоматичні зв'язки між документами.

**Створені файли:**
- `backend/grunt/core/document/links.py` — `LinkService` (sync_links, get_backlinks, delete_links)
- `backend/tests/test_links.py` — 6 тестів

**Змінені файли:**
- `backend/grunt/core/db/system_tables.py` — додано `GruntDocLink`
- `backend/grunt/core/hooks.py` — auto sync links on after_save/after_insert, delete on after_delete
- `backend/grunt/api/v1/docs.py` — додано `GET /{doctype}/{doc_id}/links`

**Логіка:**
- При збереженні: сканує Link поля → видаляє старі → створює нові записи в `grunt_doc_link`
- Backlinks: `source_doctype/source_id → target_doctype/target_id + link_fieldname`
- При видаленні: очищує всі links від і до документа

### 6.4 — Dashboard Charts / Number Cards ✅
**Мета:** Візуалізація на головній сторінці.

**Створені файли:**
- `backend/grunt/api/v1/dashboard.py` — повний API для charts і cards
- `backend/tests/test_dashboard.py` — 8 тестів

**Змінені файли:**
- `backend/grunt/core/db/system_tables.py` — додано `GruntDashboardChart`, `GruntNumberCard`
- `backend/grunt/api/v1/router.py` — підключено dashboard_router

**API:**
- `GET /dashboard/charts` — список charts
- `GET /dashboard/chart/{id}/data` — дані для графіка (labels + values)
- `GET /dashboard/cards` — список number cards
- `GET /dashboard/card/{id}/data` — значення для картки

**Логіка:**
- Chart: group_by або time-series (date_trunc month), timespan filter (last_week/month/quarter/year/all_time)
- Number Card: aggregation (count/sum/avg/min/max) + filters
- Aggregation через SQLAlchemy func

### 6.5 — Virtual DocType ✅
**Мета:** Підключення зовнішніх API як DocType.

**Створені файли:**
- `backend/grunt/core/metadata/virtual.py` — `VirtualDocType` base class
- `backend/tests/test_virtual_doctype.py` — 14 тестів

**Змінені файли:**
- `backend/grunt/core/metadata/doctype.py` — додано `is_virtual: bool = False`
- `backend/grunt/core/document/service.py` — virtual delegation в list/get/create/update/delete

**Логіка:**
- DocType з `is_virtual=True` — не створює таблицю в БД
- `VirtualDocType` base class з методами: get_list, get, create, update, delete, get_count
- `DocumentService` автоматично делегує CRUD до контролера якщо `is_virtual`
- Контролер реєструється через `document_registry` (як звичайний Document controller)

---

## Порівняльна таблиця: Frappe vs Ґрунт

| Аспект | Frappe | Ґрунт | Коментар |
|--------|--------|-------|----------|
| **Backend** | Python 3.10+ (sync Werkzeug) | Python 3.12+ (async FastAPI) | Ґрунт: async-first |
| **БД** | MariaDB (жорстка прив'язка) | PostgreSQL/SQLite/MySQL/MSSQL | Ґрунт: multi-DB |
| **ORM** | Кастомний (frappe.get_doc) | SQLAlchemy 2.0 async | Ґрунт: стандартна екосистема |
| **Frontend** | Кастомний JS (frappe-ui) | Vue 3 + TypeScript + Tailwind | Ґрунт: сучасний стек |
| **API** | REST + Whitelist RPC | REST v1 + WebSocket + OpenAPI | Ґрунт: типізований API |
| **Валідація** | Кастомна | Pydantic v2 | Ґрунт: стандартна |
| **Auth** | Cookie sessions + OAuth | JWT + bcrypt | Frappe: зріліша OAuth/SSO |
| **Multi-tenancy** | Bench (1 process = N sites) | SiteManager (per-site engine) | Обидва підтримують |
| **Background tasks** | Redis Queue / Celery | TaskIQ + APScheduler | Порівнянні |
| **Міграції** | Автоматичні (DocType sync) | Alembic + DocType compiler | Frappe: нульовий DX |
| **Workflow** | Вбудований + UI editor | WorkflowEngine + Vue editor | Frappe: зріліший |
| **Permissions** | 5 рівнів + User Permissions | RBAC + Row-level match | Frappe: глибша гранулярність |
| **Print Formats** | Jinja2 + wkhtmltopdf | Jinja2 + WeasyPrint/docxtpl/openpyxl | ✅ Реалізовано |
| **Email** | Повна підсистема | EmailAccount + EmailQueue + async SMTP | ✅ Реалізовано |
| **i18n** | Повна система (CSV) | PO/POT + gettext + plural forms | ✅ Реалізовано |
| **Нотифікації** | email/system/SMS/push | NotificationRule + system + email | ✅ Реалізовано |
| **Версіювання** | Amend + Version | GruntDocVersion (JSON diff + restore) | ✅ Реалізовано |
| **Naming Series** | Повна (autoname паттерни) | NamingService (PREFIX-.YYYY.-.####) | ✅ Реалізовано |
| **Client/Server Script** | В UI без деплою | Sandbox Python + JS executor | ✅ Реалізовано |
| **Web Form** | Публічні форми | WebFormService + public API | ✅ Реалізовано |
| **Document Links** | Автоматичні backlinks | LinkService + auto sync | ✅ Реалізовано |
| **Dashboard Charts** | Chart + Number Card | Aggregation API + config | ✅ Реалізовано |
| **Virtual DocType** | Зовнішні API як DocType | VirtualDocType base + delegation | ✅ Реалізовано |
| **Website Builder** | Вбудований | — | Не планується |

---

## Статус

| Фаза | Статус |
|------|--------|
| 1. Кастомні контролери | ✅ Завершено |
| 2. Глобальні хуки | ✅ Завершено |
| 3. Фонові завдання | ✅ Завершено |
| 4. Поштова підсистема | ✅ Завершено |
| 5. Імпорт / Експорт | ✅ Завершено |
| 6. Колаборація | ✅ Завершено |
| 7. Мультиорендність | ✅ Завершено |
| 5.1 Нотифікації | ✅ Завершено (12 тестів) |
| 5.2 Версіювання | ✅ Завершено (9 тестів) |
| 5.3 Naming Series | ✅ Завершено (19 тестів) |
| 5.4 i18n (PO/gettext) | ✅ Завершено (13 тестів) |
| 5.5 Print Formats | ✅ Завершено (32 тестів) |
| 6.1 Client/Server Script | ✅ Завершено (28 тестів) |
| 6.2 Web Form | ✅ Завершено (10 тестів) |
| 6.3 Document Links | ✅ Завершено (6 тестів) |
| 6.4 Dashboard Charts | ✅ Завершено (8 тестів) |
| 6.5 Virtual DocType | ✅ Завершено (14 тестів) |
