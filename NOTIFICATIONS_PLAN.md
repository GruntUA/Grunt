# Сповіщення: правила, канали, журнал

> Мета: **будь-яке** сповіщення (у системі, email, браузерний пуш, згодом SMS) — і з правил адміністратора,
> і з коду ядра/додатків — проходить через одне місце, яким можна керувати з адмінки
> (увімкнути/вимкнути, умова, отримувачі, канали, текст) і яке пишеться в журнал.
>
> Закриває пункти FRAPPE_GAP_PLAN: #10 (NotificationRule), частково #18 (налаштування користувача), #45 (SMS — канал),
> частково #19 (сповіщення переходів Workflow).
>
> Статуси: ❓ обговорити · ✅ робимо · ⏸ пізніше · ✔️ зроблено

## Що є зараз (2026-11-12)

- `NotificationRule` (тепер `Notification`) — подія (`after_insert`, `after_save`, `on_transition`, `value_change`, `days_before/after`),
  `condition` (simpleeval), `recipients` рядком (`owner`, `role:X`, `{field:x}`, email), `channel` = system/email/both,
  шаблони `str.format`. Оцінюється у воркері (`rule_index` + `notification/tasks.py`).
- `Notification` (тепер `NotificationLog`) — запис у «дзвонику» користувача. Браузерний пуш (`webpush`) іде **завжди** разом із ним — окремо не вимикається.
- Повз правила, текстом у коді, шлють:
  | Джерело | Файл | Канали |
  |---|---|---|
  | Перехід Workflow (`WorkflowTransition.notify/notify_email`) | `workflow/notify.py` | система + пуш (+ email) |
  | Призначення ToDo, нагадування ToDo | `tasks/doctypes/ToDo/to_do.py`, `tasks/todo_reminders.py` | + email |
  | Нагадування (Reminder) | `tasks/reminders.py` | система + пуш |
  | Стеження (follow) | `activity/follow.py` | система + пуш |
  | SLA попередження/порушення | `notification/sla.py` | налаштовується в ServiceLevel |
  | AutoRepeat успіх/збій | `tasks/auto_repeat.py` | система + пуш |
  | Згадки/коментарі | `core_events.py` | система + пуш |
  | Дайджест | `email/tasks.py` | email |
  | Розсилка звітів | `reports/delivery.py` | email + вкладення |
  | Вхід за кодом, запрошення | `auth/providers/email_link.py`, `auth/user_api.py` | email (службові) |
  | Нове звернення | `mlt_portal/appeals.py` | email + система |
  | Звернення громадян | `tsnap/.../CitizenAppeal.py` | EmailTemplate + система |
- Журнал: `EmailQueue` → `EmailMessage` лише для пошти, без зв'язку з причиною (правило/подія/документ).

## Рішення (пропозиція)

### A. Модель

**`Notification`** (було `NotificationRule`; «дзвоник» `Notification` → `NotificationLog`, як у Frappe — етап 0) — розширюємо:

| Секція | Поля |
|---|---|
| Коли | `ref_doctype` (порожньо = будь-який — для подій коду), `event` (+ `code` — «подія з коду», + `minutes_before/after` для Datetime), `event_key` (для `code`: `grunt.workflow.transition`, `mlt_portal.appeal.new`…), фільтри переходу: `workflow_actions`, `to_states` |
| Умова | `condition` — як зараз (simpleeval по `doc`, `user`, + `ctx` події) |
| Кому | дочірня таблиця `NotificationRecipient`: `kind` (Автор · Хто виконав дію · Попередній виконавець · Наступні виконавці · Роль · Поле документа · Користувач · Email · Призначені · Стежать · Отримувачі з коду), `value`, `condition`; прапорець `notify_actor` (за замовч. ні) |
| Канали | дочірня таблиця `NotificationRuleChannel`: `channel` (з реєстру каналів), `subject`/`message` — перевизначення тексту для каналу (SMS коротше, email — HTML), `email_template` (Link EmailTemplate, лише email) |
| Текст | `subject_template`, `message_template` — **Jinja (sandbox)**, контекст: `doc`, `actor`, `recipient`, `ctx` (дані події: `action`, `from_state`, `to_state`, `comment`…), `url`, `site` |
| Службове | `is_enabled`, `is_standard`, `app`, `is_customized` (див. Г), `priority` |

### Б. Канали — реєстр у коді

`grunt.notification.channels`: клас `Channel` з `name`, `label`, `deliver(recipient, rendered, ctx)`, `address_of(user)`.
Ядро: `in_app` (дзвоник + WS), `web_push` (окремо від in_app), `email` (через `EmailQueue`).
Додаток реєструє свій канал у `hooks.py` (`notification_channels = [...]`) — так прийде SMS (#45: SMS Settings + шлюз) або мобільний пуш.
Канал без адреси отримувача (немає телефону/підписки) — пропуск із записом у журнал.

### В. Події з коду → стандартні правила

Код більше не складає текст і не обирає канали сам:

```python
await notifications.trigger(
    "grunt.workflow.transition", doctype=..., doc=doc, actor=user,
    ctx={"action": ..., "from_state": ..., "to_state": ..., "comment": ...},
    recipients={"next": [...], "previous": [...]},   # «Отримувачі з коду»
)
```

Кожна така подія має **стандартне правило** (`is_standard`, `event=code`) у `records/` свого додатка з текстом, що зараз у коді.
Немає увімкненого правила — нічого не шлемо. Службові листи (код входу, скидання пароля, запрошення) — теж правила,
але з `is_mandatory`: вимкнути не можна, текст і канали — можна.

Workflow: `WorkflowTransition.notify` / `notify_email` → прибираємо; міграція створює правила `on_transition` з фільтром
`workflow_actions` (одне правило на workflow + набір отримувачів). mlt_portal — фікстури переписуємо на правила.

### Г. Стандартні правила й правки на проді

Зараз `grunt migrate` перезаписує standard record файлом — правка адміністратора на проді зникне.
Для `NotificationRule`: збереження поза dev-режимом ставить `is_customized`; migrate такі записи не чіпає
(лог «пропущено, змінено локально»); кнопка «Скинути до стандарту». Механізм — у `standard_records`, щоб підходив і іншим DocType.

### Д. Журнал доставки — `NotificationDelivery`

Один рядок на (правило × отримувач × канал): `rule`, `event_key`, `ref_doctype`/`ref_name`, `recipient`, `channel`,
`status` (Queued · Sent · Skipped · Error), `reason` (вимкнено правило / умова / немає адреси / налаштування користувача),
`subject`, посилання на `NotificationLog` / `EmailQueue` / `EmailMessage`. Статус email оновлює воркер черги.
`retention_days` — як в інших журналах. Відповідь на «хто, що, чому й чи дійшло» — тут.

### Е. Налаштування користувача (⏸ другий етап)

Таблиця в профілі: правило/подія × канал — вимкнути для себе (крім `is_mandatory`). Дайджест — сюди ж.

## Етапи

| # | Етап | Статус |
|---|---|---|
| 0 | Перейменування: `Notification` → `NotificationLog`, `NotificationRule` → `Notification`; міграція 0022 + загальний `grunt.db.rename_doctype` | ✅ гілка `feature/notification-rename` |
| 1 | Реєстр каналів (`grunt.notification.channels`, `notification_channels` у hooks.py); `in_app` / `web_push` / `email` окремо; диспетчер `deliver()` + `NotificationDelivery` (черга пошти й пуш оновлюють статус); правила, `notify()` і `grunt.notify()` — через диспетчер | ✅ гілка `feature/notification-channels` |
| 2 | Нова форма правила: таблиці отримувачів і каналів, Jinja, міграція старих `recipients`/`channel` | ❓ |
| 3 | `notifications.trigger()` + `event=code`; стандартні правила для подій ядра; `is_customized` у standard_records | ❓ |
| 4 | Workflow: правила замість `notify/notify_email`, міграція; mlt_portal, tsnap, cms на правила | ❓ |
| 5 | Налаштування користувача (#18) | ⏸ |
| 6 | SMS-канал (#45), PDF у вкладенні, зміна поля після сповіщення (#10) | ⏸ |

## Рішення користувача (2026-11-12)

1. Перейменувати: правило → `Notification`, «дзвоник» → `NotificationLog`. Журнал доставки — `NotificationDelivery`.
2. Workflow: правила замість `WorkflowTransition.notify/notify_email` (міграція переносить налаштування переходів у правила).
3. Шаблони — Jinja (sandbox).
