# Права й доступи — план

Живий план. Оновлюється після кожного кроку: що зроблено, що далі, які рішення прийняті.
Новий чат з Claude починає звідси.

**Вимога власника (2026-11-09):** налаштування прав має бути максимально гнучким і зручним
для адміністратора. Безпека й архітектура — відповідальність розробника (Claude): рішення
приймаються тут, без погодження кожної дрібниці.

Оновлено: 2026-11-11 — кроки 1 (#118), 2a (#119), 2b (#139, #140, #141) злито; 2c — гілка `feat/permissions-readonly-fields`.

---

## Чому переписуємо

Стан на v0.2.0 (`grunt/permissions/`, ~1300 рядків):

1. **Подвійна реалізація кожного правила.** `match` для документа рахує `simpleeval`, для списку —
   вузька SQL-підмножина. Так само пари `check`/`predicate` у shares, reference, child,
   UserPermission. Правило `a == user and b == 'x'` пускає в документ за посиланням, але список
   його не показує (`tests/contract/test_permissions.py`, роль `Broken`).
2. **П'ять механізмів з неявною композицією.** Ролі (OR) + shares (OR) + UserPermission (AND,
   звужує все, навіть shares і інші ролі) + `inherit_permission_from` (перекриває `match`) + child.
3. **Немає ролі в області.** Додатки будують це самі: `mlt_portal` (`MltPortalAccess` → роль +
   UserPermission, пастка «нема рядків = нема обмежень»), `letter/scripts/provision_department_access.py`.
4. **Ролі — вільні рядки.** `DocPermission.role` — Data (одруківка = тиха відмова), «System Manager»
   рядком у ~93 місцях коду, `All`/`Guest` — магічні імена.
5. **Фіксовані булеві дії.** `report` є в схемі, але ніде не перевіряється; Workflow, `whitelist`,
   Page, AppMenu, Report — кожен зі своїм списком ролей.
6. **Діри полів (FRAPPE_GAP_PLAN п.3):** приховане поле можна записати (`save_doc`/`new_doc`) і
   вгадати фільтрами/сортуванням у `get_list`.
7. **Обхід як норма:** ~380 `system_context`/`ignore_permissions` у ядрі й додатках; API-ключ має
   всі права користувача.

## Цільова модель

```
Principal (на запит, кешований)          Policy (на DocType, скомпільована)
  user, призначення ролей з областю,  →   правила: role, actions[], where, fields{}
  дозволи, змінні ($user, $user.*)          access_from (коментарі, файли, child)
                │                                   │
                └──────────────► Expr (grunt.query.nodes) ◄─┘
                                   │
                ┌──────────────────┼───────────────────┐
           список: WHERE      документ: matches()     пояснення: explain() → трасa
```

### Правило (grant)

```json
{"role": "inventory.storekeeper",
 "actions": ["read", "write", "print", "export"],
 "where": {"responsible_employee.user_id": "$user"},
 "fields": {"salary": "none", "cost": "read"}}
```

- `where` — та сама мова фільтрів, що й `grunt.db` / список (`field`, `field__in`, `link.field`).
  Компілюється в `Expr`; невідоме поле — помилка на `migrate`/збереженні DocType, не тиха відмова.
- Змінні: `$user`, `$user.<поле User>`, `$user.employee` тощо — резолвляться раз на запит.
- Запасний вихід — Python-політика, зареєстрована в хуках, що **повертає `Expr`** (не bool).
- `actions` — відкритий список: базові `read select create write delete export import print share
  report` + власні дії DocType (`DocTypeAction`, переходи Workflow: `approve`, `post`, …).
- `fields` — права на **групи полів** (`DocType.field_groups`) або окремі поля: `none` / `read` / `write`.
  Кілька правил — найширше. Замінює `hidden_fields` і `readonly_fields`.

### Призначення ролі з областю

```
RoleAssignment {user, role, scope_doctype?, scope_value?, valid_from?, valid_to?}
```

- Область додає до **всіх правил цієї ролі** умову «документ у межах області» (поле Link на
  `scope_doctype`, для дерев — піддерево). Звужує лише свою роль.
- Різні призначення — OR: «модератор розділу A» + «автор розділу B» — кожен своє.
- Замінює `UserPermission`, `MltPortalAccess`, скрипт letter. Профіль ролей (п.11) = набір призначень.
- Явні глобальні обмеження (якщо знадобляться) — окрема сутність з поясненням, не побічний ефект.

### Композиція (одна формула, документована й видима в Inspector)

```
allowed(action, doc) =
    OR  over (assignment, grant) where action ∈ grant.actions:  grant.where ∧ scope(assignment)
  ∨ share(doc, action)        — share: user | role | всі, дії, строк, право ділитися далі
  ∨ via access_from(doc)      — коментарі, файли, child-рядки: «як документ, на який вказує»
```

### Ролі й дозволи

- Роль має стабільний id (`inventory.admin`) + перекладну назву; `grant.role` — Link.
- Код перевіряє **дозволи**, не ролі: `@grunt.whitelist(perm="grunt.manage_doctypes")`,
  `grunt.can(doctype, action, doc)`. Роль — набір дозволів. System Manager — звичайна роль із `*`.
- `All`, `Guest`, `Authenticated` — вбудовані принципали.

### Шари налаштувань

- Типові права — у JSON додатка (версіонуються, фікстури).
- Правки адміністратора — окремий шар сайту; `grunt upgrade` їх не затирає; Studio показує різницю
  «як у додатку / як на сайті» і «повернути типові».

## Інваріанти безпеки (кожен закріплений тестом)

1. **Одна реалізація.** Рішення для документа = `matches(predicate, doc)` того ж `Expr`, що йде в
   WHERE списку. Контрактний тест: для кожного користувача й документа «відкривається» ⇔ «є в списку».
2. **Fail closed.** Правило, яке не компілюється, не зберігається; якщо таке все ж трапилось на
   льоту — не дає нічого, і це видно адміну (лог + позначка в Studio).
3. **Немає обходу за назвою ролі.** Лише внутрішній SYSTEM_USER; людський обхід — `grunt.sudo(reason=…)`
   з записом у журнал.
4. **Неможливо видати більше, ніж маєш.** Share, призначення ролі, правка прав — лише в межах власних
   прав того, хто видає (+ окремий дозвіл `grunt.manage_permissions`).
5. **Поля закриті з усіх боків:** читання (відповідь, експорт, звіти, пошук, агрегати, websocket),
   запис (create/update, bulk, import), фільтр і сортування за полем без права читання.
6. **Нові значення теж перевіряються:** create/update — документ після зміни мусить задовольняти
   `where` правила, що дало `create`/`write` (не можна перенести запис за межі своєї області).
7. **Кеш не роздає чужого.** Ключ кешу — версія прав + принципал; зміна прав/ролей/призначень
   інвалідує через шину (`@fanout`).
8. **Аудит.** Зміни прав, ролей, призначень, shares — Permission Log; експорт/друк/імпорт — Access Log.

## Зручність для адміністратора

- **Матриця «роль × DocType × дія»** у Studio — масове редагування, фільтр за додатком/модулем.
- **Конструктор умов `where`** — той самий, що фільтри списку (поле, оператор, значення / `$user…`).
- **«Хто має доступ»** до документа / DocType і **«чому»** (Inspector, трасa рішення).
- **«Переглянути як користувач»** (імперсонація вже є) + попередній перегляд: «після цієї зміни
  доступ отримають/втратять N користувачів».
- **Ролі з областю на формі користувача:** роль + область + строк дії одним рядком.
- **Попередження:** правило не дає нічого, роль без користувачів, роль без правил, поле, приховане
  від усіх, DocType без жодного правила.
- **Шаблони ролей** у додатках (готові «Комірник», «Бухгалтер») — адмін лише призначає.

## Кроки

| # | Крок | Статус |
|---|------|--------|
| 1 | **Одна реалізація перевірки.** `match` → лише `Expr` (`where`), документ = `matches()` з асинхронним `Linked`; прибрати `simpleeval`; непридатні `match` — помилка при завантаженні DocType | ✔️ |
| 2a | **Діри прихованих полів** (інваріант 5): запис, фільтр/сортування/групування/агрегати/пошук, `get_value`/`set_value`/`exists`, глобальний індекс | ✔️ #119 |
| 2b | **Дії** `actions[]` замість булевих + `export`/`import`/`print`/`share`/`report` — перевірка на сервері (FRAPPE_GAP п.2) | ✔️ #139, #140 |
| 2c | **Поля «лише читання»** — `readonly_fields` поруч із `hidden_fields` (FRAPPE_GAP п.3); групи полів — у 2d | ✔️ #142 |
| 2d-1 | **Нові значення при записі** (інваріант 6): insert / save / `set_value` — документ після зміни в межах `create`/`write` | ✔️ #151 |
| 2d-2 | **Матриця «роль × дія»** — вигляд «Дозволи» у списку DocType | ✔️ #151 |
| 3a | **Дозволи.** Реєстр (`permissions` у hooks.py), `Role.permissions` (System Manager — `*`), `has_perm()`, `@whitelist(perm=)`; ядро без рядкових «System Manager» | ⏳ #152 |
| 3b | **Workflow / AppMenu / Workspace / Page / Report / дії документа** — через дії правил і дозволи замість списків ролей | ⏳ `feat/permissions-roles-in-features` |
| 3c | **Ролі.** `DocPermission.role` — Link (роль мусить існувати), перекладна назва ролі | ⏳ `feat/permissions-role-link` |
| 4 | **Ролі з областю.** `RoleAssignment`; UserPermission → призначення; перевести mlt_portal, letter; прибрати UserPermission | ☐ |
| 5 | **Shares як правила + access_from.** share на user/role/всіх, строк, ділитися далі (п.40); child і `inherit_permission_from` → `access_from` | ☐ |
| 6 | **Інструменти адміна.** `explain()` + Inspector (п.7), Permission/Access Log (п.8), матриця, конструктор умов, попередження, шар сайту поверх JSON додатка | ☐ |
| 7 | **API-ключі й sudo.** обмеження ключа (перетин з правами користувача), `grunt.sudo(reason)`, ревізія `system_context` у ядрі | ☐ |

Кожен крок — окремий PR у `develop`. Сумісність API не зберігаємо (ґрунтом користується лише
власник); JSON додатків мігруємо в тому ж PR, що й зміну формату.

## Рішення

- **2026-11-09** — FRAPPE_GAP_PLAN п.2 і п.3 (прапорці дій, `readonly_fields`) реалізуються в новому
  форматі на кроці 2, а не як нові булеві колонки/списки: щоб не мігрувати двічі.
- **2026-11-09** — `match` з довільною логікою (`and`/`or` через simpleeval) більше не підтримується:
  в усіх додатках використовуються лише форми `field == user`, `field == 'x'`, `link.field == user`,
  які однаково працюють у списку й документі. Складніші умови — `where` (крок 2) або Python-політика.

- **2026-11-09** — де список і документ розходилися, перемагає семантика списку (суворіша):
  UserPermission звужує й shares; `link.field != x` для порожнього Link — «ні».
- **2026-11-09** — кеш списків/лічильників (`query_cache`) містить у ключі ролі й предикат прав;
  список, чий предикат читає інші DocType (shares, успадкований, child), не кешується —
  їхні зміни цей кеш не інвалідують.

- **2026-11-11** — формат `actions[]` переїхав з 2d у 2b: інакше нові дії довелося б додати булевими
  колонками й мігрувати двічі (рішення 09.11). Studio редагує список полем MultiSelect; матриця
  лишається в 2d як зручність, не як формат.
- **2026-11-11** — додатки — окремі репозиторії, їхні JSON у PR ядра не мігрують. `DocPermission`
  читає старі булеві ключі (`true` і `1`) як `actions` і записує вже новий формат. Прибрати
  прокладку разом з оновленням додатків на нове ядро.
- **2026-11-11** — нові дії типово не має ніхто (FRAPPE_GAP п.2). Виняток — рядки System Manager у
  JSON ядра: `read` → +`export`/`print`/`report`, `write` → +`share`, `create` → +`import`.
  Нерозмічені core DocType на сайті отримують це з JSON (`permissions_base`), розмічені — ні.
- **2026-11-11** — `share` = `share` ∧ `write` на тому ж документі (з тим самим `match`), і для
  SharedWith, і для публічного посилання DocumentShare. `export`/`import`/`report` — рівня
  DocType; `print`/`share` — рівня документа (`__perms`).
- **2026-11-11** — `report` перевіряє запуск звіту з `ref_doctype` (List, Query, Script). Групування
  й агрегати в списку — це читання, не `report`.

- **2026-11-11** — 2c йде за рішенням власника від 09.11 (FRAPPE_GAP п.3): `readonly_fields`
  поруч із `hidden_fields`, а не новий формат `fields{}`. Групи полів (`field_groups`) і матриця —
  у 2d, як зручність редагування поверх тих самих списків.

- **2026-11-12** — матриця — це вигляд «Дозволи» у списку DocType (`available(dt)` у
  `viewRegistry`), а не окрема сторінка чи вкладка ролі: рядки — сторінка списку з його фільтрами
  (модуль, додаток, пошук), роль — вибір у самому вигляді. Групи полів (`field_groups`) відкладено:
  довгих списків прихованих полів у застосунках поки немає. 2d-1 і 2d-2 — один PR.

- **2026-11-13** — крок 3 (рішення власника): id ролі — її нинішня назва (`Комірник`,
  `Адміністратор порталу`), без перейменування на `app.role` і міграції даних; лише перевірка, що
  роль існує, і перекладна назва. Дозволи — реєстр у `hooks.py` застосунку + MultiSelect
  `permissions` на Role (варіанти з реєстру, `options_source`); System Manager має `*`.
  `roles=` у `whitelist` і `has_role()` у застосунках працюють і далі — переводимо разом з
  оновленням застосунків, потім прибираємо. Крок 3 — три PR: 3a, 3b, 3c.

- **2026-11-13** — 3b: списки ролей у налаштуваннях (Workflow `allowed_roles`/`edit_roles`,
  AppMenu, Page, онбординг) лишаються — це дані, які редагує адмін, а не перевірки в коді.
  Прибрано лише обхід за назвою «System Manager»: замість нього — `*` (Workflow) або
  `grunt.manage_desk` (меню, сторінки, онбординг). Перехід Workflow як дія правила DocType
  (`approve` в `actions` з `match` — «погоджує лише свій відділ») — окреме рішення: відкритий
  список дій у `DocPermission` і міграція Workflow застосунків (mlt_portal); не в 3b.

## Журнал

### 2026-11-09 — крок 1: одна реалізація перевірки

- `grunt/permissions/query.py`: `action_predicate(user, meta, action, row=)` — предикат для будь-якої
  дії (`read_predicate` — його окремий випадок); `row_allowed()` — той самий предикат над рядком.
- `grunt/query/evaluate.py`: `matches_linked()` — `matches` з `Linked`, який розв'язується запитом
  до сховища (той самий `compile_sql`); спочатку гілки в пам'яті, потім ті, що читають БД.
- `PermissionChecker.check(doc=…)` = `row_allowed`; `doc=None` — грубий DocType-рівень, як і був.
- `match`: прибрано `simpleeval`; граматика (`MATCH_RE`, `validate_match`) — у
  `grunt/metadata/permission.py`, валідатор `DocPermission.match` відхиляє решту.
- shares: предикат враховує рівень (`Write` для write); `has_share` — лише DocType-рівень.
- reference / child: підказка `row` — для одного документа без `distinct` по всій таблиці.
- **Витік у кеші:** `query_cache` мав ключ лише з email — після зняття ролі/звуження правила
  користувач до 30 с (TTL, у Redis — для всіх воркерів) бачив ширший список, а лічильники
  кешувалися для всіх SQL-DocType. Ключ тепер містить ролі й предикат (`_access_key`).
- Тести: контрактний «документ відкривається ⇔ він є у списку» (задачі, нотатки, child-рядки,
  усі ролі), відхилення непідтримуваних `match`, регресія кешу (без виправлення падає).

**Рев'ю PR #118 (CodeQL, CodeRabbit), 2026-11-09:**
- CodeQL `py/unsafe-cyclic-import` — 3 нові пари «ім'я ← модуль» (у `develop` пакет прав і так у циклі
  через хаб `import grunt` → `grunt.app` → `rbac`; ~400 відкритих алертів). Виправлено кодом:
  `grants` → метод `DocPermission.grants()` у листовому `metadata/permission.py`; `rbac` імпортує
  модуль `query` (як уже `shares`), а не імена з нього; `_session_ctx` → `grunt.get_session()`.
  Плюс `import grunt` + `from grunt import log` в одному модулі, `items` у `_reads_db`.
- CodeRabbit: `is_literal` пропускав `'Open' and owner == 'x'` (перший і останній символ — лапки) →
  рівно один токен у лапках; тест кешу не перевіряв кешований шлях → додано крок із UserPermission
  (той самий користувач і роль, інший предикат); без предиката в ключі тест падає.
- **Системне (поза кроком):** корінь сотень алертів — хаб `grunt/__init__` → `grunt.app` → усе ядро.
  Окремий крок: модулі прав без `import grunt` (registry/session напряму), тоді пакет вийде з циклу.

### 2026-11-09 — крок 2a: поле, приховане від користувача, закрите з усіх боків

Гілка `feat/permissions-field-access`, PR #119. CodeQL у CI: циклів-алертів немає взагалі
(на відміну від #118, де давні цикли перенумерувались); 5 «Statement has no effect» на `...` у
протоколах `access.py` — замінено докстрінгом + `raise NotImplementedError`.
- **Центр — `run._secured`** (усі читання від імені користувача): фільтр, сортування, групування,
  агрегат за прихованим полем → 403 (і через Link — за правилами цільового DocType); пошук не
  дивиться в приховані поля (`Query.search_exclude`); рядки повертаються без них.
- **Запис** (`lifecycle` insert/update): зміна прихованого поля → 403; те саме значення або
  типове на новому документі — проходить (форма може їх повернути).
- **`get_value` / `set_value`** перевіряли лише DocType: тепер — сам документ (`match`, shares,
  User Permissions) і приховані поля. Знахідка: `set_value` дозволяв користувачу з
  `write` лише на свої записи (`owner == user`) змінити чужий.
- **`exists`** ішов повз правила рядків (сирий `db.exists`) — тепер через `run.fetch` від
  імені користувача.
- **Глобальний індекс** не містить полів, прихованих хоч від однієї ролі (індекс спільний для
  всіх; збіг виказав би значення); заголовок прихованого `title_field` замінює `name`.
- **Ендпоінти, що самі перевіряють доступ, пишуть через `grunt.db`:** зміна пароля
  (`hashed_password` прихований від власника), `rename_passkey` / `touch_passkey` (були
  зламані: роль не має `write`, 403 ще в `develop`), лічильник переглядів у `share.py`.
- **CodeQL:** розбір `group_by`/`aggregates` винесено в листовий `grunt/query/aggregates.py`
  (інакше `store.sql` потрапляв у цикл, +25 алертів); `access.py` описує користувача й DocType
  протоколами (`Principal`, `Target`), email системного користувача — `grunt/auth/constants.py`,
  у `Meta` — типізовані `name`/`permissions`/`fields`. Підсумок локального CodeQL: 594 проти
  602 на кроці 1, жодного нового циклу (19 «нових» у CI будуть перенумерованими старими).
- **Додатки — поки не чіпаємо (рішення власника 2026-11-09):** `grunt.exists` для перевірки
  унікальності тепер бачить лише доступні рядки — `hrm` Department (`code`, `edrpou`) і `tsnap`
  Appeal (номер) мають перейти на `grunt.db.exists`, інакше обмежений користувач не побачить
  дубля з чужої області. Зробити разом з оновленням додатків на нове ядро.
- **Відкладено в 2d:** `set_value` не перевіряє нові значення на User Permissions / `match`
  (перенесення запису за межі своєї області) — частина інваріанту 6.

**Локальний CodeQL** (scratchpad, без змін конфігурації): `codeql database create --build-mode=none`
+ запити `Imports/ModuleLevelCyclicImport.ql`, `Imports/CyclicImport.ql` — ~1,5 хв на прогін;
порівняння результатів двох прогонів показує справжні нові цикли.

**Рев'ю #119 (CodeRabbit), 2026-11-09:**
- **Пошук через Link** читав заголовок / поля пошуку цільового DocType без його правил — приховане
  там поле знову ставало оракулом. `_secured` додає до `search_exclude` імена
  `link_field.target_field`, приховані правилами цілі; сховище їх пропускає.
- **Старі записи глобального індексу** зберігали приховані значення після оновлення (і після
  приховування поля в Studio чи JSON додатка). `grunt_search_index_state` тримає підпис
  налаштувань запису на DocType (`content_signature`: поля пошуку, `title_field`, приховані);
  `refresh_stale` (у `migrate` і `registry.update`) переіндексовує DocType, чий підпис змінився.
  Без збереженого підпису (записи до цієї зміни) — переіндексація лише DocType з прихованими
  полями, решті підпис просто записується.

### 2026-11-11 — крок 2b: дії списком, експорт/імпорт/друк/поширення/звіти

PR #139 (формат) + #140 (перевірки). CodeRabbit на #139: ScheduledJob з прапорцями `1` лишився
без прав (тест на порожні рядки ядра), `0021` отримала `downgrade`.
- **Формат:** `DocPermission.actions: list[str]` з `ACTIONS` (`grunt/metadata/permission.py`);
  невідома дія — помилка валідації (одруківка не відмовляє мовчки); порядок нормалізований, тож
  збережені права ≡ JSON порівнюються по суті. Старі ключі читаються прокладкою (див. рішення).
  JSON ядра — 79 DocType, лише рядки прав (текстовою заміною, решта файлу без змін).
  Міграція `0021`: `permissions` і `permissions_base` збережених визначень + прибирає старі поля
  з форми DocPermission. Сухий прогін на копіях dev2 (293 DocType) і lagoo (104): 0 невалідних.
- **Перевірки:** `guards.doctype_guard(doctype, action)` (meta + 404/403).
  `export` — `export_file`, `export_csv`, `export_quick`, DataExport (`validate`);
  `import` — DataImport (`validate`), `run_import_job` (задача пише як SYSTEM_USER — дія
  перевіряється в того, хто запускає), `download_template` (було `read`);
  `print` — `print` (документ), `preview` (DocType і документ);
  `share` — `PermissionChecker.can_share/require_share`: SharedWith, DocumentShare, бічна панель;
  `report` — `ReportEngine.run` для звітів з `ref_doctype`.
- **`__perms`** — ще `print`, `share`. Фронтенд: `rolePermissions()`; стандартні дії форми
  (друк, «Поділитися посиланням»), кнопка друку в бічній панелі, експорт і «Створити звіт» у
  списку ховаються за правами.
- **Тести:** `tests/test_permission_actions.py` (модель, міграція, export/print/report),
  share — «write без share» і «share без write» обидва відмовляють; імпорт — потрібна дія
  `import` на цільовому DocType.
- **Поза ядром (при оновленні додатків):** ролям додатків видати `print`/`export`/`share`/
  `report`, де треба — зараз їх не має ніхто, крім System Manager на DocType ядра; конвертувати
  їхні JSON (`scratchpad/convert_perms.py` — текстова заміна лише рядків прав); оновити skill
  grunt-dev (`references/permissions.md`, `doctypes.md`, `new-app.md`).

### 2026-11-11 — застосунки на `actions`, прокладку прибрано

- JSON прав у 14 застосунках конвертовано за погодженим правилом: `print` — кожній ролі з `read`,
  `export` — разом з `report`, `share` — з `write`, `import` — нікому; System Manager — як у ядрі
  (+`export`/`print`/`report`, +`share`, +`import`). Код: hrm `tasks.py` (`p.grants("read")`),
  унікальність — `grunt.db.exists` (hrm Department, tsnap Appeal), тести cms.
- Ядро: `DocPermission` відхиляє старі прапорці з помилкою («list them as actions») — тихо не дати
  нічого було б гірше; рядки тестів ядра переписано на `actions`.
  Стару БД конвертує міграція `0021`.
- dev2: знімок `20261111-085257`, `grunt migrate` → `0021`; встановлені застосунки отримали нові дії.
  tsnap на dev2 не встановлений — його залишки в БД не оновлюються.
- **Пастка:** `tsnap/asc` (окремий репозиторій, старий Frappe-код) потрапив під скрипт конвертації —
  відновлено з git байт у байт; скрипти конвертації не запускати по `tsnap/` цілком.
- Перевірка 2026-11-11: усі 465 рядків прав у JSON 14 застосунків проходять `DocPermission`
  (0 невалідних), старих прапорців у коді застосунків немає. Skill grunt-dev (`permissions.md`,
  `doctypes.md`, `new-app.md`) переписано на `actions`/`match`/`hidden_fields`/`readonly_fields` —
  у репо `grunt-agent-skills` і обох встановлених копіях (`~/.agents`, сайт dev2).

### 2026-11-11 — крок 2c: поля «лише читання» для ролі

Гілка `feat/permissions-readonly-fields`.
- `DocPermission.readonly_fields`; `RoleAccess.readonly_fields` — поле заблоковане, якщо так кажуть
  **усі** правила користувача, що дають `write` (приховане теж блокує); будь-яке правило, що лишає
  його відкритим, перемагає. Без `write` — порожньо (запис і так заборонений).
- Сервер: `forbidden_changes` = приховані + (для наявного документа) змінені «лише читання» → 403
  у save/update (`lifecycle`) і `set_value`. Новий документ значення приймає; те саме значення
  назад — проходить.
- Форма: `__perms.readonly_fields`; `useFormController` накладає `read_only` поверх правок
  клієнтських скриптів; без `__perms` — з рядків ролей (`formReadonlyFields`).
- Studio: поле «Поля лише для читання (через кому)»; і воно, і `hidden_fields` тепер приймають
  текст через кому (раніше збереження `hidden_fields` з форми падало — модель чекала список).
- Невідома назва поля в `hidden_fields`/`readonly_fields` — 422 при збереженні DocType
  (`_validate_fields`): одруківка залишала б справжнє поле відкритим. Застарілих назв у JSON
  застосунків і на dev2 немає.
- Імпорт (`import`) пише як SYSTEM_USER і поля «лише читання» не перевіряє — це окреме право.

### 2026-11-12 — крок 2d-1: нові значення теж перевіряються (інваріант 6)

Гілка `feat/permissions-role-matrix`, спільна з 2d-2 (один PR).
- `permission_checker.require_in_scope(dt, action, row)` — `allowed()` з документом у тому
  вигляді, в якому його збираються записати: `match` правила, shares і User Permissions
  рахуються по нових значеннях. 403 з окремим текстом для створення і для зміни.
- **insert** — після хуків (`validate`, `before_insert`, `before_save`), поруч із перевіркою User
  Permissions: `create`. Раніше `match` правила `create` не перевірявся взагалі (лише рівень DocType).
- **save/update** — старий рядок, як і раніше, перевіряється на `write` до змін; тепер і злитий
  (після хуків) — теж `write`. Документ, поширений із `Write`, лишається доступним: share
  прив'язаний до `name`.
- **`set_value`** — `doc_guard` повертає рядок, перевірка йде на `{**рядок, **зміни}`. Закриває
  відкладене з 2a (перенесення запису за межі своєї області).
- Наслідок для правил ядра: виконавець ToDo (`assigned_to == user`), який не є його автором,
  не може сам перепризначити ToDo на іншого — після зміни запис уже не його. Перепризначення
  через призначення (`assignment`) іде в системному контексті й не зачеплене. Правила застосунків
  з `match` на `create`/`write` — лише «власник = user» і `menu == 'mlt_portal'`: поведінка та сама.
- Тести: `tests/test_write_scope.py` (без змін — 3 з 4 падають); усі 2348 зелені.

### 2026-11-12 — крок 2d-2: матриця «роль × DocType × дія»

- **Вигляд `permissions`** списку DocType (`frontend/src/components/views/permissions/`): роль
  обирається у вигляді (`All` — перша), рядок — правило ролі на DocType (кілька правил з різним
  `match` — кілька рядків з бейджем умови; приховані/«лише читання» поля — лічильником), колонки —
  дії. `select` при ввімкненому `read` показано ввімкненим і заблокованим. Child DocType — рядок
  без чекбоксів («доступ — як до документа, що містить таблицю»). Назва — посилання на форму DocType.
- Зміни накопичуються між сторінками списку; «Зберегти» — один запит, «Відкинути» — скасувати.
  Зміна ролі з незбереженими змінами питає підтвердження.
- **Сервер** — `grunt/api/v1/permission_matrix.py`: `get_role_matrix(role, doctypes)` і
  `save_role_matrix(role, changes)` читають і пишуть через `get_doc`/`save_doc("DocType")` —
  та сама перевірка (`write` на DocType), валідація й експорт JSON, що й у формі. Правило
  адресується індексом у `permissions` + його `match`; розбіжність → `CONFLICT` (DocType змінили
  тим часом). Нове правило — без `match`; правило без дій видаляється, якщо в нього немає `match`
  і списків полів (інакше лишається для форми). Невідома роль → `NOT_FOUND`.
- `viewRegistry`: `ViewDefinition.available(dt)` + `isViewAvailable()` — одна перевірка для
  перемикача виглядів (`ListHeader`), рендеру (`ListViewRouter`) і `getAvailableViewTypes`.
- Тести: `tests/test_permission_matrix.py` (6), `frontend/src/core/__tests__/viewRegistry.spec.ts` (2).
  Переклади — вручну в `grunt.pot` і `uk` (повний `grunt i18n extract` тягне чужий дрейф).

### 2026-11-13 — крок 3a: дозволи

Гілка `feat/permissions-perms`.

**Механізм**
- `grunt/permissions/perms.py` — реєстр `Perm(name, label, description, app)`; ядро реєструє свої,
  застосунок — `permissions = [{"name": "inventory.manage_assets", "label": "…"}]` у `hooks.py`.
- Role: MultiSelect `permissions` (`options_source = "grunt.permissions"`). `*` — усе.
  Міграція: роль System Manager отримує `*`; `ensure_system_manager` створює її з `*`.
- `has_perm(perm, user=None)` — об'єднання дозволів ролей користувача (кеш роль → дозволи,
  інвалідація через `@fanout` з контролера Role). SYSTEM_USER — усе. Невідомий дозвіл у коді —
  помилка при імпорті/реєстрації, не тиха відмова.
- `@whitelist(perm="grunt.manage_email")` поруч із `roles=` (лишається для застосунків).
- Фасад: `grunt.has_perm(perm)`. `grunt.can()` з цільової моделі — це наявний `grunt.has_permission(doctype,
  action, doc_id)`; другої назви не вводимо.
- `/me` (auth store) повертає `permissions`; фронтенд — `auth.hasPerm()` замість `isSystemManager`.

**Дозволи ядра** (з 48 `whitelist(roles=["System Manager"])` і ~25 перевірок у коді)
- `grunt.manage_doctypes` — meta (save/delete/sync DocType, compact/table_info), rebuild_index
- `grunt.manage_desk` — Workspace, Page (register/delete)
- `grunt.manage_users` — список/схвалення/відхилення користувачів, ролі користувача, API-ключі інших
- `grunt.impersonate` — «увійти як»
- `grunt.manage_email` — облікові записи, черга, тест SMTP; email hooks
- `grunt.manage_storage` — StorageRemote, хмарний OAuth, стиснення зображень, чужі файлові простори
- `grunt.manage_backups` — backup_now, списки/завантаження копій зі сховища
- `grunt.manage_integrations` — вебхуки
- `grunt.manage_apps` — GruntInstalledApp (модулі)
- `grunt.system_monitor` — health, профайлер, кеш запитів, скасування фонових задач
- `grunt.moderate_comments` — чужі коментарі
- `grunt.restore_deleted` — DeletedDocument
- `grunt.bulk_delete` — швидке масове видалення
- Не дозволи (лишаються як є): перший користувач отримує System Manager; лічильник адмінів у
  health; підпис у CLI; rate limit (ролі з JWT). User Permissions не діють на `*` (крок 4 їх
  замінить). Workflow, AppMenu, Workspace-видимість, дії документа — 3b.

**Зроблено**
- Механізм, як у плані вище; міграція `0025_role_permissions` (колонка + `*` для System Manager),
  `_grant_system_manager` створює роль з `*`; тестова БД засіває System Manager з `*`.
- `register_notification_hooks` → `register_record_hooks`: `permissions` з `hooks.py`
  реєструються й на `migrate` (стандартні ролі застосунку можуть їх містити).
- Ядро: 47 `whitelist(roles=["System Manager"])` → `perm=`; рядкові перевірки → `has_perm`
  (DeletedDocument, реєстрація з погодженням, `update_user`, impersonation — ціль з `*` не можна,
  User.roles, ApiKey, fast delete, коментарі, пароль пошти, GruntInstalledApp, FileFolder,
  User Permissions — не діють на `*`). Мертвий `superadmin_user` прибрано.
- Лишилось до 3b: `actions/builtin.py` (дії документа з `roles=`), Workflow, AppMenu,
  видимість Workspace/Page, Report (і на фронтенді `isSystemManager` = має `*`: меню, звіти).
- Фронтенд: `whoami.permissions`, `auth.hasPerm()`; після входу профіль дочитується `whoami`.
  Мертвий проп `isSystemManager` у контексті виглядів прибрано.
- **Дозвіл відкриває метод, а не дані:** `grunt.manage_email` пускає до методів пошти, але
  EmailAccount читається за правилами DocType — щоб доручити пошту не-адміну, роль отримує ще
  й правила на ці DocType (матриця 2d). Об'єднати це (дозвіл тягне правила) — питання 3b/6.
- Тести: `tests/test_perms.py` (8). CodeQL локально — 0 циклів; pyright — нових помилок немає
  (32 давні в тестах і `bootstrap_site.py`).

### 2026-11-13 — крок 3b: ролі в налаштуваннях і діях

Гілка `feat/permissions-roles-in-features` (від 3a).
- **Дії документа** (`@doc_action`): `requires` — дія правила на цьому документі (типово `read`,
  з `match`), `perm` — дозвіл, `roles` — старе (будь-яка з ролей; власник `*` проходить).
  Ядро: відновлення з кошика — `grunt.restore_deleted`, «Надіслати звіт зараз» і «Скинути до
  стандарту» — `write` на документі, пуш користувачу — `grunt.manage_users`.
- **Workflow:** `user_may_take(..., unrestricted=)` і `edit_roles` — обхід лише для `*`.
- **Меню, сторінки, онбординг, тури:** бачить усе той, хто має `grunt.manage_desk`. Онбординг
  працює в `system_context` — прапорець обчислюється до входу в нього (інакше бачили б усі).
  Мертвий `AppMenu.has_access` прибрано.
- **Фронтенд:** `isSystemManager` прибрано зовсім; «Редагувати меню» — `grunt.manage_desk`;
  конструктор і збереження звітів — правила DocType Report (`useDocTypeAllows`).
- Рядки «System Manager», що лишились у ядрі, — дані й підписи: роль першого користувача,
  лічильник адмінів у health, CLI, rate limit (ролі з JWT), докстрінги.
- Тести: `tests/test_feature_perms.py` (4); mlt_portal — 108 зелених на цьому ядрі. CodeQL — 0.

### 2026-11-13 — крок 3c: роль у правилі мусить існувати

Гілка `feat/permissions-role-link` (від 3b).
- `DocPermission.role` — Link на Role (пікер у Studio). Сервер Link-значень не перевіряє, тож
  `DocTypeController.validate`: роль, нова для цього DocType, мусить бути документом Role або
  вбудованим принципалом (`BUILT_IN_ROLES` = `All`, `Guest`), інакше 422. Старі «висячі» правила
  (на dev2 — `Administrator` в official_documents) інші правки не блокують. Матриця (2d) і
  збереження DocType у Studio йдуть цим шляхом; `save_doctype` з коду — ні (тести, встановлення).
- Role — `standard_records`: `All` і `Guest` — стандартні записи ядра (`grunt/auth/records/role/`),
  щоб пікер їх пропонував. System Manager — ні: `migrate` переписав би його 2FA / IP на сайті.
- **Перекладна назва ролі — відкладено:** ядро не перекладає назви документів у Link-полях
  узагалі; це окрема фіча (як `translated_doctype` у Frappe), не лише для ролей. Назви ролей
  застосунків і так українські.
- Знахідка: 3a-тест експортував Role.json з рядками `RoleEditor`, dev2 їх підхопив
  (`permissions == permissions_base`) — 18 зайвих правил на Role; `grunt migrate` повертає чистий JSON.
  Ролі `RoleEditor` немає, доступу вони нікому не давали.
- Тести: `tests/test_role_link.py` (4).

### 2026-11-13 — рев'ю CodeRabbit (#151 матриця, #155 3b+3c)

- **Матриця:** рядок редагується лише після того, як його правила завантажено для цієї ролі;
  відповіді для старішої ролі / завантаження відкидаються (лічильник поколінь), роль не
  змінюється під час збереження. Чернетка пам'ятає правило, яке редагує (індекс, умову, дії як
  завантажені) — сервер порівнює їх із поточними й відповідає `CONFLICT`, замість переписати
  чужу зміну; нове правило — `CONFLICT`, якщо в ролі тим часом з'явилося правило на цьому
  DocType; понад 500 DocType — відмова без запису (раніше обрізало й казало «Збережено»).
- **«Скинути до стандарту»** пише всі поля як система — лише для того, у кого на цьому DocType
  немає прихованих чи «лише читання» полів.
- `useDocTypeAllows` — `computed`: стежить за ролями після перечитування профілю.
- Не прийнято: перевірка ролей у `save_doctype` (шлях коду/встановлення; тести й застосунки
  реєструють DocType з ролями, що з'являються пізніше) і «наступні виконавці» Workflow з `*`
  (кожен адмін про кожен перехід — шум; так було й до 3b).
