# ADR 002: Структура UI-компонентів фронтенду

## Статус

Прийнято — 2026-05-11

---

## Контекст

Фронтенд Grunt (`apps/grunt/frontend/src/`) має чотири основні директорії —
`components/`, `pages/`, `core/`, `stores/` — та понад 200 Vue-файлів і TypeScript-модулів.
Без задокументованих правил кожен розробник вирішує питання структури по-своєму:
куди покласти новий компонент, як назвати composable, як підключити нове поле або тип відображення.

Цей ADR фіксує шість рішень про організацію UI-коду.

---

## Рішення 1: `components/` vs `pages/` — чітка межа відповідальності

### Правило

| Директорія | Призначення | Ознака |
|---|---|---|
| `pages/` | Компоненти, що монтуються **роутером** | Мають маршрут у `router/index.ts` |
| `components/` | **Повторно використовувані** компоненти | Без прив'язки до URL |

Page-компоненти **не можна** імпортувати в інші компоненти як дочірні — вони є точкою входу маршруту,
а не будівельним блоком.

### Структура `pages/`

```
pages/
  DeskPage.vue               ← /app (лаунчер додатків)
  auth/
    Login.vue                ← /login
    ForgotPassword.vue       ← /forgot-password
    ResetPassword.vue        ← /reset-password
    MfaVerify.vue            ← /mfa-verify
    Register.vue             ← /signup
  workspace/
    WorkspaceLayout.vue      ← /app/:workspaceName (layout-обгортка)
    WorkspaceHome.vue        ← /app/:workspaceName (головна WS)
    WorkspaceListView.vue    ← /app/:workspaceName/:doctype
    WorkspaceFormView.vue    ← /app/:workspaceName/:doctype/:id
    WorkspaceDashboard.vue   ← /app/:workspaceName/dashboard/:name
    WorkspaceReportView.vue  ← /app/:workspaceName/report/:name
    SearchResultsPage.vue    ← /app/:workspaceName/search
  studio/
    DocTypeList.vue          ← перелік DocType у Form Builder
    builder/                 ← Form Builder (canvas, properties, tabs)
    roles/                   ← управління ролями і юзерами
    workflow/                ← редактор Workflow
  admin/
    HookManager.vue
    ActivityLogViewer.vue
    EmailSettingsPage.vue
    RbacManager.vue
  errors/
    NotFound.vue             ← 404
    Forbidden.vue            ← 403
    ErrorLayout.vue
  public/
    PublicWebForm.vue
    DocumentShareView.vue
  reports/
    ReportView.vue
    QueryReportBuilder.vue
  setup/
    SetupWizard.vue
  desk/
    FileManager.vue
    DocTypeForm.vue
    DocTypeList.vue
    PrintFormatBuilder.vue
```

### Структура `components/`

```
components/
  AppIcon.vue                ← icon-компонент (Lucide + emoji fallback)
  ErrorBoundary.vue          ← обгортка для перехоплення помилок рендеру
  fields/                    ← см. Рішення 2
  views/                     ← см. Рішення 3
  workspace/                 ← елементи sidebar і навігації
  dashboard/                 ← widgets для WorkspaceDashboard
  layout/                    ← CommandPalette, NotificationsPopover, PalettePicker
  ui/                        ← дрібні загальні елементи (PresenceAvatars тощо)
  mobile/                    ← MobileBottomNav
  pwa/                       ← PWAInstallPrompt
  desk/                      ← AppCard, GruntDialog
  debug/                     ← ServerErrorModal
```

**Чому не змішувати:** сторінка і компонент — різні концепції. Сторінка відповідає на питання
"що показувати за цим URL", компонент — "як відобразити цей UI-блок". Аналогічний підхід у Nuxt і Next.js.

---

## Рішення 2: Система полів — self-contained директорії

### Структура

Кожен тип поля живе у власній директорії під `components/fields/{FieldName}/`.
Директорія є повністю самодостатньою:

```
components/fields/{FieldName}/
  {FieldName}.vue          ← головний компонент (edit-режим форми)
  manifest.json            ← метадані для реєстру
  {FieldName}.py           ← Python-реєстрація серверного типу поля
  FilterInput.vue          ← (опційно) компонент фільтра в List View
  ListCell.vue             ← (опційно) відображення у стовпці таблиці
  DesignerPreview.vue      ← (опційно) спрощений preview у Form Builder
```

### manifest.json

```json
{
  "type": "Link",
  "label": "Link",
  "icon": "link",
  "category": "Вибір і зв'язки",
  "propertySections": ["core", "flags", "display", "text", "default", "link"]
}
```

| Поле | Тип | Опис |
|---|---|---|
| `type` | `string` | Унікальний ідентифікатор — збігається з `DocField.fieldtype` |
| `label` | `string` | Назва у Form Builder palette |
| `icon` | `string` | kebab-case Lucide-іконка або emoji |
| `category` | `string` | Група у palette (напр. "Базові", "Медіа", "Вибір і зв'язки") |
| `propertySections` | `string[]` | Секції у PropertiesPanel, в порядку відображення |
| `is_layout` | `boolean?` | `true` для Section / Column / Tab (не зберігаються в БД) |

### Авто-реєстрація

`core/fieldRegistry.ts` автоматично знаходить всі `manifest.json` через `import.meta.glob`
і реєструє поля **без жодних ручних змін** у центральному файлі:

```ts
// fieldRegistry.ts (спрощено)
const manifests = import.meta.glob('@/components/fields/*/manifest.json', { eager: true })
const allVues   = import.meta.glob('@/components/fields/*/*.vue')
// Для кожного manifest.json шукає {DirName}/{DirName}.vue як головний компонент
// та {DirName}/DesignerPreview.vue як preview
```

### Додавання нового типу поля

Достатньо створити директорію з `manifest.json` і `{FieldName}.vue` — поле з'явиться
у Form Builder palette, FieldRenderer і PropertiesPanel автоматично.

**Чому self-contained директорії:** нове поле не потребує змін у framework-коді.
`FilterInput.vue` і `ListCell.vue` — опційні: якщо відсутні, List View використовує
компоненти з `fields/Default/`.

---

## Рішення 3: View-система — реєстри та auto-discovery

### Структура

Кожен тип відображення живе під `components/views/{viewName}/` із власним `index.ts`:

```
components/views/
  list/
    ListTableView.vue
    ListGroupedView.vue
    ListHeader.vue
    ListToolbarControls.vue
    ListViewRouter.vue
    ListViewSettings.vue
    index.ts               ← реєструє view у viewRegistry
  kanban/
    KanbanView.vue
    KanbanSettings.vue
    index.ts
  calendar/
    CalendarView.vue
    CalendarSettings.vue
    index.ts
  gallery/
    GalleryView.vue
    GalleryViewWrapper.vue
    index.ts
  map/
    MapView.vue
    index.ts
  tree/
    TreeView.vue
    TreeSettings.vue
    index.ts
  status/
    StatusSettings.vue
    index.ts
```

### index.ts — контракт реєстрації

```ts
// components/views/kanban/index.ts
import { Columns2 } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'
import type { DocType, DocField } from '@/types'

const def: ViewDefinition = {
  type: 'kanban',
  label: 'Kanban',
  icon: Columns2,
  order: 3,
  resolveField: (dt: DocType): DocField | null =>
    dt.fields.find(f => f.fieldtype === 'Select' && f.in_list_view) ?? null,
  component: () => import('./KanbanView.vue').then(m => m.default),
  settingsComponent: () => import('./KanbanSettings.vue').then(m => m.default),
  mountProps: (ctx) => ({
    doctype: ctx.doctype,
    rows: ctx.rows,
    kanbanField: ctx.resolvedField?.fieldname ?? '',
    workspace: ctx.workspace,
  }),
}

export default def
```

### Авто-реєстрація

`core/viewRegistry.ts` сканує `components/views/*/index.ts` через `import.meta.glob`:

```ts
const _viewModules = import.meta.glob<{ default: ViewDefinition }>(
  '@/components/views/*/index.ts',
  { eager: true },
)
for (const mod of Object.values(_viewModules)) {
  if (mod?.default) registerView(mod.default)
}
```

### Аналогічні реєстри

| Реєстр | Файл | Що реєструє |
|---|---|---|
| Field Registry | `core/fieldRegistry.ts` | Типи полів (компоненти + manifest) |
| View Registry | `core/viewRegistry.ts` | Типи відображень списків |
| Filter Registry | `core/filterRegistry.ts` | Компоненти фільтрів за типом поля |
| List Cell Registry | `core/listCellRegistry.ts` | Рендерери комірок таблиці |
| Property Section Registry | `core/propertySectionRegistry.ts` | Секції у PropertiesPanel Form Builder |

**Чому реєстри:** відкритість для розширення — новий view-тип або поле не потребує патчити framework-код.
`resolveField` в `ViewDefinition` дозволяє приховати кнопку view якщо DocType не має потрібного поля
(наприклад, Map показується тільки якщо є Geolocation-поле).

> **Важливо:** `index.ts` view **не може** імпортувати runtime-значення з `viewRegistry`
> (тільки `import type`) — щоб уникнути circular initialization ReferenceError.

---

## Рішення 4: Composables — конвенції іменування і розміщення

### Де живуть

Всі composables — в `core/composables/`. Builder-специфічні — у `core/composables/builder/`.

```
core/composables/
  useFormSave.ts
  useFormValidation.ts
  useListColumns.ts
  ...
  builder/
    useBuilderLayout.ts
    useBuilderPermissions.ts
    useBuilderWorkflow.ts
```

### Конвенція іменування: `use{Domain}{Concern}.ts`

| Префікс | Домен | Приклади |
|---|---|---|
| `useForm*` | Логіка форм | `useFormSave`, `useFormValidation`, `useFormNavigation`, `useFormShortcuts` |
| `useList*` | Логіка списків | `useListColumns`, `useListSelection`, `useListSearch`, `useListActions` |
| `useDoc*` | Документи | `useDocument`, `useDocQuery`, `useDocTypeListData` |
| `useMap*` | Карта | `useMapMarkers`, `useMapLifecycle`, `useMapExport`, `useMapPopupFields` |
| `useBuilder*` | Form Builder | `useBuilderLayout`, `useBuilderPermissions`, `useBuilderWorkflow` |

Composables без домену (`useToast`, `useColorMode`, `useShortcuts`, `useWebSocket`) —
це загальні утиліти, не прив'язані до конкретного UI-домену.

### Правила

- Composable = логіка, компонент = шаблон. Якщо в `<script setup>` більше 50 рядків —
  виносити логіку у composable.
- Composable повертає реактивні дані (`ref`, `computed`) та функції, **не компоненти**.
- Ніколи не тягнути composable з одного домену в інший напряму — використовувати store
  як посередника.

**Чому окрема директорія:** `core/composables/` — єдине передбачуване місце для пошуку
переиспользованої логіки. Composable поряд з компонентом — антипатерн: при рефакторингу
важко знайти де ще використовується.

---

## Рішення 5: Pinia stores — один store на домен

### Stores

```
stores/
  auth.ts        ← аутентифікація, поточний юзер, тема, мова
  workspace.ts   ← активний workspace, sidebar items, counts
  sidebar.ts     ← collapsed-стан sidebar (UI-only)
  doctype.ts     ← метадані DocType (поля, permissions, views)
  builder.ts     ← стан Form Builder (canvas, вибраний field, секції)
  ui.ts          ← глобальний UI-стан (modals, loading indicators)
  pages.ts       ← стан custom pages (реєстрація, параметри)
```

| Store | Відповідальність |
|---|---|
| `auth` | Хто зараз залогінений, теми, logout |
| `workspace` | Що показує sidebar (items, counts, активний WS) |
| `sidebar` | Тільки collapsed/expanded стан |
| `doctype` | Кешовані метадані DocType для поточного перегляду |
| `builder` | Весь стан Form Builder між компонентами |
| `ui` | Стан модальних вікон і глобальних індикаторів |
| `pages` | Реєстрація та параметри custom-сторінок |

### Правила

- Один store = один чіткий домен. Не створювати "загальний" store.
- Store — для **спільного** стану між компонентами. Якщо стан локальний — `ref` всередині composable.
- Не звертатись із одного store в інший напряму — виносити спільну логіку у composable.

**Чому:** чітке ownership, легко писати тести (mock одного store),
store spaghetti (коли всі читають і пишуть в один величезний store) виключається архітектурно.

---

## Рішення 6: `core/` — внутрішня бібліотека фронтенд-фреймворку

### Що належить до `core/`

```
core/
  api/               ← HTTP-клієнт і всі API-виклики
    client.ts        ← axios/fetch конфігурація
    auth.ts, docs.ts, workspace.ts, ...
  composables/       ← вся reusable логіка (см. Рішення 4)
  fieldRegistry.ts   ← реєстр типів полів
  viewRegistry.ts    ← реєстр типів відображень
  filterRegistry.ts  ← реєстр фільтрів
  listCellRegistry.ts
  propertySectionRegistry.ts
  grunt.ts           ← головний об'єкт `grunt` (window.grunt)
  renderer/
    FieldRenderer.vue  ← рендерить будь-яке поле за типом
    FormRenderer.vue   ← рендерить форму за схемою DocType
  scripting/
    executor.ts        ← виконання client scripts (DocType.js)
  ws/
    WebSocketChannel.ts
  io/
    exporters/         ← Excel, HTML export
    importers/
  pages/
    DynamicPage.vue    ← рендерер custom pages
    PublicPage.vue
    registry.ts
  attachmentChannels/  ← camera, library, local file, URL
  map/                 ← iconCache, popupFormatter
  validators.ts        ← правила валідації форм
  quickFilters.ts      ← визначення quick filters
```

### Що НЕ належить до `core/`

| Тип | Куди |
|---|---|
| Page-level компоненти (маршрути) | `pages/` |
| UI-блоки (sidebar, widgets, fields) | `components/` |
| Стан застосунку | `stores/` |
| Статичні ресурси | `assets/` |
| Типи TypeScript | `types/` |

### `grunt.ts` — публічний API для client scripts

`core/grunt.ts` експортує об'єкт `grunt`, який монтується на `window`:

```ts
// main.ts
import { grunt } from '@/core/grunt'
window.grunt = grunt
window.frappe = grunt  // Frappe-compatible alias
```

Client scripts (файли `{DocType}.js`) використовують `grunt.get_doc()`, `grunt.call()` тощо —
аналог того, як Python-код використовує `grunt.db.*` і `grunt.get_doc()`.

**Чому `core/`, а не `utils/` або `lib/`:** `core/` дзеркалює структуру Python-бекенду
де `grunt.core.*` містить ядро фреймворку. `utils/` — для несистемних утиліт,
яких у цьому проекті немає — все або domain-логіка (→ composable) або framework-API (→ `core/`).

---

## Наслідки

| Рішення | Вартість | Коли |
|---|---|---|
| `pages/` vs `components/` | нульова — поточний стан | зафіксовано |
| Self-contained field directories | нульова — поточний стан | зафіксовано |
| View registry + auto-discovery | нульова — поточний стан | зафіксовано |
| Composable naming `use{Domain}{Concern}` | низька — перейменування при рефакторингу | поточно |
| Один store на домен | нульова — поточний стан | зафіксовано |
| `core/` як internal library | нульова — поточний стан | зафіксовано |
