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
  "status_config": { ... },
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
| `search_fields` | list[str] | Поля для full-text пошуку |
| `track_changes` | bool | Зберігати версії документа (default: `true`) |
| `default_view` | str | `"list"` / `"kanban"` / `"calendar"` / `"tree"` / `"map"` |
| `is_child` | bool | Дочірня таблиця (для `Table` поля). Власних прав не має: рядок читається, коли читається батьківський документ; змінюється лише збереженням батька |
| `is_singleton` | bool | Єдиний екземпляр (для налаштувань) |
| `is_tree` | bool | Ієрархічна структура |
| `quick_entry` | bool | Діалог швидкого створення |
| `is_virtual` | bool | Без власної таблиці — документи дає контролер на `BaseDocument` (див. нижче) |

### Віртуальний DocType — контролер на `BaseDocument`

`Document` зберігає документи в таблиці; `BaseDocument` — той самий документ без сховища.
Контролер віртуального доктайпа наслідує `BaseDocument` і перевизначає лише сховище —
конвеєр (події, `validate`/`before_save`/…, права на рядок, workflow, вебхуки) спільний.

```python
from grunt.document.base import BaseDocument, DocumentList
from grunt.document.in_memory import apply_filters, apply_search, apply_sort, build_response

class ExternalCustomer(BaseDocument):
    @classmethod
    async def get_list(cls, doctype, *, page=1, per_page=20, sort_by="name",
                       sort_order="asc", filters=None, search=None, **kwargs) -> DocumentList:
        rows = await api.list_customers()
        if filters: rows = apply_filters(rows, filters)   # той самий синтаксис field__op
        if search: rows = apply_search(rows, search, ["title"])
        return build_response(apply_sort(rows, sort_by, sort_order), page, per_page)

    async def load_from_db(self, *, expand=None):   # self.name → self.data, 404 якщо нема
        self.data = await api.get_customer(self.name)

    async def db_insert(self):  # self.data — новий документ; можна замінити self.data збереженим
        self.data = await api.create_customer(self.data)

    async def db_update(self):  # self.data — збережений + зміни; self.doc_before_save — до змін
        self.data = await api.update_customer(self.name, self.data)

    async def db_delete(self):
        await api.delete_customer(self.name)
```

- Не перевизначений метод → 405 (`db_*`), 404 (`load_from_db`), порожній список (`get_list`).
  `get_count` за замовчуванням бере `meta.total` з `get_list(per_page=1)`.
- Подані значення (часткові зміни) — `self.input_data`.
- Гібрид «список з таблиці, документ — звідкись ще» (як `DocType`): `get_list`/`get_count`
  делегують у `Document.get_list`/`Document.get_count`.

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
- Кожен наступний `Column` додає ще одну колонку
- Без `columns` — рівномірний розподіл

### Типовий патерн форми

```json
[
  { "fieldname": "tab_main",    "label": "Основне",    "fieldtype": "Tab", "icon": "file-text" },

  { "fieldname": "sec_header",  "label": "",            "fieldtype": "Section" },
  { "fieldname": "title",       "label": "Назва",       "fieldtype": "Text",   "required": true, "bold": true },

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
| `Text` | String(255) | Короткий текст, 1 рядок |
| `LongText` | Text | Довгий текст, багаторядковий textarea |
| `RichText` | Text | HTML-редактор з форматуванням |
| `Code` | Text | Код з підсвічуванням (JSON / Python / SQL) |

### Числа

| fieldtype | БД | Опис |
|-----------|----|------|
| `Int` | Integer | Ціле число |
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
| `Attach` | String(500) | Файл (PDF, DOCX тощо) |
| `Image` | String(500) | Зображення; відображається як прев'ю |
| `Icon` | String | Вибір Lucide іконки |
| `Signature` | Text | Електронний підпис (canvas) |

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
{ "fieldname": "title", "label": "Назва", "fieldtype": "Text" }
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
  "fieldtype": "Text",
  "is_virtual": true,
  "read_formula": "f\"{last_name} {first_name} {middle_name or ''}\".strip()"
}
```

### `fetch_from` — автозаповнення з пов'язаного документа

Формат: `link_field.field_name_in_linked_doctype`.

```json
{ "fieldname": "employee_position", "fieldtype": "Text", "fetch_from": "employee.position", "read_only": true }
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

## status_config

```json
{
  "status_config": {
    "field": "status",
    "indicators": [
      { "value": "Чернетка",    "color": "gray",   "icon": "circle"       },
      { "value": "Активний",    "color": "green",  "icon": "circle-check" },
      { "value": "На розгляді", "color": "yellow", "icon": "loader"       },
      { "value": "Скасовано",   "color": "red",    "icon": "circle-x"     }
    ]
  }
}
```

Кольори: `gray`, `blue`, `green`, `yellow`, `orange`, `red`.
Іконки — Lucide (lowercase, дефіс): `circle`, `circle-check`, `circle-x`, `loader`, `pen`, `archive`, `shield`.

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
  { "fieldname": "number",  "label": "Номер",  "fieldtype": "Text",   "read_only": true, "bold": true, "in_list_view": true },
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
  { "fieldname": "edrpou",          "label": "ЄДРПОУ",         "fieldtype": "Text", "mandatory_depends_on": "eval: doc.is_legal_entity" },
  { "fieldname": "iban",            "label": "IBAN",            "fieldtype": "Text" }
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
