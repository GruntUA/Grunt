# ADR 003: Візуальна карта UI-зон Grunt

## Статус

Прийнято — 2026-05-11

---

## Контекст

Grunt-frontend складається з десятків компонентів, сторінок і stores. Без єдиної карти важко швидко знайти що потрібно змінити коли є запит виду "виправ заголовок форми" або "зміни поведінку App Menu". Цей документ є **візуальним довідником**: для кожної UI-зони — що вона робить, який маршрут, які файли, який store.

---

## Загальна схема маршрутів

```
/login                            → pages/auth/Login.vue
/app                              → pages/DeskPage.vue            ← App Launcher
/app/:workspaceName               → pages/workspace/AppLayout.vue
  (дочірні маршрути)
  /                               → pages/workspace/WorkspaceHome.vue
  /:doctype                       → pages/workspace/WorkspaceListView.vue
  /:doctype/new                   → pages/workspace/WorkspaceFormView.vue
  /:doctype/:id                   → pages/workspace/WorkspaceFormView.vue
  /dashboard/:dashboardName       → pages/workspace/WorkspaceDashboard.vue
  /report/:reportName             → pages/workspace/WorkspaceReportView.vue
  /search                         → pages/workspace/SearchResultsPage.vue
  /files                          → pages/desk/FileManager.vue
/403                              → pages/errors/Forbidden.vue
/* (404)                          → pages/errors/NotFound.vue
```

---

## 1. Desk — App Launcher

### Що показує

Головна сторінка після логіну. Показує всі встановлені додатки (workspaces) у вигляді карток,
лічильники документів по кожному, нещодавно відкриті документи та стрічку активності.

```
┌─────────────────────────────────────────────────────────┐
│  Доброго дня, Максим ☀️                                  │
│  [3 додатки]  [1234 документи]  [5 нещодавніх]          │
│                                                         │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐           │
│  │  🏢 Кадри │  │  📦 Tools │  │  📄 CMS   │           │
│  │  99+ docs │  │  12 docs  │  │   5 docs  │           │
│  └───────────┘  └───────────┘  └───────────┘           │
│                                                         │
│  Нещодавні документи          Стрічка активності        │
│  ─────────────────────        ─────────────────────     │
│  • Жулій В.  (Employee)       Ви редагували...          │
│  • Відпустка #123             Ви створили...            │
└─────────────────────────────────────────────────────────┘
```

### Маршрут

`/app`

### Файли

| Елемент | Файл |
|---|---|
| Сторінка | `pages/DeskPage.vue` |
| Картка додатку | `components/desk/AppCard.vue` |
| Стрічка активності | `components/dashboard/ActivityStream.vue` |

### Stores / API

| | |
|---|---|
| Store | `stores/auth` (ім'я юзера, привітання), `stores/workspace` (список workspaces) |
| API | `core/api/workspace.ts` → `getCounts()` (лічильники по кожному WS) |

---

## 2. App Layout

### Що робить

Обгортка для всіх сторінок всередині одного workspace. Відповідає за:
- Рендер `AppSidebar` (desktop) або `Drawer` (mobile)
- Передачу `workspaceName` у дочірні маршрути
- Показ `NotFound` якщо workspace не існує

```
┌──────────────────────────────────────────────────────────┐
│  AppLayout.vue  /app/:workspaceName                │
│                                                          │
│  ┌──────────┐  ┌─────────────────────────────────────┐  │
│  │Sidebar   │  │  <RouterView>                        │  │
│  │(desktop) │  │  WorkspaceHome / ListVIew / FormView │  │
│  └──────────┘  └─────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  MobileBottomNav (тільки mobile)                   │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### Файли

| Елемент | Файл |
|---|---|
| Layout-обгортка | `pages/workspace/AppLayout.vue` |
| Sidebar (desktop) | `components/workspace/AppSidebar.vue` |
| Sidebar (mobile) | `components/mobile/MobileBottomNav.vue` + PrimeVue `Drawer` |

### Stores

| Store | За що відповідає |
|---|---|
| `stores/workspace` | Завантаження і збереження активного workspace (`setActive`) |
| `stores/sidebar` | Collapsed/expanded стан sidebar |

---

## 3. Sidebar

### Що показує

Ліва панель навігації всередині workspace. Містить:
- **App Switcher** (кнопка + popup-меню зі списком всіх додатків)
- **Search** — відкриває Command Palette
- **Notifications** — NotificationsPopover
- **Закріплені документи** (pinnedItems з localStorage)
- **Огляд** — посилання на WorkspaceHome
- **AppMenu** — навігаційні елементи, згруповані по секціях. В одному додатку може бути кілька AppMenu (наприклад, HRM: «Персонал», «Документи», «Звіти»). Кожне AppMenu відображається як окремий блок у sidebar
- **Інші додатки** (посилання на решту workspaces + "На головну")
- **Адмін shortcuts** (тільки superadmin): Права доступу, Журнал, Пошта, Редагувати меню
- **Footer** — аватар + ім'я юзера → user menu (тема, акцент, вийти)

```
┌───────────────────────────────────┐
│  [👥 Кадри         ˅]  ← App Switcher (AppSwitcher popup)
├───────────────────────────────────┤
│  🔍 Пошук...               ⌘K    │
│  🔔 Сповіщення                   │
│  📌 Закріплені (якщо є)          │
├───────────────────────────────────┤
│  ⬜ Огляд                        │  ← Dashboard
├───────────────────────────────────┤
│  СПІВРОБІТНИКИ                    │  ← AppMenu (секція)
│  👤 Співробітники          99+   │
│  🏢 Відділи                59   │
│  💼 Посади                 44   │
│  ДОКУМЕНТИ                        │
│  📄 Накази                  6   │
│  ...                             │
├───────────────────────────────────┤
│  ДОДАТКИ                          │  ← інші workspaces
│  📦 UA Tools                     │
│  ← На головну                    │
├───────────────────────────────────┤
│  НАЛАШТУВАННЯ (superadmin only)  │
│  🛡 Права доступу                │
│  📋 Журнал активності            │
│  📧 Пошта                        │
│  ⚙ Редагувати меню              │
├───────────────────────────────────┤
│  [CM]  Сисоєв Максим      ˅     │  ← user menu
└───────────────────────────────────┘
```

### Файли

| Елемент | Файл |
|---|---|
| Весь sidebar | `components/workspace/AppSidebar.vue` |
| Один пункт меню | `components/workspace/SidebarItem.vue` |
| Breadcrumb (вгорі контенту) | `components/workspace/WorkspaceBreadcrumb.vue` |
| Notifications popover | `components/layout/NotificationsPopover.vue` |
| Іконка додатку | `components/AppIcon.vue` |

### AppMenu — конфігурація навігації

Структура sidebar визначається у fixture-файлі додатку через записи DocType **AppMenu**.
В одному додатку може бути кілька AppMenu — кожен відображається як окремий іменований блок у sidebar
(наприклад, HRM може мати AppMenu: «Персонал», «Документи», «Звіти»).

```
grunt_apps/{app}/fixtures/00_workspace.json  ← doctype: AppMenu (один або кілька записів)
```

Після зміни файлу потрібно запустити:
```bash
grunt fixture import hrm
```

### Stores

| Store | За що відповідає |
|---|---|
| `stores/workspace` | `workspaces` (список всіх WS), `active` (поточний), `groupedItems` (items по секціях), `counts` (лічильники) |
| `stores/sidebar` | `isCollapsed` — стан collapsed/expanded |
| `stores/auth` | `user` — ім'я, аватар, email, `is_superadmin` |

---

## 4. WorkSpace (Робоча область)

### Що показує

Стартова сторінка додатку — **робоча область** з інтерактивними елементами: кнопками швидкого
доступу, діаграмами, метриками, списками та іншими widgets для відображення поточного стану
документів і навігації. Концептуально — персоналізований дашборд конкретного додатку.
Якщо widgets відсутні — показує порожній стан з пропозицією налаштувати.

### Маршрут

`/app/:workspaceName` (порожній дочірній маршрут)

### Файли

| Елемент | Файл |
|---|---|
| Сторінка | `pages/workspace/WorkspaceHome.vue` |
| Widget-картка | `components/dashboard/WidgetCard.vue` |
| Окремі widgets | `components/dashboard/*.vue` (MetricWidget, ChartWidget тощо) |

### Stores

`stores/workspace` → `active.widgets` (масив конфігурацій widgets)

---

## 5. List View

### Що показує

Список документів одного DocType з фільтрами, пошуком, сортуванням, пагінацією та перемиканням
типу відображення (таблиця / kanban / calendar / gallery / map / tree / status).

```
┌──────────────────────────────────────────────────────────────┐
│  Кадри > Співробітники                ← WorkspaceBreadcrumb  │
├──────────────────────────────────────────────────────────────┤
│  [+Новий]  [Filters▾] [Search...]  [⊞][☰][📅] ← DocTypeToolbar│
│  [Fast filters: Активний | Звільнений]       ← FastFilterBar  │
├──────────────────────────────────────────────────────────────┤
│  ☐ │ ПІБ              │ Відділ     │ Посада    │ Статус      │
│  ──┼──────────────────┼────────────┼───────────┼─────────    │
│  ☐ │ Жулій Валерій    │ Бухгалтерія│ Бухгалтер │ Активний    │
│  ☐ │ Федоренко О.     │ IT відділ  │ Програміст│ Активний    │
│  ... (infinite scroll або pagination)                        │
├──────────────────────────────────────────────────────────────┤
│  [Bulk actions: видалити, призначити] ← BulkActionBar        │
└──────────────────────────────────────────────────────────────┘
```

### Маршрут

`/app/:workspaceName/:doctype`

### Ієрархія компонентів

```
WorkspaceListView.vue          ← pages/workspace/ (тонка обгортка)
  WorkspaceBreadcrumb.vue      ← components/workspace/
  DocTypeList.vue              ← pages/desk/  (весь стан і логіка)
    DocTypeToolbar.vue         ← components/views/  (кнопки, filters, view switcher)
      FastFilterBar.vue        ← components/views/
      FilterBar.vue            ← components/views/
    ListViewRouter.vue         ← components/views/list/  (перемикає view-тип)
      ListTableView.vue        ← components/views/list/  (view: list)
      KanbanView.vue           ← components/views/kanban/  (view: kanban)
      CalendarView.vue         ← components/views/calendar/  (view: calendar)
      GalleryView.vue          ← components/views/gallery/  (view: gallery)
      MapView.vue              ← components/views/map/  (view: map)
      TreeView.vue             ← components/views/tree/  (view: tree)
    ListHeader.vue             ← components/views/list/  (заголовок таблиці)
    BulkActionBar.vue          ← components/views/
    ListPagination.vue         ← components/views/
    QuickEntryDialog.vue       ← components/views/  (швидке створення)
```

### Stores

| Store | За що відповідає |
|---|---|
| `stores/doctype` | Метадані DocType (поля, permissions, налаштування views) |
| `stores/auth` | Перевірка permissions юзера |

### Ключові composables (DocTypeList.vue)

| Composable | За що відповідає |
|---|---|
| `useInfiniteDocTypeListData` | Завантаження і infinite scroll |
| `useListColumns` | Які стовпці показувати |
| `useListViewState` | `viewMode`, `groupBy`, `sortKey`, `sortOrder` |
| `useListRouteSync` | Синхронізація фільтрів/sorting з URL query params |
| `useListSelection` | Множинний вибір рядків (checkboxes) |
| `useListActions` | Bulk delete, export, print |
| `useListSearch` | Інлайн-пошук |
| `useFastFilters` | Швидкі фільтри під toolbar |
| `useGrouping` | Групування по полю |
| `useListClientScripts` | Виконання list hooks з `{DocType}.js` |

---

## 6. Form View

### Що показує

Форма редагування або перегляду одного документа. Ліворуч — основна форма,
праворуч — DocSidebar (коментарі, теги, прив'язки, версії, файли).

```
┌──────────────────────────────────────────────────────────────┐
│  Кадри > Співробітники > Жулій Валерій    ← Breadcrumb       │
├──────────────────────────────────────────────────────────────┤
│  [← Назад]  [Зберегти]  [Редагувати]  [...▾]  ← FormHeader  │
│  [Workflow: Активний → Відрядження → Звільнений] ← WorkflowBar│
├───────────────────────────────────┬──────────────────────────┤
│  Вкладка 1 │ Вкладка 2 │ ...    │  Коментарі               │
│  ──────────────────────────────  │  ─────────────────────   │
│  ПІБ:  [Жулій Валерій        ]  │  💬 Немає коментарів     │
│  Відділ: [Бухгалтерія        ]  │                          │
│  ────── Особисті дані ────────  │  Теги                    │
│  Дата народж: [12.05.1985    ]  │  🏷 [+ додати]           │
│  ...                            │                          │
│                                 │  Зв'язки                 │
│  Пов'язані документи (DocDash) │  🔗 LeaveRequest (3)      │
│  ─────────────────────────────  │                          │
│  Відпустки: 3  Накази: 1       │  Версії                  │
│                                 │  🕐 v4, v3, v2...        │
│                                 │  Файли                   │
│                                 │  📎 passport.pdf         │
└───────────────────────────────────┴──────────────────────────┘
```

### Маршрути

| Маршрут | Що відкриває |
|---|---|
| `/app/:workspaceName/:doctype/new` | Нова форма (id = null) |
| `/app/:workspaceName/:doctype/:id` | Форма існуючого документа |
| `?tab=TabName` | Query param для активної вкладки |

### Ієрархія компонентів

```
WorkspaceFormView.vue          ← pages/workspace/ (тонка обгортка)
  WorkspaceBreadcrumb.vue      ← components/workspace/
  DocTypeForm.vue              ← pages/desk/  (весь стан і логіка)
    FormHeader.vue             ← components/views/form/  (кнопки: зберегти, редагувати, ...)
    WorkflowBar.vue            ← components/views/  (workflow статус і переходи)
    FormRenderer.vue           ← core/renderer/  (рендерить поля за схемою DocType)
      FieldRenderer.vue        ← core/renderer/  (рендерить одне поле за типом)
    DocSidebar.vue             ← components/views/  (права панель)
      SidebarTimeline.vue      ← components/views/sidebar/  (стрічка активності)
      SidebarTags.vue          ← components/views/sidebar/
      SidebarBacklinks.vue     ← components/views/sidebar/
      SidebarShare.vue         ← components/views/sidebar/
      SidebarFileInfo.vue      ← components/views/sidebar/
    VersionHistoryPanel.vue    ← components/views/  (список версій)
    DocDashboard.vue           ← components/views/form/  (пов'язані документи)
    FormModals.vue             ← components/views/form/  (модалки форми)
    QuickEntryDialog.vue       ← components/views/  (швидке створення зв'язаного)
```

### Stores

| Store | За що відповідає |
|---|---|
| `stores/doctype` | Схема DocType (поля, tabs, sections) |

### Ключові composables (DocTypeForm.vue)

| Composable | За що відповідає |
|---|---|
| `useDocument` | CRUD документа (`doc`, `save`, `delete`, `reload`) |
| `useFormInitialization` | Ініціалізація нового/існуючого документа |
| `useFormSave` | Логіка кнопки "Зберегти" (валідація → POST → toast) |
| `useFormValidation` | Валідація required-полів перед збереженням |
| `useFormNavigation` | Перехід між документами (← →) |
| `useFormDocWatcher` | Відстеження незбережених змін (dirty flag) |
| `useFormShortcuts` | Ctrl+S, Ctrl+Enter тощо |
| `useFormActions` | Кастомні дії з `actions` у DocType |
| `useClientScripts` | Виконання form hooks з `{DocType}.js` |
| `usePresence` | Аватари юзерів які зараз дивляться цей документ |
| `useFetchFrom` | Авто-заповнення полів з пов'язаного документа |

---

## 7. Dashboard

### Що показує

Дашборд workspace з налаштовуваними widgets: метрики, графіки, списки, ярлики тощо.

```
┌─────────────────────────────────────────────────────────────┐
│  Кадри — Огляд                                              │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Metric   │  │ Metric   │  │ Shortcut │                  │
│  │ 99+      │  │ 59       │  │ [+ Новий │                  │
│  │ Співроб. │  │ Відділів │  │  наказ]  │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
│  ┌──────────────────────────┐  ┌─────────────────────────┐ │
│  │ Chart (Bar/Line/Pie)     │  │ List                    │ │
│  │                          │  │ Нещодавні накази         │ │
│  └──────────────────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Маршрути

| Маршрут | Що відкриває |
|---|---|
| `/app/:workspaceName` | `WorkspaceHome.vue` — widgets workspace |
| `/app/:workspaceName/dashboard/:dashboardName` | `WorkspaceDashboard.vue` — окремий дашборд |

### Файли

| Елемент | Файл |
|---|---|
| WorkSpace — Робоча область (стартова сторінка додатку) | `pages/workspace/WorkspaceHome.vue` |
| Окремий дашборд | `pages/workspace/WorkspaceDashboard.vue` |
| Widget-обгортка | `components/dashboard/WidgetCard.vue` |
| Конфіг-панель widget | `components/dashboard/WidgetConfigPanel.vue` |

### Типи widgets

| Widget | Файл |
|---|---|
| Числова метрика | `components/dashboard/MetricWidget.vue` |
| Графік (bar/line/pie) | `components/dashboard/ChartWidget.vue` |
| Donut-діаграма | `components/dashboard/DonutWidget.vue` |
| Gauge | `components/dashboard/GaugeWidget.vue` |
| Список документів | `components/dashboard/ListWidget.vue` |
| Таблиця | `components/dashboard/TableWidget.vue` |
| Heatmap | `components/dashboard/HeatmapWidget.vue` |
| Funnel | `components/dashboard/FunnelWidget.vue` |
| Ярлики / Shortcuts | `components/dashboard/ShortcutWidget.vue`, `ShortcutsGridWidget.vue` |
| Посилання | `components/dashboard/LinksWidget.vue` |
| Текст | `components/dashboard/TextWidget.vue` |
| Годинник | `components/dashboard/ClockWidget.vue` |
| Календар | `components/dashboard/CalendarWidget.vue` |
| Стрічка активності | `components/dashboard/ActivityWidget.vue` |

---

## 8. Report View

### Маршрут

`/app/:workspaceName/report/:reportName`

### Файли

| Елемент | Файл |
|---|---|
| Сторінка | `pages/workspace/WorkspaceReportView.vue` |
| Report viewer | `pages/reports/ReportView.vue` |
| Query Report Builder | `pages/reports/QueryReportBuilder.vue` |
| API | `core/api/reports.ts` |

---

## 9. Studio — Form Builder

### Що показує

Візуальний редактор DocType: перетягування полів, налаштування властивостей, управління
permissions, views і workflow.

```
┌─────────────────────────────────────────────────────────────────┐
│  [Дизайнер │ Налаштування │ Permissions │ Views │ Workflow]     │
│  ─────────────────────────────────────────────────────────────  │
│  ┌──────────────┐  ┌────────────────────────┐  ┌────────────┐  │
│  │  Palette     │  │  Canvas                │  │ Properties │  │
│  │  ─────────   │  │  ─────────────────────  │  │ ─────────  │  │
│  │  Базові      │  │  ┌─ Section ─────────┐  │  │ Мітка:    │  │
│  │  [Data]      │  │  │ [ПІБ] [Дата н.] │  │  │ [ПІБ    ] │  │
│  │  [Int ]      │  │  └────────────────────┘  │  │ Тип:      │  │
│  │  [Float]     │  │  ┌─ Section ─────────┐  │  │ [Data   ] │  │
│  │  Зв'язки     │  │  │ [Відділ][Посада] │  │  │ Required: │  │
│  │  [Link ]     │  │  └────────────────────┘  │  │ [✓]       │  │
│  │  ...         │  │                          │  │ ...       │  │
│  └──────────────┘  └────────────────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Маршрути

| Маршрут | Що відкриває |
|---|---|
| `/app/grunt/DocType` | Список всіх DocType |
| `/app/grunt/DocType/:id` | Form Builder для конкретного DocType |

### Ієрархія компонентів

```
pages/studio/DocTypeList.vue          ← список DocType
pages/studio/builder/
  BuilderLayout.vue                   ← головна обгортка Builder
    BuilderCanvas.vue                 ← центральна зона (drag-and-drop)
      CanvasSection.vue               ← секція на canvas
      CanvasColumn.vue                ← колонка в секції
      CanvasFieldCard.vue             ← картка поля на canvas
      CanvasTabBar.vue                ← Tab-бар
    FieldPalette.vue                  ← ліва панель (доступні поля)
    PropertiesPanel.vue               ← права панель (властивості поля)
      sections/CoreSection.vue
      sections/FlagsSection.vue
      sections/DisplaySection.vue
      sections/ValidationSection.vue
      sections/LinkSection.vue
      ... (інші секції властивостей)
    BuilderPreview.vue                ← preview форми
  tabs/
    DesignerTab.vue                   ← вкладка "Дизайнер"
    SettingsTab.vue                   ← вкладка "Налаштування"
    PermissionsTab.vue                ← вкладка "Permissions"
    ViewsTab.vue                      ← вкладка "Views"
    WorkflowTab.vue                   ← вкладка "Workflow"
  WorkflowEditor.vue                  ← редактор Workflow (з pages/studio/workflow/)
```

### Stores

`stores/builder` — весь стан Form Builder (вибраний DocType, активний field, canvas layout)

### Ключові composables

| Composable | За що відповідає |
|---|---|
| `useBuilderLayout` | Стан canvas (sections, columns, fields) |
| `useBuilderPermissions` | Управління permission rules |
| `useBuilderWorkflow` | Стан workflow editor |
| `useBuilderFields` | Утиліти для роботи з полями |
| `usePropertyEditor` | Стан PropertiesPanel (що вибрано, яка секція) |

---

## 10. Overlay UI

### Що показує

Елементи, що накладаються поверх основного інтерфейсу незалежно від поточного маршруту.

```
┌────────────────────────────────────────┐
│  Command Palette          Esc          │
│  ────────────────────────────────────  │
│  🔍  Пошук документів, дій...         │
│  ────────────────────────────────────  │
│  Нещодавні                            │
│  📄 Жулій Валерій (Employee)          │
│  📄 Відпустка #123 (LeaveRequest)     │
│  ────────────────────────────────────  │
│  Дії                                  │
│  + Новий Співробітник                 │
│  + Новий Наказ                        │
└────────────────────────────────────────┘
```

### Файли та тригери

| Елемент | Файл | Тригер |
|---|---|---|
| Command Palette | `components/layout/CommandPalette.vue` | `Ctrl+K` / `⌘K` або кнопка Search у sidebar |
| Notifications Popover | `components/layout/NotificationsPopover.vue` | Кнопка 🔔 у sidebar |
| Palette Picker (акцент) | `components/layout/PalettePicker.vue` | User menu → Акцент |
| PWA Install Prompt | `components/pwa/PWAInstallPrompt.vue` | Браузер детектує PWA-можливість |
| Server Error Modal | `components/debug/ServerErrorModal.vue` | HTTP 500 з бекенду |
| GruntDialog | `components/desk/GruntDialog.vue` | `useDialog()` composable |

Всі overlay-елементи монтуються в `App.vue` на рівні кореня.

### Composables

| Composable | За що відповідає |
|---|---|
| `useNotifications` | Toast-повідомлення (`success`, `error`, `warn`) |
| `useToast` | Глобальний ref до PrimeVue Toast |
| `useDialog` | Програмне відкриття GruntDialog |
| `useShortcuts` | Глобальні keyboard shortcuts |
| `useServerError` | Стан ServerErrorModal |
| `useNetworkStatus` | Онлайн/офлайн статус |
| `useWebPush` | Web Push підписка |

---

## Швидкий довідник

> Таблиця для швидкого пошуку: "хочу змінити X — шукати у Y"

| Якщо потрібно змінити... | Файл |
|---|---|
| App Launcher (головна з картками додатків) | `pages/DeskPage.vue` |
| Картку додатку на Desk | `components/desk/AppCard.vue` |
| Sidebar (вся ліва панель) | `components/workspace/AppSidebar.vue` |
| Один пункт меню в sidebar | `components/workspace/SidebarItem.vue` |
| AppMenu (структуру меню, секції, пункти) | `{app}/fixtures/00_workspace.json` (doctype: AppMenu, може бути кілька записів на один додаток) |
| App Switcher (список додатків у sidebar) | `components/workspace/AppSidebar.vue` → `AppSwitcher` (popup) |
| Кнопку "На головну" / список інших додатків | `components/workspace/AppSidebar.vue` → `goToDesk()`, `otherWorkspaces` |
| Toolbar над списком (кнопки, view-switcher) | `components/views/DocTypeToolbar.vue` |
| Швидкі фільтри (chips під toolbar) | `components/views/FastFilterBar.vue` |
| Таблицю зі списком документів | `components/views/list/ListTableView.vue` |
| Заголовок таблиці (колонки) | `components/views/list/ListHeader.vue` |
| Kanban board | `components/views/kanban/KanbanView.vue` |
| Заголовок форми (кнопки Save, Edit, ...) | `components/views/form/FormHeader.vue` |
| Workflow bar (статуси і переходи) | `components/views/WorkflowBar.vue` |
| Праву панель форми (коментарі, теги, файли) | `components/views/DocSidebar.vue` |
| Рендер полів у формі | `core/renderer/FormRenderer.vue`, `core/renderer/FieldRenderer.vue` |
| Конкретний тип поля | `components/fields/{FieldName}/{FieldName}.vue` |
| Відображення поля в таблиці | `components/fields/{FieldName}/ListCell.vue` |
| Фільтр по полю | `components/fields/{FieldName}/FilterInput.vue` |
| Dashboard widgets | `components/dashboard/{WidgetName}Widget.vue` |
| Command Palette | `components/layout/CommandPalette.vue` |
| Notifications | `components/layout/NotificationsPopover.vue` |
| Form Builder (canvas) | `pages/studio/builder/BuilderCanvas.vue` |
| Form Builder (palette полів) | `pages/studio/builder/FieldPalette.vue` |
| Form Builder (властивості поля) | `pages/studio/builder/PropertiesPanel.vue` |
| Сторінки 404 / 403 | `pages/errors/NotFound.vue`, `pages/errors/Forbidden.vue` |
