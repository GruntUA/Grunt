# Шари роботи з БД — план

Живий план. Оновлюється після кожного кроку: що зроблено, що далі, які рішення прийняті.
Новий чат з Claude починає звідси.

**Мета:** ядро не знає, на якій СУБД лежить DocType. Відмінності SQLite/Postgres(/MySQL)
зібрані в одному місці, а DocType може зберігатися не лише в SQL-таблиці основної бази
(віртуальний, HTTP-джерело, таблиця в іншій БД) — з тими самими правами, фільтрами й пошуком.

Оновлено: 2026-11-06 (крок 1 готовий, PostgreSQL у CI блокує)

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

### 1. `grunt/db/dialects/` — 🔨

Зроблено (2026-11-06):
- пакет `grunt/db/dialects/` (`base`, `sqlite`, `postgresql`, `mysql`),
  `dialect_for(obj)` — з рядка, URL, engine, connection, session;
- налаштування engine (pool, PRAGMA, `BEGIN IMMEDIATE`, `uk_sort_key`/`lower`) —
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
- нестабільні тести прав (`test_file_access`, `test_file_references`, `test_mfa_enforcement`,
  `test_offline_sync`) — під навантаженням інколи 403/чужий рядок; розібрати окремо.

### 2. Contract-тести — ⏳
Один набір тестів CRUD/фільтрів/сортування/агрегацій/пошуку, що проганяється на SQLite,
Postgres і фейковому `VirtualStore`. PG у CI — блокує.

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
