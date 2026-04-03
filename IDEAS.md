# Ґрунт — Ідеї для розвитку

> Файл для збору ідей. Не прив'язаний до фаз — тут все, що можна зробити.
> Статуси: 💡 ідея · 🔨 в роботі · ✅ зроблено

---

## 1. Незавершені речі з фаз (known gaps)

| # | Що | Пріоритет |
|---|-----|-----------|
| ✅ | **i18n** — uk/en переклади + Accept-Language middleware + remote translations | Середній |
| ✅ | **Naming Series** — авто-нумерація (INV-2024-0001) | Високий |
| ✅ | **Versioning** — UI панель версій + diff + відновлення в FormView | Середній |
| ✅ | **Client Scripts** — JS скрипти (вже інтегровані в FormView) | Середній |
| ✅ | **Server Scripts** — Python хуки + scheduler cron jobs | Середній |
| ✅ | **Web Forms** — публічна сторінка /form/:route з рендером і валідацією | Середній |
| ✅ | **Virtual DocTypes** — compiler пропускає sync_table для is_virtual | Низький |
| ✅ | **MkDocs документація** — генерація з docstrings | Низький |

---

## 2. Dashboard

| # | Що | Деталі |
|---|-----|--------|
| ✅ | **CalendarWidget** | Міні-calendar на дашборді, показує події/записи |
| ✅ | **TableWidget** | Pivot-таблиця: рядки/колонки/значення з DocType |
| ✅ | **FunnelWidget** | Воронка (Sales funnel, stages) |
| ✅ | **HeatmapWidget** | Теплова карта активності (GitHub-style) |
| ✅ | **ActivityWidget** | Стрічка активності як віджет дашборду |
| ✅ | **GlobalDateFilter** | Глобальний date-range фільтр для всього дашборду |
| ✅ | **Auto-refresh** | Налаштування інтервалу оновлення (30s/1m/5m) |
| ✅ | **Dashboard embedding** | iframe-код для вбудовування публічного дашборду |
| ✅ | **Dashboard PDF export** | Друк/збереження дашборду як PDF |

---

## 3. Документи та CRUD

| # | Що | Деталі |
|---|-----|--------|
| ✅ | **Import CSV/Excel** | Масовий імпорт документів з файлу |
| ✅ | **Export CSV/Excel** | Вивантаження списку з фільтрами |
| ✅ | **Bulk delete** | Вибір кількох записів → масове видалення |
| ✅ | **Bulk update field** | Масова зміна одного поля через діалог у BulkActionBar |
| ✅ | **Document Timeline** | Вкладка "Активність" у DocSidebar: хронологія ActivityLog + коментарі |
| ✅ | **Comments** | Коментарі в Timeline вкладці: додавання, видалення власних; backend `/comments` endpoints |
| ✅ | **Document Sharing** | Поділитись документом з конкретним user/role |
| ✅ | **Favorites / Bookmarks** | Кнопка закладки у DocSidebar, `Bookmark` doctype, `/bookmark` endpoints |
| ✅ | **Document Tags** | Довільні теги на будь-якому документі |
| ✅ | **Duplicate document** | Кнопка "Копіювати" у FormView |
| ✅ | **Revision history UI** | Переглядати і відновлювати старі версії документу |
| ✅ | **Comments & Mentions** | `@email` в коментарях → backend парсить mentions → Notification для кожного згаданого; dropdown автодоповнення у DocSidebar |
| ✅ | **Print Format Builder** | Сторінка `/list/PrintFormat/:id` — Jinja2 textarea + live iframe preview (debounce 800ms); `/docs/{doctype}/print-preview` POST endpoint; змінні-підказки по полях доктайпу; зразок документа |

---

## 4. ListView покращення

| # | Що | Деталі |
|---|-----|--------|
| ✅ | **Saved filters** | Зберегти поточний набір фільтрів як пресет |
| ✅ | **Column customizer** | Drag-and-drop стовпців, показати/сховати |
| ✅ | **Inline editing** | Редагувати поле прямо в таблиці (double click) |
| ✅ | **Group by** | Групування рядків за полем Select/Link |
| ✅ | **GalleryView** | Вигляд картками (як Notion Gallery) |
| ✅ | **TreeView** | Ієрархічний список (parent_field self-reference) |

---

## 5. Пошук і навігація

| # | Що | Деталі |
|---|-----|--------|
| ✅ | **Command Palette** | Cmd+K → пошук документів, переходи, дії |
| ✅ | **Global full-text search** | Пошук по всіх DocType одночасно (PostgreSQL tsvector) |
| 💡 | **Recent documents** | Останні відкриті в сайдбарі |
| 💡 | **Quick create** | Ctrl+N → швидке створення запису будь-якого DocType |
| 💡 | **Персоналізований сайдбар** | Пін улюблених пунктів меню, кастомні папки навігації, drag-and-drop порядок |

---

## 6. Нотифікації

| # | Що | Деталі |
|---|-----|--------|
| ✅ | **In-app сповіщення** | Bell icon + notification center у хедері |
| ✅ | **Email сповіщення** | Notification Rules → send email on event |
| ✅ | **Push-сповіщення** | Web Push API для браузера |
| ✅ | **Webhook відправка** | Outgoing webhook при create/update/submit |
| ✅ | **Digest email** | Щоденний/тижневий дайджест активності |

---

## 7. Автоматизація

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **Assignment Rules** | Автоматично призначати документ user/роль за умовою |
| 💡 | **Auto Repeat** | Створювати документ за розкладом (щомісяця) |
| 💡 | **Data Validation Rules** | Складні бізнес-правила без Python коду |
| 💡 | **Scheduled Jobs UI** | Управління фоновими задачами через UI |
| 💡 | **Event Triggers** | Перелік: подія → дія (без кодування) |

---

## 8. Звіти і аналітика

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **Pivot View** | Excel-подібна зведена таблиця прямо у ListView: групування по рядках/стовпцях, агрегація (count/sum/avg), export CSV |
| 💡 | **Quick Charts** | Кнопка "Chart" у ListView → бар/лінія/пай з поточними фільтрами; endpoint `/api/v1/analytics/aggregate` |
| 💡 | **AI-assisted reports** | Генерація SQL звіту з природної мови |
| 💡 | **Report Subscriptions** | Email звіт за розкладом (щопонеділка) |
| 💡 | **Cross-DocType Report** | JOIN кількох DocType в одному звіті |
| 💡 | **KPI Goals** | Задати ціль для метрики → прогрес-бар на дашборді |

---

## 9. Studio / Builder

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **DocType Import/Export JSON** | Скачати/завантажити DocType як JSON файл |
| 💡 | **Field dependency editor** | Візуальний редактор `depends_on` умов |
| 💡 | **Form Layout Templates** | Стандартні шаблони (1-col, 2-col, з табами) |
| 💡 | **Doctype Changelog** | Перегляд git-подібної історії змін схеми |
| 💡 | **Data Model Diagram** | Auto-generated ER діаграма зв'язків між DocType |

---

## 10. UI / Теми

| # | Що | Деталі |
|---|-----|--------|
| ✅ | **Real-time Presence** | Аватари користувачів у FormView, блокування полів, live-оновлення ListView через WebSocket |
| 💡 | **Theme Engine** | `ThemeSettings` singleton DocType: primary_color, accent_color, font_family, logo_url → генерує `/api/v1/theme.css`; live preview в адмін-формі |
| 💡 | **Per-user theme** | Light / Dark / System — незалежно від org-теми |

---

## 12. Безпека і адміністрування

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **Two-Factor Auth (2FA)** | TOTP (Google Authenticator) |
| 💡 | **SSO / OAuth2** | Вхід через Google, Microsoft, GitHub |
| 💡 | **IP Allowlist** | Обмеження доступу за IP |
| 💡 | **Session management** | Переглянути і завершити активні сесії |
| ✅ | **Audit Log Viewer** | UI для перегляду ActivityLog з фільтрами |
| 💡 | **Data anonymization** | Маскування полів для non-admin ролей |

---

## 13. Developer Experience

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **grunt shell** | Python REPL з preloaded context (як frappe shell) |
| 💡 | **grunt fixtures** | Зберегти/відновити тестові дані |
| 💡 | **grunt migrate --dry-run** | Показати що зміниться без застосування |
| 💡 | **API Playground** | Вбудований Swagger з авто-заповненням токену |
| 💡 | **DocType Test Generator** | Авто-генерація pytest тестів для DocType |
| 💡 | **Performance profiler** | Profiling slow queries у dev режимі |
| 💡 | **grunt bench** | Аналог frappe-bench: керування кількома apps |

---

## 14. Mobile / PWA

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **PWA підтримка** | Service Worker, offline cache, install prompt |
| 💡 | **Мобільна адаптація** | Адаптивний layout для FormView/ListView |
| 💡 | **Barcode/QR scanner** | Поле з camera input для сканування |
| ✅ | **Offline mode** | Запис у локальний IndexedDB + sync при підключенні |

---

## 15. Інтеграції

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **REST API Builder** | Декларативні custom endpoints без Python |
| 💡 | **Import from Frappe** | Міграційний інструмент DocType/data з Frappe |
| 💡 | **S3 File Storage** | Альтернатива локальному сховищу для files |
| ✅ | **SMTP конфігурація** | Налаштування через UI (EmailAccount doctype) |
| 💡 | **Telegram Bot** | Сповіщення і прості дії через бота |

---

## 16. "Все є DocType" — Frappe-підхід

> Ідея: проаналізувати Vue-фронтенд і максимально перенести хардкодні сторінки/налаштування у формат DocType — тобто керувати ними через звичайний FormView/ListView як і будь-яким іншим документом.
> Аудит проведено 2026-04-03. Знайдено 12 сторінок, 32 DocType JSON файли.

### Статус сторінок після аудиту

| Сторінка | Поточний стан | Завдання |
|----------|--------------|---------|
| `DocTypeList.vue` | ✅ Повністю на стандартному CRUD `/docs/{doctype}` | Нічого |
| `DocTypeForm.vue` | ✅ Повністю на стандартному CRUD | Нічого |
| `PrintFormatBuilder.vue` | ⚠️ `PrintFormat` DocType є, але builder — окрема сторінка з custom preview | Див. п. нижче |
| `DataImportPage.vue` | ⚠️ `DataImport` DocType є, але wizard — custom multi-step UI | Ок, wizard виправданий |
| `EmailSettingsPage.vue` | ⚠️ `EmailAccount` + `EmailQueue` DocType є, але окрема admin-сторінка | Замінити на ListView/FormView |
| `ActivityLogViewer.vue` | ⚠️ `ActivityLog` DocType є, але viewer — custom сторінка з custom endpoint `/activity/` | Замінити на ListView |
| `ReportView.vue` / `ReportList.vue` | ⚠️ `Report` DocType є, але endpoints custom (`/reports/{name}/run`) | Частково виправдано — потрібен runner |
| `RbacManager.vue` | ❌ Немає DocType — permissions зберігаються як поле DocType meta | Потрібен окремий `Permission` DocType або залишити |
| `HookManager.vue` | ❌ Чисто read-only introspection, немає DocType | Залишити як є (system view) |
| `FileManager.vue` | ❌ Немає `File` DocType — custom `/files/` endpoints | Потрібен `File` DocType |
| `DeskHome.vue` | ❌ Dashboard-like custom сторінка, дані з `/activity/recent` | Замінити або залишити |

### Конкретні задачі

| # | Що | Деталі |
|---|-----|--------|
| ✅ | **`ActivityLog` → стандартний ListView** | `ActivityLog` DocType є. Маршрут `/activity-log` → redirect до `/list/ActivityLog`. Sidebar-лінк оновлено |
| ✅ | **`EmailAccount` + `EmailQueue` → стандартний ListView/FormView** | Маршрут `/email-settings` → redirect до `/list/EmailAccount`. Sidebar-лінк оновлено |
| ✅ | **`File` DocType** | Створено `File.json`. `files.py` upload тепер також пише в File DocType table. GalleryView доступний через default_view. `files.py` delete прибирає File DocType запис |
| ✅ | **`PrintFormat` → FormView з Code editor** | Поле `template` змінено з `LongText` → `Code (html)`. Маршрут `print-format-builder` видалено з router — відкривається стандартний FormView |
| ✅ | **`Report` → FormView з Code editor** | Поля `query` та `script` змінено на `Code (sql/python)`. Секції показуються через `depends_on` залежно від `report_type` |
| ✅ | **`DocTypePermission` DocType** | Створено `DocTypePermission.json`. Startup мігрує permissions з DocType meta → таблицю, завантажує в пам'ять. Хук `after_save/after_delete` оновлює registry в реальному часі. Маршрут `rbac` → redirect до `/list/DocTypePermission` |
| ✅ | **`ScheduledJob`** | `ServerScript` з `script_type = "Scheduler Event"` вже виконує роль. `_register_server_script_jobs()` завантажує їх з БД при старті |
| ✅ | **Вбудований "grunt" workspace** | `grunt_workspace.json` оновлено: 8 секцій, 25+ DocType включно з File, DocTypePermission, OutgoingWebhook, PushSubscription, SystemSettings, Report, Users |
| 💡 | **`SystemSettings` як єдина точка входу** | Сторінки EmailSettings, Push, Security ще є окремими — можна перенести як секції SystemSettings FormView |
| 💡 | **ClientScript для PrintFormat preview** | Додати ClientScript що рендерить iframe preview при редагуванні шаблону |
| 💡 | **ClientScript для Report runner** | Додати кнопку "Запустити" через ClientScript в FormView Report |
| 💡 | **ClientScript для EmailAccount test** | Додати кнопку "Тест SMTP" через ClientScript в FormView EmailAccount |

---

_Останнє оновлення: 2026-04-03 (розділ 16 виконано)_
