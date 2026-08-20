# 006 — Deny-by-default RBAC

## Статус

Прийнято, реалізовано, застосовано на живому сайті (`dev2.itmlt.win`) — 2026-08-19.

## Контекст

`RoleAccess.is_unrestricted` (`grunt/permissions/access.py`) реалізовував конвенцію:
"немає жодного `DocTypePermission` на doctype → доступ відкритий для будь-кого
залогіненого" (dev-mode за замовчуванням). Користувач попросив зворотну
конвенцію: дані сховані, поки право не надано явно.

## Рішення

1. **`RoleAccess.is_unrestricted`** тепер повертає `True` лише для superadmin.
   Doctype без жодного permission-рядка закритий для всіх інших. Doctype, що
   має бути публічним, отримує явний `{"role": "All", ...}` рядок —
   `matching_permissions()` уже підтримував "All" як спеціальну роль, що
   збігається з будь-яким користувачем; тепер це єдиний спосіб зробити щось
   відкритим, а не побічний ефект порожнього списку.

2. **Перед флагом — права.** Перевірка масштабу показала: 4 застосунки (hrm,
   letter, inventory, cms) мали **0 doctype з правами взагалі**; car_ua (не
   встановлений на dev2.itmlt.win) — так само. Додано:
   - По одній "повний доступ"-ролі на застосунок (fixture
     `{app}/fixtures/00_roles.json`, за зразком tsnap): `Кадровик` (hrm),
     `Діловод` (letter), `Комірник` (inventory), `Контент-менеджер` (cms),
     `Адміністратор реєстру ТЗ` (car_ua, для майбутньої установки).
   - `permissions` (System Manager full CRUD + нова роль full CRUD) у 41
     doctype JSON, що раніше не мали жодного: grunt-core `PrintFormat` (1),
     hrm (15 нечайлдових), car_ua (5), letter (5 нечайлдових), inventory (11),
     cms (4).
   - Child-doctype (tsnap — 3, hrm — 14, letter — 2, grunt-core — 6)
     **свідомо не чіпали**: жодне місце в `permissions/`/`document/mixins/`
     не викликає guard з іменем child-doctype окремо — рядки читаються
     виключно як частина батьківського документа (`document/collection.py`).
   - Єдиний реальний non-superadmin користувач сьогодні
     (`robocijevgen@gmail.com`) не мав жодної ролі ніде — за рішенням
     користувача, лишився без доступу (роль призначать вручну, коли
     знадобиться).

3. **cms бракувало `"modules"` в `app.json`** — без цього поля
   `sync_installed_apps` ніколи не сканує `fixtures/`/оновлює doctype
   застосунку (порожній `app_modules`). Додано `"modules": ["cms"]`.

## Знахідка під час перевірки: систематичний дрейф прав на живому сайті

Перший прогін `pytest tests/ grunt/` після флагу — 8 тестів впали. 3 з них
напряму тестували стару конвенцію (очікувано, оновлено). Решта 5 провалилися
через **зовсім інше**: `DocumentWriteMixin._resolve_dt()` (`document/mixins/
write.py`) безумовно робить `doctype_registry._lazy_load(...)` на кожен
`new_doc`/`save_doc` (forced live-reload, щоб зміни схеми через Studio
підхоплювались без рестарту) — і `_lazy_load` резолвить сайт через
`site_manager.get_active_site()` → фолбек на `sites/currentsite.txt` →
**реальний** `dev2.itmlt.win`, ігноруючи тестовий контекст. Це відомий,
задокументований раніше (ADR 005, доповнення 2) тестовий "витік" — але цього
разу він показав щось реальне: живий сайт мав **застарілі права для 60 з 66
core doctype grunt** (`ActivityLog`, `DocumentShare`, `WebForm`, `Comment`,
`ToDo`, `DocTag`, `Translation`, `Bookmark`, `File` і майже все інше — у БД
`permissions: []`, хоча в JSON давно вже прописані реальні права).

**Причина:** `_inject_core()` (реєстрація core-doctype, `startup/doctypes/
__init__.py`) свідомо ніколи не перезаписує `permissions` після першого
встановлення doctype (`_CORE_SYNCED_DOCTYPE_ATTRS` явно виключає
`permissions` — щоб не затирати ручні правки через Studio). Права для цих 60
doctype дописували в JSON вже ПІСЛЯ першого встановлення сайту, і відтоді
ніхто не запускав `grunt doctype sync <Name>` для жодного з них — `grunt db
migrate` (звичайний "після кожної зміни" workflow) **не** підхоплює
permissions для core doctype саме через це правило.

**Наслідок:** на живому сайті права для цих 60 doctype ніколи фактично не
діяли — рятувала стара "немає прав = відкрито" конвенція. Флаг сам собою
нічого б не зламав додатково (ці функції й раніше не мали активного RBAC),
але й не дав би нічого захистити, доки дрейф не усунуто.

**Виправлення:** підтвердили зміст усіх 60 JSON-permissions (нічого
підозрілого — послідовний патерн: адміністративні doctype → лише `System
Manager`; user-facing/спільні (`Comment`, `ToDo`, `Bookmark`, довідники
Address/Country/...) → `All` з розумним підмножиною CRUD; `DocumentShare` →
`All` RWCD, бо реальний гейт — у `DocumentShare.before_insert()`, не тут).
Запущено `grunt doctype sync <Name> --site dev2.itmlt.win` для кожного з 60
— підтверджено скриптом (пряме порівняння JSON проти
`grunt_meta_doctype`-рядків): 0 залишкового дрейфу.

## Побічна знахідка 1: циклічний імпорт у `grunt` CLI

`grunt doctype sync`/`grunt doctype list` (і, ймовірно, будь-яка команда, що
першою в процесі імпортує `grunt.metadata.registry`) падали з
`ImportError: cannot import name 'doctype_registry' from partially
initialized module` — `grunt/db/__init__.py` eagerly імпортував
`grunt.db.api.GruntDB` (яка на рівні модуля імпортує
`grunt.metadata.registry`), а `grunt.metadata.registry` на рівні модуля
імпортує `grunt.db.system_tables` — підмодуль пакета `grunt.db`, тож перше
звернення до нього завжди запускає `grunt/db/__init__.py` спочатку. Коли
процес стартує з боку `grunt.metadata.registry` (як CLI), цикл змикається
до того, як `doctype_registry` встигає визначитись.

Це не залежало від жодних змін цієї сесії — довгостроково "працювало" лише
тому, що `grunt.main`/pytest conftest завжди імпортують `grunt.db` раніше
`grunt.metadata.registry` в іншому порядку.

**Фікс:** `grunt/db/__init__.py` — `GruntDB`/proxy тепер резолвляться ліниво
через module-level `__getattr__` (PEP 562), не імпортуються на рівні модуля.
Розриває цикл незалежно від того, з якого боку почався імпорт.

## Побічна знахідка 2: cms — відсутній `"label"` і колізія імен з core

`apps/cms/cms/doctypes/{footer_item,navbar_item,web_page,website_settings}/*.json`
не мали обов'язкового поля `"label"` — `sync_installed_apps` мовчки
пропускав реєстрацію всіх чотирьох (`DocType.model_validate` падав,
виняток ловився й логувався варнінгом). Додано labels українською
(відповідно до вже наявних Ukrainian-labeled полів усередині тих самих
файлів): `Елемент футера`, `Елемент навігації`, `Сторінка сайту`,
`Налаштування сайту`.

Після фіксу `FooterItem`/`NavbarItem` зареєструвались і отримали власні
таблиці коректно. Але **`WebPage`/`WebsiteSettings` колізують іменем із
вбудованими core doctype grunt** (`grunt/site/doctypes/WebPage`,
`grunt/site/doctypes/WebsiteSettings`) — реєстр doctype плоский, і
`grunt doctype sync WebPage` завжди знаходить і синхронізує **core**-версію
першою (`_find_doctype_dirs()` йде перед app-теками в пошуку). Перевірено:
у живій БД існує лише таблиця `grunt_web_page` (core, `table_name` заданий
явно) — cms-версія `WebPage`/`WebsiteSettings` **ніколи не мала власної
таблиці й не мала жодних реальних даних** на цьому сайті — фактично мертвий,
затінений код відтоді, як cms з'явився в репозиторії.

**Не виправлено в цьому заході** — перейменування doctype або видалення
дубліката потребує рішення власника: чи cms's `WebPage` мав бути окремою,
спрощеною версією, чи це просто помилка дублювання функціоналу, який
core вже надає "з коробки". `permissions`, додані в cms's `web_page.json`/
`website_settings.json` цим заходом, лишаються в файлі коректними на
майбутнє, але наразі недосяжні (core-версія завжди виграє).

## Тести

- 3 unit-тести, що напряму кодували стару конвенцію
  (`tests/unit/test_role_access.py::test_no_permissions_defined_is_unrestricted`,
  `tests/unit/test_permissions_query.py::test_no_permissions_defined_unfiltered`,
  `grunt/metadata/doctypes/DocTypePermission/tests/test_permissions.py::
  test_no_permissions_means_open`) — переписані на протилежне очікування
  (deny-by-default), перейменовані відповідно.
- 2 тести з динамічно створюваними "відкритими" doctype
  (`tests/test_search.py`'s `SIMPLE_DOCTYPE`, `tests/test_webform_submit.py`'s
  `TARGET_OPEN`) — отримали явний `{"role": "All", ...}` permission-рядок
  замість покладання на порожній список.
- Повний прогін (`pytest tests/ grunt/`) — **841 passed** (без регресій,
  до і після — той самий рахунок, оскільки нові/перейменовані тести
  замінили старі один-в-один).
- `pytest apps/{car_ua,tsnap,hrm}/tests/` — 54 passed, без змін (ці три вже
  мали реальні `DocTypePermission` для цільових doctype з попереднього
  заходу, тож флаг на них не вплинув негативно).

## Наслідки

| Плюс | Мінус / ризик |
|---|---|
| Нові doctype за замовчуванням безпечні — не треба пам'ятати додати права | Кожен НОВИЙ core doctype без `permissions` одразу закритий для всіх, крім superadmin — розробники мусять явно додати permissions row одразу, інакше "працює тільки в мене" |
| Живий сайт отримав реально діючий RBAC для 60+41 doctype, де він раніше існував лише на папері | `_inject_core`'s "seed once" правило означає: будь-яка МАЙБУТНЯ зміна `permissions` в JSON core doctype знову не підхопиться автоматичним `grunt db migrate` — треба пам'ятати `grunt doctype sync <Name>` |
| CLI-команда `grunt doctype sync`/`grunt doctype list` знову працює (циклічний імпорт пофіксовано) | — |

## Доповнення на майбутнє (не зроблено цим заходом)

- cms's `WebPage`/`WebsiteSettings` — вирішити колізію з core (перейменувати
  або видалити дублікат).
- `_resolve_dt()`'s forced lazy-reload завжди йде через `site_manager`,
  ігноруючи активний тестовий контекст — джерело витоку в реальну БД під час
  тестів (сьогодні нешкідливо, лише SELECT, але концептуально неправильно).
