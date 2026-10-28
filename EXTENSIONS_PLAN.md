# Розширення додатків — план

Живий план. Оновлюється після кожного кроку: що зроблено, що далі, які рішення прийняті.
Новий чат з Claude починає звідси.

**Мета:** додаток може не мати своєї позиції в списку додатків, а розширювати інший —
пунктами меню, полями й поведінкою його DocType — і чисто зніматися з сайту.
**Пілот:** Crystal Finance виноситься з `inventory` в окремий додаток `apps/crystal_finance`.

Оновлено: 2026-10-28 (етап 4)

---

## Рішення

- **Одна одиниця — додаток.** Окремого типу «плагін» і окремого завантажувача немає:
  розширення — звичайний додаток у `apps/` (версії, залежності, `grunt app install/uninstall`),
  відрізняється лише маніфестом.
- **Crystal Finance — окремий додаток** (2026-10-26): сайт без Crystal не повинен мати
  його таблиць, cron і пунктів меню.
- **Внески в меню пишуться в БД з власником** (`source_app`), а не збираються при читанні:
  ролі, лічильники, `count_filters` уже працюють на рядках `WorkspaceSidebarItem`.
- **Порядок — якорями `after`/`before`**, не числовими `sequence` (кілька розширень
  в одну секцію інакше конфліктують). Якір не знайдено → в кінець секції.
- **Порядок рахується при читанні** (`order_menu` в `AppMenu/app_menu.py`), у БД `idx`
  лишається порядком у фікстурі свого додатка (2026-10-26): база перезаписує свої рядки
  на кожному `migrate`, і перенумеровані позиції внесків одразу б застарівали.
  Кілька розширень в одному меню — в порядку назв додатків.
- **Поля розширення — файлові** (`<module>/doctype_ext/<DocType>.json`), ефективне
  визначення = базовий JSON ⊕ розширення встановлених додатків у порядку залежностей.
- **Спершу подумати про окремий DocType з Link** на базовий (як `CrystalFinanceItemAsset`);
  поле в чужій таблиці — лише коли воно потрібне у фільтрах/колонках списку бази.

## Що є зараз (2026-10-26)

Точки розширення в `hooks.py` ([apps/consumers.py](grunt/apps/consumers.py)):
`doc_events` (багато додатків, пріоритет), `doctype_overrides` (`add_fields`),
`override_doctype_class` (один переможець), `doctype_js`, `doc_actions`, `sidebar_sections`,
`scheduler_events`, `write_guards` тощо.

Проблеми:

1. **Меню не можна розширити.** `_replace_sidebar` ([startup/workspaces.py](grunt/startup/workspaces.py))
   на кожному `migrate` видаляє і перезаписує всі пункти AppMenu — внесок іншого додатка
   затирається. `_auto_seed_workspace` створює AppMenu кожному додатку без фікстури.
2. **`doctype_overrides` для DocType додатків, схоже, не працює** (за кодом, тестом не перевірено):
   у `migrate` ([cli/db.py](grunt/cli/db.py)) `apply_doctype_overrides` іде до
   `register_installed_app_doctypes`; той бачить різницю «збережене (з полями) ≠ JSON» і
   перезаписує з JSON — поля зникають з метаданих, і так щоразу. Працює для DocType ядра.
3. У `add_fields` немає `insert_after` (місця на формі), власника поля (uninstall не прибирає,
   колізії не видно), зміни властивостей наявних полів.
4. Злите визначення зберігається в БД → збереження базового DocType у Studio
   (`export_doctype_files`) запише чужі поля в JSON базового додатка.
5. `override_doctype_class`: другий додаток мовчки затирає першого (`_overrides.update`).
6. Uninstall (`_delete_workspace_and_registration`, [cli/app.py](grunt/cli/app.py)) знає лише
   власний AppMenu додатка.

---

## Маніфест

```toml
# apps/crystal_finance/pyproject.toml
[tool.grunt]
title = "Crystal Finance"
depends_on = ["inventory"]
extends = ["inventory"]   # вносить меню/поля в inventory; означає й depends_on
workspace = false         # без своєї позиції в списку; за замовчуванням false, якщо є extends
adopts = ["CrystalFinanceItem", "..."]  # DocType, що переходять від іншого додатка (крок 4)
```

## Етап 1 — внески в меню

- [x] `read_manifest`: ключі `extends`, `workspace` (default `not extends`); `extends` додається в `depends_on`.
- [x] Без власного AppMenu для `workspace = false` (`_seed_app_workspace_from_registry` пропускає).
- [x] Поля `source_app`, `anchor_after`, `anchor_before` у `WorkspaceSidebarItem` і `WorkspaceSection` (порожній `source_app` = власник AppMenu).
- [x] `_replace_rows`: видаляє й вставляє лише рядки свого `source_app`.
- [x] Фікстура-внесок: запис AppMenu з `extends` замість `name` (`_apply_menu_contribution`),
      у пунктах і секціях `after` / `before` (пункт — `link_to` або label, секція — назва секції).
- [x] Порядок при читанні — `order_menu` у `_workspace_to_dict` (див. рішення).
- [x] Uninstall: видалити рядки `source_app = X` в чужих AppMenu (і показати їх у плані видалення).
- [x] Дашборди: `Page.app` — власник сторінки; перемикач дашбордів додатка показує й сторінки
      додатків, що його `extends` (`_dashboards` → `manifest.extenders`, кеш на процес).
      Uninstall прибирає стандартні записи додатка (`app` = він) і записи з його фікстур у
      DocType зі `standard_records` (Page, Report, PrintFormat, ...) — напряму через БД, з
      дочірніми рядками, бо `delete_doc` у dev-режимі видалив би й теки записів у файлах додатка.
- [x] Тести: `tests/unit/test_menu_contributions.py`, `tests/test_app_manifest.py::TestExtends`.
- [x] Документація: `docs/guide/create-app.md` → «Extending another app».

## Етап 2 — поля DocType

- [x] `DocField.source_app`, `DocField.insert_after` (+ TS-тип `DocField`).
- [x] Файли `<module>/doctype_ext/<DocType>.json` — `{"fields": [...]}`, DocType = назва файлу
      (`grunt/metadata/extensions.py`).
- [x] Злиття (`apply_extensions`) **до** порівняння зі збереженим: `_register_app_doctypes` для
      DocType додатків, `load_core_doctypes(extensions=...)` для ядра (у `_inject_core` поля
      розширень замінюються цілком з файлу, поля знятих розширень зникають, поля з Studio лишаються).
      Порядок розширень — `installed_apps` (залежності першими).
- [x] Колізії: `fieldname` уже є в базі або в іншому розширенні → `doctype_ext.field_collision`, поле пропущено.
      Перевірки префікса немає — лише вимога в документації.
- [x] Studio: `export_doctype_files` вирізає чужі поля (`without_extensions`); `registry.update`
      повертає `source_app`, якщо редактор надіслав поле без нього.
- [x] Uninstall: поля `source_app = X` з чужих DocType прибираються, колонки видаляються
      (спершу індекси — SQLite не видаляє проіндексовану колонку). З `--keep-data` поля йдуть
      на наступному `migrate`, колонки лишаються.
- [x] `doctype_overrides` у `hooks.py` **прибрано** (а не лишено сумісним): ним ніхто не користувався,
      а `grunt migrate` у CLI взагалі не завантажує `hooks.py` зовнішніх додатків, тож для них він
      ніколи не працював. `apply_doctype_overrides` / `DOCTYPE_OVERRIDES` видалено.
- [x] Тести: `tests/test_doctype_ext.py` (9). Документація: `docs/guide/create-app.md`.
- [ ] Відкладено: `properties` (зміна властивостей наявних полів, як Property Setter) і режим
      «Customize» в Studio, що пише в `doctype_ext/` власника поля. Для пілота CF не потрібні.

## Етап 3 — поведінка

- [x] `doctype_mixins = {"Asset": ["crystal_finance.asset.AssetCF"]}` у `hooks.py`
      (`DocumentRegistry.register_mixins`): при першому `get()` реєстр будує
      `type("Asset", (*mixins, Asset), {})`, мікcин пізніше завантаженого додатка першим;
      DocType без контролера отримує мікcини поверх `Document`; пізня реєстрація перескладає клас.
      Зламаний шлях / не клас / конфлікт MRO → `log.error`, мікcин пропущено.
- [x] `override_doctype_class` від другого додатка на той самий DocType → `document.override_conflict`,
      лишається перший. Мікcини діють і поверх override.
- [x] `grunt.get_doc(Клас, name)` повертає зареєстрований контролер, якщо він підклас переданого
      (раніше створював екземпляр переданого класу напряму, повз реєстр).
- [x] Тести: `tests/test_doctype_mixins.py` (7). Документація: `docs/guide/create-app.md` →
      «Extending another app's behaviour» (таблиця точок розширення).

## Етап 4 — пілот: Crystal Finance окремим додатком

- [x] `adopts` у маніфесті: `_register_app_doctypes` передає DocType від додатка з `depends_on`
      (`startup.app_doctype_adopted`); якщо при цьому змінилась би назва таблиці — відмова
      (`startup.app_doctype_adopt_table_changed`). CF DocType мають `module/app = crystal_finance`
      і явний `table_name = grunt_inventory_crystal_finance_*` — дані не рухаються.
- [x] `apps/crystal_finance` (окремий git, без коміту): модулі без префікса `cf_` —
      `client` (cf), `replica` (crystal_finance), `cards`, `contracts`, `docs`, `extra`, `history`,
      `settings`, `sync`, `bundle` (cfsync_bundle); `cfsync/` (Go), DocType `CrystalFinance*`, тести.
      Дії: `crystal_finance.sync_now / create_contract / refresh_log`; cron `crystal_finance.tasks.crystal_finance_sync`.
- [x] Меню: `fixtures/00_menu.json` (`extends: inventory`, секція після «Агенти», налаштування після
      `InventorySettings`). Дашборд: окрема сторінка `crystal-finance` (`app = inventory`) з 8 CF-віджетами.
- [x] Поля `Asset.cf_item/cf_card/cf_card_status`, `Contract.cf_contract`, `AssetMovementHistory.cf_move` →
      `crystal_finance/doctype_ext/`.
- [x] Поведінка — мікcини `AssetFinance` (звірка, історія, `after_split`, «Рух активу») і
      `ContractFinance` (реквізити з Crystal). Inventory відкрив точки розширення в `Asset`:
      `after_split`, `movement_summary`, `movement_cells`, `movement_extra`.
- [x] Inventory без CF: жодного імпорту/поля/пункту; `movement.clean_row` переносить усі поля рядка,
      крім службових (раніше — білий список із `cf_move`). Тести inventory (28) проходять без CF.
- [x] hrm: `PayrollKind` ліниво імпортує `crystal_finance.replica.upsert_rows`.
- [x] Харнес тестів додатків (`testkit.make_app_fixtures`) застосовує `doctype_ext/`.
- [x] dev2: бекап `backups/grunt-before-cf-app-20261028.db`, `grunt app install crystal_finance`,
      усі 15 лічильників (таблиці CF, заповнені `cf_*`) до/після збігаються, два `migrate` поспіль без змін.
- [ ] cfsync `-push` (лише ручні відправки): URL тепер `/api/v1/app/crystal_finance/...`. Новий exe
      збереться при наступному «cfsync (.zip)», на сервер CF його кладуть вручну; pull не зачеплено.
- [x] Сторінка `crystal-finance` — `app = crystal_finance` (на dev2 виправлено напряму, фікстура без `sync`).
      План uninstall CF на dev2 (без виконання): 10 DocType, 5 полів у чужих DocType, ця сторінка,
      9 пунктів і 1 секція меню.

## Журнал

- 2026-10-26 — огляд ядра, план; рішення: CF окремим додатком.
- 2026-10-26 — етап 1 (крім дашбордів): `extends`/`workspace`, `source_app` і якорі в меню,
  фікстура-внесок, `order_menu`, uninstall. `migrate` на dev2: колонки додано, 171 пункт меню
  без змін. Повний набір тестів ядра проходить (`test_multi_worker` падає лише з `-n 4`:
  спільний канал Redis між воркерами, окремо проходить).
  Каталоги перекладів: `grunt i18n extract` переписує їх на тисячі рядків (давно не
  регенерувались) — нові рядки додано вручну в кінець.
- 2026-10-26 — етап 2. Тест підтвердив флапання: `apply_doctype_overrides` додавав поле, синк
  з JSON його прибирав — на кожному `migrate`. Тепер злиття до порівняння; на dev2 два `migrate`
  поспіль без жодного оновлення DocType. Повний набір тестів ядра проходить (крім того самого
  `test_multi_worker` з `-n 4`).
- 2026-10-28 — етап 3: `doctype_mixins`, конфлікт `override_doctype_class`, `get_doc(Клас)` через реєстр.
  Тести ядра (1453) та inventory (62) проходять.
- 2026-10-28 — етап 4: CF перенесено в `apps/crystal_finance` і встановлено на dev2 без втрати даних.
  Тести: ядро 1456, inventory 28, crystal_finance 35, hrm 7. `grunt serve` стежить лише за каталогами
  додатків, що були на старті, — після встановлення нового додатка його треба перезапустити.
- 2026-10-28 — сторінки розширень: власник у `Page.app`, перемикач за `extends`, uninstall прибирає
  записи, які додаток поставив у DocType ядра (раніше не прибирав жодних — і не лише в розширень).

## Наступний крок

Пілот завершено. Відкриті хвости: відкладені `properties` / «Customize» з етапу 2, новий
cfsync.exe для `-push`.
