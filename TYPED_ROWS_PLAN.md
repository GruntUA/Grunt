# Типізовані документи й рядки — план

Живий план. Оновлюється після кожного кроку: що зроблено, що далі, які рішення прийняті.
Новий чат з Claude починає звідси.

**Статус (2026-11-25):** кроки 1–5 злито, v0.21.0 випущено (#271); далі — типізовані діти
(worktree-и від `origin/develop` у `/home/grunt/worktrees/…` — основне дерево не чіпаємо, з
нього працює dev2).

**Рішення власника (2026-11-24):** Q1 — варіант (б); Q2 — прибрати `Document.user` (як
рекомендовано); Q3 — часткові рядки строгі; Q4 — QuerySet/`.objects` прибрати, якщо не
потрібен (не потрібен: усе покриває `get_list(Cls)`); Q5 — типізовані діти входять у цей план.

**Рішення власника (2026-11-24, крок 3):** типізоване читання — класові методи контролера в
базовому `Document`: `await Order.get_doc(name)`, `Order.find_doc(name)`,
`Order.get_list(filters=…, fields=…)`, `Order.create(…)`. Фасад `grunt.get_doc/find_doc/get_list`
— лише назва-рядок (AttrDict); класова форма `grunt.get_list(Cls)` з #265 прибрана (не
випущена). `grunt.db.*(Cls)` лишається — шар без прав і хуків. Знахідка: `grunt.get_list`
віддає рядки у формі API (дати — ISO-рядки, підписи Link), тож `get_list(Cls)` з #265
обманював тип `datetime`; `Order.get_list` іде шляхом колишнього `grunt.get_all` (права,
хуки, маскування, збережені значення). Зворотну сумісність не зберігаємо, але кожне ламання позначаємо `!` у
conventional-заголовку PR, щоб воно потрапило в CHANGELOG.

Ціль: для відомого DocType на `rows[0].` IDE показує поля DocType. pyright 0 у ядрі й
застосунках, тести зелені на sqlite і postgres, CodeQL 0. На кожну дію в ядрі лишається
один очевидний спосіб.

---

## 1. Що перевірено (вихідні припущення → факт)

| Припущення | Факт (перевірено 24.11, develop 58e413c8) |
|---|---|
| `Document.objects` має тип `Any` | **Так.** `_ObjectsDescriptor.__get__` → `Any`, тож `await MltPage.objects.filter(…).first()` має тип `Any`. Виправляється одним рядком: `def __get__[T](self, instance, owner: type[T]) -> QuerySet[T]` дає `QuerySet[Page2]` і `Page2 \| None` (перевірено в pyright). |
| `.all()` у рантаймі повертає AttrDict | **Ні.** `QuerySet.all` → `documents.get_all(model_cls)`, а той будує **екземпляри контролера** (`tests/unit/test_queryset.py` перевіряє `isinstance(found, User)`). `list[T]` тут правдивий. |
| Типізованого читання списків немає | **Є, але його майже не використовують.** `grunt.get_all(MltPage, …)` → `list[MltPage]` (справжні контролери, з правами), лише клас, 2 виклики, обидва в тестах. Це «другий `get_list`» з іншою назвою. |
| `AttrDict.__getattr__` → None для відсутнього ключа | **Так.** У Jinja `x.k is defined` завжди істинне, `\| default()` не спрацьовує (перевірено; у звичайного `dict` усе працює). `Document.__getattr__` поводиться **так само**. |
| Строгий `__getattr__` (виняток замість None) масово зламає код | **Ні.** Плагін pytest з monkeypatch (ядро не змінювали): ядро — 2416 пройшли, 2 впали (сам тест AttrDict і мок у `test_mfa` без ключа); mlt_portal — 110/110. |
| `list[AttrDict]` інваріантний до `list[dict[str, Any]]` | Так. Те саме стосуватиметься `list[MltPage]` проти `list[Document]`: у параметрах треба `Sequence[Document]`. |
| Поля з назвою методу перекриваються | Для AttrDict — `items` у 5 DocType inventory. Для контролера — **`user` у 18 DocType ядра** (`SharedWith`, `ActivityLog`, `UserSession`, `DocVersion`…) і `data` в одному. `row.user` на контролері мовчки повертає **сесійного** користувача, і pyright не помічає, бо тип теж `str \| None`. |

Знайдене дорогою:

- `serde.to_json` для невідомого об'єкта робить `str(value)`, тож контролер у JSON мовчки стає рядком `"<ProbeOrder id='PO00000'>"`.
- `grunt.get_single` лежить у фасаді «з правами», але прав **не перевіряє**: це той самий `db.get_single_value`.
- Пусте `save()` на частковому контролері (`fields=["name","title"]`) **зливає** поля й не стирає решту (перевірено). Але хуки (`validate`) бачать `None` замість незавантажених полів.
- У ~51 контролера ядра, які читаються за назвою, **немає блоку типів**, а ще 4 DocType не мають контролера взагалі.

## 2. Інвентаризація

Підрахунок через AST, ядро + cms + mlt_portal + tsnap + hrm + inventory + letter + esign +
opendata + crystal_finance + hromada_it + lagoo. У дужках — скільки з них у тестах.

| Шлях | Права | Аргумент | Рантайм | pyright | Виклики |
|---|---|---|---|---|---|
| `grunt.get_doc(str)` | так | назва | AttrDict | `AttrDict` | 206 (113) разом із наступним |
| `grunt.get_doc(Class)` | так | клас | контролер | `MltPage` ✅ | 45 з цих 206 |
| `grunt.get_doc(dict)` | create | JSON | новий незбережений контролер | `Document` | 4 |
| `grunt.find_doc` | так | назва/клас | як get_doc або None | ✅ | 3 |
| `grunt.get_doc_instance` | так | назва | контролер | `Document` | 0 у застосунках, 4 у ядрі |
| `grunt.get_list` | так | назва | `DocumentList` з AttrDict, `["data"]`-хак | `DocumentList`, `[0]` → `Any` | 106 (48), `fields=` у 69 |
| `grunt.get_all` | так | лише клас | `DocumentList` з контролерів | `list[MltPage]` ✅ | 2 (2) |
| `MltPage.objects…` | так (через get_all) | клас | контролери | **`Any`** | 15, усі в ядрі |
| `grunt.db.get_all` | **ні** | назва | `list[AttrDict]` | `list[AttrDict]`, `.title` → `Any` | **345** (51), `fields=` у **313**, `pluck=` у 26 |
| `grunt.db.get_doc` | ні | назва | AttrDict / None | `AttrDict` | 9 |
| `grunt.db.get_value` | ні | назва | значення / list / AttrDict (`as_dict`, `"*"`) | overloads | 112 (32) |
| `grunt.db.get_values` | ні | назва | AttrDict | `AttrDict` | 33 — дублікат `get_value([..], as_dict=True)` |
| `grunt.get_value` | так | назва | значення | `Any` | 7 |
| `grunt.get_single` / `db.get_single_value` | **ні / ні** | назва | значення | `Any` | 33 / 1 |
| `grunt.new_doc` / `save_doc` | так | назва | AttrDict | `AttrDict` | 411 (332) / 213 (135) |
| `await Cls.create(…)` / `QuerySet.create` | create | клас | контролер | ✅ | 2 / 2 |
| `Document.load` / `Document.new` | — | назва | контролер | `Document` | 0 / 0 (є внутрішні `load_document`/`new_document`) |

Висновок: у застосунках основний шлях — `grunt.db.get_all("X", fields=[…])`, і він
нетипізований. Типізовані шляхи (`get_doc(Class)`, `get_all(Class)`, `.objects`, `.create`)
уже існують, але їх або мало, або вони дублюють одне одного.

### Як у Frappe (звірено з `frappe/develop`, 24.11)

- `frappe._dict`: `__getattr__ = dict.get`, тобто та сама пастка з None.
- `frappe.get_doc`: overloads за формою аргументу, але **завжди повертає `Document`**, а не клас контролера.
- `get_list`/`get_all`: без анотацій. `get_all` — це `get_list` з `ignore_permissions=True`. **Назви протилежні Ґрунтовим**: у Ґрунті `grunt.get_all` перевіряє права.
- `DF.Table = list`: дочірні рядки в типах не типізовані, але в рантаймі це екземпляри дочірніх контролерів.
- Відображення «назва DocType → клас» для type checker немає. Новинка develop — `Document.docs: DocsCollection[Self]`, де `SalesInvoice.docs.get(…)` має тип контролера. Тобто Frappe теж прийшов до «клас як вхід».

## 3. Заміри

**pyright** (`reveal_type`, `pyright 1.1.x` з package.json; файли — у scratchpad):

| Вираз | Тип |
|---|---|
| `(await grunt.db.get_all("MltPage"))[0].title` | `Any` |
| `(await grunt.get_all(MltPage))[0].title` | `str` |
| `MltPage.objects` / `.first()` | `Any` / `Any` |
| те саме з виправленим дескриптором | `QuerySet[Page2]` / `Page2 \| None` |
| `get_all(MltPage)` через overload (варіант а/б) | `list[MltPage]` |
| `rows_of(Page3)` з Protocol-рядком (варіант г1) | `list[MltPageRow]`, `.save()` → error ✅ |
| одруківка `p.titel` на контролері | `Any`, **помилки немає** (`Document.__getattr__`) |

**Автодоповнення** — через `pyright-langserver` по LSP (рушій Pylance), сортування як у редакторі:

- `rows[0].` для AttrDict: 47 пунктів, перші — `copy, clear, fromkeys, get, items, keys, pop…`, **жодного поля**.
- `typed[0].` для контролера: 111 пунктів, перші — `after_save, before_delete, before_save, content, cover_image, featured, … section`. Поля разом з хуками власного класу, далі методи Document.
- `light[0].` для Protocol-рядка: 26 пунктів, перші — `section, title, name`. Лише поля.

**Вартість на списках.** sqlite, тест-зонд у дереві ядра (видалено), 2000 рядків, найкращий з 7 запусків:

| Шлях | мс |
|---|---|
| `db.get_all` — усі поля, AttrDict | 13,9 |
| `db.get_all` — 3 поля | 8,2 |
| `get_list` (права) — усі поля | 27,2 |
| `get_all(Class)` (права) — усі поля, контролери | 18,6 |
| `get_all(Class)` — 3 поля | 13,5 |

Мікробенч побудови 1000 об'єктів (без БД):

| Побудова | мс |
|---|---|
| `dict` | 0,10 |
| `as_rows` → AttrDict | 0,62 |
| контролер через `__init__` | 2,39 |
| **швидка фабрика** (`object.__new__` + `doctype`/`data`) | **0,23** |
| легкий проксі `__slots__` | 0,27 |

Читання `.title` ×1000: AttrDict 0,13 мс, контролер 0,16 мс, `d["title"]` 0,03 мс.
Висновок: контролери зі швидкою фабрикою не дорожчі за теперішній AttrDict.
**Postgres не міряли**: локального сервера немає. Побудова об'єктів однакова для обох
СУБД, а тести на postgres ганяє CI на кожному кроці.

**Jinja** (`{{ x.nope is defined }}|{{ x.nope | default('D') }}`): AttrDict → `True|None`,
`dict` → `False|D`, контролер → `True|None`. Зі строгим `__getattr__` Jinja переходить до
`x["nope"]` і отримує Undefined, як і для `dict`.

## 4. Варіанти

### (а) API приймає клас, у рантаймі — AttrDict

- **IDE:** поля видно.
- **Чесність: тип обманює.** `.save()`/`.insert()`/`.as_dict()` є в типі, але падають у рантаймі. `isinstance(row, MltPage)` хибне. `idx` у контролері дає 0, а в AttrDict — None.
- **Вартість:** як зараз.
- **Вердикт:** відкинуто — саме такий обман ми й прибираємо.

### (б) Справжні екземпляри контролера (**рекомендовано**)

- **IDE:** поля + хуки + методи. Тип правдивий: `save()` на рядку справді працює.
- **Вартість:** зі швидкою фабрикою 0,23 мс/1000 рядків, дешевше за `as_rows`.
- **`fields=`:** рядок позначається частковим (`_fields`). Читання незавантаженого поля → `AttributeError` з підказкою. `save()` на частковому рядку → помилка (хуки інакше бачать None). Приховані правами поля читаються як None — вони «завантажені, але замасковані».
- **`pluck`:** без змін, `list[Any]`.
- **Діти:** етап 1 — `list[AttrDict]`, як зараз. Окремий крок — `list[ChildCls]`, як у Frappe в рантаймі.
- **Jinja:** атрибути працюють. Строгий `__getattr__` (див. R4) лагодить `is defined`/`default`.
- **JSON:** треба навчити `to_json`/відповіді API серіалізувати Document через `.data`, а `str()`-фолбек прибрати.
- **sqlite/pg:** однаково, бо все відбувається на рівні Python.
- **Ризики:**
  - поле `user` (18 DocType) — див. R5;
  - імпорт класу в модуль-споживач може замкнути цикл. У ядрі це ловлять храповик `test_import_cycles` і CodeQL; codemod має перевіряти граф (`grunt.utils.import_graph`) і в разі циклу лишати рядок;
  - DocType без контролера (≈4 у ядрі) і контролери без блоку типів (≈51) потребують `sync-types`.

### (в) Один вхід через `MltPage.objects` / QuerySet, решту прибрати

- **IDE:** після виправлення дескриптора — як (б), бо це той самий контролер.
- **Проти:**
  - 0 використань у застосунках проти ~1100 викликів у стилі Frappe;
  - бракує `pluck`, `or_filters`, `ignore_permissions`, `search`/`cursor`/`meta`, агрегатів;
  - API в стилі Django йде проти курсу FRAPPE_GAP;
  - переписування ~800 викликів на ланцюжки дає найбільший diff.
- **Вердикт:** не основний шлях. QuerySet як дублікат `get_list(Class)` — прибрати (див. §6). Frappe-шний `docs` — лише нотатка на майбутнє.

### (г1) Згенерований легкий Protocol-рядок

`MltPageRow(Protocol)` генерується тим самим `sync-types`, а контролер оголошується як `Document[MltPageRow]`.

- **IDE:** лише поля (26 пунктів), `save()` → помилка pyright. Рантайм лишається AttrDict.
- **Проти:**
  - поля **дублюються** — згенеровано, але двічі; власник уже відкидав `Fields`-TypedDict;
  - у кожному контролері потрібен generic-параметр;
  - Protocol — не `dict`, тож `row["x"]` і `dict[str, Any]` все одно ламаються для pyright;
  - сама API-межа робить `cast`, тобто це той самий обман (а), лише вужчий.
- **Вердикт:** запасний варіант, якщо (б) не підійде за поведінкою.

### (г2) `Document` як підклас AttrDict (контролер = dict)

- **За:** рядок і документ стають одним типом; JSON, `**row` і `row["x"]` працюють.
- **Проти:**
  - переписування `self.data` по всьому ядру;
  - методи `dict` (`items`, `update`, `get`, `pop`, `copy`) перекривають поля разом з методами Document;
  - найризикованіший варіант.
- **Вердикт:** відкинуто.

### (г3) Literal-overloads «назва → клас»

Як у boto3-stubs.

- **Проти:** overloads мусять жити у функції ядра, а застосунки не можуть їх доповнити без stub-пакета, який треба генерувати й підключати. У Frappe цього теж немає.
- **Вердикт:** відкинуто.

## 5. Рекомендація: «клас контролера — тип документа й рядка» (варіант б)

Розширюємо на всі читання патерн, який уже є в `get_doc`: **клас → екземпляри цього
класу, назва-рядок → AttrDict** (для динамічного коду, де DocType відомий лише в рантаймі).

- **R1. Читання з класом.** `grunt.get_list`, `grunt.db.get_all`, `grunt.db.get_doc` і `grunt.db.get_value(…, as_dict=True)` приймають `type[D] | str`. Для класу повертають `list[D]` / `D` / `DocumentList[D]`. Зареєстрований нащадок (`doctype_mixins`) поважаємо, як у `get_doc`. Створення: `await MltPage.create(…)`, оновлення: `doc.save()`. `new_doc`/`save_doc` лишаються для назви-рядка.
- **R2. Швидка фабрика.** `Document._from_row(cls, row)`: один пошук у реєстрі на виклик, `object.__new__` на рядок, без копіювання `data`. Атрибути `session`/`engine`/… отримують значення за замовчуванням на рівні класу.
- **R3. Часткові рядки.** Див. (б): `_fields`, `AttributeError` на незавантаженому полі, заборона `save()`/`insert()`.
- **R4. Строгий `__getattr__`.**
  - `AttrDict`: відсутній ключ → `AttributeError`.
  - `Document`: поле з блоку типів, якого немає в `data`, → None (необов'язкове поле, конструктор). Ім'я поза полями → `AttributeError`.
  - Bare `Document("X")` без блоку типів лишається як зараз.
  - Результат: Jinja `is defined`/`default` і одруківки в рантаймі.
- **R5. Прибрати `Document.user`.** 66 використань `self.user` переходять на `session_user()`. Тоді поле `user` у 18 DocType читається як поле. Це рішення власника (Q2).
- **R6. JSON.** `to_json` і JSON-відповіді серіалізують Document як `.data` (з дітьми). Невідомий тип → `TypeError` замість `str()`.
- **R7. `DocumentList[T]`.** Generic-підклас `list[T]` з `.meta`. Хак із ключами `["data"]`/`["meta"]` прибрати (17 місць, переходять на `.meta` / `to_dict()`).

## 6. Що прибрати, перейменувати, злити (кожне — `!` у CHANGELOG)

| Що | Чому | Заміна |
|---|---|---|
| `grunt.get_all` | дублікат `get_list(Class)`; назва протилежна Frappe (там це **без** прав) | `grunt.get_list(Cls, …)` |
| `Document.objects`, `QuerySet`, `_ObjectsDescriptor` | третій шлях; 15 викликів у ядрі | `get_list(Cls)`, `exists`, `count`, `Cls.create`; `get_or_create` — два рядки на місці |
| `grunt.get_doc_instance` з фасаду | дублікат `get_doc(Class)` | `get_doc(Cls)`; для назви-рядка — внутрішній `load_document` |
| `Document.load` / `Document.new` | 0 використань, дублікати `load_document`/`get_doc(dict)` | — |
| `grunt.db.get_values` | = `get_value([..], as_dict=True)` | `db.get_value(…, as_dict=True)` або `db.get_doc(Cls)` |
| `grunt.db.get_value(…, "*")` | = `db.get_doc` | `db.get_doc` |
| `grunt.get_single` | без перевірки прав у «правовому» фасаді | `grunt.get_doc(Settings).field` (з правами) або `db.get_single_value` |
| `AttrDict.__getattr__` → None | ламає Jinja й ховає одруківки | `AttributeError` (R4) |
| `Document.user` | перекриває поле `user` | `session_user()` (R5) |
| `DocumentList["data"]` | хак сумісності | `.meta`, `to_dict()` |
| `QuerySet.all -> list[T]` з `# type: ignore` у `get_all` | неперевірений тип | зникає разом з QuerySet |

Лишаються: `get_doc`/`find_doc` (виняток / None), `get_list` (з правами), `grunt.db.*` (без
прав, як `frappe.db`), `get_value` (з правами, одне поле), `new_doc`/`save_doc` (динамічні)
і `Cls.create` / `doc.save()` (типізовані).

## 7. Кроки (PR ≤ ~40 файлів у develop)

### Ядро

1. ✅ PR #265 **`feat(document)!: typed reads by controller class`** — R1, R2, R3, R6, R7. Тести: типи (`reveal_type` через pyright у тесті), часткові рядки, JSON, Jinja, нащадок з реєстру, 1000+ рядків. ~15 файлів.
2. ✅ PR #266 **`refactor(document)!: strict attribute access`** — R4. Виправити мок у `test_mfa` і тест AttrDict. ~6 файлів.
3. ✅ PR #267 (3a), #269 (3b) **`refactor(core)!: one way per action`** (3a — читання класом, QuerySet, get_all, get_doc_instance з фасаду, load/new; 3b — get_values, get_value("*"), get_single) — §6, крім `Document.user`: переписати 15 місць `.objects`, 4 — `get_doc_instance`, `get_single`, `get_values` у ядрі. ~25 файлів.
4. ✅ PR #270 **`refactor(document)!: drop Document.user`** — R5 (Q2 погоджено). Разом з #268 (регресія `input_data`) і #272 (рев'ю випуску) — у v0.21.0 (PR #271).
5. ✅ PR #275–#277 **`chore(doctypes): type blocks for core controllers`** — блоки типів для всіх контролерів ядра; JSON-поля → `Any | None`; `codegen.block_imports`; шаблон і scaffold через `build_controller_context`; 5 нових дочірніх контролерів (AssignmentRuleUser, ApiKeyRole, RoleProfileRole, UserGroupMember, UserRoleProfile). Блок описує конструктор, а не збережений документ: required-поле з `read_only`/`default` має тип `| None`.
6. **`feat(codemod): typed-rows`** — новий `grunt codemod typed-rows` (поруч з `attr-access`, спільна pyright-обв'язка):
   - літерал або модульна константа DocType у `get_doc/find_doc/get_list/db.get_all/db.get_doc/db.get_value(as_dict)` → клас + імпорт. Імпорт лише якщо `import_graph` не бачить нового циклу, інакше рядок лишається і потрапляє у звіт;
   - помилки pyright `reportAssignmentType`/`reportArgumentType`/`reportReturnType` на `dict[str, Any]` / `list[dict…]` / `list[AttrDict]` → тип контролера; для параметрів — `Sequence[Cls]`;
   - наприкінці запускається `attr-access` (він уже розуміє контролери);
   - ідемпотентний, `--dry-run`, `--app`.
7. **`refactor(core): apply typed-rows`** — прогін по ядру частинами за пакетами, ≤40 файлів кожна. Орієнтовно 3–4 PR (312 літеральних викликів поза тестами).
8. **Випуск ядра** (minor, з ламаннями) — `grunt release`.

### cms

1 PR: codemod + `sync-types` + `required_grunt>=<новий>`.

### Застосунки

Перший прохід (класова форма, get_values/get_single/"*", `session_user()`, `required_grunt>=0.21`) — ✅ злито 24–25.11: hrm#3, hromada_it#1, translate#1, cms#2, letter#3, esign#3, crystal_finance#3, inventory#3, mlt_portal#14 (зливалися раніше за випуск ядра). tsnap і opendata — локальні гілки `refactor/typed-reads` без remote, злити в master локально.

Другий прохід — codemod `typed-rows`, кожен PR з `required_grunt`, після випуску ядра:

- **mlt_portal** — codemod (53 літеральні виклики).
- **tsnap** — 67 викликів.
- **hrm** — 47 викликів.
- **inventory** — 70 викликів; поле `items` на контролері вже не перекрите.

### Типізовані діти (Q5 — у плані)

- `Table → list[ChildCls]` у блоці типів; діти документа, прочитаного класом, — контролери
  дочірнього DocType зі швидкою фабрикою. Окремий PR після кроку 5 (потрібні блоки типів
  дочірніх контролерів), до codemod.

### Необов'язкове (після основних)

- Прибрати `__getattr__` з погляду type checker для класів з блоком типів, щоб pyright бачив одруківки (`p.titel`). Ціну спершу поміряти в кроці 1.

### Skill grunt-dev

Джерело — репо `/home/grunt/grunt-agent-skills`, але встановлена копія `~/.agents/skills/grunt-dev` **розійшлася з ним** (diff по всіх references).

1. Спершу звести копії в одну.
2. Потім PR у skills: `references/api.md`, `database.md`, `controllers.md` — «читати класом», таблиця «одна дія — один спосіб», часткові рядки, `session_user()`, codemod для застосунків.
3. Перевстановити skill.

Робити разом із кроком 8 (випуск ядра).

## 8. Пришвидшення (окремо, на рішення власника)

1. **Швидка фабрика контролерів** — у `get_all(Class)`/`get_doc(Class)` уже зараз: 2,39 → 0,23 мс на 1000 рядків (×10). Входить у крок 1.
2. **Подвійний прохід `as_rows`.** SqlStore уже будує AttrDict, а `as_rows` ще раз обходить усі значення кожного рядка в пошуках дітей: 0,62 мс проти 0,10 для `dict` на 1000 рядків. Будувати дітей як AttrDict одразу в сховищі й пропускати `as_rows`, коли таблиць у `fields` немає. Виграш ~0,5 мс/1000 рядків на кожному `db.get_all`.
3. **`get_list` удвічі повільніший** за `db.get_all` на 2000 рядків (27 проти 14 мс). Причину не профілював; варто зняти профіль (`grunt.db.profiler`), перш ніж щось міняти.

## 9. Питання до власника — вирішено 24.11

Q1 — (б); Q2 — прибрати; Q3 — так; Q4 — прибрати повністю; Q5 — у цьому плані.

- **Q1.** Варіант (б) як основний? Альтернативи — (г1) Protocol-рядок або (в) QuerySet.
- **Q2.** Прибрати `Document.user` (R5)?
- **Q3.** Часткові рядки: `AttributeError` на незавантаженому полі й заборона `save()` — так?
- **Q4.** QuerySet/`.objects` прибрати повністю (рекомендовано) чи лишити з виправленим дескриптором?
- **Q5.** Типізовані діти — у цьому плані чи пізніше?

## Журнал

- 2026-11-25 — злито #273 (2-й раунд CodeRabbit до #271: attr-access переписує `.get` лише на
  `self`, перетин полів для класів-тезок, ADR get_or_create, dump_many), #274 (статус плану),
  #275–#277 (крок 5). Worktree-и злитих гілок прибрано. Далі: типізовані діти, codemod
  `typed-rows`, skill.

- 2026-11-25 — злито #268 (`input_data`), #269 (3b), #270 (крок 4, `Document.user` →
  `grunt.session_user()`), #272 (рев'ю CodeRabbit до випуску: `input_data` у `_from_rows`,
  codemod `.get` лише для оголошених полів); випуск v0.21.0 — PR #271 (злито, тег v0.21.0). Другий раунд CodeRabbit на #271
  прийшов до злиття — виправлення в #273 (наступний випуск).
  Застосунки першого проходу злито (див. §7). Worktree-и кроків 1–4 і застосунків прибрано.
  Далі: крок 5, діти, codemod `typed-rows`, skill.

- 2026-11-24 — регресія #265: `Document.input_data` прибрано як «невикористаний», а його
  ставить життєвий цикл (`self.input_data = data`) і читає hromada_it (IndexValue.validate) →
  гілка `fix/input-data` (знову зарезервований, тест). Застосунки (worktree-и
  `/home/grunt/worktrees/apps/<app>`, гілки `refactor/typed-reads`): класова форма → `Cls.get_doc`,
  get_values/get_single/"*" (108 замін, AST-codemod) + борг v0.19 (list[dict]→list[AttrDict] /
  Sequence/Mapping, `User(doctype=, data=)`→`User(**…)`); `required_grunt>=0.21`; pyright 0 у
  hrm, inventory, letter, esign, crystal_finance, hromada_it, translate, tsnap, opendata; тести
  зелені (letter, translate — без тестів). mlt_portal — після коміту власника на його гілці.

- 2026-11-24 — крок 3b (гілка `refactor/one-way-values`): прибрано `grunt.db.get_values` (→
  `get_value(..., [..], as_dict=True)`), форму `get_value(..., "*")` (→ `db.get_doc`; тепер
  ValueError з підказкою) і `grunt.get_single` (→ `grunt.db.get_single_value`, він і раніше не
  перевіряв прав). Заміни — одноразовий AST-codemod (scratchpad `tools/values_codemod.py`, він
  же переписує класову форму `grunt.get_doc(Cls, …)` → `Cls.get_doc(…)` для застосунків).

- 2026-11-24 — крок 3a (гілка `refactor/one-way-reads`, worktree `/home/grunt/worktrees/one-way`):
  `Document.get_doc/find_doc/get_list` (classmethod, `Self`) поверх `DocumentAPI.doc_of /
  find_doc_of / list_of`; прибрано QuerySet і `Document.objects`, `grunt.get_all`,
  `Document.load/new`, класові overload-и `grunt.get_doc/find_doc/get_list`, `get_doc_instance` з
  фасаду (у ядрі лишається `documents.get_doc_instance` — динамічна назва з правами). Знахідки:
  `get_users_by_emails` різав до 20 (ліміт QuerySet); `lifecycle._load_existing` і
  `collection.rename_document` викликали `load` через `self`/`registry.base`. Ядро 2716 passed.

- 2026-11-24 — крок 1 у worktree `feat/typed-reads` (не закомічено, чекає рев'ю): `__doctype__`
  на класі (реєстр проставляє; `DocTypeController` = "DocType"), `Document._from_rows` (швидка
  фабрика, часткові рядки, приховані поля → None), `DocumentClass` Protocol у `attr_dict`
  (db-шар не імпортує Document), класом приймають `db.get_all/get_doc/get_value(as_dict)` і
  `get_list` (`DocumentList[T]`), `get_doc(Cls)` через фабрику; `to_json` документа →
  `as_dict()`, невідомий тип → TypeError; прибрано `DocumentList["data"/"meta"]` і
  `Document.input_data` (не використовувався). Тест `grunt/document/tests/test_typed_reads.py`
  з `assert_type` (його бачить CI-pyright). pyright 0, sqlite 2723 passed, postgres 2722 passed.
  PR #265; після рев'ю: тіла overload-ів — docstring (CodeQL py/ineffectual-statement),
  системні властивості часткового рядка теж строгі (CodeRabbit). Поле `user` (CodeRabbit,
  Major) — крок 4, до випуску.
- 2026-11-24 — крок 2 (гілка `refactor/strict-attr` поверх #265, не закомічено):
  `AttrDict.__getattr__` → `AttributeError`; `Document.__getattr__`: поле DocType (з `_dt`, якщо
  є, інакше з анотацій класу) → None, інше ім'я → `AttributeError`, клас без анотацій — як раніше.
  `User.role_names` читав службове `role_rows` атрибутом — тепер `data.get`. Jinja-середовища
  сайту, друку, сповіщень і `utils/templates` — `RowUndefined` (ланцюжок на відсутньому ключі
  порожній, як раніше; відмова пісочниці й далі `SecurityError`). Ядро sqlite 2729 / postgres
  2728, застосунки (mlt_portal, cms, tsnap, hrm, inventory) зелені проти цього коду.

- 2026-11-24 — аналіз, заміри, план. Тест-зонд у `tests/` видалено; ядро не змінено.
