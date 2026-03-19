# Ґрунт — Детальна Архітектура

## 1. Metadata Engine

### DocType Model (Pydantic)

```python
# backend/grunt/core/metadata/doctype.py

from pydantic import BaseModel, Field
from typing import Literal, Any
from enum import Enum


class FieldType(str, Enum):
    TEXT        = "Text"
    LONG_TEXT   = "LongText"
    INT         = "Int"
    FLOAT       = "Float"
    BOOL        = "Check"
    DATE        = "Date"
    DATETIME    = "Datetime"
    TIME        = "Time"
    LINK        = "Link"
    MULTI_LINK  = "MultiLink"
    SELECT      = "Select"
    ATTACH      = "Attach"
    IMAGE       = "Image"
    RICH_TEXT   = "RichText"
    JSON        = "JSON"
    CODE        = "Code"
    COLOR       = "Color"
    SECTION     = "Section"
    COLUMN      = "Column"
    TAB         = "Tab"
    TABLE       = "Table"
    SIGNATURE   = "Signature"
    GEOLOCATION = "Geolocation"


class DocField(BaseModel):
    fieldname: str                   # snake_case, унікальний в DocType
    label: str                       # Відображувана назва
    fieldtype: FieldType
    
    # Validations
    required: bool = False
    unique: bool = False
    read_only: bool = False
    hidden: bool = False
    
    # Display
    in_list_view: bool = False       # показувати в списку
    in_filter: bool = False          # доступний для фільтрації
    bold: bool = False
    
    # Type-specific
    options: str | None = None       # для Select: "Option1\nOption2"
                                     # для Link: назва DocType
                                     # для Table: назва Child DocType
    default: Any = None
    description: str | None = None
    placeholder: str | None = None
    
    # Layout (для Section/Column/Tab)
    collapsible: bool = False
    columns: Literal[1, 2, 3, 4] = 1
    
    # Validation rules
    min_value: float | None = None
    max_value: float | None = None
    max_length: int | None = None
    regex: str | None = None
    
    # Conditional display (JS expression)
    depends_on: str | None = None    # "eval: doc.status == 'Active'"
    mandatory_depends_on: str | None = None


class WorkflowState(BaseModel):
    name: str
    label: str
    color: str = "gray"             # gray, blue, green, yellow, red
    is_initial: bool = False
    is_final: bool = False


class WorkflowTransition(BaseModel):
    from_state: str
    to_state: str
    action: str                     # назва кнопки
    allowed_roles: list[str] = []
    condition: str | None = None    # Python expression


class DocTypeWorkflow(BaseModel):
    states: list[WorkflowState]
    transitions: list[WorkflowTransition]
    state_field: str = "status"     # поле для зберігання стану


class DocTypePermission(BaseModel):
    role: str
    read: bool = False
    write: bool = False
    create: bool = False
    delete: bool = False
    submit: bool = False
    report: bool = False
    # Row-level: None = no restriction
    match: str | None = None        # "owner == user" або "department == user.department"


class DocTypeListView(BaseModel):
    fields: list[str] = []         # поля для відображення
    sort_by: str = "modified"
    sort_order: Literal["asc", "desc"] = "desc"
    default_filters: dict = {}


class DocTypeFormView(BaseModel):
    layout: Literal["standard", "compact", "wide"] = "standard"
    print_format: str | None = None


class DocTypeKanbanView(BaseModel):
    column_field: str              # Select поле для колонок
    title_field: str = "name"
    color_field: str | None = None


class DocType(BaseModel):
    name: str                      # PascalCase, унікальний глобально
    label: str                     # "Договір постачання"
    module: str                    # "crm"
    
    # Flags
    is_child: bool = False         # якщо True — використовується в TABLE
    is_submittable: bool = False   # чи є кнопка Submit
    is_singleton: bool = False     # один документ на весь DocType
    track_changes: bool = True     # аудит лог
    
    # Fields
    fields: list[DocField] = []
    
    # Views config
    list_view: DocTypeListView = DocTypeListView()
    form_view: DocTypeFormView = DocTypeFormView()
    kanban_view: DocTypeKanbanView | None = None
    
    # Business logic
    workflow: DocTypeWorkflow | None = None
    permissions: list[DocTypePermission] = []
    
    # Naming
    autoname: str | None = None    # "CONTR-.YYYY.-.####" або "field:title"
    title_field: str = "name"      # поле для заголовку документа
    
    # Search
    search_fields: list[str] = []
    
    class Config:
        use_enum_values = True
```

---

## 2. DocType Compiler (DocType → SQLAlchemy)

```python
# backend/grunt/core/metadata/compiler.py

from sqlalchemy import (
    Table, Column, MetaData, 
    String, Text, Integer, Float, Boolean,
    Date, DateTime, Time, JSON,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import uuid


SA_METADATA = MetaData()

FIELDTYPE_TO_SA = {
    "Text":        lambda f: Column(f.fieldname, String(f.max_length or 255)),
    "LongText":    lambda f: Column(f.fieldname, Text),
    "Int":         lambda f: Column(f.fieldname, Integer),
    "Float":       lambda f: Column(f.fieldname, Float(precision=6)),
    "Check":       lambda f: Column(f.fieldname, Boolean, default=False),
    "Date":        lambda f: Column(f.fieldname, Date),
    "Datetime":    lambda f: Column(f.fieldname, DateTime(timezone=True)),
    "Time":        lambda f: Column(f.fieldname, Time),
    "Select":      lambda f: Column(f.fieldname, String(100)),
    "Link":        lambda f: Column(f.fieldname, String(255)),  # FK handled separately
    "Attach":      lambda f: Column(f.fieldname, String(500)),
    "Image":       lambda f: Column(f.fieldname, String(500)),
    "RichText":    lambda f: Column(f.fieldname, Text),
    "JSON":        lambda f: Column(f.fieldname, JSON),
    "Color":       lambda f: Column(f.fieldname, String(20)),
    "Code":        lambda f: Column(f.fieldname, Text),
    "Geolocation": lambda f: Column(f.fieldname, JSON),
    "Signature":   lambda f: Column(f.fieldname, Text),
}

# Ці типи НЕ створюють колонку в БД
NON_PHYSICAL_FIELDS = {"Section", "Column", "Tab", "Table", "MultiLink"}


def compile_doctype_to_table(doctype: "DocType") -> Table:
    """
    Перетворює DocType у SQLAlchemy Table.
    Таблиця має назву: grunt_{module}_{name_snake}
    """
    table_name = f"grunt_{doctype.module}_{_to_snake(doctype.name)}"
    
    columns = [
        Column("id", PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        Column("name", String(255), nullable=False),      # human-readable ID
        Column("owner", String(255), nullable=False),     # user email
        Column("created_at", DateTime(timezone=True)),
        Column("modified_at", DateTime(timezone=True)),
        Column("modified_by", String(255)),
        Column("docstatus", Integer, default=0),          # 0=draft, 1=submitted, 2=cancelled
    ]
    
    if doctype.workflow:
        columns.append(Column(doctype.workflow.state_field, String(100)))
    
    if doctype.is_child:
        columns.extend([
            Column("parent_id", PG_UUID(as_uuid=True), nullable=False),
            Column("parent_doctype", String(255), nullable=False),
            Column("parent_field", String(255), nullable=False),
            Column("idx", Integer, default=0),
        ])
    
    for field in doctype.fields:
        if field.fieldtype in NON_PHYSICAL_FIELDS:
            continue
        
        builder = FIELDTYPE_TO_SA.get(field.fieldtype.value if hasattr(field.fieldtype, 'value') else field.fieldtype)
        if not builder:
            continue
        
        col = builder(field)
        
        # Nullable за замовчуванням (required валідується на рівні API)
        col.nullable = True
        if field.default is not None:
            col.default = field.default
        
        columns.append(col)
    
    constraints = []
    unique_fields = [f.fieldname for f in doctype.fields if f.unique]
    if unique_fields:
        constraints.append(UniqueConstraint(*unique_fields))
    
    return Table(table_name, SA_METADATA, *columns, *constraints, extend_existing=True)


def _to_snake(name: str) -> str:
    import re
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
```

---

## 3. Database Session (Multi-DB)

```python
# backend/grunt/core/db/session.py

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from grunt.config import settings

# Автоматично обирає правильний dialect
# PostgreSQL: postgresql+asyncpg://...
# SQLite:     sqlite+aiosqlite:///./grunt.db
# MySQL:      mysql+aiomysql://...

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    # PostgreSQL specific
    pool_size=20 if "postgresql" in settings.database_url else 5,
    max_overflow=10 if "postgresql" in settings.database_url else 2,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

---

## 4. Config (pydantic-settings)

```python
# backend/grunt/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    # Core
    app_name: str = "Ґрунт"
    debug: bool = False
    secret_key: str                          # обов'язково в .env
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./grunt.db"
    # Приклади:
    # postgresql+asyncpg://user:pass@localhost/grunt
    # mysql+aiomysql://user:pass@localhost/grunt
    
    # Redis (optional)
    redis_url: str | None = None             # None = вимкнути кеш/WS
    
    # Auth
    access_token_expire_minutes: int = 60 * 24  # 24h
    algorithm: str = "HS256"
    
    # Storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50
    
    # CORS
    allowed_origins: list[str] = ["http://localhost:5173"]
    
    # Локалізація
    default_locale: str = "uk"
    default_timezone: str = "Europe/Kyiv"


settings = Settings()
```

---

## 5. FastAPI App Entry Point

```python
# backend/grunt/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog

from grunt.config import settings
from grunt.api.v1.router import v1_router
from grunt.core.metadata.registry import doctype_registry
from grunt.core.db.session import engine


logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("grunt.startup", version="0.1.0")
    await doctype_registry.load_all()
    yield
    # Shutdown
    await engine.dispose()
    logger.info("grunt.shutdown")


app = FastAPI(
    title="Ґрунт API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")
```

---

## 6. Vue 3 — Composable Architecture

### useDocType

```typescript
// frontend/src/core/composables/useDocType.ts

import { ref, computed } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { api } from '@/core/api'
import type { DocType, DocField } from '@/types'

export function useDocType(name: string) {
  const queryClient = useQueryClient()
  
  const { data: doctype, isLoading, error } = useQuery({
    queryKey: ['doctype', name],
    queryFn: () => api.meta.getDocType(name),
    staleTime: 5 * 60 * 1000, // 5 хвилин кеш
  })
  
  const fields = computed(() => 
    doctype.value?.fields.filter(f => !['Section', 'Column', 'Tab'].includes(f.fieldtype)) ?? []
  )
  
  const listFields = computed(() =>
    fields.value.filter(f => f.in_list_view)
  )
  
  const { mutateAsync: saveDocType } = useMutation({
    mutationFn: (dt: DocType) => api.meta.updateDocType(dt),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['doctype', name] }),
  })
  
  return { doctype, fields, listFields, isLoading, error, saveDocType }
}
```

### useDocument

```typescript
// frontend/src/core/composables/useDocument.ts

import { ref, watch } from 'vue'
import { useQuery, useMutation } from '@tanstack/vue-query'
import { api } from '@/core/api'
import { useWebSocket } from './useWebSocket'

export function useDocument(doctype: string, id: string | null) {
  const queryClient = useQueryClient()
  
  const { data: document, isLoading } = useQuery({
    queryKey: ['document', doctype, id],
    queryFn: () => api.docs.get(doctype, id!),
    enabled: computed(() => !!id),
  })
  
  // Real-time оновлення через WebSocket
  const { lastMessage } = useWebSocket(
    id ? `/api/v1/ws/${doctype}/${id}` : null
  )
  
  watch(lastMessage, (msg) => {
    if (msg?.event === 'doc_change') {
      queryClient.setQueryData(['document', doctype, id], msg.data)
    }
  })
  
  const { mutateAsync: save } = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      id ? api.docs.update(doctype, id, data) : api.docs.create(doctype, data),
  })
  
  return { document, isLoading, save }
}
```

---

## 7. Form Builder Architecture

Конструктор форм працює з **канонічним представленням** — масивом `DocField[]`.
Він ніколи не зберігає UI-стан у DocType напряму.

```
DocField[] (source of truth)
    ↓ builderEngine
BuilderCanvas (drag-and-drop)
    ↓ onChange
DocField[] (updated)
    ↓ auto-save debounce
API PATCH /meta/doctypes/{name}
```

### Drag zones:
- **Field palette** (ліва панель) → нові поля
- **Canvas** (центр) → розміщення, зміна порядку
- **Properties panel** (права панель) → налаштування вибраного поля

### Ключові компоненти:

```
components/builder/
├── BuilderLayout.vue        ← головний layout з 3 колонками
├── FieldPalette.vue         ← список доступних типів полів
├── BuilderCanvas.vue        ← drag-and-drop зона
│   ├── CanvasSection.vue    ← секція з заголовком
│   ├── CanvasRow.vue        ← рядок (1-4 колонки)
│   └── CanvasField.vue      ← окреме поле
├── PropertiesPanel.vue      ← налаштування поля
│   ├── CommonProps.vue      ← label, required, hidden...
│   └── TypeSpecificProps/
│       ├── LinkProps.vue
│       ├── SelectProps.vue
│       └── TableProps.vue
└── BuilderPreview.vue       ← попередній перегляд
```

---

## 8. Permission System

### Рівні перевірки:

```
1. DocType level  → чи може роль взагалі читати/писати цей DocType
2. Row level      → match expression ("owner == user")  
3. Field level    → read_only поля (у DocField)
```

### Реалізація в API:

```python
# backend/grunt/core/permissions/rbac.py

class PermissionChecker:
    async def check(
        self,
        user: User,
        doctype: str,
        action: Literal["read", "write", "create", "delete", "submit"],
        doc_id: str | None = None,
    ) -> bool:
        dt = await doctype_registry.get(doctype)
        
        # Знаходимо всі дозволи для ролей користувача
        allowed_perms = [
            p for p in dt.permissions
            if p.role in user.roles and getattr(p, action)
        ]
        
        if not allowed_perms:
            return False
        
        # Якщо є row-level restriction і є конкретний doc
        if doc_id:
            for perm in allowed_perms:
                if perm.match and not await self._eval_match(perm.match, user, doc_id):
                    continue
                return True
            return False
        
        return True
    
    async def _eval_match(self, expr: str, user: User, doc_id: str) -> bool:
        # Безпечний eval з обмеженим контекстом
        context = {"user": user.email, "user_roles": user.roles}
        # TODO: sandboxed eval
        return eval(expr, {"__builtins__": {}}, context)
```

---

## 9. Real-time WebSocket Architecture

```
Client                    FastAPI                   Redis Pub/Sub
  |                          |                           |
  |──── WS /ws/Договір/123 ──→|                           |
  |                          |──── SUBSCRIBE grunt:doc:123 →|
  |                          |                           |
  |  (інший client save)     |                           |
  |                          |←─ PUBLISH grunt:doc:123 ──|
  |←── {"event":"doc_change"} |                           |
  |                          |                           |
```

```python
# backend/grunt/api/v1/ws.py

from fastapi import WebSocket, WebSocketDisconnect, Depends
import asyncio, json


class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}
    
    async def connect(self, ws: WebSocket, channel: str):
        await ws.accept()
        self.connections.setdefault(channel, []).append(ws)
    
    async def disconnect(self, ws: WebSocket, channel: str):
        self.connections.get(channel, []).remove(ws)
    
    async def broadcast(self, channel: str, message: dict):
        for ws in self.connections.get(channel, []):
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@router.websocket("/ws/{doctype}/{doc_id}")
async def websocket_endpoint(
    ws: WebSocket,
    doctype: str,
    doc_id: str,
    user: User = Depends(ws_current_user),
):
    channel = f"{doctype}:{doc_id}"
    await manager.connect(ws, channel)
    try:
        while True:
            data = await ws.receive_json()
            # handle ping, subscribe, etc.
    except WebSocketDisconnect:
        await manager.disconnect(ws, channel)
```

---

## 10. Naming Conventions Summary

| Контекст | Правило | Приклад |
|----------|---------|---------|
| DocType name | PascalCase | `SalesOrder`, `ContractItem` |
| DocType fieldname | snake_case | `due_date`, `customer_name` |
| DB table | grunt_{module}_{snake_doctype} | `grunt_crm_sales_order` |
| API endpoint | /kebab-case | `/api/v1/docs/sales-order` |
| Python файли | snake_case.py | `doctype_registry.py` |
| Vue компоненти | PascalCase.vue | `FormRenderer.vue` |
| Vue composables | useCamelCase.ts | `useDocType.ts` |
| Pinia stores | use{Name}Store | `useDocTypeStore` |
| CSS classes | kebab-case | `grunt-form-field` |
| Env variables | UPPER_SNAKE | `DATABASE_URL`, `SECRET_KEY` |
