# Ґрунт — Фази Розробки (Claude Code Build Plan)

> Цей файл — детальний план для Claude Code. Кожна фаза закінчується робочим демо.
> Виконуй фази послідовно. Не починай наступну до завершення попередньої.

---

## ФАЗА 1: Metadata Engine + Basic CRUD

**Мета:** `grunt serve` → можна визначити DocType через API і зберегти документ.

### 1.1 — Проєктна структура
```
Створи повну структуру директорій згідно CLAUDE.md §3.
Додай .env.example, .gitignore (python + node + vscode).
```

### 1.2 — Config та DB Session
```
backend/grunt/config.py         ← Settings з pydantic-settings
backend/grunt/core/db/session.py ← async engine + session factory
backend/grunt/core/db/base.py   ← Base SQLAlchemy model з id, created_at, etc.
```

Перевірка: `from grunt.config import settings` без помилок.

### 1.3 — DocType Model (Pydantic)
```
backend/grunt/core/metadata/doctype.py  ← всі класи з ARCHITECTURE.md §1
backend/grunt/core/metadata/field.py    ← FieldType enum + DocField
```

Перевірка: можна створити DocType з полями через Python.

### 1.4 — DocType Compiler
```
backend/grunt/core/metadata/compiler.py  ← з ARCHITECTURE.md §2
```

Тест: DocType з 5 різними fieldtype → коректна SQLAlchemy Table.

### 1.5 — DocType Registry
```python
# backend/grunt/core/metadata/registry.py

class DocTypeRegistry:
    """Singleton реєстр усіх DocTypes. Завантажує з БД при старті."""
    
    _instance: dict[str, DocType] = {}
    
    async def load_all(self): ...       # завантажити з таблиці grunt_meta_doctype
    async def get(self, name) -> DocType: ...
    async def register(self, dt: DocType): ...  # зберегти + скомпілювати
    async def sync(self, name: str): ...        # застосувати міграцію через Alembic
```

### 1.6 — Alembic Setup + System Tables
```
backend/grunt/core/db/migrations/     ← Alembic директорія
alembic.ini

Системні таблиці (статичні, не DocType):
- grunt_meta_doctype    ← зберігає DocType як JSON
- grunt_auth_user       ← користувачі
- grunt_auth_role       ← ролі
- grunt_auth_user_role  ← M2M
- grunt_files           ← завантажені файли
```

### 1.7 — Auth
```
backend/grunt/core/auth/models.py        ← User, Role SQLAlchemy моделі
backend/grunt/core/auth/service.py       ← create_user, authenticate, hash_password
backend/grunt/core/auth/dependencies.py  ← current_user FastAPI dependency
backend/grunt/api/v1/auth.py             ← POST /auth/register, POST /auth/token
```

JWT токени. Перевірка: `POST /auth/token` → отримати token → використати в header.

### 1.8 — Meta API (/meta/*)
```
backend/grunt/api/v1/meta.py

Endpoints:
GET    /api/v1/meta/doctypes
POST   /api/v1/meta/doctypes        ← валідація + registry.register() + sync()
GET    /api/v1/meta/doctypes/{name}
PUT    /api/v1/meta/doctypes/{name} ← оновити + sync()
DELETE /api/v1/meta/doctypes/{name}
POST   /api/v1/meta/doctypes/{name}/sync  ← примусова синхронізація з БД
```

### 1.9 — Document API (/docs/*)
```
backend/grunt/api/v1/docs.py

Endpoints (динамічні — приймають будь-який doctype):
GET    /api/v1/docs/{doctype}           ← list з ?page, ?filter, ?sort, ?search
POST   /api/v1/docs/{doctype}           ← create
GET    /api/v1/docs/{doctype}/{id}      ← get one
PUT    /api/v1/docs/{doctype}/{id}      ← update
DELETE /api/v1/docs/{doctype}/{id}      ← delete

DocumentService:
- Читає DocType з registry
- Виконує queries через dynamic Table (з compiler)
- Валідує required поля, типи, унікальність
- Встановлює owner, created_at, modified_at автоматично
```

### 1.10 — CLI базовий
```
backend/grunt/cli/main.py   ← click group "grunt"

grunt init                  ← створити .env, ініціалізувати БД, створити admin
grunt serve                 ← запустити uvicorn + vite dev (через subprocess)
grunt db migrate            ← запустити Alembic upgrade head
grunt db reset              ← скинути всі таблиці (тільки якщо DEBUG=true)
```

### 1.11 — Vue: базова структура
```
frontend/src/
├── main.ts                 ← createApp, plugins
├── App.vue                 ← router-view
├── core/api/
│   ├── client.ts           ← Axios instance з interceptors
│   ├── meta.ts             ← api.meta.* методи
│   └── docs.ts             ← api.docs.* методи
├── stores/
│   ├── auth.ts             ← useAuthStore (token, user, login, logout)
│   └── doctype.ts          ← useDocTypeStore
├── pages/
│   ├── auth/Login.vue
│   └── desk/
│       ├── DeskHome.vue
│       └── [doctype]/
│           ├── ListView.vue    ← таблиця + пагінація
│           └── FormView.vue    ← форма (без builder, просто render)
└── router/index.ts
```

### 1.12 — Design System: базові компоненти
```
frontend/src/components/ui/
├── GButton.vue         ← primary, secondary, danger, ghost variants
├── GInput.vue          ← text input з label + error
├── GSelect.vue         ← dropdown
├── GModal.vue          ← dialog з backdrop
├── GBadge.vue          ← статус badge з кольором
├── GSpinner.vue        ← loading spinner
├── GTable.vue          ← таблиця з сортуванням
└── GToast.vue          ← повідомлення (success/error/info)
```

**Дизайн:** темно-зелений акцент (#2D6A4F), нейтральний сірий, чисті рядки.
Натхнення: Linear, Notion, Retool — мінімалізм + функціональність.

### ✅ Фаза 1 Done Criteria
- [ ] `grunt init && grunt serve` → сервер на :8000, Vite на :5173
- [ ] `POST /auth/token` → JWT
- [ ] `POST /api/v1/meta/doctypes` → DocType створено, таблиця в БД
- [ ] `POST /api/v1/docs/{doctype}` → документ збережено
- [ ] `GET /api/v1/docs/{doctype}` → список документів
- [ ] Login через Vue UI → бачимо список DocTypes

---

## ФАЗА 2: Form Builder + Views

**Мета:** Візуальний конструктор форм. Drag-and-drop. Усі типи полів.

### 2.1 — Field Renderers

Для кожного FieldType — Vue компонент рендеру:

```
frontend/src/components/fields/
├── FieldText.vue
├── FieldLongText.vue
├── FieldInt.vue
├── FieldFloat.vue
├── FieldCheck.vue
├── FieldDate.vue
├── FieldDatetime.vue
├── FieldSelect.vue
├── FieldLink.vue           ← autocomplete пошук по DocType
├── FieldAttach.vue         ← upload + preview
├── FieldImage.vue
├── FieldRichText.vue       ← Tiptap editor
├── FieldTable.vue          ← child table (inline grid)
└── FieldJson.vue
```

Кожен компонент: `v-model`, `field: DocField`, `disabled` prop.

### 2.2 — Dynamic Form Renderer

```
frontend/src/core/renderer/
├── FormRenderer.vue        ← рендерить форму з DocType.fields[]
├── SectionRenderer.vue     ← Section + Column layout
└── FieldRenderer.vue       ← динамічно обирає компонент за fieldtype
```

FormRenderer розуміє структуру Section/Column/Tab і рендерить grid.

### 2.3 — ListView повна версія

```
Функціональність:
- Колонки з in_list_view полів
- Сортування кліком на заголовок
- Пагінація
- Рядок фільтрів (filter bar)
- Пошук
- Bulk actions (select + delete)
- Кнопка "Новий документ"
- Посилання на FormView
```

### 2.4 — FormView повна версія

```
Функціональність:
- Breadcrumb навігація
- Заголовок документа (title_field)
- FormRenderer з усіма полями
- Кнопки: Зберегти, Скасувати, Видалити
- Відображення помилок валідації
- Auto-save індикатор
- Workflow кнопки (якщо є)
- Прикріплені файли (Attach)
```

### 2.5 — App Studio: Form Builder

```
frontend/src/pages/studio/
├── StudioLayout.vue            ← layout з сайдбаром
├── DocTypeList.vue             ← список DocTypes
└── builder/
    ├── BuilderLayout.vue       ← 3-колонковий layout
    ├── BuilderCanvas.vue       ← drag-and-drop зона
    ├── FieldPalette.vue        ← palette типів полів
    ├── PropertiesPanel.vue     ← властивості поля
    └── BuilderPreview.vue      ← live preview форми
```

Builder зберігає стан в Pinia store.
Авто-збереження через debounce (1.5 сек після зміни).

### 2.6 — KanbanView

```
frontend/src/components/views/KanbanView.vue

- Колонки з DocTypeKanbanView.column_field (Select options)
- Drag-and-drop карток між колонками
- При переміщенні: PATCH {column_field: new_value}
- Lazy loading карток
```

### 2.7 — WebSocket Real-time

```
frontend/src/core/composables/useWebSocket.ts
backend/grunt/api/v1/ws.py      ← ConnectionManager

Events:
- doc_change     → оновити документ в кеші
- list_change    → оновити список (новий/видалений документ)
- notification   → показати toast
```

### ✅ Фаза 2 Done Criteria
- [ ] Form Builder: перетягнути Text поле → з'являється в формі
- [ ] Form Builder: live preview оновлюється без перезавантаження
- [ ] ListView: фільтрація + пошук + пагінація працюють
- [ ] FormView: збереження з валідацією
- [ ] KanbanView: drag-and-drop між колонками
- [ ] WebSocket: зміна в одному вікні → оновлення в іншому

---

## ФАЗА 3: Workflow + Permissions + Apps

**Мета:** Повноцінна бізнес-логіка для enterprise-сценаріїв.

### 3.1 — Workflow Engine

```python
# backend/grunt/core/workflow/engine.py

class WorkflowEngine:
    async def get_available_transitions(
        self, doctype: str, doc_id: str, user: User
    ) -> list[WorkflowTransition]:
        """Які переходи доступні для цього користувача в цьому стані?"""
    
    async def apply_transition(
        self, doctype: str, doc_id: str, action: str, user: User
    ) -> Document:
        """Застосувати перехід. Перевірити roles + condition."""
```

### 3.2 — Workflow Builder UI

```
frontend/src/pages/studio/workflow/
├── WorkflowEditor.vue      ← візуальний редактор (SVG графік)
├── StateNode.vue           ← вузол стану
└── TransitionEdge.vue      ← ребро переходу
```

### 3.3 — Permission System

```
backend/grunt/core/permissions/
├── rbac.py         ← PermissionChecker з ARCHITECTURE.md §8
└── query.py        ← Row-level security в SQL WHERE clause
```

### 3.4 — App System

```
grunt create-app {name}

Структура app:
grunt_apps/
└── {name}/
    ├── grunt_app.py        ← app metadata + hooks
    ├── modules/
    │   └── {module}/
    │       ├── doctypes/   ← DocType JSON файли
    │       └── fixtures/   ← початкові дані
    └── public/             ← статика

grunt install-app {name}    ← встановити app
grunt uninstall-app {name}  ← видалити
```

### 3.5 — Reports Module

```
Типи звітів:
1. Script Report  ← Python функція повертає columns + data
2. Query Report   ← SQL запит (тільки SELECT)
3. List Report    ← фільтрований список DocType

UI:
pages/desk/reports/
├── ReportList.vue
├── ReportView.vue      ← результати + фільтри + export Excel
└── ChartBlock.vue      ← графік (Chart.js)
```

### ✅ Фаза 3 Done Criteria
- [ ] Workflow: статус-кнопки в FormView + перехід змінює статус
- [ ] Permissions: user без ролі не бачить захищений DocType
- [ ] Row-level: user бачить тільки "свої" документи
- [ ] `grunt create-app crm` → CRM app встановлена
- [ ] Report: SQL звіт з фільтрами і export в Excel

---

## ФАЗА 4: Production Ready

**Мета:** Готовий до реального використання у державному секторі.

### 4.1 — Document Generation
```
backend/grunt/apps/system/print_formats.py

POST /api/v1/docs/{doctype}/{id}/print
?format=docx|pdf|xlsx
?template={template_name}

Бібліотеки:
- docxtpl   → Word (.docx)
- WeasyPrint → PDF (з HTML шаблону)
- openpyxl  → Excel
```

### 4.2 — Localization
```
frontend/src/locales/
├── uk.json         ← українська (за замовчуванням)
└── en.json         ← англійська

Backend: DateField → формат DD.MM.YYYY
Числа: 1 000,00 (пробіл-роздільник тисяч)
```

### 4.3 — Audit Log
```
grunt_log_activity  ← таблиця: user, doctype, doc_id, action, changes(JSON), ip, timestamp
```

### 4.4 — Security
```
- Rate limiting (slowapi)
- Security headers (middleware)
- XSS санітизація для RichText
- CSRF protection для forms
- Input validation на всіх endpoints
```

### 4.5 — Docker Compose
```yaml
# docker-compose.yml
services:
  backend:
  frontend:
  postgres:
  redis:
  nginx:
```

### ✅ Фаза 4 Done Criteria
- [ ] `grunt print {doctype} {id} --format pdf` → PDF файл
- [ ] Всі UI тексти українською
- [ ] Audit log записується для кожної зміни
- [ ] Docker Compose: `docker compose up` → всі сервіси
- [ ] Lighthouse score: Performance ≥ 85, Accessibility ≥ 90
