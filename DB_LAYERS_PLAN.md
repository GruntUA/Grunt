# Шари роботи з БД — план

Живий план. Оновлюється після кожного кроку: що зроблено, що далі, які рішення прийняті.
Новий чат з Claude починає звідси.

**Мета:** ядро не знає, на якій СУБД лежить DocType. Відмінності SQLite/Postgres(/MySQL)
зібрані в одному місці, а DocType може зберігатися не лише в SQL-таблиці основної бази
(віртуальний, HTTP-джерело, таблиця в іншій БД) — з тими самими правами, фільтрами й пошуком.

Оновлено: 2026-11-06 (кроки 1–2 готові)

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

Лишилось:
- `write_intent.py` — переїде в крок 5 (маршрутизація читання/запису);
- restore на PG не зберігає поточну базу в `aside` (CodeRabbit, #96) — знімати `pg_dump`
  поточної бази перед `pg_restore`;
- (CodeRabbit, #96) `CREATE INDEX CONCURRENTLY` пошуку, що впав, лишає невалідний індекс —
  `ensure` його пропускає; відрізнити від того, що будується зараз в іншому процесі, і перебудувати;
- (CodeRabbit, #96) MySQL: дубль DocType (`PRIMARY`) у registry не стає 409 — `integrity_violation`
  MySQL не повертає колонку для PK.

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

### 3. `Query` AST — ⏳
`db/filters.py` розбирає вхідні дані в нейтральний `Query`; права (user permissions,
shares, власник) — вузли AST; `SqlStore` компілює в SQLAlchemy. Звіти/Query Builder
(JOIN з правами, IDEAS 2.2) будуються над AST.

### 4. Store protocol — ⏳
`Store` (`get/list/insert/update/delete/aggregate` + `capabilities`). `SqlStore` обгортає
теперішні mixins, віртуальні DocType → `VirtualStore`. Поле DocType
`storage: "sql" | "sql:<alias>" | "virtual" | "http:<connector>"`. Ядро перевіряє
`capabilities` і відповідає 400 замість падіння на SQL.

### 5. Connections + UnitOfWork + outbox — ⏳
Іменовані з'єднання сайту (`default`, `replica`, зовнішні), write_intent → маршрутизація
читання/запису. Явний UnitOfWork. Побічні ефекти (індекс пошуку, вебхуки, сповіщення,
push) — через outbox після commit.

### 6. Схема — ⏳
Компілятор видає бажану схему, мігратор діалекту її застосовує. Для `ReadOnlySqlStore`
DDL не виконується ніколи.
