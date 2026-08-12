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

## Фаза 5 — Єдина політика обробки помилок ✅ DONE (2026-08-12)

Аудит `except Exception` у `relations.py`/`collection.py`/`main.py`: більшість
уже відповідала правилу "best-effort → `.warning()`/`.exception()`, не
перериває; обов'язкове → `raise`" (`main.py` — усі перевірені блоки коректні,
не чіпав). Знайдено й виправлено 3 реальних відхилення:

- `relations.py:_resolve_link_labels` — два `except Exception: continue` БЕЗ
  жодного логу (втрата зв'язку "чому лейбл не резолвився" повністю мовчки) →
  додано `logger.warning(...)` перед `continue` в обох місцях.
- `collection.py:rename_document` (каскад system-doctype посилань:
  ActivityLog/DocVersion/File/Comment/EmailQueue) — `except Exception: continue`
  без логу → додано `.warning()` з doctype/field контекстом. Раніше після
  rename частина історичних посилань могла тихо лишитись зі старим id без
  жодного сліду в логах.
- `relations.py:_save_child_tables` — **найважливіше знайдене**: `except
  Exception: logger.exception(...)` навколо запису child-table рядків
  ковтав помилку і повертав керування так, ніби все ок — `create_document`/
  `update_document` рапортували успіх користувачу, а дочірні рядки могли бути
  видалені (DELETE вже виконався) і НЕ вставлені (INSERT впав), тобто мовчазна
  втрата даних. Це не best-effort побічний ефект, а обов'язковий крок
  збереження документа → try/except прибрано, виняток тепер пробивається до
  викликача (транзакція відкочується, клієнт отримує реальну помилку замість
  фальшивого success). Регресійний тест:
  `tests/unit/test_document_relations.py::test_save_child_tables_propagates_child_doctype_lookup_failure`.

`tree.py` — обидва ручні `WITH RECURSIVE` через `text(f"...")` (`get_tree`,
`get_ancestors`) переведено на SQLAlchemy Core `Select.cte(recursive=True)`.
Прибрано весь клас "чи провалідований кожен інтерпольований ідентифікатор" —
разом з ним видалено сам `_check_id`/`_IDENTIFIER_RE` (Фаза 3), бо вони стали
непотрібні: більше немає рядків, куди підставляються table/column names.
Регресійні тести (раніше `get_ancestors` не мав жодного тесту):
`tests/test_tree_api.py::test_tree_ancestors_ordered_root_first_excludes_self`,
`::test_tree_ancestors_root_node_returns_empty`.

`pytest tests/` — 217/217 зелений (214 + 3 нові), `ruff check` на торкнутих
файлах чистий.

## Фаза 6 — Межі модулів ✅ DONE, з ревізією вихідної тези (2026-08-12)

Вихідна теза плану ("десятки пізніх імпортів = погані межі модулів") на
перевірку виявилась перебільшеною. Перевіряв **емпірично** — тимчасово
робив кожен підозрілий lazy-імпорт top-level і запускав `import grunt.main`
(реальний entrypoint), а не гадав по коду. Результат:

**Реально виправлено (2 справжні проблеми):**
- `db/api.py:_get_registry()` — докстрінг стверджував "циклічна залежність
  grunt.db ↔ grunt.metadata.registry", але емпірично цикл **не підтвердився**
  (застарілий коментар, ймовірно з часів до видалення `DocumentService`).
  `doctype_registry` тепер звичайний top-level імпорт, `_get_registry()`
  видалено, усі 13 викликів спрощено.
- `document/base.py:_bind()` — імпортував увесь `grunt.app.grunt` заради
  трьох тонких pass-through методів (`_require_session/_require_engine/_require_user`),
  хоча справжня реалізація вже лежить у `grunt.context` (підтверджено
  прецедентом: `app/permission_api.py` явно документує, що `_require_user`
  лишається тонкою обгорткою навколо `grunt.context.require_user` саме тому,
  що зовнішній код досі викликає `grunt._require_user()`). Тепер `_bind()`
  імпортує `require_session/require_engine/require_user` напряму з
  `grunt.context` — один із двох справжніх циклів `document.base ↔ grunt.app`
  усунено.
- `document/collection.py` і `document/tree.py` — 9 inline lazy-імпортів
  `Document`/`DocumentList`/`document_registry` емпірично підтверджені
  безпечними → переведено в top-level.

**Підтверджено як СПРАВЖНІ цикли — свідомо лишено lazy (спроба top-level
ламає `import grunt.main` з `ImportError: circular import`):**
- `document/base.py` — властивість `.grunt` та `_set_grunt_context`/
  `_reset_grunt_context` (`grunt.app` composes `DocumentAPI`, яка сама працює
  з `Document`-інстансами — двобічна залежність, не усувається без переносу
  `GruntApp`-синглтона в нижчий шар; не виправдана поточними доказами).
- `document/base.py ↔ document/registry.py` — `DocumentRegistry` мусить
  розпізнавати `issubclass(obj, Document)`, а `Document`/mixins користуються
  `document_registry` для резолву контролерів. Структурний, глибокий цикл
  (`base → mixins.write → mixins.read → virtual → registry → base`);
  усунення вимагало б виділення "marker base class" без залежності від
  registry — велика окрема архітектурна робота, не робив без окремого рішення.

**Спростовано як не-проблема:** переважна більшість "пізніх імпортів" із
початкового аудиту (~80) — це або (a) імпорти лише під `if TYPE_CHECKING:`
(ніколи не виконуються в рантаймі, взагалі не стосуються циклів — хибне
спрацювання grep), або (b) свідоме відкладене підвантаження важких/опційних
підсистем (`webhook`, `search`, `notification`, `assignment`, `versioning`) —
навмисний і корисний патерн, не архітектурний борг. Не чіпав жодного з них —
форсування у top-level нічого не покращило б, лише обважнило старт модуля.

`pytest tests/` — 217/217 зелений після кожної правки, `import grunt.main`
перевірявся емпірично на кожному кроці, `ruff check` на торкнутих файлах
чистий.

## Фаза 7 — Дрібне ✅ DONE, з обґрунтованими відмовами (2026-08-12)

- `DocTypeRegistry.get()` — наївна евристика однини/множини (яку я спершу лише
  задедуплікував у `_singular_plural_variant()`) **видалена повністю** —
  користувач підтвердив: не вгадувати назву DocType, лише точний і
  регістронезалежний збіг. `get()` тепер 3, а не 4 кроки; жодних тестів на
  цю поведінку не існувало.
- `Document.host()` → `Document.bare()` — єдиний call-site (`app/document_api.py`),
  перейменовано обидва місця.
- Ambient `ContextVar` у `Document._bind()` — докстрінг тепер явно каже: це
  fallback для скриптів/CLI/фонових завдань без явного session/engine/user;
  новий код (і тести) мають передавати їх явно; кожен з трьох параметрів
  резолвиться незалежно й мовчки no-op'ає при невдачі, тож `Document()` без
  аргументів може лишитись частково зв'язаним без помилки до фактичного
  використання відсутньої частини.

**Свідомо НЕ зроблено** (після детальнішого аналізу ризик переважив користь):

- **`Document.__getattr__` — попередження в debug-режимі на невідоме поле.**
  Спробував і відкотив: `debug=True` — дефолтне значення в `config.py`, а
  `apply_field_values()` для звичайного (не child-row) запису НЕ заповнює
  ключ для необов'язкового поля без default і без значення в даних (лише
  Check-поля отримують `False`). Тобто "поле відсутнє в `self.data`" —
  штатний, дуже частий випадок (кожне `notes: str | None`, ще не встановлене
  на документі), а не ознака одруківки. Навіть попередження "раз на процес на
  (doctype, field)" почало б спрацьовувати для купи легітимних необов'язкових
  полів одразу після старту сервера — лог, який постійно кричить про
  нормальну поведінку, ігнорується і втрачає сенс. Коректний фікс (звіряти
  ім'я поля зі схемою DocType, а не з поточним `self.data`) вимагає async
  похід у registry всередині синхронного `__getattr__` — надто велика робота
  для "дрібного" пункту; не вгадую це рішення без підтвердження команди.
- **Перейменування `dt` → `doctype_def`.** 558 входжень по всій кодовій базі
  (document/, db/, metadata/ та інші модулі). Механічне, але надто великий і
  ризикований diff заради суто косметичної правки — суперечить принципу
  "мінімально". Залишено як є.

`pytest tests/` — 217/217 зелений, `ruff check` на торкнутих файлах чистий.
