# Як ми працюємо

## Гілки

- **`master`** — лише випуски. Кожен випуск — анотований тег `vX.Y.Z` на `master`.
- **`develop`** — інтеграційна гілка: усі зміни потрапляють сюди через pull request.
- **Фіча-гілки** — від `develop`, одна на логічний крок (`db-schema`, `fix-webhook-retry`, …).

## Pull request

- Один PR — один завершений крок, який можна переглянути за раз: **до ~40 файлів**. CodeRabbit
  безкоштовно рецензує PR лише до 100 файлів, тож великий крок ріжемо на кілька PR. Рев'ю PR у
  `develop` вмикає `.coderabbit.yaml`.
- Заголовок — у форматі [Conventional Commits](https://www.conventionalcommits.org/):
  `feat(store): VirtualStore для віртуальних DocType`, `fix(schema): …`, `docs: …`.
  Типи: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`; зламаний API —
  `feat(store)!: …`.
- Фіча-PR зливається в `develop` **squash-ом**: заголовок PR стає заголовком коміту, а з цих комітів
  `grunt release` збирає `CHANGELOG.md` по розділах. Виняток — синхронізація `develop` з `master`
  після випуску (див. нижче).
- Перед злиттям: CI зелений (ruff, pyright, pytest на SQLite і PostgreSQL, vitest + vue-tsc),
  коментарі CodeRabbit оброблені — виправлено або пояснено, чому ні.
- В описі PR — що змінилось і що потрібно при розгортанні (міграції, `grunt migrate`, нові
  налаштування).

## Випуск

1. Коли в `develop` зібраний завершений набір змін — PR `develop → master` зі списком змін і
   нотатками розгортання.
2. Після схвалення — злиття (merge-коміт, історія `develop` зберігається).
3. На `master`: `grunt release <patch|minor|major|X.Y.Z>` — розділ у `CHANGELOG.md` (нові міграції
   бази перелічуються окремо), коміт `chore(release): vX.Y.Z` і анотований тег. Спершу —
   `grunt release <bump> --dry-run`.
4. `git push --follow-tags` — workflow `release.yml` проганяє CI і публікує GitHub release.
5. `develop` синхронізується з `master` **merge-комітом**, не squash-ем: тоді тег випуску лишається
   в історії `develop`, і версія між тегами (`grunt version`, перевірка сумісності додатків)
   рахується від нього, а коміт із `CHANGELOG.md` є й у `develop`.

### Версії

До 1.0: **minor** — нові можливості й зміни API, що ламають сумісність; **patch** — виправлення.
Між тегами версія — наступний patch як dev-збірка (`0.2.1.dev3+gabc1234`, див. `grunt version`).

### Розгортання випуску

На кожному сайті після оновлення коду: спершу `grunt migrate --dry-run --site <сайт>` — план змін
таблиць DocType, нічого не змінює; потім `grunt migrate --site <сайт>`. Без `--site` команда
проходить усі сайти бенчу.

Перегляд показує не все: міграції Alembic (`grunt/db/migrations/versions/`, у випуску вони
перелічені в `CHANGELOG.md`) і змінені JSON DocType встановлених додатків застосовуються лише
справжнім `grunt migrate` — їх переглядайте окремо.
