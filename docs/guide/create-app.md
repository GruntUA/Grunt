# Creating an App

An **App** in Grunt is a set of DocTypes, controllers, hooks, and background tasks that extend the framework. Apps are installed on top of Grunt, similar to plugins.

## Scaffold a new app

```bash
grunt app create my_crm
```

This creates the following structure inside `apps/my_crm/`:

```
apps/my_crm/
├── my_crm/               ← Python module
│   ├── doctypes/
│   │   └── Customer/
│   │       ├── Customer.json
│   │       └── Customer.py
│   ├── tasks.py          ← Background tasks
│   └── hooks.py          ← Event hooks
├── grunt_app.py          ← App manifest + hooks entrypoint
└── app.json
```

## App manifest (`app.json`)

```json
{
  "name": "my_crm",
  "label": "My CRM",
  "version": "0.1.0",
  "description": "Customer Relationship Management",
  "author": "Your Name"
}
```

## Defining DocTypes

Create a JSON file in `my_crm/doctypes/Customer/`:

```json title="my_crm/doctypes/Customer/Customer.json"
{
  "name": "Customer",
  "label": "Customer",
  "module": "my_crm",
  "title_field": "full_name",
  "fields": [
    {"fieldname": "full_name", "label": "Full Name", "fieldtype": "Text", "required": true, "in_list_view": true},
    {"fieldname": "email", "label": "Email", "fieldtype": "Text", "in_list_view": true},
    {"fieldname": "phone", "label": "Phone", "fieldtype": "Text"},
    {"fieldname": "status", "label": "Status", "fieldtype": "Select",
     "options": "Lead\nProspect\nCustomer\nInactive", "in_list_view": true}
  ],
  "permissions": [
    {"role": "Sales", "read": true, "write": true, "create": true}
  ]
}
```

Then sync the DocType to create the database table:

```bash
grunt doctype sync Customer
```

## Adding a controller

Create a Python file next to the DocType JSON:

```python title="my_crm/doctypes/Customer/Customer.py"
from grunt.document.base import Document


class Customer(Document):
    async def validate(self) -> None:
        if self.email and "@" not in self.email:
            grunt.throw("Invalid email address")

    async def after_insert(self) -> None:
        await grunt.notify(
            users=[grunt.get_user().email],
            subject=f"New customer: {self.full_name}",
            message=f"Customer {self.full_name} was created.",
            doctype="Customer",
            doc_id=self.id,
        )
```

## Registering hooks

```python title="my_crm/hooks.py"
from grunt.hooks import on_doc


@on_doc("Customer", "after_insert")
async def on_customer_insert(doc, user, **kwargs):
    """Called after any Customer document is created."""
    await grunt.publish(
        user=user.email,
        event="msgprint",
        message=f"Welcome, {doc['full_name']}!",
        type="success",
    )
```

## Custom document actions

Register a named action in code, then bind it to a DocType from the **Actions**
tab of the DocType editor (a `DocTypeAction` row per button). Bound actions
appear as buttons in the document toolbar.

```python title="my_crm/actions.py"
from grunt.actions import doc_action


@doc_action(
    "send_welcome_email",
    label="Надіслати вітальний лист",
    doctypes=["Customer"],  # or ["*"] for any DocType
    icon="mail",  # lucide icon name
    confirm="Надіслати листа клієнту?",  # optional confirm dialog
    roles=["Sales"],  # optional — gate by role (also enforced server-side)
)
async def send_welcome_email(doc: dict, *, args: dict) -> dict:
    # ... send mail ...
    return {"message": "Лист надіслано", "refresh": False}
```

Point `hooks.py` at the module so the decorators run on startup:

```python title="my_crm/hooks.py"
doc_actions = ["my_crm.actions"]
```

The handler receives the document as a plain `dict` (`doc["doctype"]` and
`doc["name"]` are always set). Return a `dict` (`message` is toasted,
`refresh` != `False` reloads the form, `copy` is written to the clipboard), a
bare string, or nothing. A binding row may override `label` / `group` /
`variant` and add a JS `condition` (evaluated against `doc` on the client) to
show the button conditionally.

Core ships three generic actions you can bind to any DocType without writing
code: `core.duplicate`, `core.recalc` (re-save so formulas/hooks re-run) and
`core.copy_reference`.

## Document connections (the "Зв'язки" panel)

The form shows related documents grouped in a panel with live counts and a
"+ Новий" shortcut. Two ways to configure it:

* **Zero config** — any DocType with a Link field back to yours is surfaced
  automatically.
* **Explicit** — add rows to the DocType's **Зв'язки** tab (`DocTypeLink`):
  `link_doctype`, `link_fieldname` (the Link field on the other side),
  optional `group` / `label`. For a link that lives on a *child table*, also
  set `parent_doctype` (the child DocType) and `table_fieldname`. Once any row
  is declared, the table is authoritative — derivation stops.

Counts and previews come from `grunt.document.connections.get_connections`.

**Placement:** set **Показувати панель «Зв'язки» в цій вкладці** on a `Tab`
field to render the panel at the top of that tab. If no tab opts in, it
renders at the top of the first tab.

## Documents as JSON

Every document the API returns is a JSON object that names its own DocType —
child rows included — and that JSON is enough to build the document again:

```python
doc = await grunt.get_doc("Deal", "D-0001")
# {"doctype": "Deal", "name": "D-0001", ..., "items": [{"doctype": "DealItem", ...}]}

deal = await grunt.get_doc({"doctype": "Deal", "title": "Big one", "items": [...]})
await deal.insert()          # an unsaved controller - `create` permission checked
deal.as_dict(), deal.as_json()
```

`doctype` is therefore a reserved fieldname: a field naming *another* DocType
is called `ref_doctype`.

## Standard records (configuration as files)

Reports, pages, print formats, web forms, scripts, notification rules,
workflows, email templates — every DocType with **Standard records**
(`"standard_records": true`) — can ship with the app. Mark a record
**Standard** and pick its **App**; in developer mode (`DEBUG=true`) each save
writes it to the app:

```
my_crm/records/report/deals_by_stage/
  deals_by_stage.json      ← the document's JSON (no system columns)
  query.sql                ← each non-empty Code field as a file of its own
```

Deleting the record, or unmarking it, removes the folder. `grunt migrate`
applies the folders: missing records are inserted, changed ones updated —
the files are the source of truth — unchanged ones are not touched. Commit
the folder with the app's code.

## Fixtures (shipping data records)

Records that are part of the app's data — roles, home pages, seed rows — live
in `my_crm/fixtures/*.json` and are applied on install/migrate, in filename
order:

```json title="my_crm/fixtures/00_roles.json"
{"doctype": "Role", "records": [{"name": "Sales Manager"}]}
```

A plain file is a **seed**: missing records are inserted, existing ones are
never touched. To keep records built in the UI in sync with the app code,
declare them in `hooks.py` and export them from a site:

```python title="my_crm/hooks.py"
fixtures = [
    {"doctype": "Role", "filters": {"name__in": ["Sales Manager"]}, "file": "00_roles.json"},
    {"doctype": "Workflow", "filters": {"document_type": "Deal"}, "file": "02_workflow.json"},
    "LeadSource",  # every record, written to lead_source.json
]
```

```bash
grunt fixtures export my_crm [--site mysite]
```

Exported files carry `"sync": true`: on migrate, existing records are updated
to match the file (only when a value differs, fields absent from the file are
left alone). System columns, virtual fields and `Password` values are never
exported; child tables are exported with their rows.

## Adding background tasks

```python title="my_crm/tasks.py"
from grunt.tasks.broker import retryable_task


@retryable_task(max_retries=3, delay=60)
async def sync_customers_from_crm():
    """Sync customers from an external CRM."""
    # ...
    pass
```

Register the task schedule in `app.json`:

```json
{
  "scheduled_tasks": [
    {"task": "my_crm.tasks.tasks.sync_customers_from_crm", "cron": "0 */6 * * *"}
  ]
}
```
