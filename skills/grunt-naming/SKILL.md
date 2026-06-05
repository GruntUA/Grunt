---
name: grunt-naming
description: Автоіменування документів у Grunt фреймворку — поле autoname в DocType, формати серій, токени дати, лічильники NamingSeries.
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
| `grunt/naming/patterns.py` | `parse_pattern`, `build_prefix`, `format_name`, `resolve_simple` |
| `grunt/naming/service.py` | `NamingService.generate()`, `_next_counter()` |
| `grunt/naming/doctypes/NamingSeries/NamingSeries.json` | DocType лічильників |
| `grunt/document/mixins/write.py:132` | Виклик `naming_service.generate()` при INSERT |
| `tests/test_naming.py` | Тести паттернів |

---

## Типові помилки

**1. `autoname: "field:title"` — поле порожнє**
`name` стане `None`, INSERT впаде з NOT NULL. Поле має бути required або мати default.

**2. Лічильник "починається зново"**
Не баг — змінився рік/місяць → новий префікс → новий лічильник від 1.
Якщо потрібен наскрізний лічильник — прибрати дату: `"EMP-.####"`.

**3. `prompt` без `name` в даних**
`resolve_simple("prompt", {})` поверне `None` → fallback на `hash`. Задокументувати у DocType що `name` обов'язковий.
