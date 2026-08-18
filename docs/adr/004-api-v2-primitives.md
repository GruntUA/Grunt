# ADR 004: Grunt API v2 — типізовані примітиви для прикладного коду

## Статус

Прийнято (частково впроваджено) — 2026-08-17

---

## Контекст

Ядро Grunt асинхронне й доволі сучасне (contextvars замість thread-locals, типізований
`grunt.get_all[T]` уже існував), але прикладний код проти нього — контролери,
whitelisted-методи — накопичив шаблонний код, який API мав би прибирати сам.

Замість абстрактного порівняння з Frappe, відправною точкою стали чотири реальні
больові точки в `auth/doctypes/User/user.py` (440 рядків, найбільший контролер ядра):

1. **Сесія тягнеться вручну.** П'ять функцій (`get_user_by_email`, `get_user_by_id`,
   `list_users`, `create_user`, `authenticate`) брали `session: AsyncSession`
   параметром і одразу відкривали `grunt.system_context(session)` — хоча контекст уже
   живе в contextvars.
2. **Права на whitelisted-методах — ad hoc, повз RBAC.** `add_role`/`remove_role`/
   `list_users_api` кожен окремо писали `if not user.is_superadmin: throw(...)`, тоді
   як DocType-CRUD уже йде через `permission_checker`/`DocTypePermission`.
3. **Серіалізація копіюється руками.** Той самий набір полів (`name, email, full_name,
   roles, is_superadmin`) вручну збирався в словник тричі з дрібними розбіжностями.
4. **`get_doc` повертає `dict[str, Any]`**, хоча типізований `Document`-контролер із
   анотаціями полів для цього й задуманий — IDE й mypy не бачать поля.

Фреймворк у активній розробці ([[feedback-grunt-framework-changes]]) — рішення:
міняти API v1 напряму, без сумісного шару.

---

## Рішення 1: Типізований `get_doc`/`find_doc`

`grunt.get_doc` отримав overload: рядкове ім'я доктайпу — стара поведінка (`dict`);
клас-контролер — типізований інстанс, побудований напряму з переданого класу (той
самий патерн, що вже використовував `grunt.get_all[T]` — без проходу через
`document_registry`, тому повернений тип гарантовано збігається з переданим класом):

```python
order = await grunt.get_doc(Order, order_id)     # -> Order, typed
order = await grunt.get_doc("Order", order_id)    # -> dict, як і раніше
```

`find_doc(...)` — той самий шлях, але ловить `HTTPException(404)` і повертає `None`
замість прокидання — явна альтернатива для "відсутність документа — очікуваний
випадок", а не одна функція з поведінкою, що вгадується по контексту виклику.

`grunt/app/document_api.py`: `get_doc` — overload + гілка `isinstance(doctype, type)`.
`grunt/__init__.py`: дзеркальний non-`@overload` стаб (у звичайному `.py`-файлі
`@overload` вимагає реальної реалізації-диспетчера — стаб під `TYPE_CHECKING`
виконується як фасад через `__getattr__`, тому тут одна сигнатура з union-типами).

---

## Рішення 2: `Document.objects` — query builder

Тонка fluent-обгортка над тим, що вже існувало (`grunt.get_all`/`grunt.count`/
`grunt.new_doc`, `db.build_clauses` із Django-стилем `__gt/__in/...`) — не нова SQL-логіка:

```python
active = await User.objects.filter(is_active=True).order_by("-created_at").limit(20).all()
user = await User.objects.filter(email=email).first()
user, created = await User.objects.get_or_create(email=email, defaults={...})
```

`grunt/document/queryset.py` (новий файл) + `objects`-дескриптор на `Document`
(`grunt/document/base.py`) — клас-рівневий, не конфліктує з instance-`__getattr__`,
яким `Document` маршрутизує доступ до полів через `self.data`.

**Свідомо не зроблено:** слідування по Link-полях (`.expand("roles")`/`has_many`).
Реальної механіки такого зв'язування зараз немає взагалі (є лише `__label`-ін'єкція
для списків, і то не для одиничного `get_document`) — це найбільша нова підсистема з
усього запропонованого, і поки що не зрозуміло, чи вона взагалі потрібна поза
`User.roles`-подібними випадками. Відкладено до появи другого реального прикладу
використання.

---

## Рішення 3: `@grunt.whitelist(roles=[...], require=predicate)`

```python
@grunt.whitelist(roles=["superadmin"])
async def add_role(user_id: str, role_name: str) -> dict: ...
```

**Важливий нюанс, знайдений тестами, а не спроєктований одразу:** перша версія
зберігала `roles`/`require` як пасивні атрибути функції й перевіряла їх лише в HTTP-
диспетчері (`api/v1/method.py`). Тест `test_list_users_requires_superadmin`, що
викликає `list_users_api()` напряму (без HTTP-шару), показав: прямий виклик повністю
обходив перевірку — старий інлайн-код (`if not user.is_superadmin: throw(...)`) був
насправді надійнішим саме тому, що перевірка йшла *всередині тіла функції*, незалежно
від шляху виклику.

Виправлено: `whitelist()` тепер повертає справжню обгортку, яка читає користувача з
активного grunt-контексту (`require_user()`) і кидає `errors.forbidden()` **на
кожному виклику** — через HTTP-диспетчер чи напряму з іншого Python-коду (хук, тест,
інший whitelisted-метод). Одне джерело правди, немає шляху виклику, що обходить
перевірку.

`grunt/api/context.py: whitelist()`, `grunt/permissions/roles.py: user_has_roles()`
(новий, чистий helper — `user.is_superadmin or будь-яка з roles у user.roles`).

**Свідомо не зроблено:** консолідація з `api/permissions.py: can_read/can_write/...`.
Перша спроба (переписати `_check_doctype_permission` через `permission_checker`)
зламала 9 тестів — виявилось, що `can_read`/`can_write` **навмисно** незалежні від
`permission_checker`: працюють з будь-яким рядковим ім'ям доктайпу через прямий
запит `DocTypePermission`-таблиці, без вимоги, щоб доктайп був зареєстрований у
`doctype_registry` (на відміну від строгого, registry-прив'язаного шляху guarded
CRUD-пайплайна). Це два різні, обидва потрібні дизайни, а не дублювання — відкочено
до оригіналу з поясненням у докстрінгу.

---

## Рішення 4: `Schema.dump()`/`dump_many()`

```python
class UserPublic(Schema):
    fields = ("name", "email", "full_name", "roles", "is_superadmin")

return UserPublic.dump(user)
```

Без магії через анотацію типу повернення — свідомо простіше й менш ризиковано, ніж
автоматична серіалізація за return-type. `grunt/document/schema.py` (новий файл).

**Знахідка з другої міграції (нижче):** `Schema` у цьому вигляді підходить лише для
identity-мапінгу (вихідний ключ = ім'я поля документа). У `File.py` публічна
відповідь перейменовує поля (`file_url` → `url`, `file_name` → `filename`,
`file_size` → `size_bytes`) і по-різному в різних ендпоінтах (`upload()` віддає
`id`, `get_list()` — `name`, для того самого документа) — гомогенізувати під одну
схему означало б тихо змінити вже живий HTTP-контракт. `Schema` там свідомо НЕ
застосований — dict-білдинг лишився ручним. Розширення на aliasing/перейменування
полів — окрема, обґрунтована реальним прикладом задача, а не спекулятивна наперед.

---

## Рішення 5: Контекст без ручного `session`-параметра — але без зайвої елевації

П'ять функцій із `user.py` втратили параметр `session`; читають його через
`require_session()` з ambient contextvar. Це торкнулось ~14 викликів поза `user.py`
(auth-роути, CLI, tasks, assignment-сервіс) — усі оновлені.

Друга ітерація (за фідбеком у процесі): у місцях, де обгортку `async with
grunt.system_context(session): ...` додано **лише** щоб `require_session()` всередині
цих п'яти функцій знайшов сесію — замінено на голий `grunt.context(session)`. Ці
функції самі підіймаються до `SYSTEM_USER` там, де це потрібно (для `User.objects`,
`grunt.new_doc`); зовнішній `system_context` був зайвою, оманливою елевацією, що
нічого не додавала. Залишено `system_context` лише там, де він був **до** цієї
зміни (усталена ідіома файлу для фонових операцій) — не чіпалось за межами того, що
сам додав.

Побічний наслідок: `api/v1/auth/core.py`, `oauth.py`, `password.py` використовували
голий `APIRouter()` — жодного grunt-контексту не було взагалі, обгортки довелось
додавати вручну на кожному виклику. Замість цього `GruntRouter` отримав
`optional_auth: bool = False` — при `True` роутер сам активує ambient-контекст через
`grunt_context_optional` (гостьовий, не вимагає токена) для всіх ендпоінтів роутера;
маршрути, яким усе ж потрібен реальний користувач, зберігають власний
`Depends(current_user)`. Прибрало ручні `async with grunt.context(...)` з тіл
`register`/`login`/`mfa-login`/`forgot-password` повністю.

---

## Наслідки

| Компонент | Файл | Статус |
|---|---|---|
| `Document.objects` (QuerySet) | `document/queryset.py` | новий |
| `Schema` | `document/schema.py` | новий |
| `user_has_roles` | `permissions/roles.py` | новий |
| typed `get_doc`/`find_doc` | `app/document_api.py`, `__init__.py` | розширено |
| `whitelist(roles=, require=)` | `api/context.py`, `api/v1/method.py` | розширено |
| `GruntRouter(optional_auth=)` | `api/router.py` | розширено |
| Референс-переписування 1 | `auth/doctypes/User/user.py` | завершено |
| Референс-переписування 2 | `storage/doctypes/File/file.py` | завершено |
| Тести | `test_queryset.py`, `test_whitelist_roles.py`, `test_file_controller.py` | нові, 18 тестів |

Повний прогін: `ruff check grunt/` чистий, `pytest tests/ grunt/` — 820/820,
`mypy grunt --ignore-missing-imports` — без нових помилок понад ті, що вже існували
в неторкнутих файлах (CI: `continue-on-error`).

### Друга міграція: `storage/doctypes/File/file.py`

Обрано за критеріями: справжні Link-поля (`uploaded_by → User`, `attached_to_doctype
→ DocType`), кілька whitelisted-методів, ручний dict-білдинг відповіді. Застосовано:
`File.objects.create(...)` замість `grunt.new_doc("File", ...)` у `upload()` (типізований
інстанс — атрибути замість `dict.get(...)`), `File.objects.filter(...).order_by(...)
.limit(...).page(...).all()`/`.count()` замість `grunt.get_list`/`grunt.count` у
`get_list()`.

**Свідомо НЕ застосовано:** `roles=`/`require=` на `remove()` — права там власницькі
(`match: owner==user` через `write_guard`/`DocTypePermission`), не рольові; додавання
`roles=["superadmin"]` зламало б звичайних користувачів, що видаляють власні файли.
Хороший контрприклад: `roles=`/`require=` — не "додай на кожен whitelist", а лише
там, де раніше був справжній статичний рольовий чек. `get_content()`'s ad hoc
"гість може читати лише публічний файл" також не мігровано — `require=` перевіряє
лише користувача, а тут потрібен ще й стан документа (`is_public`) з аргументів
виклику — за межами форми предиката, яку задумано.

**Свідомо поза цим ADR** (наступний захід):
- Relations (`has_many`/`.expand("roles")`) — досі не було жодного випадку, де
  чистий identity-based `.objects` не вистачило б; лишається гіпотетичною потребою.
- Розширення `Schema` на aliasing/перейменування полів — обґрунтовано знахідкою в
  `File.py`, конкретний дизайн (мапінг вихідний_ключ→поле чи щось інше) — окремим
  заходом, коли з'явиться другий приклад, що підтвердить форму.
- Типізована конверсія решти ~49 `get_doc`/~56 `get_list`/~86 `whitelist` викликів
  у `api/v1/*` та інших модулях — старий `get_doc(str) -> dict` лишається робочим
  паралельно (не сумісний шар "про всяк випадок", а другий легітимний виклик-шейп,
  як і зараз співіснують `db.get_all`/`grunt.get_all[T]`).
- Ширше прибирання `session`-параметра поза цими п'ятьма функціями (ще ~24 місця в
  10+ інших файлах).

---

## Стратегія подальшого впровадження

Фаза "збудувати й довести" тут завершена: примітиви підтверджені на двох різних
контролерах (простий `User` без Link-полів, `File` зі справжніми Link-полями й
різношаблонною серіалізацією) — жоден не показав дірки в дизайні, лише межі
застосовності (aliasing, ownership-based права).

Свідоме рішення: **не робити виділений mass-migration заходу** для решти ~140
`get_doc`/`get_list`/`whitelist` викликів. Старий (`get_doc(str) -> dict`) і новий
(`get_doc(Class) -> instance`) виклик-шейпи співіснують без конфлікту — це не
сумісний шар, а другий легітимний спосіб виклику, як і зараз `db.get_all`/
`grunt.get_all[T]`. Тому міграція решти контролерів відбувається **опортуністично**:
хтось торкається файлу з іншої причини — заодно переводить на нові primitives, а не
чекає окремого спринту на "узгодженість заради узгодженості". Якщо конкретний
контролер/модуль почне боліти раніше — мігрувати прицільно, не за розкладом.

---

## Доповнення: Phase 1 mass-migration (2026-08-18)

Користувач попросив таки зробити виділений захід, а не чекати опортуністичної
міграції. Дослідження (3 Explore-агенти) показало: сліпа конвертація всіх ~140
сайтів була б шкідливою (більшість `get_doc`/`get_list` у `api/v1/*` — dict-style
для JSON-відповіді, типізація там не потрібна). Реальна цінність знайшлась у трьох
вузьких категоріях — зроблено всі три:

**A. 20 whitelisted-функцій у 15 файлах** → `@grunt.whitelist(roles=["superadmin"])`
(`hooks.py`, `email.py` ×5 через спільний `_require_admin()` — видалено, `reports.py`
×2, `meta.py` ×5, `search.py`, `webhooks.py` ×2, `workspace.py` ×2, `pages.py` ×2).

**B. `get_doc` → `find_doc`, виправлення dead-code**: 7 сайтів, де `if not doc:` після
`get_doc` ніколи не спрацьовувало (`get_doc` кидає 404 раніше, ніж може повернути
falsy) — `webhook/incoming_service.py`, `webhook/service.py`, `api/v1/data_import.py`,
`api/v1/workspace.py` (`get_workspace`), `api/v1/dashboard.py` ×2 (звужено занадто
широкий `except Exception` до конкретно "не знайдено"), `io/doctypes/DataImport/
data_import.py` (обережно — зберегли точну структуру path-traversal guard'а,
`find_doc` лише зробив `if doc:` реально робочим). **Свідомо не чіпали**
`website/router.py` ×2 — там широкий `except` навмисний (best-effort рендеринг
публічної сторінки, не лише "не знайдено").

**C. Типізована інстанціація, включно з реальним багом**:
- `assignment/service.py:preview_rule` — `get_doc(AssignmentRule, id)` напряму.
- `workflow/engine.py:apply_transition` — динамічний doctype (не фіксований клас),
  тож не типізований overload, а вже наявний `grunt.get_doc_instance(name, id)`
  замість ручного `document_registry.get()` + інстанціації.
- **`tasks/doc_method.py:_run_doc_method` — справжній баг**: `getattr(dict, method)`
  на результаті `grunt.get_doc(doctype_str, id)` завжди `None` (dict не має довільних
  атрибутів) → `enqueue_doc_method` **завжди** падав з `AttributeError`, незалежно
  від того, чи метод існує. Виправлено тим самим `get_doc_instance()`.
- `api/v1/workspace.py:_get_ws_controller` — типізований `get_doc(AppMenu, name)`,
  прибрало заразом dead-code перевірку і ручний `document_registry.get()` (який теж
  ніколи не falsy).

**Побічна знахідка**: `get_doc_instance` ніколи не був доданий до фасаду
`grunt/__init__.py` — існував лише на інстансі (`grunt.app.grunt`). Додано до обох
dispatch-tuples, консистентно з `get_doc`/`find_doc`.

**Ще одна знахідка**: типізований `get_doc(Class, id)` через верхньорівневий пакет
(`import grunt`) має менш точний тип повернення (`dict | D` union, не звужується до
`D`), бо mypy забороняє `@overload` без реалізації у звичайному (не `.pyi`) файлі —
стаб у `grunt/__init__.py` тому не overloaded. Реальні overloads — на інстансі
`GruntApp` (`from grunt.app import grunt`). Для викликів, де результат прив'язується
до точно типізованого return/variable (як `_get_ws_controller() -> AppMenu`) —
використовувати `from grunt.app import grunt`, не `import grunt`.

Результат: `ruff check grunt/` чистий, `pytest tests/ grunt/` — 825/825 (5 нових
regression-тестів у `test_mass_migration_bugfixes.py`, що напряму доводять два
баг-фікси), `mypy grunt --ignore-missing-imports` — 56 помилок (було 58, жодної
нової — усі в нечіпаних файлах).

**Далі — знову опортуністично**: решта `get_doc`/`get_list` сайтів, де немає жодного
з трьох знайдених патернів.

---

## Доповнення 2: session-параметри (2026-08-18, той самий день)

Користувач попросив зробити й відкладений раніше 28-пунктовий інвентар
session-параметрів, а не чекати опортуністичного заходу.

**Зроблено — 32 функції в ~12 файлах**, кожна після перевірки РЕАЛЬНОГО caller'а
(не лише статичного патерна "бере session → одразу відкриває system_context"):
`UserRole.get_user_roles`; `UserSession` (усі 4 — `create_session`, `touch_session`,
`terminate_session`, `terminate_all_user_sessions`); `auth/service.py` (5 —
`create_refresh_token`, `rotate_refresh_token`, `revoke_refresh_tokens_for_user`,
`create_password_reset_token`, `consume_password_reset_token`); `webform/service.py`
(увесь клас — `get_form`, `get_form_fields`, `submit`, `_count_submissions` —
розширено з 2 запланованих до всіх 4, бо `session` наскрізно тік через увесь клас і
часткова зміна дала б непослідовний API); `notification/service.py` (3 мертві,
ніде не викликані методи — `get_notifications`/`mark_read`/`mark_all_read`);
`assignment/service.py` + `AssignmentLog.create` (увесь ланцюжок, 8 методів —
корінь виклику, `hooks.py`, вже мав ambient-контекст, бо хуки виконуються всередині
`write_guard`-перевіреного request-контексту); `webhook/incoming_service.py` (увесь
клас, 5 методів) + переведення `api/v1/webhooks.py`'s публічного `/incoming/{slug}`
роутера на `GruntRouter(optional_auth=True)` (був голий `APIRouter()`, як `core.py`
до Доповнення 1); `api/v1/auth/core.py: update_me`/`list_sessions` (бонус, поза
початковим списком).

**Реальний баг знайдений і виправлений у процесі**: `AssignmentLog.create` мав
`session: AsyncSession | None = None` з `if not session: return` — тихий no-op guard.
Обидва реальні виклики (з `_assign_to_user`/`_assign_to_role`) вже не передавали
`session=` після рефакторингу решти ланцюжка → записи про призначення перестали б
писатись УЗАГАЛІ, мовчки. Виправлено разом з рештою ланцюжка.

**Свідомо НЕ займались — 5 функцій/груп, кожна з конкретною причиною**:
- `tasks/scheduler.py` (`_write_job_log`/`_update_job_log`) — викликаються з
  APScheduler-задачі через власний `async_session_factory()`, без жодного
  `grunt.context(...)` навколо. Ambient-контексту просто немає.
- `notification/service.py` (`evaluate_rules`, `_create_notification`,
  `_resolve_role_recipients`, `_queue_email`, `_broadcast_ws`) — `evaluate_rules`
  викликається з `evaluate_notification_rules_task` (offloaded у background task
  саме для ізоляції від request-сесії) з власною свіжою сесією, теж без ambient-
  контексту. `_resolve_role_recipients` має другий caller (`api/messages.py`) із
  ambient-контекстом, але оскільки перший — ні, лишили обидва як є, щоб не
  розходились.
- `startup/settings.py`/`workspaces.py`/`fixtures.py` — bootstrap/migration-код
  (`grunt migrate`, `grunt site create`), той самий патерн: власний
  `session`+`engine` явно, без ambient-контексту.
- `auth/api_key_service.py: authenticate_api_key` — резолвиться як частина
  `current_user()`-залежності, тобто ДО того, як `grunt_context` встигає
  активувати ambient-контекст (той самий chicken-and-egg, що й `optional_user`
  у Доповненні 1).
- `website/router.py` — 2 місця з get_doc (не session-параметр), лишені в
  Доповненні 1 з тієї ж причини (навмисно широкий except для best-effort
  рендерингу).

Спільна нитка через усі "не займались" випадки: **background/bootstrap-код, що
свідомо створює власну сесію ізольовано від request-контексту** — це не той самий
"забули прибрати параметр" патерн, що в `user.py`, а архітектурна межа, яку не
варто стирати.

Результат: `ruff check grunt/` чистий, `pytest tests/ grunt/` — 825/825 (без нових
тестів у цьому доповненні — усі зміни покриті наявними `test_webform_submit.py`,
`grunt/auth/doctypes/User/tests/test_auth.py`, `test_assignment.py` через реальні
HTTP/whitelisted виклики), `mypy` — 56 помилок (без змін від Доповнення 1).
