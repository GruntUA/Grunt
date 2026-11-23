---
name: grunt-naming
description: Автоіменування документів у Grunt фреймворку — поле autoname в DocType, формати серій, токени дати й полів, naming_series:, Document Naming Rule, лічильники NamingSeries.
---

# Автоіменування документів у Grunt

## Як це працює

Поле `autoname` в `DocType.json` визначає, як генерується `name` нового документа.
Генерація відбувається при `INSERT` у `grunt/naming/service.py → NamingService.generate()`.

---

## Типи autoname

### 1. `prompt` — користувач вводить ім'я вручну

```json
{ "autoname": "prompt" }
```

При створенні документа поле `name` **обов'язково** передається в даних.
Якщо `name` відсутній — ім'я не згенерується (повернеться `None`).

```python
grunt.new_doc("Page", {"name": "about-us", "title": "About Us"})
```

---

### 2. `hash` — короткий UUID (fallback)

```json
{ "autoname": "hash" }
```

Генерує `uuid4().hex[:10]` — 10 символів hex. Використовується для службових/проміжних записів.
Також є **fallback** — якщо `autoname` порожній або не розпізнаний, застосовується `hash`.

---

### 3. `field:<fieldname>` — значення поля

```json
{ "autoname": "field:email" }
```

`name` документа = значення вказаного поля. Поле повинно бути унікальним або природним ключем.

```json
{ "autoname": "field:title" }   // Department, Position, LeaveType
{ "autoname": "field:email" }   // User
{ "autoname": "field:prefix" }  // NamingSeries (сама себе іменує)
```

---

### 4. Паттерн з токенами — серія + лічильник

```json
{ "autoname": "INV-.YYYY.-.####" }
```

Підтримувані токени:

| Токен   | Результат              | Приклад      |
|---------|------------------------|--------------|
| `.YYYY.` | 4-значний рік          | `2026`       |
| `.YY.`   | 2-значний рік          | `26`         |
| `.MM.`   | 2-значний місяць       | `03`         |
| `.DD.`   | 2-значний день         | `07`         |
| `.####.` | лічильник N цифр (zfill) | `0042`     |

Кількість `#` визначає ширину лічильника: `.###.` → `001`, `.#####.` → `00001`.

**Приклади паттернів і результатів:**

```
"EMP-.####"                  → EMP-0001
"INV-.YYYY.-.####"           → INV-2026-0042
"DOC-.YYYY.-.MM.-.###"       → DOC-2026-03-007
"CONTR-.YYYY.-.MM.-.DD.-.##" → CONTR-2026-03-07-01
"X-.YY.-.###"                → X-26-003
```

Ті самі токени можна писати у фігурних дужках (стиль `format:` із Frappe): `{YYYY}`, `{MM}`, `{####}`.

### 5. Значення поля в назві — `{fieldname}`

```json
{ "autoname": "ВХ-{department}-.YYYY.-.####" }   // ВХ-ЦНАП-2026-0001
```

Усе перед лічильником — ключ лічильника, тож **для кожного значення поля свій лік**
(`ВХ-ЦНАП-2026-`, `ВХ-ОСББ-2026-`). Порожнє поле → помилка валідації «Заповніть …».

### 6. `naming_series:` — серію обирає користувач

```json
{
  "autoname": "naming_series:",
  "fields": [
    {"fieldname": "naming_series", "fieldtype": "Select",
     "options": "ВХ-.YYYY.-.####\nВХ-СКАРГА-.YYYY.-.####"}
  ]
}
```

Значення поля — один із варіантів (порожнє → `default` поля або перший варіант;
обране записується в документ). Значення поза списком відхиляється — інакше будь-хто
міг би рахувати в чужій серії.

---

## Дата в назві

`YYYY/MM/DD` — **місцева** дата сайту (`settings.default_timezone`, `Europe/Kyiv`), а не UTC.
Якщо в DocType задано `naming_date_field` (поле Date/Datetime; «Дата для назви» в редакторі DocType),
дата береться з документа: лист, що надійшов 31.12, отримає номер минулого року, навіть якщо
його зареєстрували 2 січня. Порожнє поле → сьогодні.

---

## Document Naming Rule — серія за умовою

DocType `DocumentNamingRule` («Правила нумерації», меню Ґрунт → Конструктор):

| Поле | Зміст |
|------|-------|
| `document_type` | DocType, документи якого нумерує правило |
| `autoname` | Шаблон (той самий синтаксис, крім `prompt` і `naming_series:`) |
| `condition` | Python-вираз над `doc` (simpleeval), напр. `doc.department == 'ЦНАП'`; порожньо — завжди |
| `priority` | Вищий перевіряється першим |
| `disabled` | Вимкнене правило ігнорується |

Порядок вибору назви нового документа (`NamingService.new_name`):

1. Перше ввімкнене правило DocType, умова якого справджується → його шаблон
   (перекриває і `autoname` DocType, і `autoname()` контролера).
2. Переданий `name` — якщо шаблон **без** лічильника (фікстури, імпорт).
3. `autoname()` контролера.
4. `autoname` DocType (`naming_series:` → обрана серія).

Умова, що падає з помилкою, вважається хибною (лог `naming.rule_condition_failed`).
Умова бачить **надіслані** значення (до застосування default полів).
Правила кешуються на процес, скидаються при збереженні/видаленні правила.

---

## Зайняті номери

Якщо згенерована назва вже існує (лічильник відкотили, документ імпортовано з таким
номером) — береться наступний номер, до 1000 спроб, потім помилка «встановіть лічильник».

---

## Лічильники: DocType NamingSeries

Кожен унікальний **префікс** (частина паттерну до лічильника) має рядок у таблиці `NamingSeries`:

| Поле      | Тип  | Зміст                              |
|-----------|------|------------------------------------|
| `prefix`  | Text | Обчислений префікс (є `name`)      |
| `current` | Int  | Поточне значення лічильника        |

Префікс будується з паттерну шляхом заміни токенів дати на поточні значення:

```
"INV-.YYYY.-.####"  при 2026-03 → prefix = "INV-2026-"
"DOC-.YYYY.-.MM.-.###" при 2026-03 → prefix = "DOC-2026-03-"
"EMP-.####"         → prefix = "EMP-"
```

**Важливий наслідок:** при зміні дати (новий рік/місяць) — лічильник починається з 1, бо змінюється префікс. Це нормальна поведінка.

Атомарність: `SELECT ... FOR UPDATE` → increment → `FLUSH`.

Керування з UI: кнопка «Лічильник серії…» у формі DocType і правила; там само показано
«Наступна назва». API (`perm="grunt.manage_doctypes"`):

| Метод | Зміст |
|-------|-------|
| `grunt.api.v1.naming.preview(doctype, pattern?, doc?)` | `{pattern, prefix, current, next, fields}` — без збільшення лічильника; `fields` — поля, яких бракує для `{field}` |
| `grunt.api.v1.naming.counter(prefix)` | останній виданий номер |
| `grunt.api.v1.naming.set_counter(prefix, current)` | встановити останній виданий номер (наступний = +1) |

---

## Визначення в DocType.json

```json
{
  "name": "Invoice",
  "label": "Рахунок",
  "module": "billing",
  "autoname": "INV-.YYYY.-.####",
  "title_field": "title",
  "fields": [...]
}
```

`title_field` — окремий параметр, не пов'язаний з `autoname`. Визначає яке поле відображається як заголовок у UI (за замовчуванням `"name"`).

---

## Префікс `format:` зі Studio UI

Studio зберігає паттерн із префіксом `format:`:

```json
{ "autoname": "format:INV-.YYYY.-.####" }
```

`NamingService` автоматично відрізає цей префікс перед обробкою. В коді додатку писати `format:` не потрібно.

---

## Ключові файли

| Файл | Зміст |
|------|-------|
| `grunt/naming/patterns.py` | `parse_pattern`, `build_prefix`, `format_name`, `field_tokens`, `resolve_simple` |
| `grunt/naming/service.py` | `NamingService.new_name()` (порядок вибору), `generate()`, `preview()`, `set_current()`; `naming_date()`, `series_pattern()` |
| `grunt/naming/rules.py` | кеш Document Naming Rule, `matching_rule()` |
| `grunt/naming/doctypes/NamingSeries/NamingSeries.json` | DocType лічильників |
| `grunt/naming/doctypes/DocumentNamingRule/` | правило нумерації за умовою |
| `grunt/api/v1/naming.py` | preview / counter / set_counter |
| `grunt/document/mixins/lifecycle.py` | `_build_initial_row` → `naming_service.new_name()` при INSERT |
| `tests/test_naming.py`, `tests/test_naming_rules.py` | Тести паттернів, правил, naming_series, дат |

---

## Типові помилки

**1. `autoname: "field:title"` — поле порожнє**
`name` стане `None`, INSERT впаде з NOT NULL. Поле має бути required або мати default.

**2. Лічильник "починається зново"**
Не баг — змінився рік/місяць → новий префікс → новий лічильник від 1.
Якщо потрібен наскрізний лічильник — прибрати дату: `"EMP-.####"`.

**3. `prompt` без `name` в даних**
`resolve_simple("prompt", {})` поверне `None` → fallback на `hash`. Задокументувати у DocType що `name` обов'язковий.
