# ADR 001: Філософія структури фреймворку Grunt

## Статус

Прийнято — 2026-05-03

---

## Контекст

Grunt розробляється як metadata-driven фреймворк для побудови бізнес-застосунків.
Без задокументованих архітектурних рішень кожен розробник вирішує питання структури
по-своєму, що призводить до непослідовності: `grunt/core/doctypes/user/` (snake_case)
поряд з `hrm/hrm/doctypes/Employee/` (PascalCase), зайві рівні вкладеності `backend/`
та `core/`, фронтенд поза Python-пакетом тощо.

Цей ADR фіксує чотири фундаментальних рішення.

---

## Рішення 1: Термінологія deployment-контейнера → **project**

Директорія, що містить `apps/` і `sites/`, називається **project**.

```
my-project/              ← project
  apps/
    grunt/               ← фреймворк (теж app)
    hrm/                 ← застосунок
    cms/                 ← застосунок
  sites/
    dev.example.com/
      grunt.site         ← маніфест site
      .env
      grunt.db
    prod.example.com/
  .venv → apps/grunt/.venv
```

**CLI:**
```bash
grunt project create ./my-project   # створити project
grunt site create dev.example.com   # створити site всередині project
grunt site use dev.example.com      # активний site для CLI
```

**Чому не "bench":** bench — термін Frappe, не інтуїтивний поза цією екосистемою.
**Чому не "workspace":** надто абстрактно, не відображає deployment-природу.
**Чому "project":** Django project, Laravel project — зрозуміло з першого погляду.

---

## Рішення 2: Фреймворк = Додаток

Grunt — це просто Grunt-app, що надає ядро системи. `apps/grunt/` має **ідентичну**
структуру будь-якому іншому застосунку.

### Цільова структура (однакова для grunt і будь-якого app)

```
apps/{app_name}/
  {module_name}/            ← Python-модуль (один або кілька на app)
    doctypes/               ← доктайпи належать МОДУЛЮ, не app
      {DocTypeName}/
        ...
    {service}.py
  frontend/                 ← Vue-app ВСЕРЕДИНІ app (тільки у grunt)
    src/
      components/
        fields/             ← field type components + .py реєстрація
  grunt_app.py              ← маніфест + hooks
  app.json
  pyproject.toml
  package.json
  vite.config.ts
```

### Поточна структура grunt (підлягає міграції)

```
apps/grunt/
  backend/          ← зайвий рівень — буде видалено
    grunt/
      core/         ← зайвий рівень — буде видалено
        metadata/
        doctypes/
        ...
  frontend/         ← поза пакетом — буде переміщено всередину
```

### Після міграції

```
apps/grunt/
  auth/                    ← модуль; doctypes всередині нього
    doctypes/
      User/
      Role/
      ApiKey/
      UserSession/
    dependencies.py
    service.py
  document/
    doctypes/
      DocVersion/
      Comment/
      DocTag/
      DocLink/
    service.py
  email/
    doctypes/
      EmailAccount/
      EmailQueue/
    sender.py
  metadata/                ← ядро: DocType engine
    doctypes/
      DocType/
      DocField/
    compiler.py
    registry.py
  notification/
    doctypes/
      Notification/
      NotificationRule/
  webhook/
    doctypes/
      IncomingWebhook/
      OutgoingWebhook/
      WebhookLog/
  workflow/
    engine.py              ← стани/переходи в DocType.workflow, не окремі доктайпи
  api/                     ← модуль без доктайпів
  cache/
  cli/
  db/
  i18n/
  middleware/
  naming/
  permissions/
  print/
  reports/
  scripting/
  search/
  site/
  startup/
  storage/
  tasks/
  utils/
  webform/
  website/
  frontend/                ← Vue-app (було apps/grunt/frontend/)
    src/
      components/
        fields/
  grunt_app.py
  app.json
  pyproject.toml
  package.json
  vite.config.ts
```

**Наслідки для імпортів:**
```python
# До
from grunt.core.metadata import DocType
from grunt.core.document.service import DocumentService

# Після
from grunt.metadata import DocType
from grunt.document.service import DocumentService
```

**Вартість міграції:** висока. Виконується окремим кроком після ухвалення ADR.

---

## Рішення 3: Grunt — моноліт

Весь вбудований функціонал фреймворку живе в одному пакеті `grunt`.
Email, search, notifications, webhooks — не окремі пакети, а модулі фреймворку.

**Переваги:**
- `pip install grunt` → все доступно одразу
- Немає версійних конфліктів між grunt-core і grunt-email
- Межа чітка: `grunt/` — фреймворк, `apps/` — застосунки

**Виняток:** модуль може стати окремим пакетом лише якщо потребує важкої опціональної
залежності (напр., специфічний cloud SDK, ML-бібліотека). Рішення приймається окремо.

---

## Рішення 4: Доктайпи є частиною модуля, а не застосунку

**Принцип:** Модуль — основна одиниця організації коду. Доктайп завжди належить модулю,
а не безпосередньо app. App — лише контейнер для Python-пакету та маніфесту.

### Стандартна структура app

```
{app_name}/                      ← корінь app (git repo)
  {module_name}/                 ← Python-модуль (один або кілька на app)
    doctypes/
      {DocTypeName}/             ← PascalCase = точна назва DocType
        {DocTypeName}.json       ← схема DocType
        {DocTypeName}.py         ← Python controller
        {DocTypeName}.js         ← form hooks (опціонально)
        tests/
    reports/
      {ReportName}/
        {ReportName}.json        ← схема звіту
        {ReportName}.py          ← логіка звіту
        tests/
    print_formats/
      {FormatName}/
        {FormatName}.json        ← схема формату
        {FormatName}.html        ← Jinja-шаблон
    fixtures/                    ← початкові дані модуля (YAML/JSON)
    {service}.py                 ← бізнес-логіка модуля
  grunt_app.py                   ← маніфест + hooks
  app.json
  pyproject.toml
```

> Нові типи ресурсів (pages, dashboards, workflows тощо) додаються як нова
> піддиректорія всередині модуля за тим самим патерном.

### Приклад: hrm app з двома модулями

```
hrm/
  personnel/                     ← модуль "personnel"
    doctypes/
      Employee/
        Employee.json
        Employee.py
        Employee.js
        tests/
      Department/
      Position/
    reports/
      EmployeeList/
        EmployeeList.json
        EmployeeList.py
    print_formats/
      EmployeeCard/
        EmployeeCard.json
        EmployeeCard.html
    fixtures/
    service.py
  leave/                         ← модуль "leave"
    doctypes/
      LeaveRequest/
      LeaveType/
    reports/
      LeaveBalance/
    service.py
  grunt_app.py
  app.json
  pyproject.toml
```

### Grunt як app: кожен top-level модуль містить свої доктайпи

```
grunt/
  auth/                          ← модуль "auth"
    doctypes/
      User/
        User.json
        User.py
        User.js
        tests/
      Role/
      ApiKey/
      UserSession/
    dependencies.py
    service.py
  email/                         ← модуль "email"
    doctypes/
      EmailAccount/
      EmailQueue/
    sender.py
  notification/                  ← модуль "notification"
    doctypes/
      Notification/
      NotificationRule/
    service.py
  workflow/                      ← модуль "workflow"
    doctypes/
      (стани та переходи зберігаються в DocType.workflow, не окремі доктайпи)
    engine.py
  webhook/                       ← модуль "webhook"
    doctypes/
      IncomingWebhook/
      OutgoingWebhook/
      WebhookLog/
  search/                        ← модуль "search"
    doctypes/
      (немає окремих доктайпів)
    engine.py
  metadata/                      ← модуль "metadata" (ядро)
    doctypes/
      DocType/
      DocField/
    compiler.py
    registry.py
  document/                      ← модуль "document"
    doctypes/
      DocVersion/
      Comment/
      DocTag/
      DocLink/
    service.py
  ...
  grunt_app.py
  app.json
  pyproject.toml
```

### Правила іменування

| Об'єкт | Конвенція | Приклад |
|---|---|---|
| Директорія доктайпу | PascalCase | `Employee/`, `LeaveRequest/` |
| Файли всередині | відповідають назві директорії | `Employee.py`, `Employee.json` |
| Модуль | snake_case | `auth`, `hr_management`, `leave` |
| App root | snake_case | `hrm`, `grunt`, `ua_tools` |

**Чому PascalCase для директорій доктайпів:**
`ls auth/doctypes/` показує список DocType-імен без перетворень.
Імпорт контролера: `from grunt.auth.doctypes.User import User`.

### Що видалити з grunt

- `grunt/core/doctype/` (однина, поточна) — містить лише `user_utils.py`, не доктайп.
  Переміщується до `grunt/auth/`.

---

## Наслідки

| Рішення | Вартість | Коли |
|---|---|---|
| Термін "project" | низька — документація + CLI | наступний спринт |
| Флатенінг `core/` + видалення `backend/` | **висока** — всі імпорти | окремий refactoring PR |
| PascalCase для doctypes директорій | середня — перейменування + loader | разом з флатенінгом |
| Моноліт | нульова — поточний стан | зафіксовано |
