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
3. Після схвалення PR зливається merge-комітом. Workflow `release.yml` ставить анотований тег
   `vX.Y.Z` на коміт випуску і публікує GitHub release з розділу `CHANGELOG.md`.

Коміт випуску вже є в `develop`, тож синхронізувати `develop` з `master` не потрібно: тег лишається
в історії `develop`, і версія між тегами (`grunt version`, перевірка сумісності додатків) рахується
від нього. Поки PR випуску не злито й тег не поставлено, наступний `grunt release` відмовить.

Репозиторій без `develop` (додатки): коміт випуску йде в гілку `release/vX.Y.Z`, PR — у `master`.
Тег і GitHub release додатку ставить той самий workflow ядра — у додатку лише виклик:

```yaml
on:
  push:
    branches: [master]
  workflow_dispatch:
jobs:
  release:
    uses: GruntUA/Grunt/.github/workflows/release.yml@develop
    permissions:
      contents: write
```

### Залежності

Щопонеділка workflow `.github/workflows/deps.yml` відкриває (або оновлює) PR
`build(deps): update dependencies` з гілки `deps/weekly` у `develop`: усі npm- і Python-пакети до
найновіших версій, мажорні теж (`npm-check-updates --peer`, `uv lock --upgrade` з підняттям нижніх
меж у `pyproject.toml`), компоненти shadcn-vue з `ui/`, перевстановлені з реєстру, і мажорну версію Node.js у
`mise.toml` та `engines` (CI бере її з `mise.toml`). Мінорну версію Python міняємо свідомо, вручну. В описі PR —
що оновилось і які мажорні версії ще чекають, поки їх дозволять peer-залежності. Запустити
позачергово — Actions → Dependencies → Run workflow.

PR відкриває `GITHUB_TOKEN`, тож CI сам не стартує: **закрити й одразу знову відкрити PR** — тоді
запускаються CI, CodeQL і перевірка заголовка. Зелений — зливаємо squash (у `CHANGELOG.md` —
розділ «Dependencies»); червоний — виправляємо в тій самій гілці. Наступного понеділка workflow
перебудує гілку з `develop`, тож виправлення має потрапити в `develop` до того. Локально
`grunt update` ставить закомічені версії. Dependabot лишився лише для GitHub Actions.

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
