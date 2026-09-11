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
| 2.1 | 💡 | **Chart-widgets на Dashboard** | Типи: лінійний, стовпчастий, кругова діаграма, gauge, KPI-картка. Конфігурація через DocType `DashboardWidget`, дані — через Report або прямий запит. Chart.js вже є в залежностях. |
| 2.2 | 💡 | **Візуальний Query Builder** | Drag-and-drop конструктор запитів для Query Reports — вибір полів, умов, групування — без SQL. Генерує SQLAlchemy-запит у фоні. |
| 2.3 | 💡 | **Scheduled Report Delivery** | Запуск звіту за розкладом (cron) → генерація XLSX/PDF → відправка на список email. Конфігурація через DocType `ReportSchedule`. |
| 2.4 | 💡 | **Drill-down у звітах** | Клік на рядок/стовпець у зведеному звіті відкриває деталізований список документів, що стоять за цифрою. |
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
| 4.2 | 💡 | **OAuth-провайдери** | Логін через Google, Microsoft, GitHub. Таблиця `OAuthProvider` у Studio, backend через `authlib`. Partial implementation вже є. |
| 4.3 | 💡 | **REST API Connector** | DocType `ApiConnector` — конфігурація зовнішнього REST API (base URL, auth, headers). `grunt.call_api("MyConnector", "/endpoint", data)` у Server Scripts. |
| 4.4 | 💡 | **Zapier / Make (n8n) webhooks** | Incoming webhook endpoint `/api/v1/webhook/{token}` → виконує Server Script або створює документ. Дозволяє підключити будь-який no-code інструмент. |
| 4.5 | 💡 | **S3-compatible storage UI** | Сторінка конфігурації файлового сховища (local / S3 / MinIO) з тест-кнопкою. Зараз конфігурується тільки через env. |

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
| 6.6 | 💡 | **Inline edit у ListView** | Подвійний клік на комірку таблиці — редагування на місці без відкриття форми. Для полів типу Text, Select, Check. |
| 6.7 | 💡 | **DocType Playground** | Сторінка в Studio де можна протестувати DocType: заповнити форму, побачити згенерований JSON, перевірити API. |
| 6.8 | 💡 | **Типізовані проксі для полів у контролері (через реєстр)** | `register_field_type` отримує новий параметр `proxy_factory: Callable[[options, value], Any] \| None`. `Document.__getattr__` перевіряє реєстр і автоматично обгортає значення — без жодних знань фреймворку про конкретні типи. Приклад: Link реєструє `LinkProxy` з `__await__` → `str(self.parent_kved)` = `"KVED-001"` (зворотна сумісність), `kved = await self.parent_kved` → повний Document, `kved.name_uk` → значення. Пряме `self.parent_kved.name_uk` без await неможливе (async DB). Для окремих полів лінкованого документа краще використовувати існуючий механізм `fetch_from`. Аналогічно Table → `TableRowProxy`. Передумова: синхронний in-memory кеш мети DocType (fieldname → fieldtype + options) для використання в `__getattr__`. |

---

## 7. Мобільний / PWA

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 7.1 | 💡 | **Offline-first форма** | Service Worker кешує остання відкриті документи. При відсутності мережі — дає читати/редагувати, синхронізує при поновленні. |
| 7.2 | 💡 | **Push Notifications (PWA)** | Web Push API: підписка через браузер, відправка через `grunt.notify()`. WebPush модуль вже є, треба підключити до Notification flow. |
| 7.3 | 💡 | **Mobile-first ListView** | На малих екранах замість таблиці — картки з ключовими полями (як у мобільних CRM). Автоматично за breakpoint. |
| 7.4 | 💡 | **Scan to fill** | Кнопка сканування QR/barcode у мобільній формі для полів типу `Barcode`. Використовує camera API браузера. |

---

## 8. Безпека і відповідність

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 8.1 | 💡 | **2FA Enforcement Policy** | Системна настройка `require_2fa_for_roles: [Admin, Manager]` — при логіні без 2FA переадресовує на setup. MFA-код вже є, треба policy. |
| 8.2 | ✅ | **Audit Log Diff UI** | Сторінка `ActivityLog` показує не просто "Update", а конкретно які поля змінилися і з якого на яке значення (diff). |
| 8.3 | 💡 | **Data Retention Rules** | DocType `RetentionPolicy`: автоматичне видалення/архівування документів старших N днів. Запускається через Scheduled Job. |
| 8.4 | 💡 | **IP Allowlist** | Обмеження входу за IP-адресою для окремих ролей. Конфігурується в `Role` або `SystemSettings`. |
| 8.5 | ✅ | **Session management** | Реалізовано: `UserSession` DocType (таблиця `grunt_core_user_session`), сесія створюється при логіні, завершується при logout. API: whitelisted methods `grunt.auth.doctypes.UserSession.user_session.list_my_sessions` / `revoke_my_session` через `/api/v1/method/*`. Frontend: `/profile` — сторінка з картками сесій (IP, браузер, ОС, остання активність, завершення). Посилання у DeskTopBar. |

---

## 9. Екосистема

| # | Статус | Ідея | Опис |
|---|--------|------|------|
| 9.1 | 💡 | **App Marketplace** | Каталог готових grunt-apps (CRM, HR, Склад) з встановленням через `grunt install-app <url>`. |
| 9.2 | ✅ | **grunt scaffold** | Реалізовано: `grunt doctype scaffold MyName` — генерує `.json` + `.py` controller + JavaScript client script за шаблоном. |
| 9.3 | 💡 | **VS Code Extension** | Підсвічування JSON-схеми DocType, автодоповнення fieldtype/options, команда "Open in Studio". |
| 9.4 | 💡 | **DocType Import/Export** | Експорт DocType (і його даних-фікстур) в ZIP → імпорт на іншому сайті. `grunt export-doctype MyApp` / `grunt import-doctype myapp.zip`. |
| 9.5 | 💡 | **Grunt DevTools (браузерне розширення)** | Панель для відлагодження: поточний DocType, активні WebSocket-підписки, останні API-запити, SQL-запити поточної сторінки. |
