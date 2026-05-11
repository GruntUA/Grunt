# ADR 003: Візуальна карта UI-зон Grunt

## Статус

Прийнято — 2026-05-11 (оновлено)

---

## Контекст

Grunt-frontend складається з десятків компонентів, сторінок і stores. Без єдиної карти важко швидко знайти що потрібно змінити. Цей документ є **візуальним довідником**: для кожної UI-зони — що вона робить, який маршрут, які файли, який store.

---

## Загальна схема маршрутів

```
/login                            → pages/auth/Login.vue
/app                              → pages/DeskPage.vue            ← App Launcher
/app/:workspaceName               → pages/app/AppLayout.vue
  (дочірні маршрути)
  /                               → pages/app/AppHome.vue
  /:doctype                       → pages/app/AppListView.vue
  /:doctype/new                   → pages/app/AppFormView.vue
  /:doctype/:id                   → pages/app/AppFormView.vue
  /page/:pageName                 → pages/app/AppPage.vue
  /report/:reportName             → pages/reports/ReportView.vue
  /search                         → pages/app/SearchResultsPage.vue
  /files                          → pages/desk/FileManager.vue
/403                              → pages/errors/Forbidden.vue
/* (404)                          → pages/errors/NotFound.vue
```

---

## 1. Desk — App Launcher

### Що показує

Головна сторінка після логіну. Показує всі встановлені додатки у вигляді карток, лічильники документів по кожному, нещодавно відкриті документи та стрічку активності.

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
│  ─────────────────────────    ─────────────────────     │
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
| Store | `stores/auth` (ім'я юзера), `stores/app` (список workspaces) |
| API | `core/api/workspace.ts` → `getCounts()` |

---

## 2. App Layout

### Що робить

Обгортка для всіх сторінок всередині одного workspace. Відповідає за:
- Рендер `AppSidebar` (desktop) або `Drawer` (mobile)
- Передачу `workspaceName` у дочірні маршрути
- Показ `NotFound` якщо workspace не існує

### Файли

| Елемент | Файл |
|---|---|
| Layout-обгортка | `pages/app/AppLayout.vue` |
| Sidebar (desktop) | `components/app/AppSidebar.vue` |
| Sidebar (mobile) | `components/mobile/MobileBottomNav.vue` + PrimeVue `Drawer` |

### Stores

| Store | За що відповідає |
|---|---|
| `stores/app` | Завантаження і збереження активного workspace (`setActive`) |
| `stores/sidebar` | Collapsed/expanded стан sidebar |

---

## 3. Sidebar

### Що показує

Ліва панель навігації всередині workspace. Містить:
- **App Switcher** (кнопка + popup-меню зі списком всіх додатків)
- **Search** — відкриває Command Palette
- **Notifications** — NotificationsPopover
- **Закріплені документи** (pinnedItems з localStorage)
- **Огляд** — посилання на AppHome (домашня сторінка)
- **AppMenu** — навігаційні елементи, згруповані по секціях
- **Адмін shortcuts** (тільки superadmin): Права доступу, Журнал, Пошта, Редагувати меню
- **Footer** — аватар + ім'я юзера → user menu (тема, акцент, вийти)

```
┌───────────────────────────────────┐
│  [👥 Кадри         ˅]  ← App Switcher
├───────────────────────────────────┤
│  🔍 Пошук...               ⌘K    │
│  🔔 Сповіщення                   │
│  📌 Закріплені (якщо є)          │
├───────────────────────────────────┤
│  ⬜ Огляд                        │  ← AppHome
├───────────────────────────────────┤
│  СПІВРОБІТНИКИ                    │  ← AppMenu (секція)
│  👤 Співробітники          99+   │
│  🏢 Відділи                59   │
│  💼 Посади                 44   │
│  ДОКУМЕНТИ                        │
│  📄 Накази                  6   │
│  📊 Огляд HRM (Page)            │  ← sidebar item type=Page
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
| Весь sidebar | `components/app/AppSidebar.vue` |
| Один пункт меню | `components/app/SidebarItem.vue` |
| Breadcrumb (вгорі контенту) | `components/app/AppBreadcrumb.vue` |
| Notifications popover | `components/layout/NotificationsPopover.vue` |
| Іконка додатку | `components/AppIcon.vue` |

### AppMenu — конфігурація навігації

Структура sidebar визначається у fixture-файлі додатку через записи DocType **AppMenu**.
В одному додатку може бути кілька AppMenu — кожен відображається як окремий іменований блок у sidebar.

```
grunt_apps/{app}/fixtures/00_workspace.json  ← doctype: AppMenu (один або кілька записів)
```

Після зміни файлу:
```bash
grunt fixture import hrm
```

### Stores

| Store | За що відповідає |
|---|---|
| `stores/app` | `workspaces`, `active`, `groupedItems`, `counts` |
| `stores/sidebar` | `isCollapsed` |
| `stores/auth` | `user` (ім'я, аватар, is_superadmin) |

---

## 4. AppHome (Домашня сторінка)

### Що показує

Стартова сторінка додатку. Якщо у AppMenu налаштоване поле `home_page` (посилання на **Page** докумeнт), завантажує та рендерить його widgets. Якщо `home_page` не вказано — показує порожній стан з підказкою.

### Маршрут

`/app/:workspaceName` (порожній дочірній маршрут)

### Файли

| Елемент | Файл |
|---|---|
| Сторінка | `pages/app/AppHome.vue` |
| Widget-картка | `components/dashboard/WidgetCard.vue` |
| Окремі widgets | `components/dashboard//*.vue` |

### Stores / API

- `stores/app` → `active.home_page` (name документа Page)
- `core/api/pages.ts` → `getPageData(pageName)` — обчислює дані widgets
- `core/api/docs.ts` → `docsApi.get('Page', pageName)` — завантажує список widgets

---

## 5. Page (Сторінка)

### Концепція

`Page` — уніфікований DocType для будь-якого комбінованого контенту: дашборди з метриками/графіками, сторінки з ярликами і посиланнями, або змішані. Різниця між "дашбордом" і "воркспейсом" — тільки в тому, якими widgets заповнює сторінку користувач. Зберігається в DocType `Page` (таблиця: `grunt_site_page`).

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
│  │ Chart (Bar/Area/Donut)   │  │ List                    │ │
│  │                          │  │ Нещодавні накази         │ │
│  └──────────────────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Маршрут

`/app/:workspaceName/page/:pageName`

### DocType

| Поле | Тип | Опис |
|---|---|---|
| name | autoname | Унікальний ідентифікатор |
| label | Text | Назва сторінки |
| description | Text | Опис |
| is_published | Check | Видима не-адмінам |
| roles | Text | Доступ за ролями (через кому) |
| widgets | Table → PageWidget | Список widgets |

Дочірня таблиця **PageWidget** (таблиця: `grunt_site_page_widget`) містить конфігурацію кожного widget.

### Файли

| Елемент | Файл |
|---|---|
| Перегляд / редагування | `pages/app/AppPage.vue` |
| Widget-обгортка | `components/dashboard/WidgetCard.vue` |
| Конфіг-панель widget | `components/dashboard/WidgetConfigPanel.vue` |

### API

| | |
|---|---|
| Дані widgets | `GET /api/v1/page-data/:name` |
| CRUD | `core/api/docs.ts` → `docsApi.get/create/update('Page', ...)` |
| Frontend | `core/api/pages.ts` → `getPageData(name)` |

### Типи widgets

| Widget | Файл |
|---|---|
| Числова метрика | `components/dashboard/MetricWidget.vue` |
| Gauge | `components/dashboard/GaugeWidget.vue` |
| Графік (bar/area) | `components/dashboard/ChartWidget.vue` |
| Donut-діаграма | `components/dashboard/DonutWidget.vue` |
| Список документів | `components/dashboard/ListWidget.vue` |
| Таблиця | `components/dashboard/TableWidget.vue` |
| Heatmap | `components/dashboard/HeatmapWidget.vue` |
| Funnel | `components/dashboard/FunnelWidget.vue` |
| Ярлик (shortcut) | `components/dashboard/ShortcutWidget.vue` |
| Сітка ярликів | `components/dashboard/ShortcutsGridWidget.vue` |
| Посилання (links) | `components/dashboard/LinksWidget.vue` |
| Текст | `components/dashboard/TextWidget.vue` |
| Годинник | `components/dashboard/ClockWidget.vue` |
| Календар | `components/dashboard/CalendarWidget.vue` |
| Стрічка активності | `components/dashboard/ActivityWidget.vue` |

---

## 6. List View

### Маршрут

`/app/:workspaceName/:doctype`

### Ієрархія компонентів

```
AppListView.vue                ← pages/app/
  AppBreadcrumb.vue            ← components/app/
  DocTypeList.vue              ← pages/desk/
    DocTypeToolbar.vue         ← components/views/
    ListViewRouter.vue         ← components/views/list/
      ListTableView.vue
      KanbanView.vue
      CalendarView.vue
      GalleryView.vue
      MapView.vue
      TreeView.vue
    ListHeader.vue
    BulkActionBar.vue
    ListPagination.vue
    QuickEntryDialog.vue
```

---

## 7. Form View

### Маршрути

| Маршрут | Що відкриває |
|---|---|
| `/app/:workspaceName/:doctype/new` | Нова форма |
| `/app/:workspaceName/:doctype/:id` | Форма існуючого документа |

### Ієрархія компонентів

```
AppFormView.vue                ← pages/app/
  AppBreadcrumb.vue            ← components/app/
  DocTypeForm.vue              ← pages/desk/
    FormHeader.vue             ← components/views/form/
    WorkflowBar.vue            ← components/views/
    FormRenderer.vue           ← core/renderer/
    DocSidebar.vue             ← components/views/
    DocDashboard.vue           ← components/views/form/
```

---

## 8. Report View

### Маршрут

`/app/:workspaceName/report/:reportName`

### Файли

| Елемент | Файл |
|---|---|
| Сторінка | `pages/app/AppReportView.vue` |
| Report viewer | `pages/reports/ReportView.vue` |
| Query Report Builder | `pages/reports/QueryReportBuilder.vue` |
| API | `core/api/reports.ts` |

---

## 9. Studio — Form Builder

### Маршрути

| Маршрут | Що відкриває |
|---|---|
| `/app/grunt/DocType` | Список всіх DocType |
| `/app/grunt/DocType/:id` | Form Builder для конкретного DocType |

### Ієрархія компонентів

```
pages/studio/builder/
  BuilderLayout.vue
    BuilderCanvas.vue
    FieldPalette.vue
    PropertiesPanel.vue
    BuilderPreview.vue
  tabs/
    DesignerTab.vue
    SettingsTab.vue
    PermissionsTab.vue
    ViewsTab.vue
    WorkflowTab.vue
```

### Stores

`stores/builder`

---

## 10. Overlay UI

| Елемент | Файл | Тригер |
|---|---|---|
| Command Palette | `components/layout/CommandPalette.vue` | `Ctrl+K` / кнопка Search |
| Notifications Popover | `components/layout/NotificationsPopover.vue` | Кнопка 🔔 |
| Palette Picker | `components/layout/PalettePicker.vue` | User menu → Акцент |
| Server Error Modal | `components/debug/ServerErrorModal.vue` | HTTP 500 |

---

## Швидкий довідник

| Якщо потрібно змінити... | Файл |
|---|---|
| App Launcher (головна з картками) | `pages/DeskPage.vue` |
| Картку додатку на Desk | `components/desk/AppCard.vue` |
| Sidebar (вся ліва панель) | `components/app/AppSidebar.vue` |
| Один пункт меню в sidebar | `components/app/SidebarItem.vue` |
| AppMenu (структуру меню) | `{app}/fixtures/00_workspace.json` (doctype: AppMenu) |
| App Switcher | `components/app/AppSidebar.vue` → AppSwitcher popup |
| Домашню сторінку (AppHome) | `pages/app/AppHome.vue` |
| Page (сторінку з widgets) | `pages/app/AppPage.vue` |
| Widget будь-якого типу | `components/dashboard/{WidgetName}Widget.vue` |
| Конфігурацію widget у редакторі | `components/dashboard/WidgetConfigPanel.vue` |
| Toolbar над списком | `components/views/DocTypeToolbar.vue` |
| Таблицю зі списком документів | `components/views/list/ListTableView.vue` |
| Заголовок форми | `components/views/form/FormHeader.vue` |
| Праву панель форми | `components/views/DocSidebar.vue` |
| Рендер полів у формі | `core/renderer/FormRenderer.vue` |
| Конкретний тип поля | `components/fields/{FieldName}/{FieldName}.vue` |
| Command Palette | `components/layout/CommandPalette.vue` |
| Form Builder (canvas) | `pages/studio/builder/BuilderCanvas.vue` |
| Form Builder (властивості поля) | `pages/studio/builder/PropertiesPanel.vue` |
| Сторінки 404 / 403 | `pages/errors/NotFound.vue`, `pages/errors/Forbidden.vue` |
