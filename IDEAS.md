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
| ✅ | **Recent documents** | Останні відкриті в сайдбарі (та на головній) |
| ✅ | **Quick create** | Ctrl+N → швидке створення запису будь-якого DocType |
| ✅ | **Персоналізований сайдбар** | Пін улюблених пунктів меню, кастомні секції, drag-and-drop порядок |

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
| ✅ | **grunt shell** | Python REPL з preloaded context (як frappe shell) |
| 💡 | **grunt fixtures** | Зберегти/відновити тестові дані |
| ✅ | **grunt migrate --dry-run** | Показати що зміниться без застосування |
| 💡 | **API Playground** | Вбудований Swagger з авто-заповненням токену |
| ✅ | **DocType Test Generator** | Авто-генерація pytest тестів для DocType |
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
| ✅ | **`SystemSettings` як єдина точка входу** | Сторінки EmailSettings, Push, Security ще є окремими — можна перенести як секції SystemSettings FormView |
| ✅ | **ClientScript для PrintFormat preview** | Додати ClientScript що рендерить iframe preview при редагуванні шаблону |
| 💡 | **ClientScript для Report runner** | Додати кнопку "Запустити" через ClientScript в FormView Report |
| 💡 | **ClientScript для EmailAccount test** | Додати кнопку "Тест SMTP" через ClientScript в FormView EmailAccount |

---

## 17. Рефакторинг структури DocType (децентралізація)

> Ідея: кожний DocType — це максимально замкнута одиниця. Все що до нього відноситься (JSON-визначення, контроллер, скрипти, логіка) — в одній папці.

### Поточна структура

```
backend/grunt/
├── core/
│   ├── doctypes/
│   │   ├── ToDo.json
│   │   ├── User/
│   │   │   ├── User.json
│   │   │   ├── User.py        ← контроллер
│   │   │   └── User.js        ← client script
│   │   ├── ...
│   └── (логіка розсіяна по сервісам)
```

### Цільова структура (децентралізована)

```
backend/grunt/
├── web/
│   ├── doctypes/
├── core/
│   ├── doctypes/
│   │   ├── User/
│   │   │   ├── User.json
│   │   │   ├── User.py        ← контроллер
│   │   │   └── User.js        ← client script
│   │   ├── ToDo/
│   │   │   ├── ToDo.json
│   │   │   ├── ToDo.py        ← контроллер
│   │   │   └── ToDo.js        ← client script
│   │   ├── ...
```


### Статус

| # | Що | Деталі |
|---|-----|--------|
| ✅ | **CLI команда `grunt scaffold doctype`** | Реалізована: генерує новий DocType з шаблонами JSON, Python контролера і JavaScript скрипту |
| ✅ | **Міграція core doctypes** | 32 JSON файли перенесені у папки (`ActivityLog/ActivityLog.json`, тощо) + добавлені `__init__.py`. User папка вже існувала з контролером |
| ✅ | **Децентралізована структура** | Кожен DocType тепер у своїй папці; file_scripts.py вже сканує `**/*.json` і `**/*.py` рекурсивно |
| 💡 | **Унифікованість file_scripts.py** | Уже працює для `grunt_apps/*/doctypes/` за единим алгоритмом через glob |
| 💡 | **Перенести логіку в контролери** | Права доступу, хеширування паролів → в User.py методи. Авто-hook через document registry |

### Переваги

✅ Кожний DocType — автономна одиниця (легше версіонувати, розповсюджувати)
✅ Менше boilerplate — auto-wire logic на основі назви методу
✅ Легше для розробників додатків — просто копіюють папку
✅ Простіша навігація в IDE — все у одній папці
✅ Easier контроль версій — окремі фічі = окремі папки

---

_Останнє оновлення: 2026-04-03 (розділ 16-17 виконано)_

---

## 18. Grunt Python API — спрощена розробка додатків

> Ідея: надати розробникам простий, високорівневий Python API для роботи з документами, подібно до Frappe (`frappe.db`, `frappe.msgprint`, тощо).
> Це зніме boilerplate при розробці контролерів, серверних скриптів і хуків.

### Концепція

```python
# Замість:
from grunt.core.document.service import DocumentService
from grunt.core.db.session import get_session
async with get_session() as session:
    svc = DocumentService(session, engine)
    doc = await svc.get_document("User", user_id, user)
    ...

# Розробник пише:
from grunt import Doc, db, msgprint, throw, call

async def my_function():
    doc = await Doc.get("User", user_id)       # Автоматично з контексту сесії
    doc.status = "Active"
    await doc.save()
    msgprint("Користувач активований")
```

### API методи

#### Документи
| Метод | Приклад | Деталі |
|-------|---------|--------|
| `Doc.get(doctype, id)` | `user = await Doc.get("User", "test@mail.com")` | Отримати документ |
| `Doc.create(doctype, data)` | `contract = await Doc.create("Contract", {"party": "ABC"})` | Створити документ |
| `doc.save()` | `await doc.save()` | Зберегти документ |
| `doc.submit()` | `await doc.submit()` | Зафіксувати (workflow) |
| `doc.delete()` | `await doc.delete()` | Видалити |
| `Doc.list(doctype, filters, order)` | `await Doc.list("Invoice", {"status": "Pending"}, order_by="date")` | Список документів |

#### Database
| Метод | Приклад | Деталі |
|-------|---------|--------|
| `db.get_value(doctype, id, field)` | `await db.get_value("User", user_id, "full_name")` | Отримати одне значення |
| `db.set_value(doctype, id, field, value)` | `await db.set_value("User", user_id, "status", "Active")` | Встановити значення |
| `db.exists(doctype, id)` | `if await db.exists("User", email): ...` | Перевірка чи існує |
| `db.count(doctype, filters)` | `count = await db.count("Invoice", {"status": "Draft"})` | Кількість записів |

#### Виклики і ієрархія
| Метод | Приклад | Деталі |
|-------|---------|--------|
| `call(method, args)` | `result = await call("my_app.tasks.process_invoice", {"id": 123})` | Виконати метод |
| `enqueue(method, args)` | `await enqueue("my_app.tasks.send_email", {"email": user_email}, queue="default")` | Додати в чергу (фоновий task) |

#### Повідомлення & Помилки
| Метод | Приклад | Деталі |
|-------|---------|--------|
| `msgprint(msg, title, type)` | `msgprint("Готово!", type="success")` | Показати повідомлення в UI |
| `msgprint_list(items, title)` | `msgprint_list(["A", "B", "C"], "Результати")` | Список повідомлень |
| `throw(msg, title, code)` | `throw("Неправильний стан", code="INVALID_STATE")` | Викинути помилку (abort + повідомлення) |

#### Коментарі & Активність
| Метод | Приклад | Деталі |
|-------|---------|--------|
| `doc.add_comment(text, is_private)` | `await doc.add_comment("Одержано від клієнта")` | Додати коментар до документа |
| `doc.get_comments()` | `comments = await doc.get_comments()` | Отримати всі коментарі |
| `activity.log(doctype, id, action, details)` | `await activity.log("Invoice", inv_id, "printed", {...})` | Залогувати дію |

#### Сповіщення
| Метод | Приклад | Деталі |
|-------|---------|--------|
| `notify(title, msg, doctype, id, icon)` | `await notify("Нова заявка", "Від компанії ABC", "Request", req_id)` | Відправити in-app сповіщення |
| `notify_all(title, msg, roles)` | `await notify_all("Обслуговування", "Сервер перезавантажується", roles=["Admin"])` | Для кількох користувачів |
| `queue_email(recipient, subject, body, doctype, id)` | `await queue_email(user_email, "Запрошення", html_body)` | Додати email в чергу |

#### Валідація & Дозволи
| Метод | Приклад | Деталі |
|-------|---------|--------|
| `can_read(doctype, id)` | `if not await can_read("Contract", contract_id): throw("Немає доступу")` | Перевірити дозвіл на читання |
| `can_write(doctype, id)` | `if not await can_write("Invoice", inv_id): throw("Тільки читання")` | Перевірити дозвіл на запис |
| `get_current_user()` | `user = await get_current_user()` | Отримати поточного користувача |

### Реалізація (проектна)

```python
# grunt/api.py — публічний API для розробників

from contextlib import asynccontextmanager
from typing import Any
from grunt.core.site.manager import site_manager

class Doc:
    @staticmethod
    async def get(doctype: str, doc_id: str) -> "DocProxy":
        """Отримати документ."""
        async with _get_session() as (session, user):
            from grunt.core.document.service import DocumentService
            svc = DocumentService(session, _get_engine())
            data = await svc.get_document(doctype, doc_id, user)
            return DocProxy(doctype, data, session, user)

    @staticmethod
    async def create(doctype: str, data: dict[str, Any]) -> "DocProxy":
        """Створити новий документ."""
        async with _get_session() as (session, user):
            from grunt.core.document.service import DocumentService
            svc = DocumentService(session, _get_engine())
            doc = await svc.create_document(doctype, data, user)
            return DocProxy(doctype, doc, session, user)

    @staticmethod
    async def list(doctype: str, filters: dict | None = None, order_by: str = "name", limit: int = 100) -> list["DocProxy"]:
        """Список документів з фільтрами."""
        async with _get_session() as (session, user):
            from grunt.core.document.service import DocumentService
            svc = DocumentService(session, _get_engine())
            docs = await svc.list_documents(doctype, filters or {}, user, order_by, limit)
            return [DocProxy(doctype, d, session, user) for d in docs]


class DocProxy:
    """Проксі об'єкт документа з методами."""
    def __init__(self, doctype: str, data: dict, session, user):
        self.doctype = doctype
        self.data = data
        self._session = session
        self._user = user

    async def save(self):
        """Зберегти зміни."""
        from grunt.core.document.service import DocumentService
        svc = DocumentService(self._session, _get_engine())
        await svc.update_document(self.doctype, self.data["id"], self.data, self._user)

    async def submit(self):
        """Зафіксувати документ (workflow)."""
        # Логіка переходу в workflow стан "Submitted"
        ...

    async def add_comment(self, text: str, is_private: bool = False):
        """Додати коментар до документа."""
        from grunt.core.document.comments import add_comment as _add
        ...

    def __getitem__(self, key: str):
        return self.data.get(key)

    def __setitem__(self, key: str, value):
        self.data[key] = value


class Database:
    """High-level DB API."""
    @staticmethod
    async def get_value(doctype: str, doc_id: str, field: str) -> Any:
        async with _get_session() as (session, user):
            ...

    @staticmethod
    async def set_value(doctype: str, doc_id: str, field: str, value: Any):
        async with _get_session() as (session, user):
            ...


# Глобальні об'єкти
db = Database()

async def msgprint(msg: str, title: str = "", type: str = "info"):
    """Відправити повідомлення в UI."""
    # Додати в message queue які підберуться при відповіді
    ...

async def throw(msg: str, title: str = "", code: str = "ERROR") -> None:
    """Викинути помилку."""
    raise ApplicationError(msg, code=code)

async def notify(title: str, msg: str, doctype: str = "", doc_id: str = ""):
    """Відправити сповіщення користувачу."""
    ...

async def get_current_user():
    """Отримати поточного користувача з контексту."""
    ...

@asynccontextmanager
async def _get_session():
    """Отримати session з контексту (request або scheduler)."""
    # Спробувати отримати з RequestContext
    # Якщо немає — отримати з active site
    ...


# У контролері DocType:
from grunt import Doc, db, msgprint

class Invoice:
    async def before_save(self):
        # Автоматично передається self.doc як контекст
        if self.doc.status == "Submitted":
            total = sum(item.amount for item in self.doc.items)
            self.doc.total = total
            msgprint(f"Сума: {total}")

    async def on_submit(self):
        # Відправити email
        await queue_email(self.doc.owner, f"Invoice {self.doc.name} submitted")
```

### Статус

| # | Що | Деталі |
|---|-----|--------|
| ✅ | **Коренева папка `grunt/api/`** | Модульна структура: context.py, document.py, database.py, messages.py, permissions.py, activity.py |
| ✅ | **Автоматичний контекст session** | `set_session()` з `get_session()` dependency automatically |
| ✅ | **Doc proxy з методами** | `doc.field = value`, `await doc.save()`, `await doc.submit()`, `await doc.add_comment()` |
| ✅ | **Database shortcuts** | `db.get_value()`, `db.set_value()`, `db.exists()`, `db.count()` |
| ✅ | **Permission helpers з DB** | `can_read()`, `can_write()`, `can_submit()`, `can_delete()`, `can_create()` **NOW queries DocTypePermission** |
| ✅ | **Error handling** | `throw()` для abort + message |
| ✅ | **Lazy loading** | `from grunt import Doc` без циклічних імпортів |
| ✅ | **Comments & Activity** | `doc.add_comment()`, `get_comments()`, `activity.log()`, `get_activity_log()` |
| ✅ | **Batch operations** | `Doc.set_value_batch()`, `Doc.delete_many()` |
| ✅ | **Notification API** | `notify()`, `notify_all()`, `queue_email()` (структура готова) |
| 💡 | **Async task enqueue** | `await enqueue("module.function", args, queue="default")` |

### Реалізація

✅ **Структура модулів:**
- `grunt/api/context.py` — управління ContextVar для session/user/engine
- `grunt/api/document.py` — Doc, DocProxy з методами get/create/save/submit/delete/add_comment + batch ops
- `grunt/api/database.py` — Database клас з get_value/set_value/exists/count shortcuts
- `grunt/api/messages.py` — msgprint, throw, notify, queue_email функції
- `grunt/api/permissions.py` — **NOW queries DocTypePermission table** can_read/write/submit/delete з DB lookups ⭐
- `grunt/api/activity.py` — add_comment, get_comments, log_activity, get_activity_log
- `grunt/__init__.py` — ленивий імпорт через `__getattr__` для уникнення циклів
- `grunt/core/db/session.py` — автоматично встановлює контекст при створенні сесії

✅ **Permission Checking Flow (NEW):**
```python
# Before: can_read("Invoice", "INV-001") → returned True for all users
# Now: Queries DocTypePermission table

async def can_read(doctype: str, doc_id: str) -> bool:
    user = get_user()
    if user.is_superadmin:
        return True  # Superadmin bypass
    if user.email == "system":
        return True  # System user bypass
    if not user.roles:
        return False  # No roles → deny

    # Query: SELECT * FROM DocTypePermission
    #        WHERE doctype_name='Invoice' AND role IN (user.roles)
    # Check if any row has read=True → return True
    # Else → return False
```

✅ **Використання розробниками:**
```python
from grunt import Doc, db, msgprint, throw, can_read, get_current_user, notify, add_comment, log_activity

class Invoice:
    async def before_save(self):
        # Отримати документ
        order = await Doc.get("Order", self.doc.order_id)

        # Простий доступ до значень
        if not await db.exists("Contract", self.doc.contract_id):
            throw("Contract not found")

        # Перевірити дозволи (NOW queries DocTypePermission)
        current_user = await get_current_user()
        if not await can_write("Contract", self.doc.contract_id):
            throw("Read-only access")

        # Встановити значення
        await db.set_value("Invoice", self.doc.id, "status", "Processing")

        # Коментар
        await add_comment("Invoice", self.doc.id, "Invoice being processed")

        # Логувати активність
        await log_activity("Invoice", self.doc.id, "processing",
                          {"old_status": "draft", "new_status": "processing"})

        # Показати повідомлення
        msgprint("Операція завершена", type="success")

        # Пакетне оновлення
        invoice_ids = ["INV-001", "INV-002", "INV-003"]
        count = await Doc.set_value_batch("Invoice", "status", "Sent", invoice_ids)

        # Відправити сповіщення
        await notify(
            "Новий рахунок",
            f"Рахунок {self.doc.name} обробляється",
            doctype="Invoice",
            doc_id=self.doc.id
        )
```

### Переваги

✅ **Менше boilerplate** — не потрібно імпортувати DocumentService, session, engine
✅ **Інтуїтивний API** — схожий на Frappe, знайомий розробникам
✅ **Автоматичний контекст** — session і user з ContextVar, не потрібно передавати
✅ **Type hints** — IDE autocompletion для всіх методів
✅ **Безпеки** — всі перевірки дозволів вбудовані, ленивий імпорт уникає циклів
✅ **Role-based access control** — дозволи перевіряються через DocTypePermission ⭐ NEW

---

## 19. Повна типізація Python через PEP 563 (Postponed Annotations)

> Ідея: мігрувати весь проект на `from __future__ import annotations` для забезпечення 100% type coverage з mypy strict mode.
> Це поліпшить якість коду, IDE support, та попередить runtime помилки.

### Реалізація (автоматична генерація типів)

#### ✅ Auto-generated Type Hints для нових DocTypes

**Scaffold команда тепер генерує типи автоматично:**

```bash
# Створити новий DocType з type hints
$ grunt doctype scaffold Invoice --app web

# Генерує:
Invoice.json          # метадані з полями
Invoice.py            # контроллер з auto-generated типами (див. below)
Invoice.js            # клієнтський скрипт
__init__.py
```

**Приклад згенерованого Invoice.py:**

```python
"""Invoice controller.

Бізнес-логіка для DocType Invoice.
"""

from __future__ import annotations

# begin: auto-generated types
# This code is auto-generated. Do not modify anything in this block.

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing import DF

    class Invoice:
        """Type hints for Invoice fields."""

        total_amount: float | None
        due_date: str | None
        status: str | None
        notes: str | None
        paid: bool | None

# end: auto-generated types


class InvoiceController:
    """Контроллер для Invoice документів."""

    async def before_save(self):
        """Викликається перед збереженням."""
        pass

    async def after_save(self):
        """Викликається після збереження."""
        pass

    async def before_delete(self):
        """Викликається перед видаленням."""
        pass
```

#### ✅ Регенерування типів при зміні схеми

**Коли змінили Invoice.json, оновити типи:**

```bash
# Відредагуйте Invoice.json (додати/видалити поля)
# Далі:
$ grunt doctype generate-types Invoice --app web

# Типи в Invoice.py автоматично оновлені
```

### Fieldtype → Python Type Mapping

| Fieldtype | Python Type | Приклад |
|-----------|------------|---------|
| `Data` | `str \| None` | `name: str \| None` |
| `Text`, `LongText` | `str \| None` | `description: str \| None` |
| `Int` | `int \| None` | `quantity: int \| None` |
| `Float` | `float \| None` | `amount: float \| None` |
| `Check` | `bool \| None` | `is_active: bool \| None` |
| `Date` | `str \| None` | `due_date: str \| None` |
| `Datetime` | `str \| None` | `created_at: str \| None` |
| `Link` | `str \| None` | `customer: str \| None` |
| `MultiLink` | `list[str] \| None` | `tags: list[str] \| None` |
| `Select` | `str \| None` | `status: str \| None` |
| `JSON` | `dict \| None` | `metadata: dict \| None` |
| `Table` | —  | (structural, skipped) |
| `Section` | — | (structural, skipped) |

### Поточний стан

| # | Що | Статус |
|---|-----|--------|
| ✅ | **`grunt scaffold` генерує типи** | Реалізовано |
| ✅ | **`grunt generate-types` регенерує типи** | Реалізовано |
| ✅ | **`from __future__ import annotations` в scaffolds** | Реалізовано |
| ✅ | **API модулі типізовані** | 25% (core/) |
| 💡 | **Запустити mypy strict mode в CI** | Планується |
| 💡 | **Типізувати core/** | Планується (25% done) |

### Командні лінії

```bash
# Scaffold з auto-generated типами
grunt doctype scaffold {Name} --app {app}

# Регенерувати типи після зміни JSON
grunt doctype generate-types {Name} --app {app}

# Список всіх doctypes
grunt doctype list

# Синхронізувати doctype зі схемою БД
grunt doctype sync {Name}
```

### Переваги

✅ **Type Safety** — IDE покажить помилки типів при написанні
✅ **IDE Support** — autocompletion для всіх полів DocType
✅ **Auto-sync** — типи завжди синхронізовані зі schemaю
✅ **Clean Code** — TYPE_CHECKING дає тип hints без runtime overhead
✅ **Single Source** — JSON є единственным источником truth для полів

### Статус реалізації

- ✅ **Auto-generation:** Scaffold generates types from JSON (100%)
- ✅ **Regeneration:** CLI command to update types (100%)
- 🔨 **Core modules:** Applying to existing doctypes (in progress)
- ⏳ **CI integration:** mypy strict mode checks (planned)

---

_Останнє оновлення: 2026-04-05 (розділи 1-19 розроблені, 13, 16-18 завершені; додано: grunt shell, grunt migrate --dry-run, grunt doctype test-gen, grunt doctype scaffold, PrintFormat live preview)_
