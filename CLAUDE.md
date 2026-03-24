# Ґрунт Framework — Claude Code Instructions

> Це головний файл інструкцій для Claude Code (VS Code). Читай його повністю перед будь-якими змінами.
> Ґрунт — metadata-driven application framework для побудови CMS, ERP, реєстрів та інших бізнес-додатків.

---

## 1. Концептуальна модель

### Що таке Ґрунт?

Ґрунт — це **фреймворк для фреймворків**. Він не є кінцевим додатком — він є платформою, на якій інші розробники будують власні додатки (CMS, ERP, реєстри, CRM тощо).

Ключова ідея: **всі структури даних та UI описуються через метадані** (DocType). Немає ручного написання міграцій чи форм — розробник описує модель, Ґрунт робить усе інше.

### Центральна абстракція: DocType

```
DocType (метадані моделі)
├── name: "Договір"
├── module: "crm"
├── fields: [...]           ← описують структуру даних
├── views: [list, form, kanban, calendar]
├── workflow: {...}          ← стани та переходи
└── permissions: [...]       ← хто що може

→ Автоматично генерує:
   ├── Таблицю в БД
   ├── REST API (/api/v1/docs/Договір)
   ├── UI форму
   ├── Список документів
   └── WebSocket канал
```

### Архітектурні рівні

```
┌────────────────────────────────────┐
│     Додатки (apps)                 │  CMS, ERP, Реєстри — розробляються поверх
├────────────────────────────────────┤
│     Ґрунт Core                     │  Metadata Engine, Workflow, Permissions
├────────────────────────────────────┤
│     Runtime                        │  FastAPI + SQLAlchemy + Redis + Vue 3
└────────────────────────────────────┘
```

---

## 2. Технологічний стек

### Backend
| Компонент | Технологія | Примітки |
|-----------|-----------|----------|
| Runtime | Python 3.12+ | Обов'язково `>=3.12` |
| Web framework | FastAPI 0.111+ | Async-first |
| ORM | SQLAlchemy 2.0 (async) | Multi-DB через dialect |
| Валідація | Pydantic v2 | Для API схем і DocType |
| Міграції | Alembic | Авто-генерація з DocType |
| Cache/Pub-Sub | Redis 7+ (redis-py async) | Optional але рекомендовано |
| Background tasks | Celery + Redis | Для довгих операцій |
| WebSocket | FastAPI WebSocket | Real-time події |
| Auth | python-jose + passlib | JWT + bcrypt |
| CLI | Click | `grunt` команда |

### Підтримувані бази даних (через SQLAlchemy dialects)
- **PostgreSQL** — основна, рекомендована для production
- **SQLite** — для dev/testing, без додаткових залежностей
- **MySQL/MariaDB** — опціонально
- **MS SQL Server** — опціонально (через `pyodbc`)

> ⚠️ Ніколи не пиши SQL напряму. Завжди використовуй SQLAlchemy Core або ORM.

### Frontend
| Компонент | Технологія |
|-----------|-----------|
| Framework | Vue 3.4+ (Composition API) |
| Мова | TypeScript 5+ |
| Bundler | Vite 5+ |
| State | Pinia |
| Router | Vue Router 4 |
| Стилі | TailwindCSS 3 + CSS Variables |
| Компоненти | власна UI-бібліотека (grunt-ui) |
| HTTP | Axios + Vue Query (TanStack) |
| Drag & Drop | VueDraggable (Sortable.js wrapper) |
| Rich Text | Tiptap 2 |
| Icons | Lucide Vue |

---

## 3. Структура проєкту

```
grunt/
├── CLAUDE.md                    ← ТИ ТУТ
├── ARCHITECTURE.md              ← детальна архітектура
├── PHASES.md                    ← план фаз розробки
├── pyproject.toml               ← Python deps (uv)
├── uv.lock
├── package.json                 ← workspace root
│
├── backend/                     ← Python backend
│   ├── grunt/                   ← основний пакет
│   │   ├── __init__.py
│   │   ├── main.py              ← FastAPI app entry point
│   │   ├── config.py            ← Settings (pydantic-settings)
│   │   │
│   │   ├── core/                ← ядро фреймворку
│   │   │   ├── metadata/        ← DocType engine
│   │   │   │   ├── doctype.py   ← DocType model
│   │   │   │   ├── field.py     ← Field definitions
│   │   │   │   ├── registry.py  ← DocType registry (singleton)
│   │   │   │   └── compiler.py  ← DocType → SQLAlchemy Table
│   │   │   ├── db/
│   │   │   │   ├── session.py   ← async session factory
│   │   │   │   ├── base.py      ← Base model
│   │   │   │   └── migrations/  ← Alembic
│   │   │   ├── auth/
│   │   │   │   ├── models.py
│   │   │   │   ├── service.py
│   │   │   │   └── dependencies.py
│   │   │   ├── workflow/
│   │   │   │   ├── engine.py    ← State machine
│   │   │   │   └── transitions.py
│   │   │   ├── permissions/
│   │   │   │   ├── rbac.py      ← Role-based access control
│   │   │   │   └── query.py     ← Row-level security
│   │   │   └── cache/
│   │   │       └── redis.py
│   │   │
│   │   ├── api/                 ← REST API
│   │   │   ├── deps.py          ← Shared dependencies
│   │   │   └── v1/
│   │   │       ├── router.py    ← v1 router
│   │   │       ├── meta.py      ← /meta/* DocType CRUD
│   │   │       ├── docs.py      ← /docs/* Document CRUD
│   │   │       ├── auth.py      ← /auth/*
│   │   │       ├── files.py     ← /files/* uploads
│   │   │       └── ws.py        ← WebSocket /ws
│   │   │
│   │   └── apps/                ← вбудовані apps
│   │       └── system/          ← System app (users, roles, settings)
│   │
│   └── tests/
│
├── frontend/                    ← Vue 3 frontend
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       │
│       ├── core/                ← ядро фронтенду
│       │   ├── api/             ← API client
│       │   ├── builder/         ← Form/View builder engine
│       │   ├── renderer/        ← Dynamic form renderer
│       │   └── composables/     ← useDocType, useDocument, etc.
│       │
│       ├── components/
│       │   ├── ui/              ← Design system (Button, Input, Modal...)
│       │   ├── builder/         ← Builder UI компоненти
│       │   └── views/           ← ListView, FormView, KanbanView...
│       │
│       ├── pages/               ← Route pages
│       │   ├── studio/          ← App Studio (builder)
│       │   ├── desk/            ← App Desk (runtime)
│       │   └── auth/
│       │
│       └── stores/              ← Pinia stores
│
└── grunt-cli/                   ← CLI інструмент
    ├── grunt.py
    └── commands/
```

---

## 4. Типи полів DocType

Кожне поле DocType має `fieldtype`. Підтримувані типи:

```python
class FieldType(str, Enum):
    # Прості
    TEXT       = "Text"        # varchar(255)
    LONG_TEXT  = "LongText"    # text
    INT        = "Int"         # integer
    FLOAT      = "Float"       # numeric(20,6)
    BOOL       = "Check"       # boolean
    DATE       = "Date"        # date
    DATETIME   = "Datetime"    # timestamp with timezone
    TIME       = "Time"        # time
    
    # Зв'язки
    LINK       = "Link"        # FK до іншого DocType
    MULTI_LINK = "MultiLink"   # many-to-many
    
    # Медіа
    ATTACH     = "Attach"      # посилання на файл
    IMAGE      = "Image"       # зображення
    
    # Структурні (не в БД)
    SECTION    = "Section"     # роздільник секцій
    COLUMN     = "Column"      # колонка (2/3 колонки)
    TAB        = "Tab"         # таб
    TABLE      = "Table"       # дочірня таблиця (Child DocType)
    
    # Спеціальні
    SELECT     = "Select"      # dropdown з options
    RICH_TEXT  = "RichText"    # HTML через Tiptap
    JSON       = "JSON"        # jsonb
    CODE       = "Code"        # code editor
    COLOR      = "Color"       # color picker
    SIGNATURE  = "Signature"   # підпис
    GEOLOCATION = "Geolocation" # координати
```

---

## 5. API контракти

### DocType API

```
GET    /api/v1/meta/doctypes              → список DocTypes
POST   /api/v1/meta/doctypes              → створити DocType
GET    /api/v1/meta/doctypes/{name}       → отримати DocType
PUT    /api/v1/meta/doctypes/{name}       → оновити DocType
DELETE /api/v1/meta/doctypes/{name}       → видалити DocType
POST   /api/v1/meta/doctypes/{name}/sync  → синхронізувати з БД
```

### Document API

```
GET    /api/v1/docs/{doctype}             → список документів
POST   /api/v1/docs/{doctype}             → створити документ
GET    /api/v1/docs/{doctype}/{id}        → отримати документ
PUT    /api/v1/docs/{doctype}/{id}        → оновити документ
DELETE /api/v1/docs/{doctype}/{id}        → видалити документ
POST   /api/v1/docs/{doctype}/{id}/submit → зафіксувати (workflow)
```

### Query параметри для GET list:

```
?page=1&per_page=20
?sort=name&order=asc
?filter[status]=active
?filter[date__gte]=2024-01-01
?fields=name,title,status    ← часткова вибірка
?search=keyword              ← full-text search
```

### WebSocket

```
WS /api/v1/ws/{doctype}/{id}

← {"event": "doc_change", "data": {...}}
← {"event": "workflow_transition", "data": {...}}
← {"event": "notification", "data": {...}}

→ {"action": "subscribe", "doctype": "Договір"}
→ {"action": "unsubscribe"}
```

---

## 6. Стандарти коду

### Python

```python
# ✅ Правильно: async функції, type hints, Pydantic
async def get_document(
    doctype: str,
    doc_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> DocumentResponse:
    ...

# ✅ SQLAlchemy 2.0 стиль
result = await session.execute(
    select(Document).where(Document.id == doc_id)
)
doc = result.scalar_one_or_none()

# ❌ Заборонено: sync функції в async контексті
# ❌ Заборонено: прямий SQL через session.execute("SELECT...")
# ❌ Заборонено: global state без Lock
```

### TypeScript / Vue

```typescript
// ✅ Завжди: defineComponent + Composition API + <script setup>
<script setup lang="ts">
import { ref, computed } from 'vue'
import type { DocType, DocField } from '@/types'

const props = defineProps<{
  doctype: DocType
  modelValue: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
}>()
</script>

// ❌ Заборонено: Options API
// ❌ Заборонено: any тип без коментаря // eslint-disable-next-line
// ❌ Заборонено: v-html без sanitize
```

### Іменування
- Python: `snake_case` для всього; класи `PascalCase`
- TypeScript: `camelCase` для змінних; `PascalCase` для типів/компонентів
- API endpoints: `kebab-case` (`/api/v1/meta/doctypes`)
- DocType name: `PascalCase` в коді, людська назва в `label`
- Файли Vue: `PascalCase.vue` для компонентів, `kebab-case.ts` для composables

---

## 7. Фази розробки

### Фаза 1 — Metadata Engine + Basic CRUD
**Мета:** Робоча база — можна визначити DocType і зберігати дані.

- [x] `DocType` модель (Pydantic + SQLAlchemy)
- [x] `DocType Registry` — in-memory реєстр
- [x] `DocType Compiler` — DocType → SQLAlchemy Table
- [x] Alembic auto-migration при sync
- [x] REST API: `/meta/*` і `/docs/*`
- [x] Базова аутентифікація (JWT)
- [x] Vue: Router, Pinia, API client
- [x] Vue: базова ListView і FormView (без builder)
- [x] CLI: `grunt init`, `grunt serve`

**Done criteria:** `grunt init myapp && grunt serve` → можна створити DocType через API і побачити дані.

---

### Фаза 2 — Form Builder + Views
**Мета:** Візуальний конструктор форм у стилі Notion.

- [x] Builder UI: drag-and-drop полів
- [x] Панель властивостей поля
- [x] Попередній перегляд форми в реальному часі
- [x] Renderer: рендеринг форми з метаданих
- [x] Всі типи полів з UI компонентами
- [x] KanbanView, CalendarView
- [x] Фільтри і сортування в ListView
- [x] WebSocket real-time оновлення

---

### Фаза 3 — Workflow + Permissions + Apps
**Мета:** Повноцінна бізнес-логіка.

- [x] Workflow engine: стани, переходи, дії
- [x] Візуальний редактор workflow
- [x] RBAC: ролі, дозволи на рівні DocType і документа
- [x] Permission Query (row-level security)
- [x] App система: `grunt create-app`
- [x] Модуль Reports (агрегати, фільтри)
- [x] Dashboard з widgets

---

### Фаза 4 — Production Ready
**Мета:** Готовність до реального використання.

- [x] Document generation (docxtpl, WeasyPrint, openpyxl)
- [x] Plugin/Hook system
- [x] Аудит лог
- [ ] i18n (українська мова за замовчуванням)
- [x] Rate limiting, CORS, security headers
- [x] Docker Compose для deployment
- [ ] Документація (MkDocs)

---

## 8. Правила для Claude Code

### Завжди роби:
1. **Читай ARCHITECTURE.md** перед роботою з новим модулем
2. **Пиши тести** — кожна нова функція/endpoint має мати тест
3. **Використовуй type hints** — у Python і TypeScript
4. **Логуй через `structlog`** — не `print()`, не `logging.basicConfig`
5. **Обробляй помилки** — FastAPI HTTPException з правильними кодами
6. **Перевіряй дозволи** — кожен endpoint має `current_user` dependency

### Ніколи не роби:
1. ❌ Не пиши міграції вручну — генеруй через Alembic
2. ❌ Не використовуй sync SQLAlchemy в async контексті
3. ❌ Не зберігай секрети в коді — тільки через `config.py` з env
4. ❌ Не використовуй `Any` в Pydantic моделях без коментаря
5. ❌ Не видаляй існуючі поля DocType без міграції
6. ❌ Не пиши бізнес-логіку в API endpoints — тільки в service шарі

### При роботі з DocType:
- Завжди валідуй через `DocTypeValidator` перед збереженням
- Після зміни полів завжди запускай `doctype.sync()` для міграції
- Child DocType (TABLE поле) — окремий DocType з `is_child=True`
- `name` поля DocType — унікальний `snake_case` ідентифікатор

### Структура відповіді API:
```json
{
  "success": true,
  "data": {...},
  "meta": {
    "total": 100,
    "page": 1,
    "per_page": 20
  }
}
```

При помилці:
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Поле 'name' є обов'язковим",
    "details": [...]
  }
}
```

---

## 9. Команди розробника

```bash
# Setup
uv sync                          # встановити Python deps
npm install                      # встановити Node deps

# Dev
grunt serve                      # запустити backend + frontend
grunt serve --backend-only       # тільки FastAPI
grunt serve --frontend-only      # тільки Vite

# Database
grunt db init                    # ініціалізувати БД
grunt db migrate                 # запустити міграції
grunt db reset                   # скинути БД (тільки dev)

# DocType
grunt doctype list               # список DocTypes
grunt doctype sync <name>        # синхронізувати DocType з БД

# Testing
pytest backend/tests/            # Python тести
npm test                         # Vue тести (vitest)
npm run e2e                      # E2E (Playwright)

# Code quality
ruff check . --fix               # Python linting + autofix
mypy backend/grunt               # Type checking
npm run typecheck                # Vue type check
```

---

## 10. Glossary

| Термін | Пояснення |
|--------|-----------|
| **DocType** | Визначення моделі (схема + UI + логіка) |
| **Document** | Екземпляр (запис) DocType |
| **Field** | Поле DocType |
| **Module** | Логічна група DocTypes (напр. "CRM", "HR") |
| **App** | Набір модулів + конфігурація (встановлюється поверх Ґрунт) |
| **Workspace** | Персоналізована стартова сторінка |
| **Desk** | Runtime UI для кінцевих користувачів |
| **Studio** | Builder UI для розробників |
| **Workflow** | Граф станів документа |
| **Child Table** | Вбудована таблиця в документі (TABLE поле) |
| **Sync** | Процес застосування змін DocType до схеми БД |
