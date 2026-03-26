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
}


def is_system_doctype(name: str) -> bool:
    """Return True if *name* is a core system DocType."""
    return name in SYSTEM_DOCTYPES
