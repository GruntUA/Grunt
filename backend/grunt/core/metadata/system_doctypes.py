"""System DocType definitions — core DocTypes that always exist.

Like Frappe's principle: everything is a DocType, including DocType itself.
These are injected into the registry at startup, their physical tables are
synced, and their document tables are populated from the registry state.
"""

from __future__ import annotations

from grunt.core.metadata.doctype import DocType
from grunt.core.metadata.field import DocField


SYSTEM_DOCTYPES: dict[str, DocType] = {
    "DocType": DocType(
        name="DocType",
        label="Тип документа",
        module="core",
        is_child=False,
        track_changes=False,
        search_fields=["name", "label"],
        title_field="label",
        fields=[
            DocField(
                fieldname="label",
                label="Назва",
                fieldtype="Text",
                in_list_view=True,
                in_filter=False,
                required=True,
            ),
            DocField(
                fieldname="module",
                label="Модуль",
                fieldtype="Text",
                in_list_view=True,
                in_filter=True,
            ),
            DocField(
                fieldname="is_child",
                label="Дочірній",
                fieldtype="Check",
                in_list_view=True,
                in_filter=True,
            ),
        ],
    ),
    "BackgroundTaskLog": DocType(
        name="BackgroundTaskLog",
        label="Лог фонових завдань",
        module="core",
        track_changes=False,
        fields=[
            DocField(
                fieldname="task_name",
                label="Завдання",
                fieldtype="Text",
                in_list_view=True,
                in_filter=True,
            ),
            DocField(
                fieldname="status",
                label="Статус",
                fieldtype="Select",
                options="Started\nSuccess\nError",
                in_list_view=True,
                in_filter=True,
            ),
            DocField(
                fieldname="started_at",
                label="Початок",
                fieldtype="Datetime",
                in_list_view=True,
            ),
            DocField(
                fieldname="finished_at",
                label="Завершення",
                fieldtype="Datetime",
                in_list_view=True,
            ),
            DocField(
                fieldname="error_message",
                label="Помилка",
                fieldtype="LongText",
            ),
            DocField(
                fieldname="arguments",
                label="Аргументи",
                fieldtype="JSON",
            ),
        ],
    ),
    "EmailAccount": DocType(
        name="EmailAccount",
        label="Обліковий запис пошти",
        module="core",
        fields=[
            DocField(
                fieldname="email_address",
                label="Email адреса",
                fieldtype="Text",
                required=True,
                in_list_view=True,
            ),
            DocField(
                fieldname="enable_outgoing",
                label="Дозволити вихідну пошту",
                fieldtype="Check",
                default=False,
            ),
            DocField(
                fieldname="smtp_server",
                label="SMTP сервер",
                fieldtype="Text",
                depends_on="eval:doc.enable_outgoing",
            ),
            DocField(
                fieldname="smtp_port",
                label="SMTP порт",
                fieldtype="Int",
                default=587,
                depends_on="eval:doc.enable_outgoing",
            ),
            DocField(
                fieldname="use_tls",
                label="Використовувати TLS",
                fieldtype="Check",
                default=True,
                depends_on="eval:doc.enable_outgoing",
            ),
            DocField(
                fieldname="smtp_user",
                label="Користувач SMTP",
                fieldtype="Text",
                depends_on="eval:doc.enable_outgoing",
            ),
            DocField(
                fieldname="smtp_password",
                label="Пароль SMTP",
                fieldtype="Text",  # Should be Password fieldtype if available
                depends_on="eval:doc.enable_outgoing",
            ),
            DocField(
                fieldname="enable_incoming",
                label="Дозволити вхідну пошту",
                fieldtype="Check",
                default=False,
            ),
            DocField(
                fieldname="imap_server",
                label="IMAP сервер",
                fieldtype="Text",
                depends_on="eval:doc.enable_incoming",
            ),
            DocField(
                fieldname="imap_port",
                label="IMAP порт",
                fieldtype="Int",
                default=993,
                depends_on="eval:doc.enable_incoming",
            ),
            DocField(
                fieldname="use_ssl",
                label="Використовувати SSL",
                fieldtype="Check",
                default=True,
                depends_on="eval:doc.enable_incoming",
            ),
        ],
    ),
    "EmailQueue": DocType(
        name="EmailQueue",
        label="Черга листів",
        module="core",
        fields=[
            DocField(
                fieldname="sender",
                label="Відправник",
                fieldtype="Text",
                in_list_view=True,
            ),
            DocField(
                fieldname="recipient",
                label="Отримувач",
                fieldtype="Text",
                in_list_view=True,
            ),
            DocField(
                fieldname="subject",
                label="Тема",
                fieldtype="Text",
                in_list_view=True,
            ),
            DocField(
                fieldname="content",
                label="Вміст",
                fieldtype="LongText",
            ),
            DocField(
                fieldname="status",
                label="Статус",
                fieldtype="Select",
                options="Pending\nSent\nError",
                default="Pending",
                in_list_view=True,
                in_filter=True,
            ),
            DocField(
                fieldname="error_message",
                label="Помилка",
                fieldtype="LongText",
            ),
            DocField(
                fieldname="email_account",
                label="Обліковий запис",
                fieldtype="Link",
                options="EmailAccount",
            ),
        ],
    ),
    "DataImport": DocType(
        name="DataImport",
        label="Імпорт даних",
        module="core",
        fields=[
            DocField(
                fieldname="reference_doctype",
                label="Тип документа",
                fieldtype="Link",
                options="DocType",
                required=True,
                in_list_view=True,
            ),
            DocField(
                fieldname="import_file",
                label="Файл для імпорту",
                fieldtype="Attach", # Assuming Attach/Text for now
                required=True,
            ),
            DocField(
                fieldname="import_type",
                label="Тип імпорту",
                fieldtype="Select",
                options="Insert New Records\nUpdate Existing Records\nUpsert",
                default="Upsert",
            ),
            DocField(
                fieldname="status",
                label="Статус",
                fieldtype="Select",
                options="Pending\nIn Progress\nCompleted\nFailed",
                default="Pending",
                in_list_view=True,
            ),
            DocField(
                fieldname="total_rows",
                label="Всього рядків",
                fieldtype="Int",
                read_only=True,
            ),
            DocField(
                fieldname="processed_rows",
                label="Оброблено",
                fieldtype="Int",
                read_only=True,
            ),
            DocField(
                fieldname="error_log",
                label="Журнал помилок",
                fieldtype="LongText",
                read_only=True,
            ),
        ],
    ),
    "Comment": DocType(
        name="Comment",
        label="Коментар",
        module="core",
        fields=[
            DocField(fieldname="reference_doctype", label="Тип документа", fieldtype="Link", options="DocType", required=True),
            DocField(fieldname="reference_id", label="ID документа", fieldtype="Text", required=True),
            DocField(fieldname="content", label="Вміст", fieldtype="LongText", required=True),
            DocField(fieldname="comment_type", label="Тип", fieldtype="Select", options="Comment\nInfo\nWarning\nError", default="Comment"),
        ],
    ),
    "ToDo": DocType(
        name="ToDo",
        label="Завдання",
        module="core",
        fields=[
            DocField(fieldname="description", label="Опис", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="reference_doctype", label="Тип документа", fieldtype="Link", options="DocType"),
            DocField(fieldname="reference_id", label="ID документа", fieldtype="Text"),
            DocField(fieldname="assigned_to", label="Виконавець", fieldtype="Text", in_list_view=True), # Link: User later
            DocField(fieldname="status", label="Статус", fieldtype="Select", options="Open\nClosed", default="Open", in_list_view=True),
            DocField(fieldname="priority", label="Пріоритет", fieldtype="Select", options="Low\nMedium\nHigh\nUrgent", default="Medium", in_list_view=True),
            DocField(fieldname="due_date", label="Термін", fieldtype="Date", in_list_view=True),
        ],
    ),
    "SharedWith": DocType(
        name="SharedWith",
        label="Доступ",
        module="core",
        fields=[
            DocField(fieldname="reference_doctype", label="Тип документа", fieldtype="Link", options="DocType", required=True),
            DocField(fieldname="reference_id", label="ID документа", fieldtype="Text", required=True),
            DocField(fieldname="user", label="Користувач", fieldtype="Text", required=True), # Link: User
            DocField(fieldname="permission", label="Дозвіл", fieldtype="Select", options="Read\nWrite", default="Read"),
        ],
    ),
    "ActivityLog": DocType(
        name="ActivityLog",
        label="Журнал активності",
        module="core",
        track_changes=False,
        fields=[
            DocField(fieldname="reference_doctype", label="Тип документа", fieldtype="Link", options="DocType", required=True, in_list_view=True),
            DocField(fieldname="reference_id", label="ID документа", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="user", label="Користувач", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="action", label="Дія", fieldtype="Select", options="Create\nUpdate\nDelete\nSubmit\nCancel\nShare\nComment", required=True, in_list_view=True),
            DocField(fieldname="details", label="Деталі", fieldtype="LongText"),
        ],
    ),

    # ── Phase 5: Notifications ────────────────────────────────────────────

    "NotificationRule": DocType(
        name="NotificationRule",
        label="Правило нотифікації",
        module="core",
        fields=[
            DocField(fieldname="doctype", label="Тип документа", fieldtype="Link", options="DocType", required=True, in_list_view=True, in_filter=True),
            DocField(fieldname="event", label="Подія", fieldtype="Select", options="after_insert\nafter_save\non_transition\nvalue_change", required=True, in_list_view=True, in_filter=True),
            DocField(fieldname="channel", label="Канал", fieldtype="Select", options="system\nemail\nboth", default="system", in_list_view=True),
            DocField(fieldname="recipients", label="Отримувачі", fieldtype="Text", required=True),
            DocField(fieldname="condition", label="Умова (Python)", fieldtype="LongText"),
            DocField(fieldname="subject_template", label="Шаблон теми", fieldtype="Text", default="{doctype}: {name}"),
            DocField(fieldname="message_template", label="Шаблон повідомлення", fieldtype="LongText", default="{doctype} {name} was {event}"),
            DocField(fieldname="is_enabled", label="Активне", fieldtype="Check", default=True, in_list_view=True, in_filter=True),
        ],
    ),
    "Notification": DocType(
        name="Notification",
        label="Повідомлення",
        module="core",
        track_changes=False,
        fields=[
            DocField(fieldname="user", label="Користувач", fieldtype="Text", required=True, in_list_view=True, in_filter=True),
            DocField(fieldname="subject", label="Тема", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="message", label="Повідомлення", fieldtype="LongText", required=True),
            DocField(fieldname="doctype", label="Тип документа", fieldtype="Text", in_list_view=True),
            DocField(fieldname="doc_id", label="ID документа", fieldtype="Text"),
            DocField(fieldname="is_read", label="Прочитано", fieldtype="Check", default=False, in_list_view=True, in_filter=True),
        ],
    ),

    # ── Phase 5: Versioning ───────────────────────────────────────────────

    "DocVersion": DocType(
        name="DocVersion",
        label="Версія документа",
        module="core",
        track_changes=False,
        fields=[
            DocField(fieldname="doctype", label="Тип документа", fieldtype="Link", options="DocType", required=True, in_list_view=True, in_filter=True),
            DocField(fieldname="doc_id", label="ID документа", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="version", label="Версія", fieldtype="Int", required=True, in_list_view=True),
            DocField(fieldname="user", label="Користувач", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="changes", label="Зміни", fieldtype="JSON"),
        ],
    ),

    # ── Phase 5: Naming Series ────────────────────────────────────────────

    "NamingSeries": DocType(
        name="NamingSeries",
        label="Серія нумерації",
        module="core",
        fields=[
            DocField(fieldname="prefix", label="Префікс", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="current", label="Поточний номер", fieldtype="Int", default=0, in_list_view=True),
        ],
    ),

    # ── Phase 5: i18n ─────────────────────────────────────────────────────

    "Translation": DocType(
        name="Translation",
        label="Переклад",
        module="core",
        fields=[
            DocField(fieldname="source", label="Оригінал", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="language", label="Мова", fieldtype="Text", required=True, in_list_view=True, in_filter=True),
            DocField(fieldname="translated", label="Переклад", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="context", label="Контекст", fieldtype="Text"),
        ],
    ),

    # ── Phase 5: Print Formats ────────────────────────────────────────────

    "PrintFormat": DocType(
        name="PrintFormat",
        label="Формат друку",
        module="core",
        fields=[
            DocField(fieldname="doctype", label="Тип документа", fieldtype="Link", options="DocType", required=True, in_list_view=True, in_filter=True),
            DocField(fieldname="template_type", label="Тип шаблону", fieldtype="Select", options="html\ndocx", default="html", in_list_view=True),
            DocField(fieldname="template", label="Шаблон", fieldtype="LongText", required=True),
            DocField(fieldname="is_default", label="За замовчуванням", fieldtype="Check", default=False, in_list_view=True),
        ],
    ),

    # ── Phase 6: Scripting ────────────────────────────────────────────────

    "ServerScript": DocType(
        name="ServerScript",
        label="Серверний скрипт",
        module="core",
        fields=[
            DocField(fieldname="script_type", label="Тип", fieldtype="Select", options="DocType Event\nAPI\nScheduler Event", required=True, in_list_view=True, in_filter=True),
            DocField(fieldname="doctype", label="Тип документа", fieldtype="Link", options="DocType", in_list_view=True),
            DocField(fieldname="event", label="Подія", fieldtype="Select", options="before_insert\nafter_insert\nbefore_save\nafter_save\nbefore_delete\nafter_delete\nvalidate"),
            DocField(fieldname="api_method", label="API метод", fieldtype="Text"),
            DocField(fieldname="cron", label="Cron вираз", fieldtype="Text"),
            DocField(fieldname="script", label="Скрипт (Python)", fieldtype="LongText", required=True),
            DocField(fieldname="is_enabled", label="Активний", fieldtype="Check", default=True, in_list_view=True, in_filter=True),
            DocField(fieldname="allow_guest", label="Дозвіл для гостей", fieldtype="Check", default=False),
        ],
    ),
    "ClientScript": DocType(
        name="ClientScript",
        label="Клієнтський скрипт",
        module="core",
        fields=[
            DocField(fieldname="doctype", label="Тип документа", fieldtype="Link", options="DocType", required=True, in_list_view=True, in_filter=True),
            DocField(fieldname="script", label="Скрипт (JavaScript)", fieldtype="LongText", required=True),
            DocField(fieldname="is_enabled", label="Активний", fieldtype="Check", default=True, in_list_view=True, in_filter=True),
        ],
    ),

    # ── Phase 6: Web Forms ────────────────────────────────────────────────

    "WebForm": DocType(
        name="WebForm",
        label="Веб-форма",
        module="core",
        fields=[
            DocField(fieldname="title", label="Заголовок", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="route", label="URL маршрут", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="doctype", label="Тип документа", fieldtype="Link", options="DocType", required=True, in_list_view=True, in_filter=True),
            DocField(fieldname="introduction", label="Вступ", fieldtype="LongText"),
            DocField(fieldname="success_message", label="Повідомлення успіху", fieldtype="Text", default="Дякуємо! Вашу заявку прийнято."),
            DocField(fieldname="success_url", label="URL після відправки", fieldtype="Text"),
            DocField(fieldname="login_required", label="Потрібна авторизація", fieldtype="Check", default=False, in_list_view=True),
            DocField(fieldname="is_published", label="Опубліковано", fieldtype="Check", default=True, in_list_view=True, in_filter=True),
            DocField(fieldname="max_submissions", label="Макс. відповідей", fieldtype="Int", default=0),
            DocField(fieldname="submit_label", label="Текст кнопки", fieldtype="Text", default="Надіслати"),
            DocField(fieldname="fields", label="Поля (JSON)", fieldtype="JSON"),
        ],
    ),

    # ── Phase 6: Dashboard ────────────────────────────────────────────────

    "DashboardChart": DocType(
        name="DashboardChart",
        label="Графік дашборду",
        module="core",
        fields=[
            DocField(fieldname="chart_type", label="Тип графіка", fieldtype="Select", options="bar\nline\npie\ndonut", default="bar", in_list_view=True, in_filter=True),
            DocField(fieldname="doctype", label="Тип документа", fieldtype="Link", options="DocType", required=True, in_list_view=True),
            DocField(fieldname="value_field", label="Поле значення", fieldtype="Text", required=True),
            DocField(fieldname="group_by", label="Групувати за", fieldtype="Text"),
            DocField(fieldname="timespan", label="Період", fieldtype="Select", options="last_week\nlast_month\nlast_quarter\nlast_year\nall_time", default="last_year", in_list_view=True),
            DocField(fieldname="filters", label="Фільтри (JSON)", fieldtype="JSON"),
            DocField(fieldname="color", label="Колір", fieldtype="Text", default="#2D6A4F"),
            DocField(fieldname="is_public", label="Публічний", fieldtype="Check", default=True),
        ],
    ),
    "NumberCard": DocType(
        name="NumberCard",
        label="Числова картка",
        module="core",
        fields=[
            DocField(fieldname="label", label="Назва", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="doctype", label="Тип документа", fieldtype="Link", options="DocType", required=True, in_list_view=True),
            DocField(fieldname="aggregation", label="Агрегація", fieldtype="Select", options="count\nsum\navg\nmin\nmax", default="count", in_list_view=True),
            DocField(fieldname="value_field", label="Поле значення", fieldtype="Text"),
            DocField(fieldname="filters", label="Фільтри (JSON)", fieldtype="JSON"),
            DocField(fieldname="color", label="Колір", fieldtype="Text", default="#2D6A4F"),
            DocField(fieldname="icon", label="Іконка", fieldtype="Text"),
            DocField(fieldname="is_public", label="Публічний", fieldtype="Check", default=True),
        ],
    ),

    # ── Phase 6: Document Links ───────────────────────────────────────────

    "DocLink": DocType(
        name="DocLink",
        label="Зв'язок документа",
        module="core",
        track_changes=False,
        fields=[
            DocField(fieldname="source_doctype", label="Тип джерела", fieldtype="Text", required=True, in_list_view=True, in_filter=True),
            DocField(fieldname="source_id", label="ID джерела", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="target_doctype", label="Тип цілі", fieldtype="Text", required=True, in_list_view=True, in_filter=True),
            DocField(fieldname="target_id", label="ID цілі", fieldtype="Text", required=True, in_list_view=True),
            DocField(fieldname="link_fieldname", label="Поле зв'язку", fieldtype="Text", required=True),
        ],
    ),
}


def is_system_doctype(name: str) -> bool:
    """Return True if *name* is a core system DocType."""
    return name in SYSTEM_DOCTYPES
