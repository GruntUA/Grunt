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
  Заголовок PR у `develop` перевіряє CI (`.github/workflows/pr-title.yml`).
- Фіча-PR зливається в `develop` **squash-ом**: заголовок PR стає заголовком коміту, а з цих комітів
  `grunt release` збирає `CHANGELOG.md` по розділах. Виняток — синхронізація `develop` з `master`
  після випуску (див. нижче).
- Перед злиттям: CI зелений (ruff, pyright, pytest на SQLite і PostgreSQL, vitest + vue-tsc),
  коментарі CodeRabbit оброблені — виправлено або пояснено, чому ні.
- В описі PR — що змінилось і що потрібно при розгортанні (міграції, `grunt migrate`, нові
  налаштування).

## Випуск

1. `grunt release --dry-run` — розділ `CHANGELOG.md` і нотатки розгортання для `origin/develop`.
   Версію визначають коміти (`auto`): є `feat` або зламаний API (`!`) — **minor**, лише
   виправлення — **patch**; явно — `grunt release <patch|minor|major|X.Y.Z>`.
2. `grunt release` — у тимчасовому worktree (власна копія `apps/grunt` не змінюється): коміт
   `chore(release): vX.Y.Z` з новим розділом `CHANGELOG.md` (нові міграції бази перелічуються
   окремо), push у `develop` і PR `develop → master` з нотатками розгортання (міграції,
   `grunt migrate`, перезапуск worker для нових DocType, змінені залежності).
   З `--deps` спершу оновлюються lock-файли в межах діапазонів `pyproject.toml` /
   `package.json` (`uv lock --upgrade`, `npm update`) — окремим PR у `develop`
   (`build(deps): …`, у `CHANGELOG.md` — розділ «Dependencies»), який `grunt release` зливає,
   щойно його CI зелений; червоний CI зупиняє випуск. Мажорні версії так не приходять — їх оновлює
   `grunt upgrade` окремим PR.
3. Після схвалення PR зливається merge-комітом. Workflow `release.yml` ставить анотований тег
   `vX.Y.Z` на коміт випуску і публікує GitHub release з розділу `CHANGELOG.md`.

Коміт випуску вже є в `develop`, тож синхронізувати `develop` з `master` не потрібно: тег лишається
в історії `develop`, і версія між тегами (`grunt version`, перевірка сумісності додатків) рахується
від нього. Поки PR випуску не злито й тег не поставлено, наступний `grunt release` відмовить.

Репозиторій без `develop` (додатки): коміт випуску йде в гілку `release/vX.Y.Z`, PR — у `master`.

Мажорні версії залежностей — щопонеділка PR від Dependabot у `develop` (`.github/dependabot.yml`;
пакети `@tiptap/*` — одним PR). Зелений CI — зливаємо як звичайний PR; червоний — виправляємо в
тій самій гілці або закриваємо, і Dependabot більше не пропонує цю версію.

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
