# Code scanning (CodeQL) — план

Живий план. Оновлюється після кожного кроку: що зроблено, що далі, які рішення прийняті.
Новий чат з Claude починає звідси.

**Ціль (2026-11-18):** 0 відкритих алертів у Security → Code scanning для master і develop.
Як і в [IMPORT_CYCLES_PLAN.md](IMPORT_CYCLES_PLAN.md): алерт закриваємо правкою коду;
dismiss («false positive» / «used in tests») — лише останній крок, коли код справді
правильний і переписати його без шкоди не можна, з поясненням у коментарі dismiss.

Оновлено: 2026-11-18 — кроки 1–4 злито (#198, #199, #201, #202, #203, #205); develop: 134 → **19** відкритих (усі — ⏸ нижче). Храповик увімкнено. Далі — переписати код під ⏸.

---

## Стан на старті

- master: **143** відкриті (1 critical, 11 error, 11 high, 14 medium, 16 warning, 90 note);
  109 — у робочому коді, 34 — у тестах.
- develop: **134** — уже закриті #5, #20–22 (request-forgery у `api/docs.ts`, `api/pages.ts`),
  #24–26 (`useListRouteSync.ts`), #28 (`Login.vue`), #29 (`EditorContextMenu.vue`).
  Підуть на master з наступним випуском — окремо не чіпаємо, лише перевірити після випуску.
- Свіжий список: `gh api 'repos/GruntUA/Grunt/code-scanning/alerts?state=open&ref=refs/heads/develop&per_page=100' --paginate`.
- Локальний CodeQL: `~/.local/share/codeql-v2.27.4` (див. пам'ять про lazy-імпорти).

## Кроки

Кожен крок — окрема фіча-гілка → PR у develop. Порядок — за серйозністю.

### 1. Безпека: high / medium у робочому коді ✅ (#198)

PR #198 (злито 2026-11-18), закривається кодом:
#23 (query → лише `field.fieldname` DocType), #6–8 (`__uid` — лічильник), #27 (`event.origin`),
#15 (`/ready` → `"error"`, деталі в лог), #1100 (превʼю: повідомлення Jinja `TemplateError`
екрановане, інші винятки — лише тип + лог), #1 (release.yml `permissions: contents: read`).
Тест: `tests/test_error_detail_exposure.py`.

Не закриваються кодом:
- #12, #13 (`startup/errors.py`) — трейс віддається лише під `if settings.debug`; CodeQL цю
  гілку не бачить → dismiss «won't fix» з поясненням (після злиття, коли перевіримо, що
  алерти лишились саме ці).
- #16 / #1126 (`api_key_service.py`) — це Permissions 7c ф.2 (прибрати SHA-256 після
  перехешування ключів), окремо тут не робимо.


| # | Правило | Де | Що зробити |
|---|---|---|---|
| 23 | js/remote-property-injection | `frontend/src/core/composables/useFormInitialization.ts:79` | ключі з query/route — білий список полів DocType або `Object.create(null)`/`Map`; відкидати `__proto__`, `constructor` |
| 6–8 | js/insecure-randomness | `frontend/src/components/fields/Table/useTableRows.ts:22,42,57` | `__uid` — лише ключ рядка, не секрет. Fallback `Math.random()` замінити на лічильник (`r${++seq}`) — алерт зникне без dismiss |
| 16 | py/weak-sensitive-data-hashing | `grunt/auth/api_key_service.py:50` | SHA-256 від 256-бітного випадкового ключа — криптографічно достатньо, але CodeQL вимагає KDF. Варіант: HMAC-SHA256 з секретом сайту (`hmac.new(secret, key, sha256)`) — сильніше (витік БД не дає перевіряти ключі офлайн) і закриває алерт. Потребує міграції/перехешування → обговорити |
| 27 | js/missing-origin-check | `public/sw.js:56` | у `message` перевіряти `event.origin === self.location.origin` (або `event.source` — клієнт цього SW) |
| 1100, 15, 12, 13 | py/stack-trace-exposure | `api/v1/document/export.py:286`, `api/v1/health.py:53`, `startup/errors.py:126,238` | не віддавати `str(exc)` клієнту: у відповідь — загальний текст/код, деталі — у `grunt.log`. Для `errors.py` — трейс лише в dev-режимі, перевірити, чи CodeQL бачить гілку |
| 1 | actions/missing-workflow-permissions | `.github/workflows/release.yml:11` | явний `permissions:` (мінімум; `contents: write` лише там, де треба) |

### 2. Справжні баги: error / warning у робочому коді ✅ (#199, решта ⏸)

PR #199 (злито 2026-11-18). Справжніх багів не знайшлося:
- #102–111 — CodeQL не розуміє `match` (захоплення в `case`, `case _`) і PEP 695 (`type X = …`,
  `def f[T]`). Виключати запити в `codeql.yml` **не будемо** (рішення власника) — ⏸ пізніше
  подумати, як переписати код. Поки що: pyright `reportPossiblyUnbound` і
  `reportUnsupportedDunderAll` → error у `pyrightconfig.json`; `html.py` спрощено (dict замість `match`).
- #92, #93 — `return None` після `async with track_progress` досяжний (менеджер гасить
  `TaskCancelledError` у джобі); переписано на `result = None … return result`, тест на скасований
  плановий бекап.
- #1077 — явний `DocumentList.__eq__` (рівність як у списку, `meta` не входить).
- #30–37 — Jinja-шаблони без `<script>`: JS-екстрактор CodeQL читає `{{ }}` як JavaScript.
  `paths-ignore` не робимо — ⏸ разом із #102–111 подумати про переписування.
- Заодно: `methods.generated.d.ts` відстав від ядра (`test_core_registry_is_up_to_date` падав на develop).


| # | Правило | Де |
|---|---|---|
| 102–108 | py/uninitialized-local-variable | `io/exporters/html.py:92,93`, `query/compile_sql.py:103`, `query/evaluate.py:113`, `query/nodes.py:167`, `scripting/server_script.py:104`, `store/virtual.py:40` |
| 109–111 | py/undefined-export | `db/schema/changes.py:117`, `query/nodes.py:189,191` — у `__all__` ім'я, якого нема |
| 1077 | py/missing-equals | `document/document_list.py:6` — підклас з атрибутами без `__eq__` |
| 92, 93 | py/unreachable-statement | `backups/tasks.py:107`, `storage/tasks.py:40` |
| 30–37 | js/call-to-non-callable, js/implicit-operand-conversion | Jinja-шаблони `email/templates/*.html`, `io/exporters/templates/list_export.html` — CodeQL парсить `{{ }}` як JS. Спершу глянути, чи там справді inline-`<script>`; якщо ні — винести JS у окремий блок/файл або перебудувати вираз, dismiss — лише якщо інакше ніяк |

Кожен uninitialized/undefined-export — перевірити, чи це реальний `NameError`/`UnboundLocalError`
на якійсь гілці; якщо так — тест на цю гілку.

### 3. Тести й CI ✅ (#201; workflow-пункти — у #198)

| # | Правило | Де | Що зробити |
|---|---|---|---|
| ~~2–4~~ ✅ у кроці 1 | actions/missing-workflow-permissions | `.github/workflows/test.yml:19,44,100` | `permissions: contents: read` на рівні workflow |
| ~~18, 19~~ ✅ у кроці 1 (setup-uv → SHA v7.6.0) | actions/unpinned-tag | `test.yml:26,75` | закріпити сторонні actions на SHA (з коментарем-версією) |
| 9 | py/reflective-xss | `tests/test_app_static_mount.py:52` | екранувати / повертати `PlainTextResponse` у тестовому застосунку |
| 65 | py/jinja2/autoescape-false | `tests/test_error_pages.py:30` | `autoescape=select_autoescape()` або `True` |
| 94–98 | py/unreachable-statement | `test_perf_stats.py`, `test_progress.py` |
| 87–90 | py/ineffectual-statement | `test_mcp.py`, `test_multi_worker.py`, `test_websocket.py` |
| 288–302, 1061, 1104–1108, 121 | import-and-import-from, repeated-import | тести — один стиль імпорту на модуль |
| 129–131 | py/unused-import | тести |

### 4. Шум: note у робочому коді ✅ (#202, #203)

- #202: `grunt.utils.aio.cancel_and_wait()` замість п'яти копій cancel+suppress+await (за рев'ю
  CodeRabbit — не ковтає скасування самого викликача); docstring замість `...` в `@overload`;
  без прапорців через `global` (`functools.cache`, обробник логів за назвою, кеш i18n — кортеж,
  `local.in_bootstrap()`); справжні типи в `cast()`; коментарі в порожніх `except`;
  `docs.ts` кодує `doctype`/id (#5).
- #203: клієнтські скрипти DocType пишуть хуки як `export function on_load(frm)` — executor
  прибирає `export`; старий формат працює. Застосунки (hrm 13, inventory 4, letter 3, ua_tools 3,
  mlt_portal 2, …) переводяться разом із наступним `required_grunt`.
- #205 (з рев'ю #202): назви документів можуть містити `/` — `{doc_id:path}` у REST і WS.
- Нові алерти від правок за рев'ю (#1127 `test_aio.py`, #1128 `extract.py`) — закрито окремим PR.

Початковий опис кроку:


- **py/ineffectual-statement (24)** — `cache/bus.py`, `db/api.py`, `document/api.py`,
  `document/mixins/lifecycle.py`, `progress.py`, `startup/lifespan.py`, `storage/backends.py`,
  `tasks/scheduler.py`, `tasks/worker.py`. Імовірно `...` у тілах Protocol/overload або голі
  вирази — розібрати шаблон один раз, далі масово.
- **js/unused-local-variable (28)** — `grunt/*/doctypes/*/*.js` (клієнтські скрипти DocType):
  невикористані параметри/деструктуризація. Можливо, спільна причина — сигнатура хука
  `(frm, doc)` з невикористаним аргументом → `_`-префікс або прибрати.
- **py/unused-import (6)** — `apps/consumers.py`, `document/bulk_ops.py`, `print/filters.py`,
  `reports/engine.py`, `search/terms.py`, `storage/remote.py`. Перевірити, чи це не
  ре-експорт (тоді — `__all__`).
- **py/unused-global-variable (6)** — `migrations/0026…:59`, `document/pipeline.py:93`,
  `events.py:64`, `i18n/extract.py:72`, `local.py:28`, `logging_config.py:221`.
- **py/empty-except (3)** — `activity/__init__.py:167`, `scripting/file_scripts.py:302`,
  `utils/http.py:25` — коментар-причина або `contextlib.suppress`.
- **py/import-and-import-from** — `bootstrap_site.py:3`.

## Відкладено ⏸ (19 на develop, 2026-11-18)

| Алерти | Чому відкрито | Що далі |
|---|---|---|
| #102, #103, #106–108 py/uninitialized-local-variable | CodeQL не розуміє захоплення в `match`/`case` і `def f[T]` (PEP 695) | придумати переписування без шкоди для читабельності; виключень у `codeql.yml` не робимо (рішення власника) |
| #109–111 py/undefined-export | `type X = …` (PEP 695) у `__all__` | те саме |
| #30–37 js/* у Jinja-шаблонах | JS-екстрактор читає `{{ }}` як JavaScript (шаблони без `<script>`) | те саме |
| #12, #13 py/stack-trace-exposure | трейс лише під `settings.debug`, CodeQL гілку не бачить | рішення власника: dismiss чи переписати |
| #1126 py/weak-sensitive-data-hashing | SHA-256 ключів API | Permissions 7c ф.2 |

### 5. Храповик ✅ (2026-11-18)

Ruleset **«CodeQL ratchet»** (id 27547399) на `develop` і `master`: правило «Require code scanning
results», CodeQL, обидва пороги `all` — PR, що додає будь-який новий алерт, не зливається.
Наявні відкриті алерти злиттю не заважають. Обхід — роль admin (`grunt release` комітить у master
напряму). Перевірити/змінити: `gh api repos/GruntUA/Grunt/rulesets/27547399`.

## Рішення

- 2026-11-18: жодних виключень у `codeql.yml` (`query-filters`, `paths-ignore`) — алерти закриваємо переписуванням коду; хибні на `match`/PEP 695 і Jinja відкладено.
- 2026-11-18: `__uid` рядків Table — лічильник модуля, не `crypto.randomUUID`: це лише ключ, і на http-origin `randomUUID` нема.
- 2026-11-18: превʼю друку показує автору текст помилки Jinja (його власний шаблон), а для інших винятків — лише тип; `str(exc)` іде в лог.
- 2026-11-18: сторонні actions — на SHA з коментарем-версією; `actions/*` лишаються на тегах (CodeQL їх не позначає).
