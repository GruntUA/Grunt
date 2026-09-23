# Ґрунт — Ідеї для розвитку

> Файл для збору ідей. Не прив'язаний до фаз — тут все, що можна зробити.
> Статуси: 💡 ідея · 🔨 в роботі · ✅ зроблено

---

## 1. Незавершене (почато, але не доведено до кінця)

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 1.1 | ✅ | **Система сповіщень** | `grunt.notify()` і `notify_all()` є заглушками — не створюють записів у БД, не ставлять листи в чергу. Потрібно дописати: збереження Notification-документа, відправка email через чергу, підключення WebPush. |
| 1.2 | ✅ | **Трекінг запланованих завдань** | ScheduledJob має поля `next_run_at`, `last_run_at`, `run_count`, `status`, `last_error` — але вони ніколи не заповнюються. Потрібно оновлювати після кожного виконання та рахувати помилки. |
| 1.3 | ✅ | **msgprint у контексті запиту** | `grunt.msgprint()` зараз логує через structlog. Потрібно: складати повідомлення в чергу поточного запиту й відправляти через WebSocket одним пакетом після відповіді. |
| 1.4 | ✅ | **i18n — повні переклади** | PO/POT інфраструктура повністю реалізована, json-файлів перекладу немає. Frontend завантажує переклади через `/api/v1/translations/{locale}`. `grunt.po` розширено: +60 рядків для auth, documents, permissions, email, files, sessions, jobs, UI. |

---

## 2. Звітність і аналітика

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 2.1 | ✅ | **Chart-widgets на Dashboard** | Реалізовано через віджети `Page` (`PageWidget`): метрики + `chart_area`/`chart_bar`/…, агрегація по DocType з фільтрами. Використовується в home-сторінках (grunt, inventory, letter, translate). |
| 2.2 | 💡 | **Візуальний Query Builder** | Drag-and-drop конструктор запитів для Query Reports — вибір полів, умов, групування — без SQL. Генерує SQLAlchemy-запит у фоні. |
| 2.3 | ✅ | **Scheduled Report Delivery** | Поля на `Report` (секція «Розсилка»): `schedule_frequency` Daily/Weekly/Monthly, `schedule_recipients`, `schedule_filters`, `last_sent_at`. Щоденна задача 07:00 (`grunt/reports/delivery.py`) запускає звіт від імені власника → XLSX-вкладення в `EmailQueue.attachments`. Дія «Надіслати зараз». PDF — ні. |
| 2.4 | ✅ | **Drill-down у звітах** | Згрупований List-звіт повертає `meta.drilldown`; клік на рядок у `ReportView` відкриває список DocType з фільтрами звіту + значеннями групи. |
| 2.5 | ✅ | **Збережені фільтри** | Реалізовано в `FilterBar.vue`: збереження пресетів фільтрів за іменем у localStorage (per-user per-doctype), завантаження та видалення через dropdown меню. |

---

## 3. Collaboration

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 3.1 | ✅ | **@mentions у коментарях** | При введенні `@ім'я` у Comment-полі — dropdown з користувачами. Отримувач отримує сповіщення. Comment DocType вже є, треба додати mention-парсинг і hook. |
| 3.2 | 💡 | **Thread-reply у коментарях** | Можливість відповідати на конкретний коментар. Поле `parent_comment` у Comment, UI рендерить дерево. |
| 3.3 | ✅ | **Document diff (версії)** | Реалізовано: `VersionHistoryPanel.vue` відображає список версій з inline diff (старе → нове значення поля), кнопкою відновлення. Вбудовано у `DocTypeForm.vue` через боковий sidebar. |
| 3.4 | 💡 | **Реакції на коментарі** | Emoji-реакції (👍 ✅ ❓) на коментарях через окрему таблицю `CommentReaction`. Невелика, але дає соціальну динаміку. |
| 3.5 | ✅ | **Гостьовий доступ до документа** | Генерація захищеного посилання на документ для перегляду/підпису зовнішнім користувачем (без логіну в систему). |

---

## 4. Інтеграції

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 4.1 | ✅ | **Webhooks UI** | Сторінка керування вихідними вебхуками: список, тестовий запит, лог останніх доставок (WebhookLog вже є). |
| 4.2 | ✅ | **OAuth-провайдери** | Pluggable auth-провайдери (реєстр + `/api/v1/auth` + `issue_login`): OIDC (`grunt/auth/providers/oauth.py`), WebAuthn/passkey. |
| 4.3 | 💡 | **REST API Connector** | DocType `ApiConnector` — конфігурація зовнішнього REST API (base URL, auth, headers). `grunt.call_api("MyConnector", "/endpoint", data)` у Server Scripts. |
| 4.4 | ✅ | **Zapier / Make (n8n) webhooks** | Реалізовано DocType `IncomingWebhook` (`grunt/webhook/`) з `field_mapping` → створення документа. |
| 4.5 | 🔨 | **S3-compatible storage UI** | Бекенд є (`config.py`: `storage_backend` local/s3, `s3_bucket`/`s3_endpoint_url` для MinIO/R2). Лишилось: UI-конфігурація з тест-кнопкою (зараз лише env). |

---

## 5. Продуктивність і масштаб

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 5.1 | ✅ | **Query-level кешування** | Реалізовано для read-only DocType у `get_list`: in-memory cache + Redis (опційно) з TTL, інвалідація кешу DocType при create/update/delete/bulk/set_value. |
| 5.2 | 💡 | **Read replica підтримка** | Конфігурація `DATABASE_REPLICA_URL` → всі SELECT-запити без транзакції йдуть на репліку. Прозоро через кастомний session factory. |
| 5.3 | ✅ | **N+1 query detector** | Реалізовано в `profiler.py`: якщо один HTTP-запит генерує >N SQL-запитів — виводить `WARNING n1_suspect` у structlog з кількістю запитів і шляхом. Поріг `n1_threshold=10` (змінюється через `PUT /api/v1/dev/profiler/settings`). |
| 5.4 | ✅ | **Пагінація курсором** | Реалізовано keyset pagination для `/api/v1/docs/{doctype}` через опціональний параметр `cursor=`; у `meta` повертається `next_cursor`. |
| 5.5 | ✅ | **Lazy-load зв'язків у формі** | Реалізовано `expand=` для `GET /api/v1/docs/{doctype}/{id}`: можна явно розгортати relation-поля (`Table`, `MultiLink`) лише за потреби. |

---

## 6. UX / DX

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 6.1 | 💡 | **Field Validation Builder** | Візуальний конструктор regex/range валідацій у Studio — без написання JS. Зберігається в `DocField.validation_rule`. |
| 6.2 | ✅ | **Темна тема** | Повністю реалізовано: `useColorMode.ts`, Theme Engine (`/api/v1/theme.css`), per-user theme у `User.theme`, ручний toggle, cross-tab sync, темна варіація кольорів через HEX→HSL. |
| 6.3 | 💡 | **Guided onboarding / Setup Wizard** | При першому запуску — покроковий wizard: назва системи, email SMTP, перший користувач, тестовий DocType. Зменшує поріг входу для нових розробників. |
| 6.4 | ✅ | **Keyboard shortcuts** | Реалізовано в `CommandPalette.vue`: `Ctrl+K` — command palette, `Ctrl+N` — quick create. Форма: `Ctrl+S` — зберегти. |
| 6.5 | ✅ | **Command Palette** | Реалізовано: `CommandPalette.vue` — fuzzy-пошук по DocTypes, документах, workspaces і командах. Групований результат, навігація клавіатурою, quick create, статичні дії. |
| 6.6 | 🔨 | **Inline edit у ListView** | Зроблено у Report-в'юсі: прапорець `DocField.editable_in_grid` + click-to-edit у `ReportGridView.vue`. Лишилось: звичайний ListView. |
| 6.7 | 💡 | **DocType Playground** | Сторінка в Studio де можна протестувати DocType: заповнити форму, побачити згенерований JSON, перевірити API. |
| 6.8 | 💡 | **Типізовані проксі для полів у контролері (через реєстр)** | `register_field_type` отримує новий параметр `proxy_factory: Callable[[options, value], Any] \| None`. `Document.__getattr__` перевіряє реєстр і автоматично обгортає значення — без жодних знань фреймворку про конкретні типи. Приклад: Link реєструє `LinkProxy` з `__await__` → `str(self.parent_kved)` = `"KVED-001"` (зворотна сумісність), `kved = await self.parent_kved` → повний Document, `kved.name_uk` → значення. Пряме `self.parent_kved.name_uk` без await неможливе (async DB). Для окремих полів лінкованого документа краще використовувати існуючий механізм `fetch_from`. Аналогічно Table → `TableRowProxy`. Передумова: синхронний in-memory кеш мети DocType (fieldname → fieldtype + options) для використання в `__getattr__`. |

---

## 7. Мобільний / PWA

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 7.1 | 💡 | **Offline-first форма** | Service Worker кешує остання відкриті документи. При відсутності мережі — дає читати/редагувати, синхронізує при поновленні. |
| 7.2 | ✅ | **Push Notifications (PWA)** | `PushSubscription` + `grunt/webpush/service.py`, підключено до `notification/service.py`; налаштування web-push у `SystemSettings`. |
| 7.3 | ✅ | **Mobile-first ListView** | До 768px список (і згрупований) показується картками `components/views/list/ListCards.vue`: заголовок = `title_field` або перша не-Select/Check колонка, статус-бейдж, до 4 пар «поле: значення» тими самими list-cell компонентами, що й таблиця, чекбокс виділення, позначка track_seen. Брейкпоінт — `useCardLayout.ts`. |
| 7.4 | ✅ | **Scan to fill** | `BarCode.vue`: сканування камерою та з зображення через BarcodeDetector (native або polyfill). |

---

## 8. Безпека і відповідність

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 8.1 | ✅ | **2FA Enforcement Policy** | Прапорець `Role.require_mfa`. `issue_login` для користувача з такою роллю без MFA повертає challenge `mfa_setup_required` + токен `mfa_setup` (без access-токенів); `/mfa-verify` в режимі налаштування: QR → код → резервні коди → вхід (`mfa_enroll_begin`/`mfa_enroll_complete`). `refresh_api` завершує відкриті сесії таких користувачів. |
| 8.2 | ✅ | **Audit Log Diff UI** | Сторінка `ActivityLog` показує не просто "Update", а конкретно які поля змінилися і з якого на яке значення (diff). |
| 8.3 | ✅ | **Data Retention Rules** | `DocType.retention_days` + `retention_date_field` (поля в редакторі DocType; `log_retention_days` перейменовано). Нічна задача `grunt.tasks.retention.purge_expired_documents` (03:00): `is_log` — масовий DELETE (fallback `SystemSettings.log_retention_days` → 30); інші — поштучно через звичайне видалення (кошик, хуки, дочірні), ≤1000/доктайп/ніч, кожне в savepoint. Архівування (замість видалення) — ні. |
| 8.4 | ✅ | **IP Allowlist** | `Role.allowed_ips` (IP/CIDR, по рядку): користувач з такою роллю входить лише з об'єднання дозволених мереж (`issue_login` — усі способи входу; `refresh_api` завершує сесію з іншої адреси). Спільний `grunt/auth/ip_policy.py` (і для ApiKey). `client_ip` довіряє forwarded-заголовкам лише від `settings.trusted_proxies` (loopback) або Cloudflare-edge (`trust_cloudflare`, лише CF-Connecting-IP); rate-limit, вебформи, ApiKey переведено на нього. |
| 8.5 | ✅ | **Session management** | Реалізовано: `UserSession` DocType (таблиця `grunt_core_user_session`), сесія створюється при логіні, завершується при logout. API: whitelisted methods `grunt.auth.doctypes.UserSession.user_session.list_my_sessions` / `revoke_my_session` через `/api/v1/method/*`. Frontend: `/profile` — сторінка з картками сесій (IP, браузер, ОС, остання активність, завершення). Посилання у DeskTopBar. |

---

## 9. Екосистема

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 9.1 | 💡 | **App Marketplace** | Каталог готових grunt-apps (CRM, HR, Склад) з встановленням через `grunt install-app <url>`. |
| 9.2 | ✅ | **grunt scaffold** | Реалізовано: `grunt doctype scaffold MyName` — генерує `.json` + `.py` controller + JavaScript client script за шаблоном. |
| 9.3 | 💡 | **VS Code Extension** | Підсвічування JSON-схеми DocType, автодоповнення fieldtype/options, команда "Open in Studio". |
| 9.4 | ✅ | **DocType Import/Export** | DocType і так пишуться у файли додатка при збереженні (`export_doctype_files`) і синхронізуються при migrate. Для записів-конфігурації: `fixtures = [...]` у `hooks.py` + `grunt fixtures export <app>` → `<module>/fixtures/*.json` з `"sync": true` (loader оновлює наявні записи, коли значення відрізняються). ZIP свідомо не робили — додатки живуть у git. |
| 9.5 | 💡 | **Grunt DevTools (браузерне розширення)** | Панель для відлагодження: поточний DocType, активні WebSocket-підписки, останні API-запити, SQL-запити поточної сторінки. |

---

## 10. Беклог з рев'ю та аудитів

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 10.1 | ✅ | **Централізувати `workspaceUrl()`** | `core/workspaceUrl.ts`: `docUrl(doctype, id?, ws?)` (канонічний `/app/…`, encode, workspace за DocType якщо не задано) + `workspaceUrl(ws, …segments)`; ~45 викликів у ~25 файлах переведено. Alias `/:workspaceName` + редірект у `beforeEach` замінено одним redirect-маршрутом для старих закладок. Виправлено биті `/${doctype}/…` гілки без workspace. |
| 10.2 | 💡 | **Роль вкладки «Поля» в редакторі DocType** | Сира таблиця `DocField` дублює Конструктор. Сховати або генерувати `PropertiesPanel` з метаданих `DocField` замість рукописних секцій. |
| 10.3 | ✅ | **Прибрати мертвий код** | Мертві `docsApi.getSharedWith/getTags/getComments/getBookmark` видалено; дублікатів `apps/grunt/auth|naming` вже не було. `SharedWith` виявився НЕ мертвим — див. 10.9. |
| 10.4 | ✅ | **Доступ до коментарів/тегів/файлів за документом** | Атрибут DocType `inherit_permission_from: [<doctype field>, <id field>]` (Comment, DocTag, File). `grunt/permissions/reference.py`: read/select рядка — лише з read батьківського документа (враховує match, UserPermission, share); списки — `ref_id IN (select name from <батько> з його фільтром)`; створення на нечитаний документ — 403. Неприв'язані рядки (бібліотека файлів) — як раніше. Граматику `match` не розширювали. |
| 10.5 | ✅ | **Підписка на документ (follow)** | DocType `DocFollow` + кнопка «Стежити» в бічній панелі. Сповіщення підписникам (крім автора дії) про зміни (з назвами полів, з `record_update_changes`) і нові коментарі; підписки видаляються разом із документом. Стежити можна лише за тим, що можеш читати. Автопідписки (на автора/коментатора) — ні. |
| 10.6 | 💡 | **Реєстр секцій бічної панелі** | Hook `sidebar_sections` для додатків + серверні `perms` у bundle `get_sidebar`. |
| 10.7 | 💡 | **Table field: залишки аудиту** | Віртуалізація, блокування Save форми при помилках рядків, responsive stack-cards, перф `TableEditRow`. |
| 10.8 | 🔨 | **AttachPicker: залишки** | ✅ Прев'ю: `grunt/storage/thumbnails.py` — WebP 480px для картинок і першої сторінки PDF (pypdfium2, не AGPL) при завантаженні, `File.thumbnail_path`, `get_content(thumb=1)` з тими самими правами/підписом; `grunt files thumbnails` — backfill; бібліотека й FileManager вантажать мініатюри замість оригіналів. Підписані файлові запити мають окремий rate-limit (`rate_limit_files`, 600/хв/IP). Лишилось: віртуалізація сітки, roving-tabindex. |
| 10.9 | ✅ | **Справжній DocShare** | `grunt/permissions/shares.py`: `SharedWith` Read → read/select, Write → +write, лише на цей документ (не create/delete). Fallback у `PermissionChecker.check` (не кешується) + `name IN (shared)` в `apply_permission_filter`. Контролер: ділитися може лише той, хто може писати документ; рядки share бачать отримувач і автор. |
| 10.10 | ✅ | **Приватні вкладення за замовчуванням** | Зроблено: `grunt/storage/signing.py` — `SignedFileURLResponse` (default_response_class) підписує кожен `get_content?file_id=` у JSON (`&exp&sig`, HMAC, 12 год, округлення до години) + HTML друку; `get_content` приймає підпис без токена; підписи знімаються на запис (create/update); `upload` — вкладення (`attached_to_*`) приватні, бібліотека публічна; вебформи й вхідна пошта — приватні. Наявні 45 файлів на живому сайті переведено в приватні (23.09.2026). |
