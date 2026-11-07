# Як ми працюємо

## Гілки

- **`master`** — лише випуски. Кожен випуск — анотований тег `vX.Y.Z` на `master`.
- **`develop`** — інтеграційна гілка: усі зміни потрапляють сюди через pull request.
- **Фіча-гілки** — від `develop`, одна на логічний крок (`db-schema`, `fix-webhook-retry`, …).

## Pull request

- Один PR — один завершений крок, який можна переглянути за раз: **до ~40 файлів**. CodeRabbit
  безкоштовно рецензує PR лише до 100 файлів, тож великий крок ріжемо на кілька PR.
- Заголовок — у форматі [Conventional Commits](https://www.conventionalcommits.org/):
  `feat(store): VirtualStore для віртуальних DocType`, `fix(schema): …`, `docs: …`.
  Типи: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`; зламаний API —
  `feat(store)!: …`.
- PR зливається в `develop` **squash-ом**: заголовок PR стає заголовком коміту, а з цих комітів
  `grunt release` збирає `CHANGELOG.md` по розділах.
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
5. `develop` синхронізується з `master` (коміт із `CHANGELOG.md` має бути і там).

### Версії

До 1.0: **minor** — нові можливості й зміни API, що ламають сумісність; **patch** — виправлення.
Між тегами версія — наступний patch як dev-збірка (`0.2.1.dev3+gabc1234`, див. `grunt version`).

### Розгортання випуску

На кожному сайті після оновлення коду: спершу `grunt migrate --dry-run` (план змін схеми), потім
`grunt migrate`.
