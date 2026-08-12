# План рефакторингу ядра Grunt

Мета: код ядра (`grunt/`) має виглядати написаним професійним архітектором — прості,
однозначні шляхи виконання, без дублювання, без прихованої магії. Правимо ядро прямо
й мінімально, без турботи про зворотну сумісність (фреймворк в активній розробці).

Джерело: архітектурний аудит `document/`, `db/`, `metadata/`, `main.py`, `hooks.py`,
`app/document_api.py`, `permissions/` (2026-08-12).

Порядок виконання: 0 → 1 → 2/3 паралельно → 4 → 5 → 7 → 6 останньою.
Після кожної фази — повний `pytest tests/` (зачіпається сам CRUD-пайплайн).

## Фаза 0 — Один вхід, одні гарантії ✅ DONE (2026-08-12)

Проблема: `app/document_api.py` (фасад `grunt_app.*`) викликав `hooks.fire(...)`
навколо CRUD, а `Document.insert()/save()/delete()` (`document/base.py`) — ні,
бо обидва йшли через `create_document/update_document/delete_document`
(`document/mixins/write.py`), які самі хуків не викликали. Наслідок: notification
rules, assignment rules, backlink sync, ActivityLog для create — усе спрацьовувало
лише через фасад, і мовчки НЕ спрацьовувало при прямому `doc.save()`/`doc.insert()`
з контролера чи фонового завдання.

Зроблено: `hooks.fire()` перенесено всередину `create_document/update_document/
delete_document` у `write.py` — тепер це єдине джерело істини для side-effects,
а фасад лише делегує. Асиметрія ActivityLog для create (раніше залежала від
викликаного лише через фасад wildcard-хука `log_activity`) вирішилась автоматично,
бо `after_insert` тепер завжди викликається з пайплайну.

Регресійний тест: `tests/test_docs_api.py::test_direct_insert_fires_same_hooks_as_facade`
(реєструє `hooks.on_doc` і перевіряє, що прямий `Document.insert()/.save()/.delete()`
викликає ті самі хуки, що й `grunt_app.new_doc/save_doc/delete_doc`). Повний
`pytest tests/` — 214/214 зелений.

Свідомо не чіпали: `collection.bulk_delete` — це окремий, задокументований
оптимізований batch-шлях (1 DELETE замість N), який навмисно не йде через
`hooks.fire` (notification/assignment/backlink sync) заради швидкості на великих
обсягах. Це не той самий клас бага — трейд-офф явний і задокументований у docstring.

## Фаза 1 — Зняти MRO-залежність mixins ✅ DONE (2026-08-12)

Було: `DocumentWriteMixin.get_document()` — заглушка, що кидає
`NotImplementedError`; реальна реалізація — в `DocumentReadMixin`. Працювало лише
завдяки порядку в `class Document(DocumentReadMixin, DocumentWriteMixin)`.

Зроблено: `DocumentWriteMixin` тепер явно успадковує `DocumentReadMixin`
(`class DocumentWriteMixin(DocumentReadMixin)`), заглушку-дублікат видалено —
`get_document` успадковується напряму. `Document` тепер має один базовий клас
(`class Document(DocumentWriteMixin)`), MRO фіксований і однозначний, порядок
базових класів більше нізвідки не читається. `session`/`_ml` типи-анотації теж
успадковуються, дублікат прибрано з `write.py`.

Заразом узгоджено свіжість метаданих: `delete_document()` тепер теж викликає
`self._resolve_dt()` (форсований lazy-reload), як і create/update — раніше
delete міг оперувати застарілим визначенням DocType в multi-worker деплої.

`pytest tests/` — 214/214 зелений, `ruff check` чистий.

## Фаза 2 — Декомпозиція god-функцій ✅ DONE (2026-08-12)

- `collection.list_documents()` (~165 рядків) розкладено на `_list_singleton`,
  `_select_columns`, `_resolve_list_filter_extra`, `_apply_where`,
  `_resolve_sort`, `_apply_pagination`, `_finalize_rows`, `_build_next_cursor` —
  за зразком декомпозиції в `write.py`.
- `metadata/registry.py:_inject_core()` (~140 → ~85 рядків): два хардкод-списки
  атрибутів винесено в документовані модульні константи
  `_CORE_SYNCED_DOCTYPE_ATTRS`/`_CORE_SYNCED_FIELD_ATTRS` з явним поясненням "це
  allow-list core-authoritative властивостей; усе інше — Studio/user
  customization, ніколи не перезаписується" + коментар "додав нову властивість —
  додай і сюди". **Свідомо НЕ перейшли на інтроспекцію моделі** — це змінило б
  поведінку (почало б силоміць перезаписувати workflow/permissions/list_view з
  JSON при кожному завантаженні, стираючи Studio-кастомізації користувачів); без
  підтвердження бізнес-наміру команди це надто ризиковано для "мінімальної"
  правки. Merge-логіку розбито на `_merge_core_fields`,
  `_sync_core_doctype_attrs`, `_sync_core_field_attrs`, `_reorder_core_fields`.
- `hooks.py:fire()` — докстрінг тепер явно перелічує всі 6 підсистем побічних
  ефектів (global/doctype хуки, server scripts, backlink sync, notification
  rules, assignment rules) з умовами спрацювання; код-структуру не чіпали
  (кожна стадія вже читається як окремий блок з власним try/except).

## Фаза 3 — Прибрати дублювання ✅ DONE (2026-08-12)

- WHERE-побудова в `collection.list_documents()` дублювалась для запиту й count
  → єдиний `_apply_where()`, використаний в обох.
- 6 майже ідентичних `_run_{create,update,delete}_{before,after}_hooks` у
  `write.py` → один `_run_lifecycle_hooks(doc, *hook_names)`.
- `_check_id` продубльований двічі в `tree.py` → винесено на рівень модуля
  (`_IDENTIFIER_RE` + `_check_id`).
- `_friendly_integrity_error` (regex-парсер помилок SQLite/Postgres) жив серед
  CRUD-логіки в `write.py` → винесено в новий `grunt/db/errors.py`
  (`friendly_integrity_error`), regex-и скомпільовано на рівні модуля.

`pytest tests/` — 214/214 зелений після кожної правки; `ruff check` на всіх
торкнутих файлах чистий.

## Фаза 4 — Видалити мертве/backward-compat ✅ DONE (2026-08-12)

- `metadata/field.py:register_field_type()` — легасі function-based API без
  жодного викликача (перевірено по всій кодовій базі, включно з усіма ~30
  реальними field-type плагінами під `frontend/src/components/fields/*/*.py` —
  усі вже на новому `FieldType`+`register_field_type_class`). Видалено.
  `_SA_TYPE_MAP`/`_FIELD_META`/`_PYTHON_TYPE_MAP` **не чіпали** — коментар
  називав їх "legacy", але вони насправді активно використовуються
  (`to_sa_column`, `is_physical_fieldtype`, `get_python_type`); коментар
  виправлено, щоб не вводив в оману.
- `db/api.py` — видалено дубльований `_db_proxy`/module `__getattr__`
  ("Backward-compatible module proxy"). Виявилось, що це **копія** того самого
  патерну, який вже легітимно живе в `grunt/db/__init__.py` (і там реально
  використовується для `grunt.db.get_all(...)`-стилю). Копія в `api.py` була
  недосяжна — ніщо не робить `import grunt.db.api as x; x.<unknown>`.
- `document/registry.py` — три "Backwards-compatible aliases" видалено;
  `main.py`/`cli/utils.py` переведено на прямі `index_core_controllers()` /
  `index_external_app_controllers()`. Заразом видалено `index_app_controllers()`
  (конвенція `grunt_apps/{app}/...`, яку викликав лише мертвий `discover_controllers`
  алias — самої директорії `grunt_apps/` в проєкті не існує) та невикористаний
  `_load_controller`.

`pytest tests/` — 214/214 зелений, `ruff check` на торкнутих файлах чистий
(2 лінт-warnings у `main.py:403-404` — pre-existing, не з цього рефакторингу).

## Фаза 5 — Єдина політика обробки помилок

`except Exception` — усюди по-різному (`.exception`, `.warning`, мовчазний
`pass`). Правило: best-effort побічні ефекти → `.warning()`, не переривають
транзакцію; обов'язкові кроки → `raise`. Застосувати послідовно в `relations.py`,
`collection.py`, `main.py`. Заразом: `tree.py` будує SQL вручну через
`text(f"...")` із саморобною валідацією ідентифікаторів → перевести на
`Table.cte(recursive=True)`.

## Фаза 6 — Межі модулів (найбільша, окремо і в кінці)

Пізні імпорти "щоб обійти циклічну залежність" — норма в `db/api.py`,
`document/base.py`, `relations.py`, `write.py`, `collection.py`, `tree.py`.
Симптом циклічної залежності `grunt.document` ↔ `grunt.db` ↔ `grunt.metadata` ↔
`grunt.app`. Виділити спільні примітиви в нижчий модуль без зворотних
залежностей.

## Фаза 7 — Дрібне (низький ризик, можна паралельно)

- `Document.__getattr__` тихо повертає `None` на невідоме поле — одруківка в
  назві поля мовчки ковтається. Попередження в debug-режимі.
- `DocTypeRegistry.get()` — наївна евристика однини/множини, продубльована в
  двох гілках, здатна мовчки резолвити не той DocType.
- Перейменування: `dt` → `doctype_def`; `Document.host()` → `Document.bare()`.
- Ambient `ContextVar` замість явного передавання залежностей — для нового коду
  explicit passing, ambient-fallback лишити як legacy-шлях на вихід.
