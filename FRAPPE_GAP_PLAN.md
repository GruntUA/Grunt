# Ґрунт vs Frappe — розриви у функціоналі

> Порівняння з `frappe/frappe@develop` (листопад 2026): 338 доктайпів Frappe проти ~95 у ядрі ґрунту.
> Для 55 пар однакових доктайпів порівняно поля JSON і метадані (`grunt/metadata/field.py`, `doctype.py`).
> Відсортовано за корисністю для фреймворку (найкорисніше — вгорі). Кожен пункт обговорюємо по черзі.
>
> Статуси: ❓ обговорити · ✅ робимо · ⏸ пізніше · ❌ не робимо · ✔️ зроблено
>
> Свідомо не розглядаємо: AI-модуль Frappe (`flow/*`, `studio_ai_*`) — без AI в ядрі; `docstatus`/Submit/Cancel/Amend —
> прибрано міграцією 0006, стани веде Workflow. Вже мають відповідник: Web Form/Web Page/Website (додаток cms),
> Auto Email Report (розсилка в Report), Number Card/Dashboard Chart (PageWidget), Log Settings (`retention_days`),
> Recorder (SQL-профайлер, автоіндекси #113), Bulk Update, Deleted Document, Milestone, Reminder, SLA, Translation (додаток translate).

## Зведення

| # | Пункт | Статус |
|---|-------|--------|
| 1 | Умовний «лише читання» поля (`read_only_depends_on`) + полагодити `mandatory_depends_on` | ✅ |
| 2 | Права `export` / `import` / `print` / `share` у DocPermission + полагодити `report` | ✔️ (PERMISSIONS 2b) |
| 3 | Поля «лише читання» для ролі (`readonly_fields`) + закрити діри `hidden_fields` | ✅ |
| 4 | `set_only_once`, `no_copy`, `allow_duplicate` | ✅ |
| 5 | Точність (`precision`) і метод округлення чисел | ✅ |
| 6 | Налаштування списку на сервері (колонки, фільтри, спільні пресети) | ✅ |
| 7 | Permission Inspector («чому користувач бачить/не бачить документ») | ❓ |
| 8 | Permission Log + Access Log (аудит прав, експорту, друку) | ❓ |
| 9 | AssignmentRule: Round Robin / Load Balancing / за полем, зняття призначення | ❓ |
| 10 | NotificationRule: PDF у вкладенні, зміна поля після сповіщення, зсув у хвилинах | ❓ |
| 11 | Role Profile / Module Profile, `desk_access`, `home_page`, `disabled` у Role | ❓ |
| 12 | User Group | ❓ |
| 13 | Вхідна пошта → документ (`append_to`), автовідповідь, підпис, «без відповіді N хв» | ❓ |
| 14 | OAuth для Gmail / Microsoft 365 в EmailAccount | ❓ |
| 15 | EmailQueue: відкладене надсилання, пріоритет, повтори, відписка | ❓ |
| 16 | Prepared Report + підсумковий рядок, ролі, тайм-аут у Report | ❓ |
| 17 | Document Naming Rule (серія нумерації за умовою) | ❓ |
| 18 | Налаштування сповіщень користувача (канали за типами, дайджест) | ❓ |
| 19 | Workflow: заборона самопогодження, дії при переході, вхідні «на погодження», кілька workflow | ❓ |
| 20 | Політика входу: надійність/строк пароля, одна сесія, години входу, IP користувача, лише SSO | ❓ |
| 21 | Вкладення: `max_attachments`, `protect_attached_files`, `force_private_attachments` | ❓ |
| 22 | Print Format Builder + параметри сторінки | ❓ |
| 23 | Raw printing (ZPL / ESC-POS) для етикеток | ❓ |
| 24 | OutgoingWebhook: тіло за шаблоном, метод, динамічний URL, повтори | ❓ |
| 25 | ServerScript: rate limit для API, тип Permission Query | ❓ |
| 26 | DataImport: мапінг значень, журнал пропущених рядків, роздільник, Google Sheets | ❓ |
| 27 | Automation Flow (візуальні ланцюжки «тригер → дії») | ❓ |
| 28 | Contact + Address з прив’язкою до кількох документів | ❓ |
| 29 | Event (події з учасниками, повтором) + синхронізація календаря | ❓ |
| 30 | LDAP / Active Directory | ❓ |
| 31 | OAuth Provider (ґрунт як SSO для інших систем) | ❓ |
| 32 | Connected App + Integration Request (закриває IDEAS 4.3 ApiConnector) | ❓ |
| 33 | Kanban Board як збережена дошка | ❓ |
| 34 | Маскування значень полів (`mask`) | ❓ |
| 35 | Дрібні властивості DocField | ❓ |
| 36 | Дрібні властивості DocType | ❓ |
| 37 | EmailTemplate прив’язаний до DocType | ❓ |
| 38 | AutoRepeat: лист із PDF, дні тижня, документ на кожного виконавця | ❓ |
| 39 | ActivityLog: входи/виходи з IP; Comment `published`/`seen` | ❓ |
| 40 | SharedWith: право ділитися далі, «для всіх», лист; UserPermission `hide_descendants` | ❓ |
| 41 | Запити на вивантаження/видалення персональних даних | ❓ |
| 42 | Package / Package Release (перенесення налаштувань між сайтами) | ❓ |
| 43 | FormTour: позиції, умовні кроки, тури поза формою | ❓ |
| 44 | LetterHead з картинки, розміри, вирівнювання | ❓ |
| 45 | SMS Settings + SMS Log | ❓ |
| 46 | Note (оголошення з «прочитали») і Success Action | ❓ |
| 47 | Дрібні налаштування системи | ❓ |
| 48 | Address Template за країною | ❓ |
| 49 | DuckDB sync (аналітична копія для важких звітів) | ❓ |

---

## Деталі

### 1. Умовний «лише читання» поля
**Статус:** ❓
- **Frappe:** `DocField.read_only_depends_on` — вираз, за яким поле стає лише для читання.
- **Ґрунт зараз:** `read_only` (постійно), `depends_on` (показ), `mandatory_depends_on` (обов’язковість). Умовного read-only немає.
- **Навіщо:** типовий сценарій «після погодження сума не змінюється», «поле редагує лише до певного статусу» — без клієнтських скриптів.
- **Знахідка:** `mandatory_depends_on` оголошено (`field.py`, Studio), але ніде не застосовується — ні у формі, ні на сервері.
- **Рішення (09.11):** ✅ робимо як у Frappe:
  - нове поле `read_only_depends_on` (метадані, DocField, Studio) + робочий `mandatory_depends_on`;
  - обчислення **лише на клієнті** тим самим `evalDependsOn`; сервер ці умови не перевіряє;
  - новий документ окремо не обробляємо: якщо поле має бути доступне при першому створенні, розробник сам пише це в умові (напр. `eval:!doc.__islocal && doc.status == 'Approved'` — точну ознаку нового документа уточнити при реалізації).

### 2. Права export / import / print / email / share
**Статус:** ❓
- **Frappe:** окремі прапорці в DocPerm: `export`, `import`, `print`, `email`, `share`.
- **Ґрунт зараз:** `read select write create delete report` + `match`, `hidden_fields`. Експорт фактично прив’язаний до `report`/read.
- **Навіщо:** держустановам потрібно «бачить, але не вивантажує / не друкує / не ділиться».
- **Знахідка:** прапорець `report` є в DocPermission, але ніде не перевіряється (його немає навіть у `PermissionAction`). Експорт (`export_csv`, `export_file`) і друк (`print`) вимагають лише read; поширення — write на документ.
- **Рішення (09.11):** ✅ робимо:
  - нові прапорці `export`, `import`, `print`, `share` + `report` у `PermissionAction`, перевірка на сервері, кнопки ховати через `__perms`;
  - `email` — не зараз, повернемося разом із п.13 (надсилання листа з документа в ґрунті немає);
  - **без міграції сумісності:** нові прапорці типово вимкнені, права в ролях налаштовуються наново (ґрунтом користується лише власник);
  - `share` вимагає ще й `write` (не можна поширенням видати «Запис», якого сам не маєш) — погоджено.

### 3. Рівні доступу до полів (permlevel)
**Статус:** ❓
- **Frappe:** `DocField.permlevel` + рядки DocPerm на рівнях 1..9: група полів, яку роль може читати, але не змінювати (або не бачити).
- **Ґрунт зараз:** `DocPermission.hidden_fields` — лише сховати поле від ролі.
- **Навіщо:** «бухгалтер бачить зарплату, але змінює лише кадровик».
- **Знахідки (діри в `hidden_fields`):**
  - приховане поле можна записати: `save_doc` / `new_doc` (`grunt/app/document_api.py`) лише вирізають його з відповіді;
  - за прихованим полем можна фільтрувати/сортувати в `get_list` (`aggregate` це вже забороняє) — значення вгадується фільтрами `field__gt=…`.
- **Рішення (09.11):** ✅ робимо, без переходу на permlevel:
  - `DocPermission.readonly_fields` поруч із `hidden_fields`; правило кількох рядків як у `hidden_fields` — поле лише для читання, якщо так кажуть усі рядки ролей користувача, що дають `write`;
  - перевірка **на сервері**: зміна такого поля → 403; при **створенні** документа (з правом `create`) значення приймається;
  - у формі поле недоступне — `readonly_fields` у `__perms`;
  - заодно закрити обидві діри: заборонити запис прихованих полів і фільтр/сортування за ними в `get_list`.

### 4. set_only_once, no_copy, allow_copy
**Статус:** ❓
- **Frappe:** `set_only_once` — поле не змінюється після першого збереження; `no_copy` — не переноситься при дублюванні; `DocType.allow_copy` — вимикає «Дублювати».
- **Ґрунт зараз:** немає.
- **Навіщо:** номери, дати реєстрації, унікальні коди не мають копіюватися/змінюватися.
- **Зараз:** дублювання суто клієнтське (`useFormActions.ts` → `handleDuplicate`), відкидає `PROTECTED_DUPLICATE_FIELDS` і поле стану workflow.
- **Рішення (09.11):** ✅ робимо:
  - `no_copy` — властивість поля (метадані, Studio); при дублюванні не копіюється, і в рядках дочірніх таблиць. `unique` поля й поле назви **автоматично не виключаємо** — оператор перейменує сам;
  - `set_only_once` — після збереження непорожнього значення змінювати не можна; перевірка на клієнті **і на сервері**;
  - `DocType.allow_duplicate` (типово увімкнено) — вимкнений ховає «Дублювати»; серверної перевірки не треба;
  - `PROTECTED_DUPLICATE_FIELDS` лишається, але береться зі спільного джерела — `STANDARD_COLUMNS` (`grunt/metadata/compiler.py`): у списку зараз застаріле `updated_at` замість `modified_at`, а `workflow_state` дублює обробку поля стану.

### 5. Формати чисел і точність
**Статус:** ❓
- **Frappe:** `DocField.precision`, `non_negative`; SystemSettings `number_format`, `float_precision`, `currency_precision`, `rounding_method`, `time_format`, `first_day_of_the_week`; Currency `fraction`, `fraction_units`, `smallest_currency_fraction_value`, `number_format`, `symbol_on_right`; Language — формати дати/чисел, перший день тижня.
- **Ґрунт зараз:** `date_format` у SystemSettings, `decimal_places` у Currency.
- **Навіщо:** коректне округлення сум, відображення за локаллю.
- **Зараз:** Currency — `Numeric(18,2)`, округлення Python `round()` (банківське + похибка float: `round(0.125,2)=0.12`, `round(1.005,2)=1.0`); на клієнті `Math.round(n*100)/100`. Float — `Double`, до 10 знаків. Розділювачі й символ валюти — з мови через `Intl`. `min_value`/`max_value` перевіряються на сервері.
- **Рішення (09.11):** ✅ робимо:
  - `SystemSettings.rounding_method` — налаштування (опенсорс: різним країнам/галузям потрібне різне): комерційне (half-up) і банківське (half-even); рахувати через `Decimal`, однаково на сервері й клієнті. Типове значення — уточнити при реалізації (пропозиція: комерційне);
  - `precision` для Float, Currency, Percent: показ + округлення при збереженні; для Currency колонка `Numeric(18, precision)` (типово 2), тобто зміна precision = зміна колонки (міграція схеми);
  - **не робимо:** `non_negative` (= `min_value: 0`), `number_format`, `symbol_on_right`, `fraction_units` — покриває `Intl` за мовою;
  - перший день тижня брати з мови (`uk` → понеділок); перевірити, чи `Calendar.vue` зараз не починає з неділі (не задано `weekStartsOn`).

### 6. Налаштування списку на сервері
**Статус:** ❓
- **Frappe:** List View Settings, List Filter — збережені на сервері, з можливістю поділитися.
- **Ґрунт зараз:** колонки та пресети фільтрів у `localStorage` (`useListColumns.ts`, `FilterBar.vue`) — не переходять між пристроями, ними не поділитися.
- **Навіщо:** користувач працює з кількох пристроїв; керівник налаштовує вигляд для відділу.
- **Зараз у `localStorage`:** колонки (`useListColumns.ts`, його ж читає `useMapPopupFields.ts`), сортування/групування (`useListViewState.ts`), швидкі фільтри (`useQuickFilterPrefs.ts`), пресети фільтрів (`FilterBar.vue`), налаштування «Звіту» (`useReportModel.ts`), недавні документи (`recentDocs.ts`), дерево, бічна панель.
- **Рішення (09.11):** ✅ робимо:
  - `UserViewSettings` (користувач + DocType + вигляд → JSON): колонки, сортування/групування, швидкі фільтри, налаштування «Звіту»; клієнт читає разом із метаданими, пише з debounce, `localStorage` — лише кеш;
  - `SavedFilter`: назва, DocType, фільтри, власник, спільний доступ — **нікому / ролям / всім** (окремим користувачам — ні, поки що); власник змінює/видаляє, інші лише застосовують;
  - «Зберегти як типове для всіх» (право змінювати DocType) → зберігається **в DocType** (експортується у файл додатка, як `default_view`/`sort_field`); «Скинути» повертає до типового;
  - **недавні документи — на сервер** (спільні для всіх пристроїв);
  - локально лишаються розгорнуті вузли дерева, ширина/стан бічної панелі.

### 7. Permission Inspector
**Статус:** ❓
- **Frappe:** форма «користувач + DocType + документ + дія» → пояснення, які правила дали/забрали доступ.
- **Ґрунт зараз:** немає; доступ складається з ролей, `match`, UserPermission, shares, `inherit_permission_from` — розбиратися важко.
- **Навіщо:** підтримка та налагодження прав.
- **Рішення:** —

### 8. Permission Log + Access Log
**Статус:** ❓
- **Frappe:** Permission Log — хто і коли змінив ролі/права/UserPermission; Access Log — хто експортував, друкував, завантажував дані.
- **Ґрунт зараз:** ActivityLog/DocVersion для документів; окремого аудиту прав і доступу до даних немає.
- **Навіщо:** персональні дані, вимоги держсектору.
- **Рішення:** —

### 9. AssignmentRule
**Статус:** ❓
- **Frappe:** правило Round Robin / Load Balancing / Based on Field, список користувачів, ваги (`weighted_users`), `unassign_condition`, `close_condition`, дні тижня, `due_date_based_on`, пріоритет правил.
- **Ґрунт зараз:** фільтри + одна роль або один користувач.
- **Навіщо:** розподіл звернень/заявок між виконавцями без скриптів.
- **Рішення:** —

### 10. NotificationRule
**Статус:** ❓
- **Frappe:** `attach_print` + `print_format`, `attach_files`, `set_property_after_alert`, `send_to_all_assignees`, вибір відправника, `minutes_offset` для Datetime, канал «вебхук» (Slack/Teams-подібний), подія «Method».
- **Ґрунт зараз:** події після створення/збереження/переходу/зміни значення, днів до/після; канали system/email.
- **Навіщо:** «надіслати контрагенту PDF документа», «нагадати за 30 хв до події».
- **Рішення:** —

### 11. Role Profile / Module Profile, властивості Role
**Статус:** ❓
- **Frappe:** Role Profile — набір ролей, який призначається користувачу; Module Profile / `block_modules` — приховати модулі; Role `desk_access`, `home_page`, `disabled`.
- **Ґрунт зараз:** ролі призначаються поштучно; Role має `require_mfa`, `allowed_ips`.
- **Навіщо:** швидке заведення типових користувачів, чистіший інтерфейс.
- **Рішення:** —

### 12. User Group
**Статус:** ❓
- **Frappe:** групи користувачів, які можна вказувати в призначеннях, сповіщеннях, Link-полях.
- **Ґрунт зараз:** лише ролі.
- **Навіщо:** «надіслати відділу», «призначити групі» без створення ролі під кожен відділ.
- **Рішення:** —

### 13. Вхідна пошта → документ, можливості EmailAccount
**Статус:** ❓
- **Frappe:** `append_to` + `DocType.email_append_to/sender_field/subject_field` — вхідний лист створює або доповнює документ; автовідповідь, підпис, футер, `notify_if_unreplied`, IMAP-теки, `always_bcc`, Reply-To, рахунок за замовчуванням для вхідних/вихідних.
- **Ґрунт зараз:** SMTP/IMAP, EmailMessage з `ref_doctype/ref_name`.
- **Навіщо:** звернення громадян, заявки сервісу, листування з контрагентами.
- **Рішення:** —

### 14. OAuth для Gmail / Microsoft 365
**Статус:** ❓
- **Frappe:** EmailAccount → Connected App (OAuth2 XOAUTH2).
- **Ґрунт зараз:** паролі застосунків.
- **Навіщо:** M365 вимкнув basic auth, Google обмежує паролі застосунків.
- **Рішення:** —

### 15. EmailQueue
**Статус:** ❓
- **Frappe:** `send_after`, `priority`, `retry`, посилання відписки (`add_unsubscribe_link`, Email Unsubscribe), `expose_recipients`, `show_as_cc`.
- **Ґрунт зараз:** черга з базовими полями.
- **Рішення:** —

### 16. Prepared Report та Report
**Статус:** ❓
- **Frappe:** Prepared Report — звіт рахується у фоні, користувач отримує збережений результат; Report `add_total_row`, `roles`, `disabled`, `timeout`, `reference_report`.
- **Ґрунт зараз:** звіти рахуються синхронно.
- **Рішення:** —

### 17. Document Naming Rule
**Статус:** ❓
- **Frappe:** правило іменування з умовами та пріоритетом (різні серії для різних підрозділів/типів).
- **Ґрунт зараз:** `autoname` + NamingSeries на DocType.
- **Рішення:** —

### 18. Налаштування сповіщень користувача
**Статус:** ❓
- **Frappe:** Notification Settings / Notification Type Preference — увімкнути/вимкнути пошту та системні сповіщення за типом, дайджест, автостеження за створеними/коментованими/призначеними документами.
- **Ґрунт зараз:** немає персональних налаштувань.
- **Рішення:** —

### 19. Workflow
**Статус:** ❓
- **Frappe:** `allow_self_approval`, `enable_action_confirmation`, `transition_tasks` (дії при переході), `next_action_email_template`, повідомлення стану, кілька workflow на DocType з умовою/пріоритетом, Workflow Action — вхідні «очікує мого погодження».
- **Ґрунт зараз:** стани, переходи з ролями, умовою, коментарем, `prompt_fields`, сповіщеннями; `update_field/update_value` у стані.
- **Рішення:** —

### 20. Політика входу
**Статус:** ❓
- **Frappe:** оцінка надійності пароля (zxcvbn), примусова зміна раз на N днів, `deny_multiple_sessions`, `simultaneous_sessions`, `login_after/before`, IP на користувача, вхід за username/телефоном, `disable_user_pass_login`, `logout_on_password_reset`.
- **Ґрунт зараз:** правила складності пароля, блокування за спробами, MFA, IP на роль, passkeys, вхід за посиланням.
- **Рішення:** —

### 21. Вкладення
**Статус:** ❓
- **Frappe:** `DocType.max_attachments`, `protect_attached_files` (не можна видалити), `force_private_attachments`, `make_attachments_public`.
- **Ґрунт зараз:** `public_attachments`.
- **Рішення:** —

### 22. Print Format Builder
**Статус:** ❓
- **Frappe:** візуальний конструктор друкованої форми (поля, секції, таблиці), поля сторінки, розмір паперу, шрифт, мова друку, ролі, друковані форми для звітів; Print Settings, Print Style.
- **Ґрунт зараз:** Jinja-шаблон + LetterHead.
- **Рішення:** —

### 23. Raw printing
**Статус:** ❓
- **Frappe:** `raw_printing` + `raw_commands`, Network Printer Settings.
- **Ґрунт зараз:** немає.
- **Навіщо:** етикетки inventory напряму на термопринтер.
- **Рішення:** —

### 24. OutgoingWebhook
**Статус:** ❓
- **Frappe:** `request_structure` (form/json), `webhook_json` (Jinja), `webhook_data` (вибір полів), `request_method`, `is_dynamic_url`, `max_retries`, черга.
- **Ґрунт зараз:** подія, URL, секрет, заголовки, умова, тайм-аут.
- **Рішення:** —

### 25. ServerScript
**Статус:** ❓
- **Frappe:** `enable_rate_limit` для API-скриптів; тип Permission Query (умова доступу до списку).
- **Ґрунт зараз:** типи DocType Event / API / Scheduler Event.
- **Рішення:** —

### 26. DataImport
**Статус:** ❓
- **Frappe:** `value_mappings`, журнал пропущених рядків, шаблон з попередженнями, імпорт із Google Sheets, вибір роздільника/sniffer, `mute_emails`.
- **Ґрунт зараз:** мапінг колонок, insert/update, dry run, журнал помилок.
- **Рішення:** —

### 27. Automation Flow
**Статус:** ❓
- **Frappe (новинка develop):** Automation Flow / Action / Trigger Queue / Run / Run Step — візуальний ланцюжок «тригер → умови → дії» з журналом виконання.
- **Ґрунт зараз:** ServerScript, NotificationRule, OutgoingWebhook, AssignmentRule — окремо.
- **Рішення:** —

### 28. Contact + Address
**Статус:** ❓
- **Frappe:** Contact (кілька email/телефонів), Address з `links` (Dynamic Link до кількох документів), `is_primary`, `is_shipping`.
- **Ґрунт зараз:** Address без зв’язків; контрагенти дублюються в додатках (inventory, letter).
- **Рішення:** —

### 29. Event
**Статус:** ❓
- **Frappe:** Event (учасники, повтор, нагадування, приватність) + синхронізація з Google Calendar.
- **Ґрунт зараз:** календарний вигляд для будь-якого DocType, Reminder.
- **Рішення:** —

### 30. LDAP / Active Directory
**Статус:** ❓
- **Frappe:** LDAP Settings + мапінг груп на ролі.
- **Ґрунт зараз:** OIDC, WebAuthn.
- **Рішення:** —

### 31. OAuth Provider
**Статус:** ❓
- **Frappe:** OAuth Client, Scope, Authorization Code, Bearer Token — фреймворк як сервер авторизації.
- **Ґрунт зараз:** лише клієнт OIDC.
- **Рішення:** —

### 32. Connected App + Integration Request
**Статус:** ❓
- **Frappe:** OAuth-підключення до зовнішніх сервісів, Token Cache, журнал вихідних інтеграційних запитів.
- **Ґрунт зараз:** немає (IDEAS 4.3 ApiConnector — 💡).
- **Рішення:** —

### 33. Kanban Board
**Статус:** ❓
- **Frappe:** збережена дошка з власними колонками, порядком, фільтрами, полями картки.
- **Ґрунт зараз:** kanban за `kanban_column_field` DocType.
- **Рішення:** —

### 34. Маскування значень
**Статус:** ❓
- **Frappe:** `DocField.mask` + `DocPerm.mask` — значення показується як `****1234` для ролей без права бачити повністю.
- **Ґрунт зараз:** лише повне приховування (`hidden_fields`).
- **Рішення:** —

### 35. Дрібні властивості DocField
**Статус:** ❓
- `fetch_if_empty`, `remember_last_selected_value`, `print_hide`, `print_hide_if_no_value`, `print_width`, `report_hide`, `sort_options`, `documentation_url`, `show_on_timeline`, `hide_seconds`/`hide_days` (Duration), `make_attachment_public`.
- **Рішення:** —

### 36. Дрібні властивості DocType
**Статус:** ❓
- `queue_in_background` (збереження у фоні), `show_title_field_in_link`, `default_print_format`, `default_email_template`, `grid_page_length`, `rows_threshold_for_grid_search`, `allow_import`.
- **Рішення:** —

### 37. EmailTemplate для DocType
**Статус:** ❓
- **Frappe:** `reference_doctype` — у формі пропонуються лише доречні шаблони.
- **Рішення:** —

### 38. AutoRepeat
**Статус:** ❓
- **Frappe:** надсилання створеного документа поштою з PDF, `repeat_on_days` (дні тижня), `submit_on_creation`, документ на кожного виконавця.
- **Рішення:** —

### 39. ActivityLog і Comment
**Статус:** ❓
- **Frappe:** ActivityLog фіксує входи/виходи з IP і статусом Success/Failed; Comment `published`, `seen`.
- **Ґрунт зараз:** UserSessionLogin (перевірити, чи покриває невдалі спроби).
- **Рішення:** —

### 40. SharedWith і UserPermission
**Статус:** ❓
- **Frappe:** DocShare `share` (ділитися далі), `everyone`, `notify_by_email`; UserPermission `hide_descendants`.
- **Рішення:** —

### 41. Персональні дані
**Статус:** ❓
- **Frappe:** Personal Data Download Request / Deletion Request з етапами.
- **Рішення:** —

### 42. Package / Package Release
**Статус:** ❓
- **Frappe:** пакування DocType, скриптів, записів у пакет і імпорт на іншому сайті.
- **Ґрунт зараз:** додатки + fixtures; IDEAS 9.1 Marketplace — 💡.
- **Рішення:** —

### 43. FormTour
**Статус:** ❓
- **Frappe:** позиція підказки, умовний перехід, поля дочірніх таблиць, `next_on_click`, тури по сторінках/звітах/дашбордах.
- **Ґрунт зараз:** кроки з полем або елементом.
- **Рішення:** —

### 44. LetterHead
**Статус:** ❓
- **Frappe:** шапка/підвал з картинки з розмірами і вирівнюванням, скрипти, CSS, бланк для звітів.
- **Ґрунт зараз:** логотип + Jinja-шапка/підвал.
- **Рішення:** —

### 45. SMS
**Статус:** ❓
- **Frappe:** SMS Settings (довільний HTTP-шлюз з параметрами), SMS Log; OTP по SMS.
- **Рішення:** —

### 46. Note і Success Action
**Статус:** ❓
- **Frappe:** Note — оголошення з «хто прочитав», показ при вході; Success Action — підказка з наступними кроками після першого збереження.
- **Рішення:** —

### 47. Дрібні налаштування системи
**Статус:** ❓
- `max_file_size`, видалення EXIF, шифрування бекапів, `max_report_rows`, попередження про зовнішні посилання, `dormant_days`, `allow_guests_to_upload_files`, шаблони вітального листа / скидання пароля.
- **Рішення:** —

### 48. Address Template
**Статус:** ❓
- **Frappe:** Jinja-шаблон відображення адреси за країною.
- **Рішення:** —

### 49. DuckDB sync
**Статус:** ❓
- **Frappe (новинка develop):** DuckDB Sync — аналітична копія вибраних таблиць для важких звітів.
- **Рішення:** —
