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
