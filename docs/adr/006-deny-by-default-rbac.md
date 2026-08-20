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

## Доповнення: три знахідки цього заходу закриті (2026-08-20, наступного дня)

Обидва пункти "на майбутнє" вище (крім cms-колізії з core, яка потребує
рішення власника про перейменування/видалення) вирішено + додано третій,
знайдений при огляді того самого коду.

**1. Колізії імен doctype між застосунками — тепер відмовляються, а не
мовчки перезаписуються.** `sync_installed_apps` (`grunt/startup/
app_install.py`) блочно порівнювала `existing_dt` з новим і викликала
`doctype_registry.update()` без жодної перевірки, ЧИЙ це doctype — саме так
cms's `WebPage` тимчасово переписав core-версію в цьому ж заході. Додано
перевірку `existing_dt.app != app_name` перед `update()` — при колізії
логує `registry.app_doctype_name_collision` (error) і пропускає запис
замість перезапису. Регресія: `tests/test_doctype_name_collision.py` —
будує фейковий зовнішній застосунок на диску, реєструє "чужий" doctype з
тим самим іменем, підтверджує, що оригінал лишається недоторканим.

**2. `_lazy_load()` тепер віддає перевагу активній сесії контексту, а не
завжди йде через `site_manager`.** Джерело "витоку в реальну БД під час
тестів", яке двічі спливало цим заходом (спочатку в `grunt.testkit`, потім
у власному наборі тестів grunt). Тепер: якщо `grunt.context()` вже активний
(будь-який реальний запит, будь-який тест з `ctx`/`grunt.context(...)`) —
`_lazy_load` читає через ЦЮ сесію; лише коли контексту зовсім немає
(фонові задачі/шедулер з власною сирою сесією) — фолбек на `site_manager`,
як і раніше. Поведінка живого сайту не змінюється (там ambient-сесія і сесія
з `site_manager` — одна й та сама БД); змінюється лише те, що тести й
будь-який процес з кількома доступними сайтами більше не читають "не той"
сайт. Регресія: `tests/unit/test_registry_lazy_load_session.py` — 2 тести
(з активним контекстом `site_manager.get_active_site` не викликається
взагалі; без контексту — фолбек і далі працює).

**3. Дрейф `permissions` для core doctype тепер видно одразу, а не через
випадковий збій тесту.** `_inject_core()`'s "seed once" правило (permissions
— свідомо Studio-власна, ніколи не перезаписується автоматично) лишається
незмінним — це правильна поведінка, не баг. Але мовчання про сам факт
дрейфу — і було коренем усієї сьогоднішньої знахідки (60 doctype). Додано
`registry.core_permissions_drifted` warning у `_inject_core()`: щоразу, як
JSON-права doctype відрізняються від того, що реально збережено, лунає
явне попередження з підказкою (`grunt doctype sync <Name>`) — при кожному
старті сервера чи `grunt db migrate`, а не лише коли хтось випадково це
помітить. Регресія: `tests/unit/test_core_permissions_drift_warning.py` —
підтверджує і сам warning, і що збережені (Studio) права й далі не
перезаписуються автоматично.

**Перевірка:** усі три фікси підтверджено revert-тестом (`git stash` файлу
з фіксом → тест провалюється з очікуваною причиною → `git stash pop`).
Повний прогін (`pytest tests/ grunt/`) — **846 passed** (843 було б без
трьох нових тестів; +3 регресійних тести, 0 регресій в наявних).
`pytest apps/{car_ua,tsnap,hrm}/tests/` — 54 passed, без змін.

## Доповнення 2: cms-колізія вирішена видаленням дубліката (2026-08-20)

Дослідження (Explore-агент, повне читання обох пар doctype + контролерів +
`website/router.py`) підтвердило: cms's `WebPage`/`WebsiteSettings` —
цілком мертвий скелет (порожні `templates/`, `www/`, `hooks.py`,
контролери — `pass`/тривіальна нормалізація, жодного route чи шаблону).
Core-версія — надмножина за полями (block-based content model,
`WebPageBlock`) і вже повністю підключена до рендерингу/sitemap. Жодних
реальних даних під cms-версіями не існувало (підтверджено раніше в
Доповненні 1 — фізичної таблиці не було ніколи).

**Дія:** видалено `apps/cms/cms/doctypes/web_page/` і
`apps/cms/cms/doctypes/website_settings/` повністю. `FooterItem`/
`NavbarItem` (незалежні generic nav/footer child-таблиці, не мають Link на
WebPage) лишено як є — вони отримали власні фізичні таблиці й коректно
зареєстровані; наразі не мають "батька" (jerelo Table-поля через видалене
cms's WebsiteSettings), але видалення непотрібних дублікатів — не привід
видаляти й функціонально коректний, хоч і поки не задіяний, код без
окремого рішення власника.

**Побічний фікс:** виявлено, що колізійний захист із Доповнення 1
(`sync_installed_apps`) не покривав ручний шлях — `grunt doctype sync
<Name>` (CLI) блочно робив `update()` без перевірки власника ВЗАГАЛІ, і не
проставляв `DocType.app` для core doctype (лише `load_core_doctypes` це
робив; сам CLI читає JSON напряму, де `app` майже завжди `null`). Це
означало: колізійний захист можна було обійти вручну через CLI для будь-
якого doctype, чий `app` ще не проставлений (виявилось — майже всі core
doctype, включно з `WebsiteSettings`, що саме через це показав `app: null`
у живій БД навіть ПІСЛЯ ручного sync у Доповненні 1).

Виправлено `grunt/cli/doctype.py: doctype_sync` — тепер відстежує, з якого
каталогу (core чи який застосунок) фактично знайдено JSON-файл,
проставляє `DocType.app` за цим (як і `load_core_doctypes`), і відмовляє
з чіткою помилкою, якщо існуючий у БД рядок належить іншому застосунку.
Перевірено вручну на живому сайті: `grunt doctype sync WebPage`/
`WebsiteSettings --site dev2.itmlt.win` тепер коректно проставляють
`app: grunt` (раніше — `null` для WebsiteSettings).

**Тести:** прямого CliRunner-тесту для цієї конкретної CLI-гілки не
додано — логіка структурно ідентична вже протестованій гілці в
`sync_installed_apps` (Доповнення 1), а сам CLI-шлях верифіковано вручну
проти живого сайту. `pytest tests/ grunt/` — **846 passed**, без регресій
від видалення cms-doctype чи CLI-зміни. `pytest apps/{car_ua,tsnap,hrm}/
tests/` — кожен окремо, як і весь захід, — 49/3/2 passed.

**Побічна знахідка (не виправлено, не критично):** запуск тестів кількох
застосунків **одночасно** в одному процесі pytest (`pytest apps/car_ua/
tests apps/tsnap/tests apps/hrm/tests`) ламається — спільні глобальні
синглтони (`doctype_registry`, `app.dependency_overrides` в
`grunt.testkit`) конфліктують між конфтестами різних застосунків. Кожен
застосунок окремо — завжди коректно (і саме так вони запускались увесь
цей захід). Не виправлено — поза обсягом; testkit проєктувався для
ізольованого запуску одного застосунку за раз.
