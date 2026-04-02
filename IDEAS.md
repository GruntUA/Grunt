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
| 💡 | **MkDocs документація** — генерація з docstrings | Низький |

---

## 2. Dashboard

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **CalendarWidget** | Міні-calendar на дашборді, показує події/записи |
| 💡 | **TableWidget** | Pivot-таблиця: рядки/колонки/значення з DocType |
| 💡 | **FunnelWidget** | Воронка (Sales funnel, stages) |
| 💡 | **HeatmapWidget** | Теплова карта активності (GitHub-style) |
| ✅ | **ActivityWidget** | Стрічка активності як віджет дашборду |
| 💡 | **GlobalDateFilter** | Глобальний date-range фільтр для всього дашборду |
| 💡 | **Auto-refresh** | Налаштування інтервалу оновлення (30s/1m/5m) |
| 💡 | **Dashboard embedding** | iframe-код для вбудовування публічного дашборду |
| 💡 | **Dashboard PDF export** | Друк/збереження дашборду як PDF |

---

## 3. Документи та CRUD

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **Import CSV/Excel** | Масовий імпорт документів з файлу |
| 💡 | **Export CSV/Excel** | Вивантаження списку з фільтрами |
| 💡 | **Bulk actions** | Вибір кількох записів → масове видалення/оновлення поля |
| 💡 | **Document Timeline** | Права панель: хронологія змін, коментарі, вкладення |
| 💡 | **Comments & Mentions** | @username в коментарях → сповіщення |
| 💡 | **Document Sharing** | Поділитись документом з конкретним user/role |
| 💡 | **Favorites / Bookmarks** | "Зірочка" на документ → швидкий доступ |
| 💡 | **Document Tags** | Довільні теги на будь-якому документі |
| ✅ | **Duplicate document** | Кнопка "Копіювати" у FormView |
| 💡 | **Revision history UI** | Переглядати і відновлювати старі версії документу |
| 💡 | **Print Format Builder** | Візуальний редактор шаблонів друку (HTML/Jinja) |

---

## 4. ListView покращення

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **Saved filters** | Зберегти поточний набір фільтрів як пресет |
| 💡 | **Column customizer** | Drag-and-drop стовпців, показати/сховати |
| 💡 | **Inline editing** | Редагувати поле прямо в таблиці (double click) |
| 💡 | **Group by** | Групування рядків за полем Select/Link |
| 💡 | **GalleryView** | Вигляд картками (як Notion Gallery) |
| 💡 | **TreeView** | Ієрархічний список (parent_field self-reference) |

---

## 5. Пошук і навігація

| # | Що | Деталі |
|---|-----|--------|
| ✅ | **Command Palette** | Cmd+K → пошук документів, переходи, дії |
| 💡 | **Global full-text search** | Пошук по всіх DocType одночасно (PostgreSQL tsvector) |
| 💡 | **Recent documents** | Останні відкриті в сайдбарі |
| 💡 | **Quick create** | Ctrl+N → швидке створення запису будь-якого DocType |

---

## 6. Нотифікації

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **In-app сповіщення** | Bell icon + notification center у хедері |
| 💡 | **Email сповіщення** | Notification Rules → send email on event |
| 💡 | **Push-сповіщення** | Web Push API для браузера |
| 💡 | **Webhook відправка** | Outgoing webhook при create/update/submit |
| 💡 | **Digest email** | Щоденний/тижневий дайджест активності |

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

## 10. Безпека і адміністрування

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **Two-Factor Auth (2FA)** | TOTP (Google Authenticator) |
| 💡 | **SSO / OAuth2** | Вхід через Google, Microsoft, GitHub |
| 💡 | **IP Allowlist** | Обмеження доступу за IP |
| 💡 | **Session management** | Переглянути і завершити активні сесії |
| ✅ | **Audit Log Viewer** | UI для перегляду ActivityLog з фільтрами |
| 💡 | **Data anonymization** | Маскування полів для non-admin ролей |

---

## 11. Developer Experience

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

## 12. Mobile / PWA

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **PWA підтримка** | Service Worker, offline cache, install prompt |
| 💡 | **Мобільна адаптація** | Адаптивний layout для FormView/ListView |
| 💡 | **Barcode/QR scanner** | Поле з camera input для сканування |
| 💡 | **Offline mode** | Запис у локальний IndexedDB + sync при підключенні |

---

## 13. Інтеграції

| # | Що | Деталі |
|---|-----|--------|
| 💡 | **REST API Builder** | Декларативні custom endpoints без Python |
| 💡 | **Import from Frappe** | Міграційний інструмент DocType/data з Frappe |
| 💡 | **S3 File Storage** | Альтернатива локальному сховищу для files |
| 💡 | **SMTP конфігурація** | Налаштування через UI (EmailAccount doctype) |
| 💡 | **Telegram Bot** | Сповіщення і прості дії через бота |

---

_Останнє оновлення: 2026-04-02_
