---
name: grunt-doctypes
description: Довідник по всіх типах полів, налаштуваннях DocType, layout (Tab/Section/Column), умовній логіці та advanced фічах Grunt фреймворку. Активується при створенні або редагуванні DocType.
---

# Grunt DocType — повний довідник полів і налаштувань

## Структура DocType.json

```json
{
  "name": "Invoice",
  "label": "Рахунок",
  "module": "billing",
  "autoname": "INV-.YYYY.-.####",
  "title_field": "title",
  "image_field": "photo",
  "search_fields": ["title", "client"],
  "track_changes": true,
  "default_view": "list",
  "fields": [ ... ],
  "status_field": "status",
  "status_indicators": [ ... ],
  "list_view": { ... },
  "form_view": { ... }
}
```

---

## DocType — налаштування рівня документа

| Параметр | Тип | Опис |
|----------|-----|------|
| `name` | str | PascalCase, унікальний в системі |
| `label` | str | Назва в UI |
| `module` | str | Модуль додатку (snake_case) |
| `autoname` | str | Правило генерації `name` — див. grunt-naming |
| `title_field` | str | Яке поле відображається як заголовок (default: `"name"`) |
| `image_field` | str | Поле Image/Attach для аватара в списку |
| `search_fields` | list[str] | Поля пошуку в списку й Link-полі (`name` і `title_field` — завжди); кожне слово запиту має знайтися в якомусь полі |
| `in_global_search` | bool | `false` — не індексувати для глобального пошуку Ctrl+K (службові записи, телеметрія, великі довідники). Default `true` |
| `track_changes` | bool | Зберігати версії документа (default: `true`) |
| `default_view` | str | `"list"` / `"kanban"` / `"calendar"` / `"tree"` / `"map"` |
| `is_child` | bool | Дочірня таблиця (для `Table` поля). Власних прав не має: рядок читається, коли читається батьківський документ; змінюється лише збереженням батька |
| `is_singleton` | bool | Єдиний екземпляр (для налаштувань) |
| `is_tree` | bool | Ієрархічна структура |
| `quick_entry` | bool | Діалог швидкого створення |
| `storage` | `"sql"` \| `"virtual"` | Де лежать документи: `sql` (типово) — таблиця DocType; `virtual` — без таблиці, документи дає сховище контролера, `store_class` (див. нижче). `meta.has_table` — `storage == "sql"` |

### Віртуальний DocType — сховище `VirtualStore`

Контролер — завжди `Document` (хуки й бізнес-логіка); де лежать документи, вирішує **сховище**
(`grunt.store`): за замовчуванням `SqlStore` (таблиця DocType), для віртуального — клас, який
контролер називає в `store_class`. Конвеєр (події, `validate`/`before_save`/…, права, workflow,
вебхуки, індекс пошуку) спільний для всіх сховищ.

```python
from grunt.document.base import Document
from grunt.query.query import Query, Sort
from grunt.store import DELETE, INSERT, UPDATE, Unavailable, VirtualStore


class ExternalCustomerStore(VirtualStore):
    capabilities = frozenset({INSERT, UPDATE, DELETE})  # без них — 405
    not_supported_message = None  # або N_("…") — текст 405
    search_fields = ("title",)  # None — name, title_field, search_fields DocType
    default_sort = Sort("title", descending=False)  # коли запитане поле в рядках відсутнє

    async def rows(self, query: Query) -> list[dict]:
        # Усі рядки джерела; фільтри, пошук, сортування, сторінки й ПРАВА (match, shares,
        # User Permissions) застосовує VirtualStore — так само, як SQL. query — лише підказка
        # (grunt.store.virtual.equals(query, "period") — значення фільтра field=value).
        if not api.ready():
            raise Unavailable(_("API недоступне"))  # порожній список з поясненням
        return await api.list_customers()

    async def get(self, name, *, expand=None):  # необов'язково; за замовчуванням — пошук у rows()
        return await api.get_customer(name)  # None → 404

    async def insert(self, doc, *, input, user):  # повертає збережений документ
        return await api.create_customer(doc)

    async def update(self, name, doc, *, before, input, user):
        # doc — збережений + зміни, before — до змін, input — лише подані значення
        return await self.output(await api.update_customer(name, doc))

    async def delete(self, name, *, before):
        await api.delete_customer(name)


class ExternalCustomer(Document):
    store_class = ExternalCustomerStore
```

- DocType з `"storage": "virtual"` без `store_class` — порожнє сховище: жодного документа, запис → 405.
- `update` повертає документ так, як його показує `output` (серіалізований).
- Гібрид «список з таблиці, документ — звідкись ще» (як `DocType`): `class DocTypeStore(SqlStore)`
  перевизначає `get`/`insert`/`update`/`delete`, `fetch`/`count` лишаються табличними.
- Що сховище вміє, — `capabilities` (`grunt.store`: `INSERT UPDATE DELETE AGGREGATE REFERENCES
  HISTORY BULK`); ядро відмовляє (405/400/422) замість падіння на відсутній таблиці.

---

## Layout: Tab → Section → Column

Поля `Tab`, `Section`, `Column` не зберігаються в БД — лише структурують форму.
Фронтенд парсить плаский масив `fields` у ієрархію `Tab > Section > [Column[]]`.

### Tab (вкладка)

```json
{ "fieldname": "tab_main", "label": "Основне", "fieldtype": "Tab", "icon": "info" }
```

- Все після `Tab` до наступного `Tab` — в цій вкладці
- Без `Tab` — одна неявна вкладка
- `icon` — назва Lucide іконки (lowercase: `"user"`, `"file-text"`, `"settings"`)

### Section (розділ)

```json
{ "fieldname": "sec_details", "label": "Деталі", "fieldtype": "Section", "collapsible": true }
```

- Групує поля в рамках вкладки
- `collapsible: true` — можна згорнути/розгорнути; стартує згорнутою, якщо всі поля в ній порожні
- `depends_on` на Section приховує весь розділ, на Tab — всю вкладку

### Column (колонка)

```json
{ "fieldname": "col_left",  "fieldtype": "Column" }
{ "fieldname": "col_right", "fieldtype": "Column" }
```

- Перший `Column` у розділі розбиває на дві колонки (ліва / права)
- Кожен наступний `Column` додає ще одну колонку (максимум 4)
- Колонки складаються в одну за шириною самого розділу (container query), а не
  вікна: 2 колонки — від `@lg`, 3 — від `@3xl`, 4 — від `@4xl`

### Ширина: `columns` (у дванадцятих, 1–12, за замовчуванням 12)

- **На `Column`** — частка розділу: `8` + `4` → дві третини й третина.
  Колонки без `columns` ділять решту порівну; якщо ширини не задано ніде —
  колонки рівні. Колонки з шириною стоять поруч лише з порогу (2 — `@lg`,
  3 — `@3xl`, 4 — `@4xl`), нижче — одна під одною
- **На будь-якому іншому полі** — частка своєї колонки: поля з `6` + `6` чи
  `4` + `4` + `4` стають в один рядок і переносяться, як слова. Поле без
  `columns` займає весь рядок. Вужча за ~24rem колонка показує всі поля на
  всю ширину
- Приховане поле (`depends_on`, `hidden`) місця в рядку не займає
- У Studio: ширина поля — у властивостях поля («Ширина»), ширина колонки —
  перемикач над колонкою на полотні розділу

```json
{ "fieldname": "agent_file", "fieldtype": "Attach", "columns": 8 },
{ "fieldname": "file_size",  "fieldtype": "Int", "options": "Bytes", "columns": 4 },
{ "fieldname": "checksum",   "fieldtype": "Data" }
```

Часто ширини полів у одній колонці дають кращий результат, ніж кілька
`Column`: пари «назва — значення» лишаються в одному рядку, а довге поле
(sha256, Code, LongText) без `columns` займає всю ширину. Розділ без
`label` (`"label": ""`) не має заголовка — зручно, щоб після `Column`
продовжити на всю ширину.

### Типовий патерн форми

```json
[
  { "fieldname": "tab_main",    "label": "Основне",    "fieldtype": "Tab", "icon": "file-text" },

  { "fieldname": "sec_header",  "label": "",            "fieldtype": "Section" },
  { "fieldname": "title",       "label": "Назва",       "fieldtype": "Data",   "required": true, "bold": true },

  { "fieldname": "sec_info",    "label": "Деталі",      "fieldtype": "Section" },
  { "fieldname": "col_a",       "fieldtype": "Column" },
  { "fieldname": "status",      "label": "Статус",      "fieldtype": "Select" },
  { "fieldname": "date",        "label": "Дата",        "fieldtype": "Date" },
  { "fieldname": "col_b",       "fieldtype": "Column" },
  { "fieldname": "amount",      "label": "Сума",        "fieldtype": "Float" },
  { "fieldname": "currency",    "label": "Валюта",      "fieldtype": "Select" },

  { "fieldname": "tab_extra",   "label": "Додатково",   "fieldtype": "Tab", "icon": "settings" },
  { "fieldname": "notes",       "label": "Примітки",    "fieldtype": "LongText" }
]
```

---

## Всі типи полів (fieldtype)

### Текст

| fieldtype | БД | Опис |
|-----------|----|------|
| `Data` | String(`max_length`, 255) | Короткий текст, 1 рядок. `options` — автопідказки (по одній на рядок), значення будь-яке |
| `LongText` | Text | Довгий текст, багаторядковий textarea |
| `RichText` | Text | HTML-редактор з форматуванням |
| `HTMLView` | Text | Розмітка, яку формує сервер (зведена таблиця, звіт): у формі рендериться як HTML, не редагується. Санітизується при кожному записі (і через `set_value`). Значення екрануйте `html.escape` |
| `Code` | Text | Код з підсвічуванням; мова в `options`: `json` / `python` / `sql` / `html` / `css` / `js` |

### Числа

| fieldtype | БД | Опис |
|-----------|----|------|
| `Int` | Integer | Ціле число; з `"options": "Bytes"` — розмір у байтах, показується як `1.4 MB` (у списку й у формі; точне число — в підказці) |
| `Float` | Float(6) | Дробове число |
| `Percent` | Float(6) | Відсоток, відображається з `%` |
| `Duration` | Float(6) | Тривалість (год/хв) |
| `Rating` | Float(2) | Зірки 1–5 |

### Дата/час

| fieldtype | БД | Опис |
|-----------|----|------|
| `Date` | Date | Лише дата |
| `Time` | Time | Лише час |
| `Datetime` | DateTime(tz) | Дата + час з timezone |

### Вибір

| fieldtype | БД | Опис |
|-----------|----|------|
| `Check` | Boolean | Чекбокс |
| `Select` | String(100) | Список опцій; `options`: рядки через `\n` |
| `MultiSelect` | JSON | Множинний вибір |
| `Color` | String(20) | Палітра кольорів |

```json
{ "fieldtype": "Select", "options": "Чернетка\nПідписано\nВідправлено" }
```

`"translatable": true` (Select / MultiSelect) — підписи опцій перекладаються (msgctxt `select:<DocType>.<field>`), а в БД зберігається незмінне значення: схема віддає `option_labels` {значення: підпис}. Вмикати для людських слів (`Open\nClosed`, `Low\nHigh`); технічні коди (fieldtype, кольори, події) — без прапорця, вони не перекладаються взагалі.

```json
{ "fieldtype": "Select", "options": "Open\nIn Progress\nClosed", "translatable": true }
```

### Посилання

| fieldtype | БД | Опис |
|-----------|----|------|
| `Link` | String(255) | FK на інший DocType; `options`: назва DocType |
| `DynamicLink` | String(255) | Посилання на довільний DocType (визначається полем) |
| `MultiLink` | — | М2М, не фізичне поле |

```json
{ "fieldtype": "Link", "options": "Employee" }
{ "fieldtype": "Link", "options": "Employee", "link_filters": "{\"status\": \"Працює\"}" }
```

### Файли та медіа

| fieldtype | БД | Опис |
|-----------|----|------|
| `Attach` | String(500) | Файл (PDF, DOCX тощо); дозволені типи — нижче |
| `Image` | String(500) | Зображення; відображається як прев'ю |
| `Icon` | String | Вибір Lucide іконки |
| `Signature` | Text | Електронний підпис (canvas) |

**Які файли можна прикріпити.** Перелік задає адмін сайту в «Системні
налаштування → Файли → Дозволені типи файлів» (`SystemSettings.allowed_file_types`,
дефолт — зображення, PDF, офісні документи, text/csv/json, zip, підписи/сертифікати):
MIME-типи або розширення (`.exe`), по одному на рядок чи через кому.
Розширення звіряється з іменем файлу, бо браузер шле `.exe` то як
`application/x-msdownload`, то як `application/octet-stream`. Серверний код
перевіряє тип через `await files.validate_file_type(content_type, filename)`
(його ж викликає `files.store`). Файли завжди віддаються як завантаження.

### Структуровані дані

| fieldtype | БД | Опис |
|-----------|----|------|
| `Table` | — | Дочірня таблиця; `options`: ім'я child DocType |
| `JSON` | JSON | Вільна JSON структура |

```json
{ "fieldtype": "Table", "options": "InvoiceLine" }
```

### Спеціальні

| fieldtype | БД | Опис |
|-----------|----|------|
| `Button` | — | Кнопка-дія |
| `Geolocation` | JSON | Координати (карта) |
| `BarCode` | String(255) | Штрихкод |

---

## Властивості поля (DocField)

### Обов'язкові

```json
{ "fieldname": "title", "label": "Назва", "fieldtype": "Data" }
```

### Відображення в списку

```json
{ "in_list_view": true, "bold": true }
```

`bold: true` виділяє жирним в списку — використовуй для головного поля (title, number).

### Валідація

```json
{
  "required": true,
  "unique": true,
  "min_value": 0,
  "max_value": 100,
  "max_length": 200,
  "regex": "^[A-Z]{3}-\\d{4}$"
}
```

### Доступ

```json
{ "read_only": true }
{ "hidden": true }
{ "index": true }
```

`index: true` — додає DB індекс. Використовуй для полів що фільтруються або сортуються часто.

### Значення за замовчуванням

```json
{ "default": "Чернетка" }
{ "default": "Today" }
{ "default": "1" }
```

`"Today"` — спеціальне значення для `Date`, підставляє поточну дату.

### Допоміжний текст

```json
{ "description": "Заповнюється автоматично при збереженні" }
{ "placeholder": "Введіть ЄДРПОУ..." }
```

### Швидкий перегляд і фільтри

```json
{
  "in_filter": true,
  "in_quick_entry": true,
  "in_quick_filter": true
}
```

---

## Умовна логіка

### `depends_on` — умова видимості

Вираз JavaScript з префіксом `eval:` (доступна змінна `doc`) або просто ім'я поля —
тоді умова «поле заповнене/увімкнене».

```json
{ "depends_on": "has_discount" }
{ "depends_on": "eval: doc.order_type === 'Відпустка'" }
{ "depends_on": "eval: doc.has_discount" }
{ "depends_on": "eval: doc.amount > 0 && doc.status !== 'Скасовано'" }
```

Якщо вираз = `false` — поле (або Section) зникає з форми.

### `mandatory_depends_on` — умовна обов'язковість

```json
{ "mandatory_depends_on": "eval: doc.type === 'Юридична особа'" }
```

Поле стає обов'язковим лише якщо умова виконується.

---

## Авто-обчислення

### `formula` — обчислювальне поле (Python, при збереженні)

Вираз виконується на backend при кожному `save`. Контекст: всі поля документа як змінні.

```json
{
  "fieldname": "total",
  "fieldtype": "Float",
  "formula": "qty * unit_price",
  "read_only": true
}
```

```json
{ "formula": "price * qty * (1 - discount / 100) if discount else price * qty" }
{ "formula": "round(amount * vat_rate / 100, 2)" }
```

Доступні: `abs, round, min, max, sum, len, str, int, float, bool`. Без імпортів.

### `read_formula` + `is_virtual` — віртуальне поле (Python, при читанні)

Поле не зберігається в БД. Обчислюється кожен раз при отриманні документа.

```json
{
  "fieldname": "full_name",
  "fieldtype": "Data",
  "is_virtual": true,
  "read_formula": "f\"{last_name} {first_name} {middle_name or ''}\".strip()"
}
```

### `fetch_from` — автозаповнення з пов'язаного документа

Формат: `link_field.field_name_in_linked_doctype`.

```json
{ "fieldname": "employee_position", "fieldtype": "Data", "fetch_from": "employee.position", "read_only": true }
```

При зміні поля `employee` (Link) — автоматично підтягується `position` з Employee.

### `aggregate_function` — агрегація з дочірньої таблиці

```json
{
  "fieldname": "total_amount",
  "fieldtype": "Float",
  "label": "Загальна сума",
  "aggregate_function": "sum",
  "aggregate_table": "items",
  "aggregate_field": "amount",
  "read_only": true
}
```

| `aggregate_function` | Опис |
|----------------------|------|
| `sum` | Сума значень |
| `count` | Кількість рядків |
| `avg` | Середнє |
| `min` / `max` | Мінімум / максимум |

`aggregate_table` — `fieldname` поля типу `Table`. `aggregate_field` — поле в child DocType.

---

## Статуси: status_field + status_indicators

Select-поле статусу показується кольоровим бейджем з іконкою (список, шапка форми,
бічна панель, канбан, експорт у HTML).

```json
{
  "status_field": "status",
  "status_indicators": [
    { "value": "Чернетка",    "color": "secondary", "icon": "pencil-line"  },
    { "value": "На розгляді", "color": "info",      "icon": "loader"       },
    { "value": "Активний",    "color": "success",   "icon": "circle-check" },
    { "value": "Призупинено", "color": "warn",      "icon": "circle-pause" },
    { "value": "Скасовано",   "color": "danger",    "icon": "circle-x"     }
  ]
}
```

- `status_field` — fieldname Select-поля (будь-яке, напр. `list_status`); без нього
  бейдж береться з поля `status`.
- `value` — точне значення опції; `label` — інший підпис (перекладається, як і `value`).
- Кольори (`StatusIndicator.color`): `secondary` (сірий, за замовчуванням), `info` (синій),
  `success` (зелений), `warn` (жовтий), `danger` (червоний), `contrast`. Старі назви
  `gray`/`blue`/`green`/`yellow`/`orange`/`red`/`purple`/`pink` теж працюють.
- Іконки — Lucide (lowercase, дефіс): `circle`, `circle-check`, `circle-x`, `loader`,
  `pencil-line`, `archive`, `eye-off`, `circle-slash`, `shield`.
- Бейдж малюється для Select; для «Активний/Неактивний» з бейджем — Select, не Check.

---

## Налаштування відображень

### list_view

```json
{
  "list_view": {
    "fields": ["title", "status", "date"],
    "sort_by": "date",
    "sort_order": "desc",
    "default_filters": { "status__ne": "Архів" },
    "fast_filters": [
      { "fieldname": "status", "label": "Статус" }
    ]
  }
}
```

### form_view

```json
{
  "form_view": {
    "layout": "wide"
  }
}
```

`layout`: `"standard"` (default) / `"compact"` / `"wide"`.

### kanban_view

```json
{
  "kanban_view": {
    "column_field": "status",
    "title_field": "title",
    "color_field": "priority"
  }
}
```

### calendar_view

```json
{
  "calendar_view": {
    "field": "start_date",
    "end_field": "end_date",
    "title_field": "title"
  }
}
```

---

## Типові патерни

### Ідентифікатор + статус (шапка)

```json
[
  { "fieldname": "number",  "label": "Номер",  "fieldtype": "Data",   "read_only": true, "bold": true, "in_list_view": true },
  { "fieldname": "date",    "label": "Дата",   "fieldtype": "Date",   "required": true,  "default": "Today", "in_list_view": true },
  { "fieldname": "col_h",   "fieldtype": "Column" },
  { "fieldname": "status",  "label": "Статус", "fieldtype": "Select", "required": true,  "default": "Чернетка", "in_list_view": true, "in_filter": true }
]
```

### Сума + ПДВ + разом (formula)

```json
[
  { "fieldname": "amount",     "label": "Сума",  "fieldtype": "Float", "required": true },
  { "fieldname": "vat_rate",   "label": "ПДВ %", "fieldtype": "Float", "default": 20 },
  { "fieldname": "vat_amount", "label": "ПДВ",   "fieldtype": "Float", "formula": "round(amount * vat_rate / 100, 2)", "read_only": true },
  { "fieldname": "total",      "label": "Разом", "fieldtype": "Float", "formula": "amount + vat_amount", "read_only": true, "bold": true }
]
```

### Умовний блок (depends_on)

```json
[
  { "fieldname": "is_legal_entity", "label": "Юридична особа", "fieldtype": "Check" },
  { "fieldname": "sec_legal",       "label": "Реквізити",      "fieldtype": "Section", "depends_on": "eval: doc.is_legal_entity" },
  { "fieldname": "edrpou",          "label": "ЄДРПОУ",         "fieldtype": "Data", "mandatory_depends_on": "eval: doc.is_legal_entity" },
  { "fieldname": "iban",            "label": "IBAN",            "fieldtype": "Data" }
]
```

### Таблиця з агрегацією

```json
[
  { "fieldname": "items",        "label": "Позиції",       "fieldtype": "Table", "options": "InvoiceLine" },
  { "fieldname": "total_amount", "label": "Загальна сума", "fieldtype": "Float",
    "aggregate_function": "sum", "aggregate_table": "items", "aggregate_field": "line_total",
    "read_only": true, "bold": true }
]
```
