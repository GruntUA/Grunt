# Шари роботи з БД — план

Живий план. Оновлюється після кожного кроку: що зроблено, що далі, які рішення прийняті.
Новий чат з Claude починає звідси.

**Мета:** ядро не знає, на якій СУБД лежить DocType. Відмінності SQLite/Postgres(/MySQL)
зібрані в одному місці, а DocType може зберігатися не лише в SQL-таблиці основної бази
(віртуальний, HTTP-джерело, таблиця в іншій БД) — з тими самими правами, фільтрами й пошуком.

Оновлено: 2026-11-07 (кроки 1–4 готові; далі 5 — Connections + UnitOfWork + outbox)

---

## Цільова схема

```
┌ 1. Document / Service  ─ хуки, валідація, права, workflow. SQL не знає.
│        ↓ Query (власний AST: filters, fields, sort, group, page)
├ 2. Query + Permissions ─ права додаються предикатами в AST, а не в SQL
│        ↓ Store protocol
├ 3. Stores ─ SqlStore │ VirtualStore │ HttpStore │ ReadOnlySqlStore (чужа БД)
│        ↓ (лише SqlStore)
└ 4. Dialect ─ SqliteDialect │ PostgresDialect │ MysqlDialect  (+ Connections / UnitOfWork)
```

## Рішення

- **SQLAlchemy Core лишається.** Свого ORM і обгортки над Core не робимо: Core уже є
  шаром діалектів, `grunt/db/dialects/` лише закриває його прогалини (сортування,
  FTS, DDL-особливості, обслуговування).
- **`dialect.name ==` поза `grunt/db/dialects/` заборонено.** Перевіряє
  `tests/test_dialect_boundary.py`; у ньому список ще не перенесених файлів, який має
  лише скорочуватись.
- **Назва діалекту як рядок лишається публічною** там, де це API для користувача:
  `db_dialect` у Script Report, `dialect` у відповіді `table_info`.
- **Жодних запасних варіантів** (2026-11-06): generic-діалекту немає, `dialect_for()` для
  невідомої СУБД чи об'єкта без bind (сесія без engine) кидає `UnknownDatabaseError`;
  `current_dialect()` поза сесією — теж помилка. `like_term`/`match_columns` вимагають
  діалект явно. `Dialect` — ABC: `date_bucket`, `compaction_command`, `compaction_scope`
  обов'язкові для кожної СУБД.
- **Store protocol охоплює реальні потреби** (SQL, virtual, HTTP, чужа SQL-база
  read-only), документних СУБД не абстрагуємо.

## Кроки

### 1. `grunt/db/dialects/` — ✅ (дрібні залишки — у «Лишилось»)

Зроблено (2026-11-06):
- пакет `grunt/db/dialects/` (`base`, `sqlite`, `postgresql`, `mysql`),
  `dialect_for(obj)` — з рядка, URL, engine, connection, session;
- налаштування engine (pool, PRAGMA, `BEGIN IMMEDIATE`, Unicode `lower`) —
  з `site/manager.py` у `SqliteDialect.setup_engine`; відносний шлях SQLite — `resolve_url`;
- вирази: `text_sort` (було `text_sort_expr`), `date_bucket` (було `db/buckets.py`,
  лишився сумісний обгортковий `date_bucket`), `like_contains` (ASCII-LIKE на SQLite);
- схема: `can_alter_column_type`, `group_concat_sql` (**виправлено баг PG:**
  перевірка дублікатів перед unique-індексом використовувала `GROUP_CONCAT`, якого
  в Postgres немає), видалення unique (`drop_unique_index` у savepoint — на PG
  невдалий `DROP INDEX` раніше обривав транзакцію), перебудова таблиці SQLite
  для inline-обмежень;
- обслуговування: `server_version`, `database_size` (health), `compaction_scope` +
  `compaction_command`, `compaction_footprint`, `table_storage` (`compact_table`/`table_info`),
  `vacuum_sql` (`grunt app remove --vacuum`);
- `search/terms.py`: `like_term`, `session_dialect`, `escape_like` делегують у діалект
  (`search/service.py` не чіпали);
- `tests/test_dialect_boundary.py`, `tests/unit/test_dialects.py`.
- Перевірено: ruff, pyright, повний pytest на SQLite (1814 ✓; `test_offline_sync` нестабільно
  дає 403 під xdist, окремо проходить), engine живих сайтів dev2/lagoo (WAL, `uk_sort_key`,
  кириличний `lower`). **На Postgres не перевірено** — локально PG немає, чекаємо CI.

Зроблено (2026-11-06, пошук):
- `Dialect.upsert(table, row, key)` — `ON CONFLICT` (SQLite/PG) / `ON DUPLICATE KEY` (MySQL);
  на SQLite замість delete+insert;
- `grunt/db/dialects/fulltext.py`: `FullTextSpec` (таблиця + key/title/label/content) і
  `Dialect.fulltext(spec)` → `SqliteFts5` / `PostgresTsvector` / `MysqlFulltext` з єдиним
  `ensure / write / delete / clear / match`; `match()` → `None` = fallback на LIKE;
- `search/service.py` більше не знає СУБД; FTS5-колонка зберегла назву `idx_id` — таблиці
  на наявних сайтах працюють без перебудови (перевірено на dev2, 31 тис. записів);
- індекс `grunt_search_idx_doctype` тепер на всіх СУБД (був лише на PG), створюється
  `checkfirst`; на PG — уже не `CONCURRENTLY`;
- MySQL: FULLTEXT-індекс тепер зветься `grunt_search_idx_ft` (був `idx_ft_content`) —
  на наявній MySQL-базі з'явиться другий, старий можна видалити.

Зроблено (2026-11-06, бекапи):
- `Dialect.dump_suffix / dump_estimate / dump / restore_dump`: знімок SQLite (backup API +
  `quick_check` + zstd) — у `sqlite.py`, `pg_dump`/`pg_restore` — у `postgresql.py`; MySQL —
  `BackupError` як і раніше;
- `grunt/backups` лишився оркестратором (набір, прогрес, місце, лок, ротація); крок набору —
  `_Step(read, space, dest, make)`, оцінка місця не змінилась;
- **тест межі без винятків** — `NOT_YET_MOVED` прибрано.

Зроблено (2026-11-06, помилки цілісності):
- `Dialect.integrity_violation(exc)` → `ConstraintViolation(kind, table, columns, constraint)`:
  SQLite — текст, Postgres — SQLSTATE + поля asyncpg (fallback на текст), MySQL — коди помилок;
- `db/errors.friendly_integrity_error(exc, dt, bind)` — без регулярок драйверів. Виправлено
  на PG: NOT NULL не розпізнавався; колонку unique брало хибно (`core_web_article_route`
  замість `route`); дубль DocType у registry давав 500 замість 409.

Зроблено (2026-11-06, PostgreSQL зелений):
- тести: окрема база на xdist-воркер (`testkit.worker_database_url`, `Dialect.create_database`),
  `bind_test_site` (сайт `__pytest__` — тестовий engine і тимчасова тека сайтів),
  `hold_task_queue` (`.kiq()` у тестах нікуди не шле — ні в dev-Redis, ні in-process);
- `CheckBool` (`db/types.py`) для Check-полів: `1` / `"0"` / `"true"` → `bool` у порівняннях
  і записі, `is_(True)` → `IS true`. Закрило `boolean = integer` на PG;
- пошук на PG: дефіси → пробіли перед `to_tsvector` (індекс `grunt_search_idx_ts2`);
- бекапи (рев'ю CodeRabbit): пароль PG через `PGPASSWORD`, збої `pg_dump`/`pg_restore` і
  битий архів — `BackupError`, відкат файлів SQLite, якщо підміна бази не вдалась;
- CI: `fsync`/`synchronous_commit`/`full_page_writes` off для тестового PG;
  **`continue-on-error` прибрано — PostgreSQL тепер блокує, як SQLite**
  (перший зелений прогін: 1819 passed, 0 failed; локально 1843/1844).
- Локальний PostgreSQL для тестів: `pgserver` (Python 3.12, `uv run --no-project --python 3.12
  --with pgserver`), `TEST_DATABASE_URL=postgresql+asyncpg://postgres@/grunt_test?host=<pgdata>`.

Зроблено (2026-11-07, залишки CodeRabbit #96):
- restore на PG: перед `pg_restore` — `pg_dump` поточної бази в `aside/database.pgdump`
  (zstd:1); `pg_restore --single-transaction` — битий архів відкочується, база як була
  (перевірено на живому PG);
- пошук на PG: `ensure` бере advisory lock (`pg_try_advisory_lock(hashtext(<індекс>))`) —
  не взяв → індекс будує інший процес, не чіпаємо; взяв, а індекс `indisvalid = false` →
  залишок збою, `DROP INDEX CONCURRENTLY` і будуємо знову;
- MySQL: `ConstraintViolation.primary_key` (ключ `PRIMARY`) + `columns_in(table)` — колонки PK
  з таблиці; registry порівнює `columns_in(meta_table) == ("name",)` → дубль DocType = 409.

Лишилось:
- `write_intent.py` — переїде в крок 5 (маршрутизація читання/запису).

Ізоляція тестів (2026-11-06) — **нестабільних тестів більше немає** (2× SQLite 1852/1852,
2× PG 1851/1851 паралельно):
- причина «плаваючих» 403/чужих рядків/зайвого System Manager — **спільний Redis** між
  xdist-воркерами (і з dev-сервером): `doc_cache`/`query_cache`/шина кешу з ключами від сайту
  `__pytest__`, однакового в усіх воркерах. `testkit.isolate_from_redis()` — тести без Redis, як CI;
- `grunt_search_index` не видалявся між тестами (немає в жодній MetaData) — teardown тепер
  `search_index_service.drop_table()` (з FTS5-таблицею);
- серверна тестова база перестворюється на старті прогону (`_gw0`…, без xdist — `_main`;
  `Dialect.create_database(replace=True)`) — залишки перерваного прогону не потрапляють у наступний.

Швидкість тестів (2026-11-06): `testkit.TestSchema` — схема створюється раз на воркер, між
тестами таблиці лише чистяться (`Dialect.empty_tables`: PG — один `TRUNCATE`, інші — `DELETE`).
DDL тесту відстежується: створені ним таблиці видаляються після нього, а зміна базової схеми
(ALTER/індекс/DROP/перекомпільована таблиця) чи нерозпізнаний DDL — повне перестворення.
Локально `-n 4`: SQLite 207 → 85 с, PostgreSQL 272 → 100 с, без падінь.

Зроблено за другим рев'ю CodeRabbit (2026-11-06): у виразі tsvector константи — SQL-літерали
(з параметрами загальний план asyncpg не бачив GIN-індекс: `Seq Scan`, перевірено на PG 16);
URL сайту → параметри libpq для `pg_dump`/`pg_restore` (`ssl`→`sslmode`, драйверні відкидаються);
psycopg (`pgcode`/`diag`) в `integrity_violation`; `dialect_name` питає `get_bind()` у сесії без
`.bind`; окремі повідомлення для FK/CHECK/NOT NULL без колонки; лапки таблиці з діалекту в `table_info`.

### 2. Contract-тести — ✅ (2026-11-06)

`tests/contract/`: один набір даних (`ContractItem`/`ContractGroup`: Data, Int, Currency, Check,
Date, Datetime, Select, Link, MultiLink, кирилиця, `NULL` і `''`) і кейси, записані як контракт.
CI проганяє їх на SQLite і PostgreSQL; `test_in_memory.py` — ті самі кейси через
`grunt.document.in_memory` (віртуальні DocType). 170 кейсів, зелені на обох СУБД.

Правила, які контракт фіксує (і що довелось виправити):
- **сортування**: текст — `lower()` за кодами Unicode, **без правил окремих мов** (рішення
  2026-11-06: дані бувають різними мовами впереміш; мовні колації — не справа ядра). На PG
  `lower(col) COLLATE "C"` — інакше порядок залежить від колації бази (`en_US`, `uk_UA` сортують
  по-своєму), MySQL — `utf8mb4_bin`, SQLite — свій Unicode `lower()`, in-memory — `str.lower()`.
  **Порожні (NULL) в кінці** в обидва боки (`Dialect.sort_key/order_by/sort`, MySQL — емуляція);
  `name` за кодами (`Dialect.exact`: PG `COLLATE "C"`) розв'язує рівні значення — і `abc`/`ABC`
  при сортуванні за `name` (курсор за `name` раніше порівнював сиру назву — пропуск; #97); те саме в дереві, звітах, `get_all`, агрегатах;
- **курсорна пагінація** йде тим самим порядком (раніше: сира колонка проти ключа абетки,
  значення курсора — рядок, обрив на `NULL`; на PG 7 з 10 кейсів давали пропуски/дублі/помилку);
- **фільтри**: число рядком з query string (`qty__gt=5`, CSV в `__in`) — числом (PG не порівнював
  `int` з `'5'`); `__like` не враховує регістр на всіх СУБД (як завжди на SQLite);
  `__like/__ilike` — **шаблон** (`%`, `_` працюють: додатки передають `%…%`), а пошук у списку й
  глобальний — **текст** (`%`, `_` буквально);
- **бакети дат** Datetime — в UTC: сесія PG завжди UTC (`Dialect.connect_args` — asyncpg
  `server_settings`, psycopg `options`; сайт, тести, додатки). Раніше `to_char`/`date()` брали
  пояс сесії — 2025-12-31 23:00 UTC потрапляло в 2026. Перетворення в SQL (`timezone('UTC', …)`)
  не годиться: для «наївної» колонки `timestamp` воно зсуває навпаки (CodeRabbit, #97);
- **in-memory** = SQL: типізоване порівняння (числа, Check, дати), NULL не підходить під
  порівняння, `%`/`_` у like, той самий порядок тексту, порожні в кінці. LIKE — лінійне
  зіставлення, не regex: `%a%a%…` з `.*`-групами давав експоненційний бектрекінг (ReDoS, #97).

### 3. `Query` AST — ✅ (2026-11-07)

`db/filters.py` розбирає вхідні дані в нейтральний `Query`; права (user permissions,
shares, власник) — вузли AST; `SqlStore` компілює в SQLAlchemy. Звіти/Query Builder
(JOIN з правами, IDEAS 2.2) будуються над AST.

**Що є зараз (інвентаризація 2026-11-07):**
- фільтри: `build_clauses`/`apply_filters` (~20 викликів: `db/api.py` ×8, `collection`, `tree`,
  `reports/engine`, монітори) одразу дають SQLAlchemy; `in_memory.py` — друга реалізація тих
  самих операторів на Python (контракт тримає їх однаковими, але це дві копії);
- права: `apply_permission_filter` склеює SQL з п'яти джерел — `match` (`PermissionMatch.to_sql`),
  reference (`inherit_permission_from`), child, shares (`SharedWith`), User Permissions; перевірка
  одного документа (`rbac.check`, `PermissionMatch.evaluate`, `doc_passes`) — окрема Python-логіка;
- **знайдено (2026-11-07):** User Permissions кожен виклик додавав сам (`build_conditions`), а
  `grunt.get_all` і `grunt.aggregate` — забули: показували рядки, які `get_list` ховав.
  Виправлено: `apply_permission_filter` сам додає User Permissions, окремі виклики прибрано
  (`collection`, `tree_rpc`, `reports/engine`, `reference`), тест `test_get_all_and_aggregate_are_restricted`.
  Саме цей клас помилок («крок прав, який треба не забути») AST має прибрати.

**Дизайн.** Пакет `grunt/query/` (шар 2 — над Store, не в `db/`):

- `nodes.py` — незмінні dataclass-вузли, що знають лише назви полів DocType, не колонки:
  - `Cmp(field, op, value)` — `eq ne gt gte lt lte`; значення вже типізоване за полем Meta;
  - `Like(field, pattern, negate)` — шаблон `%`/`_`, регістр не враховується;
  - `In(field, values, negate)`, `Empty(field, negate)` (`is set` — NULL або `''` для тексту),
    `Null(field, negate)`, `Range(field, lo, hi)` (`__year` → півінтервал, індекс працює);
  - `And / Or / Not`, `TRUE / FALSE`;
  - `Linked(field, Query)` — значення поля серед `name` іншого запиту: `match` через Link
    (`team.region == user`), shares (`name IN SharedWith…`), reference, child — усе це один вузол;
  - `MultiLink(field, values | None, negate)`; `Search(text, fields)` — пошук у списку;
  - `Raw(clause)` — лазівка для `list_filter_extra` контролерів (SQL-only; VirtualStore → 400).
- `Query(doctype, where, fields, sort, group_by, aggregates, limit, offset, after)` — `after`
  замість курсора-рядка; порядок (порожні в кінці, `name` розв'язує рівні) — властивість Query.
- `parse.py` — `filters → Expr` (теперішній `split_key`/`typed_value`, але типізація за полем Meta,
  тож in-memory отримує ту саму). Невідомі поля — пропускаються, як зараз (змінити на 400 — у кроці 4).
- `permissions.read_predicate(user, meta) → Expr` замість `apply_permission_filter`: усі асинхронні
  довантаження (значення User Permissions, корені shares, дерева, `DISTINCT` reference) — тут,
  результат — чистий Expr. Fail-closed = `FALSE`.
- **Одна точка**: `secure(query, user) = query.where(And(query.where, read_predicate(user, meta)))`;
  виконавець (`run(session, query, as_user=…)`) приймає лише Query — пропустити права неможливо,
  «сирий» шлях (`ignore_permissions`) — явний аргумент.
- `compile_sql.py` — `Expr → SQLAlchemy` через `Dialect` (сортування, `like_contains`, `exact`,
  keyset); `evaluate.py` — `Expr → bool` для dict: замінює `in_memory.apply_filters` і
  поступово — перевірку одного документа (`doc_passes`, `match`), тож список і `get_doc`
  відповідають одним предикатом. `Linked` в evaluate — через довантаження (як `evaluate_doc`).

**Порядок (кожен — окремий зелений PR, контракт `tests/contract/` — сітка безпеки):**
- 3a. ✅ (2026-11-07) Вузли + `parse` + `compile_sql`; `build_clauses` = `compile(parse(…))`; `in_memory` → `evaluate`
  (прибирає другу копію операторів). Поведінка не змінюється.
  Зроблено: `grunt/query/{nodes,parse,compile_sql,evaluate}.py`. Вузли: `Cmp Like In Null Empty Year
  MultiLink And Or Const` (`TRUE`/`FALSE`); `and_`/`or_` сплющують і поглинають константи.
  **Відхилення від дизайну:** (1) значення в AST — як їх дали; типізує виконавець (SQL — за колонкою,
  `typed_value`; пам'ять — за значенням рядка, `_pair`), бо Meta не знає стандартних колонок і так
  поведінка не змінюється; (2) загального `Not` немає — NOT у SQL (тризначний) і в Python розходяться
  на NULL, тож заперечення — прапорець `negate` у листках з явним правилом для NULL. `Linked`, `Search`,
  `Raw` — у 3b/3c, коли з'являться споживачі. `filters.py` — тонкі обгортки (`DISPLAY_OPS` лишився там,
  решта реекспортується з `grunt.query.parse`). Невідомі поля: `parse_filters(fields=…)` пропускає;
  `fields=None` (пам'ять) — невідомий оператор (`__child_of`) → `ValueError`, як і було.
  Перевірено: `tests/unit/test_query_ast.py` + контракт; SQLite 2057, PG 2058, pyright 0.
- 3b. ✅ (2026-11-07) `PermissionMatch.to_expr`, `read_predicate`; `apply_permission_filter` = `compile(read_predicate)`
  (тимчасова обгортка). Контракт-кейси на права (match, shares, reference, child, UP) на обох СУБД.
  Зроблено: вузол `Linked(field, doctype, where, select="name", negate)` + `linked_doctypes(expr)`;
  `to_sql(…, tables=…)` компілює його в `IN (SELECT …)`, таблиці збирає обгортка через `get_meta`
  (компіляція лишається синхронною). Джерела прав повертають Expr: `PermissionMatch.to_expr`,
  `user_permission_predicate` (було `build_conditions`), `shared_predicate` (було `shared_names_clause`),
  `reference_predicates` / `readable_predicate` (було `reference_conditions` / `readable_names` — тепер
  предикат батька вкладається в `Linked`, без окремого `SELECT`), `child_predicate`.
  `tests/contract/test_permissions.py` — 18 кейсів; **ті самі кейси зелені й на старому коді**
  (перевірено, повернувши старі `grunt/permissions/*`), тож поведінка не змінилась. Зафіксовано
  як контракт: без жодної ролі — 403, а не порожній список; share сам дає доступ до свого документа;
  `link.field != v` = «не серед рядків, де `field == v`» (порожнє поле цілі — підходить, порожній Link — ні).
  Тести: `_UP_CACHE` чиститься між тестами (`conftest.setup_db`) — кеш User Permissions за email
  протікав між тестами на одному воркері (плаваюче падіння `test_permission_engine`).
- 3c. ✅ (2026-11-07) `list_documents` / `get_all` / `count` / `aggregate` / tree / звіти будують `Query` і йдуть через
  `run`; обгортки `apply_filters`/`apply_permission_filter` зникають.
  Зроблено: `grunt/query/sql.py` — `filter_expr(filters, table, meta)` і `where(stmt, expr, table, doctype)`
  (довантажує таблиці `Linked`) — **єдиний шлях фільтрів і прав у WHERE**. `grunt/db/filters.py` видалено
  (`DISPLAY_OPS`, `FILTER_OPS`, `split_key`… — у `grunt.query.parse`, `typed_value` — у `compile_sql`);
  `apply_permission_filter` видалено — лишився `read_predicate`. `grunt.db.get_all/aggregate`: колбек
  `scope` → `predicate: Expr` (фасад передає `read_predicate`). `collection`, `tree`/`tree_rpc`, звіти —
  `where(…, and_(read_predicate, filter_expr))`.
  Заодно: `grunt.db.delete` / `bulk_update` з фільтрами лише на невідомі колонки (одруківка) тепер
  `ValueError`, а не операція над **усіма** рядками (раніше невідомий ключ мовчки зникав).
  **Відхилення:** окремого об'єкта `Query` + `run` ще немає — без Store йому нема споживача, а
  сортування/курсор/групування поки в місцях виклику. Переноситься в крок 4: `Store.list(query)` —
  там він і з'явиться разом з `capabilities`. `list_filter_extra` і пошук у списку лишились
  SQL-умовами після предиката (вузли `Raw`/`Search` — теж у кроці 4, коли VirtualStore має їх відхиляти).
- 3d. ✅ (2026-11-07) JOIN з правами для звітів/Query Builder (IDEAS 2.2).
  Зроблено: `grunt/reports/joins.py` — `report_source(meta, user, fieldnames)`: поле через Link
  `customer.region` (один хоп, як у `match`) → `LEFT JOIN` цілі (alias `j_<link>`, один на Link) з
  `read_predicate` цілі в `ON`. Колонки — `WriteableColumnCollection` з ключами `customer.region`, тож
  `filter_expr`/`to_sql` компілюють фільтри й умови по JOIN без змін. Недоступний рядок цілі → поля
  порожні (рядок звіту лишається; фільтр/групування по цілі нічого про нього не видають).
  **Заодно виправлено:** звіти не застосовували `hidden_fields` навіть для свого DocType — колонкою,
  фільтром чи групуванням можна було прочитати приховане поле. Тепер поле, якого глядач не бачить
  (приховане, або DocType цілі без `read`), відсутнє в джерелі: колонка випадає, фільтр/умова
  пропускаються (як невідома колонка — не оракул). Drill-down вимикається, якщо групування чи умови
  йдуть через Link (список так фільтрувати не вміє). Фронтенд: `QueryReportBuilder` додає до доступних
  полів поля кожного Link (`Клієнт → Регіон`); недоступна ціль — пропускається.
  Тести: `grunt/reports/tests/test_report_joins.py` (7).

### 4. Store protocol — ✅ (2026-11-07)
`Store` (`get/list/insert/update/delete/aggregate` + `capabilities`). `SqlStore` обгортає
теперішні mixins, віртуальні DocType → `VirtualStore`. Поле DocType
`storage: "sql" | "sql:<alias>" | "virtual" | "http:<connector>"`. Ядро перевіряє
`capabilities` і відповідає 400 замість падіння на SQL.

**Інвентаризація (2026-11-07):** сховище вже є, але в контролері: `BaseDocument` має
`load_from_db / db_insert / db_update / db_delete / get_list / get_count`; `Document`
перевизначає їх SQL-ом (`mixins/read.py`, `write.py`), 12 віртуальних контролерів — своїми
`apply_filters/apply_sort/apply_search/build_response`. Права для них — обхід `_readable_rows`
(до 5000 рядків, `permission_checker.check` кожного). `dt.is_virtual` — ~40 перевірок; решта коду
бере `dt.table` і на віртуальному падає. `grunt.db.*` — ~900 викликів напряму в SQL.

**Рішення (погоджено 2026-11-07):**
- `storage` зараз лише `"sql" | "virtual"`; `sql:<alias>` — у кроці 5 (з'єднання), `http:` — коли
  з'явиться живий конектор;
- `grunt.db.*` теж іде через `store_for` — для не-SQL зрозуміла помилка `capabilities`;
- **сумісність не зберігаємо**: старий API віртуальних контролерів (`get_list`/`get_count`/
  `load_from_db`/`db_*` на контролері) прибирається, `ControllerStore` не робимо — усі контролери
  (і `translate`) переходять на Store;
- невідомі поля у фільтрах → 400 — окремим PR після 4a.

**Дизайн:**
- `grunt/query/query.py` — `Query(doctype, where, fields, sort, limit, offset, after, search,
  group_by, aggregates)`, `Sort(field, descending)`; `after = (значення, name)` — keyset;
- `grunt/query/run.py` — `fetch / count / aggregate / page(query, *, user=… | ignore_permissions=True)`:
  рівно одне з двох, інакше `TypeError`; права (`read_predicate`) додаються тут;
- `grunt/store/` — `Store` (протокол), `SqlStore(meta, session)`, `store_for(meta)`;
  `VirtualStore` — контролер дає `rows()`, фільтри/сортування/пошук/права — `evaluate`;
- вузол `Raw(clause)` — `list_filter_extra` (лише SQL; `evaluate` → помилка).

**Порядок:**
- 4a. ✅ (2026-11-07, не закомічено) `Query` + `run` + `SqlStore.fetch/count/aggregate`; на них — `table_list`/`table_count`,
  `grunt.db.get_all/get_value/get_values/exists/count/aggregate`, фасад `grunt.get_all/aggregate`
  (параметр `predicate` у `grunt.db` прибрано). Поведінка не змінюється.
  Зроблено: `grunt/query/{query,run}.py`, `grunt/store/{base,sql,__init__}.py`; `db.api.list_query` /
  `aggregate_query` — `Query` з аргументів `grunt.db`; пошук у списку — `store.sql.search_condition`
  (з `document/query.py`), DSL агрегатів — `store.sql.parse_aggregation/group_field`; вузол `Raw`
  (`list_filter_extra`). `run.*` без `user=`/`ignore_permissions=True` (або з обома) → `TypeError`.
  **Відхилення:** MultiLink-поле в `fields` списку (`get_list`) тепер повертає список назв, як у
  `grunt.db.get_all` (раніше мовчки випадало); `grunt.db.get_all` теж розв'язує рівні значення за `name`.
  `field_years` лишився прямим SQL (`capabilities` — у 4d). Перевірено: ruff, pyright 0;
  SQLite 2081+, PG 2089/0.
- 4b+4c (об'єднано, погоджено 2026-11-07 — без `VirtualStore` методи сховища з контролерів не
  прибрати). **Один клас `Document`, `BaseDocument` зникає**: контролер — хуки й бізнес-логіка,
  сховище оголошує атрибутом `store = BackupStore` (без нього — `SqlStore`; віртуальний без
  store — порожнє сховище). Кроки конвеєра загальні: singleton через `store.count`, формули,
  `fill_route`, вебхуки, індекс пошуку — для всіх; версії, переприв'язка посилань — за `capabilities`.
  `Store`: `get(name, expand)`, `insert(doc, input)`, `update(name, doc, before, input)`,
  `delete(name, before)` — запис повертає збережений документ. `SqlStore` — код `read.py`/`write.py`
  (дочірні таблиці, MultiLink, агрегати); `DocTypeStore(SqlStore)` — запис через registry.
  `VirtualStore`: підклас дає `rows()` (+ за потреби `get/insert/update/delete`); фільтри, сортування,
  пошук і **права** — `evaluate`; `Linked` спершу розв'язується в `In(значення)` запитом через store
  цілі. `_readable_rows` зникає.
  ✅ (2026-11-07, не закомічено). Зроблено:
  - `grunt/store/base.py` — `Store` (база: нічого не зберігає, запис → 405 з `not_supported_message`
    сховища), `capabilities`: `INSERT UPDATE DELETE AGGREGATE REFERENCES HISTORY BULK`; `get / insert /
    update / delete / output / distinct / columns`. `SqlStore` — код колишніх `mixins/read.py` і
    `write.py` (видалені); `update` повертає документ у вигляді `output` (дочірні перечитано).
  - `grunt/store/virtual.py` — `VirtualStore` (`rows(query)`, `search_fields`, `default_sort`),
    `Unavailable` (джерело недосяжне → порожній список з `meta.unavailable_message`), `resolve_linked`,
    `equals(query, field)` — підказка джерелу (період PerfTrend, ім'я ScheduledJob).
  - `store_for(meta)` — `store_class` контролера, інакше `SqlStore` / порожній `Store` (віртуальний).
  - **Один `Document`**, `BaseDocument` прибрано; `load_document` → `store.get` + read formulas;
    конвеєр: `capabilities` перевіряються до хуків, singleton через `store.count`, `fill_route` +
    формули, індекс пошуку, вебхуки — для всіх; версії — `HISTORY`, `replace_with` — `REFERENCES`,
    пакетне видалення — `BULK`, перейменування — `REFERENCES`. `payload.update_values` — значення
    оновлення (спільні для конвеєра й `SqlStore`).
  - Права без таблиці: `read_predicate(user, meta)`; функції прав беруть `columns`, а не `Table`;
    `Meta.columns` (віртуальний — системні + фізичні поля, таблиця не компілюється);
    `filter_expr(filters, columns, meta)`; distinct у `reference_predicates` — `store.distinct`.
  - Списки (`list_documents`/`count_documents`) — один шлях через `run` для всіх сховищ;
    `is_table_backed`, `controller_class(...).get_list`, `_readable_rows`, `grunt/document/in_memory.py` —
    видалено. `doc_guard` і WS-кімната документа читають документ зі сховища (і для віртуальних).
  - Контролери: Backup, BackgroundJob, BackgroundWorker, ScheduledJob, SqlProfilerRequest, PerfTrend,
    SystemHealthReport, Hook → `*Store(VirtualStore)`; DocType → `DocTypeStore(SqlStore)`;
    `translate.TranslatableString` → `TranslatableStringStore`. Skill `grunt-doctypes` переписано.
  **Зміни поведінки:** права віртуальних — предикатом у пам'яті (правило `match` поза SQL-підмножиною
  тепер fail-closed, як для таблиць; раніше — повний simpleeval по рядку, ліміт 5000); віртуальні
  отримали read formulas, підписи Link у списку, проєкцію `fields`, курсорні сторінки; WS-кімната /
  `doc_guard` віртуального документа — перевірка рядка (неіснуючий → відмова).
  Тест: shares на віртуальному DocType (`Linked` через SharedWith → `In`).
  Пошук і порядок віртуальних — **з налаштувань DocType** (`title_field`, `search_fields`,
  `sort_field`/`sort_order`), без атрибутів класу; значення, яких у JSON бракувало, перенесено в JSON
  (BackgroundJob, BackgroundWorker, ScheduledJob, SqlProfilerRequest, Hook, TranslatableString).
  За рев'ю CodeRabbit #98 (3d): конструктор звітів бере поля з сервера —
  `grunt.reports.doctypes.Report.report.fields` → `joins.report_fields` (ті самі правила, що
  `report_source`: без прихованих полів і полів недоступної цілі); застаріла відповідь при швидкій
  зміні DocType більше не перезаписує поля.
  Перевірено: ruff, pyright 0; SQLite 2087/0, PG 2088/0; translate 31, vitest 328, lagoo 20,
  hromada_it 42, opendata 76, crystal_finance 40.
- 4d. ✅ (2026-11-07, не закомічено) Перевірки `capabilities` у точках входу.
  Зроблено: capability `SQL` (рядки — SQL-таблиця: сирі умови, звіти з JOIN, дерева, бакети років,
  сирий запис `grunt.db`, кеш списків) у `SqlStore` і `DocTypeStore`; `supports(meta, cap)` — без
  сесії (атрибут класу). Звіти й дерево без `SQL` → 400 з назвою DocType; `field_years` → `[]`;
  `list_filter_extra` — лише для таблиць; кеш `get_list`/`count` — лише `SQL`; `grunt.aggregate` —
  `AGGREGATE`, колонки з `meta.columns`; `grunt.get_all` для віртуальних тепер з правами.
  `grunt.db`: `get_doc`/`get_single_value` віртуального — зі сховища; сирий запис (`set_value`,
  `delete`, `bulk_update`, `insert_one`, `insert_many`) без `SQL` → 422.
  **Відхилення:** вузол `Search` не потрібен — `VirtualStore` сам виконує пошук (`Query.search`).
  Решта `is_virtual` (схема, CLI, retention, AutoRepeat, ServiceLevel, кошик, посилання на файли,
  health) означає «є своя таблиця в основній базі» — переходить у 4e (`storage`).
  Перевірено: ruff, pyright 0; SQLite 2089/0, PG 2090/0.
- 4e. ✅ (2026-11-07, не закомічено) Поле `storage`, міграція.
  Зроблено: `DocType.storage: "sql" | "virtual"` (типово `sql`) замість `is_virtual`; похідна
  властивість `has_table` (`storage == "sql"`) — нею перевіряють «є своя таблиця» (схема, CLI,
  retention, AutoRepeat, ServiceLevel, MilestoneTracker, кошик, посилання на файли, health, пошук,
  `store_class`, opendata). `is_virtual` на рівні DocType прибрано (на рівні поля — read formula —
  лишився). Форма DocType: Select «Сховище» (`sql`/`virtual`), `depends_on` — від `storage`; JSON ядра
  і `translate` — `"storage": "virtual"`; синхронізований з ядра атрибут — `storage`. Міграція 0019:
  колонка `storage` у таблиці DocType і ключ у збережених визначеннях (`is_virtual` прибрано; стара
  колонка лишається). Перевірено на копії dev2: 292 визначення, 11 віртуальних — ті самі.
  До `grunt migrate` сайт не ламається: модель ігнорує невідомий ключ, атрибути DocType ядра й
  додатків при завантаженні беруться з JSON. Фронтенд: тип `DocType.storage`, `indexHints`.
  Перевірено: ruff, pyright 0; SQLite 2091/0, PG 2092/0; vitest 328; translate 31, lagoo 20,
  hromada_it 42, opendata 76, crystal_finance 40. Тест міграції 0019.

### 5. Connections + UnitOfWork + outbox — ⏳
Іменовані з'єднання сайту (`default`, `replica`, зовнішні), write_intent → маршрутизація
читання/запису. Явний UnitOfWork. Побічні ефекти (індекс пошуку, вебхуки, сповіщення,
push) — через outbox після commit.

Гілка `db-connections` (від `db-store-protocol`), окремий PR.

**Інвентаризація (2026-11-07):**
- вихідні вебхуки — HTTP-запит **усередині транзакції збереження** (таймаут до 10 с кожен,
  послідовно): збереження чекає чужі сервери, SQLite тримає блокування запису, при відкаті вебхук
  уже пішов, повторів немає;
- `.kiq()` посеред транзакції (правила сповіщень, `doc_method`, …): worker може стартувати до commit
  і не побачити документа; після відкату задача все одно виконається;
- web push і realtime-трансляції (workflow, activity) — одразу, до commit;
- «після commit» уже є, але у двох самописних місцях (`cache.bus.after_commit`,
  `email._kick_queue_after_commit`), черга в пам'яті;
- з'єднання: одна база на сайт, replica немає, зовнішніх баз немає.

**Рішення (погоджено 2026-11-07):**
- іменовані з'єднання, replica, `storage: "sql:<alias>"` — **відкладено** до першого реального
  споживача (окремий крок); `write_intent` лишається як є;
- вебхуки — асинхронно через outbox: доставка після commit, з повторами.

**Порядок:**
- 5a. ✅ (2026-11-07, не закомічено) `grunt.db.commit.on_commit(fn, session=, key=)` — один API
  «після commit»: відкат (зовнішньої транзакції) — нічого, відкат savepoint — решта лишається, поза
  транзакцією — одразу; `key` — один виклик на транзакцію; помилка — у лог; `drain()` для тестів.
  На ньому `cache.bus.publish`, очищення `QueryCache`/`DocumentCache`, kick черги листів
  (`bus.after_commit` і `email._kick_queue_after_commit` прибрано). Тести: `tests/test_on_commit.py`.
- 5b. ✅ (2026-11-07, не закомічено) `grunt.enqueue(task, *args, **kwargs)` (`grunt/tasks/enqueue.py`) —
  задача в чергу після commit. Переведено: правила сповіщень (`events`), `grunt.enqueue_doc`,
  запуск імпорту (і гілка без Redis — та сама). Лишились на прямому `.kiq()`: планувальник (чекає
  `kiq` з id журналу) і явні дії користувача без залежності від транзакції (бекап, стиснення
  зображень, хмарні копії) — там помилку брокера має побачити користувач.
  Заодно: імпорти `create_user`/`get_user_by_email`/… — з `grunt.auth.users`, а не через повторний
  експорт у `User/user.py` (Pylance `reportPrivateImportUsage`; ядро, тести, lagoo, crystal_finance,
  inventory).
- 5c. ✅ (2026-11-08, не закомічено) Outbox для вебхуків.
  Зроблено: таблиця `grunt_core_outbox` (`OUTBOX_TABLE` у `SA_METADATA` — створюється `grunt migrate`
  через `create_all`, як `grunt_core_multi_link`); `grunt/outbox.py`: `put(handler, payload)` — рядок у
  поточній транзакції + kick задачі `deliver` після commit (один на транзакцію); `deliver_due` —
  claim рядка (`claimed_until`, 5 хв — упалий запуск відпускає), виклик обробника (функція модуля за
  dotted path), видалення; помилка → `attempts`+1, `due_at` += backoff (30 с · 2ⁿ, до 6 год),
  `last_error`; після `MAX_ATTEMPTS` (8) — `log.error` і рядок прибрано. Планувальник — `deliver`
  щохвилини (повтори, залишки). Вебхуки: `fire()` лише кладе в outbox `deliver_webhook` (назва
  вебхука, подія, тіло на момент події); обробник бере поточні налаштування (вимкнений/видалений —
  пропуск), закриває транзакцію перед HTTP, пише `WebhookLog` кожної спроби й комітить його до
  повтору. «Тестова доставка» лишилась синхронною. Тести: `tests/test_outbox.py` (11, SQLite і PG).
  Вебхуків на dev2/lagoo немає — до `grunt migrate` нічого не впаде.
- 5d. Push і realtime — через `on_commit`.

### 6. Схема — ⏳
Компілятор видає бажану схему, мігратор діалекту її застосовує. Для `ReadOnlySqlStore`
DDL не виконується ніколи.
