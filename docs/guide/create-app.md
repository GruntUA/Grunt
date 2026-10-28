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
└── pyproject.toml      ← Package + app manifest ([tool.grunt])
```

## App manifest (`pyproject.toml`)

The standard `[project]` table holds the name, description and authors;
`[tool.grunt]` adds what only Grunt needs. A directory under `apps/` is an app
when its `pyproject.toml` has `[tool.grunt]`.

```toml
[project]
name = "my_crm"
dynamic = ["version"]
description = "Customer Relationship Management"
authors = [{ name = "Your Name", email = "you@example.com" }]

[tool.grunt]
title = "My CRM"
depends_on = []                 # app names or { name = "cms", url = "https://..." }
# required_grunt = ">=0.5"      # PEP 440 specifier; an incompatible app is not loaded
# modules = ["my_crm"]          # default: [<app directory name>]
```

The version comes from git tags `vX.Y.Z` (`grunt release --app my_crm`); an
untagged repository reports `0.1.devN+g<hash>`. The sidebar icon (a Lucide
name) and colour live in the `AppMenu` record of `fixtures/00_workspace.json`;
without a colour one is picked from a palette by the workspace name.

## Extending another app

An app can live inside another app's menu instead of having its own entry in
the app list (an integration, an add-on module):

```toml
[tool.grunt]
title = "Crystal Finance"
extends = ["inventory"]   # implies depends_on = ["inventory"]
# workspace = false       # default when extends is set: no AppMenu of its own
```

Its menu items go into an `AppMenu` fixture with `extends` instead of `name`:

```json
{
  "doctype": "AppMenu",
  "records": [{
    "extends": "inventory",
    "sections": [{"section": "Crystal Finance", "icon": "landmark", "after": "Агенти"}],
    "items": [
      {"section": "Crystal Finance", "label": "Картки ОЗ", "link_to": "CrystalFinanceCard", "show_count": true},
      {"section": "Налаштування", "link_to": "CrystalFinanceSettings", "after": "InventorySettings"}
    ]
  }]
}
```

The rows are stored with `source_app` set to the contributing app: the base
app's own sync on `grunt migrate` leaves them alone, and `grunt app uninstall`
removes them. Placement, worked out when the menu is read:

* an item's `after`/`before` - next to the item with that `link_to` (or label);
* otherwise at the end of its section, if the base menu has that section;
* a new section goes after/before the section named in its `sections` entry;
* anything left goes to the end of the menu.

Several apps contributing to one menu are placed in app-name order.

### Adding fields to another app's DocType

One file per DocType in a module's `doctype_ext/`, named after the DocType:

```json
// crystal_finance/doctype_ext/Asset.json
{
  "fields": [
    {"fieldname": "cf_card", "label": "Картка ОЗ", "fieldtype": "Link",
     "options": "CrystalFinanceCard", "insert_after": "inventory_number"}
  ]
}
```

`grunt migrate` stores each DocType as its own JSON plus the extension fields
of the site's installed apps (in dependency order); a field goes right after
its `insert_after` field, else at the end. Merged fields carry `source_app`:

* a fieldname the DocType already has (its own or another extension's) is
  refused with a `doctype_ext.field_collision` error - prefix your fields
  (`cf_card`, not `card`);
* saving the base DocType in Studio never writes them into its JSON file;
* uninstalling the app removes them and drops their columns; with
  `--keep-data` they leave the DocType on the next `migrate`, the columns stay.

Works for core DocTypes too (`User`, ...). Before adding fields to someone
else's table, consider a DocType of your own with a Link to it - shown on its
form as a connection or a sidebar section; a field in the base table is worth
it when it must be filtered or shown in the base list.

### Extending another app's behaviour

Every hook below works on any app's DocType, not only your own:

| `hooks.py` name | What it adds |
| --- | --- |
| `doc_events` | handlers for lifecycle events (`validate`, `on_update`, ...), several apps, by `priority` |
| `doctype_mixins` | methods on the controller class, several apps |
| `override_doctype_class` | a replacement controller class - one app per DocType |
| `doc_actions` | toolbar buttons (`@doc_action(doctypes=[...])`) |
| `doctype_js` | client scripts for the form |
| `sidebar_sections` | panels in the form sidebar |
| `scheduler_events` | background jobs |

```python title="crystal_finance/hooks.py"
doctype_mixins = {"Asset": ["crystal_finance.asset.AssetFinance"]}
```

```python title="crystal_finance/asset.py"
class AssetFinance:
    async def validate(self) -> None:
        await super().validate()  # the rest of the chain: other mixins, the Asset controller
        ...

    def card_status(self) -> str: ...
```

The registry builds `class Asset(<mixins>, Asset)` the first time the
controller is needed, the mixin of the app loaded last in front; a mixin
method that calls `super()` keeps the base behaviour and the other apps'
mixins. `grunt.get_doc(Asset, name)` returns the extended class too. Prefer
mixins (or `doc_events`) to `override_doctype_class`: a second app overriding
the same DocType is refused with a `document.override_conflict` error.

## Defining DocTypes

Create a JSON file in `my_crm/doctypes/Customer/`:

```json title="my_crm/doctypes/Customer/Customer.json"
{
  "name": "Customer",
  "label": "Customer",
  "module": "my_crm",
  "title_field": "full_name",
  "fields": [
    {"fieldname": "full_name", "label": "Full Name", "fieldtype": "Data", "required": true, "in_list_view": true},
    {"fieldname": "email", "label": "Email", "fieldtype": "Data", "in_list_view": true},
    {"fieldname": "phone", "label": "Phone", "fieldtype": "Data"},
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

## Sidebar sections

Add rows to the document sidebar without writing any Vue. A section is a
function that returns `label → value` rows; the desk draws every section the
same way, under the built-in ones.

```python title="my_crm/hooks.py"
sidebar_sections = [
    {
        "name": "deal_totals",
        "label": "Totals",
        "method": "my_crm.sidebar.deal_totals",
        "doctypes": ["Customer"],  # omitted - every DocType
        "roles": ["Sales"],  # omitted - everyone who can read the document
    },
]
```

```python title="my_crm/sidebar.py"
import grunt


async def deal_totals(doctype: str, doc_id: str, doc: dict) -> list[dict]:
    won = await grunt.db.count("Deal", {"customer": doc_id, "status": "Won"})
    return [
        {"label": "Won deals", "value": won, "link": f"/app/crm/Deal?customer={doc_id}"},
        {"label": "Tier", "value": doc.get("tier"), "indicator": "green"},
    ]
```

The document has already passed the read check. Return `None` or `[]` to hide
the section. `link` is a desk path (opened in place) or a URL (new tab);
`indicator` (green, red, orange, yellow, blue, gray) shows the value as a
coloured badge. A section that raises is logged and skipped.

## First-steps checklists

A **Module onboarding** record is a checklist shown on the app's home and on
the desk home until its steps are done (or someone hides it). It is a standard
record, so mark it **Standard**, pick the app, and it ships as files.

Each step has an **Action**: *Create Entry* and *Update Settings* complete by
themselves - once a record of the DocType exists, or the settings field is
filled in (or equals **Expected value**); *Go to Page*, *View Report*, *Read
Docs* and *Watch Video* count once opened. Any step can be skipped.
**Progress** is either the site's (one shared setup checklist) or each user's
(a step counts the user's own records).

## Documents as JSON

Every document the API returns is a JSON object that names its own DocType —
child rows included — and that JSON is enough to build the document again:

```python
doc = await grunt.get_doc("Deal", "D-0001")
# {"doctype": "Deal", "name": "D-0001", ..., "items": [{"doctype": "DealItem", ...}]}

deal = await grunt.get_doc({"doctype": "Deal", "title": "Big one", "items": [...]})
await deal.insert()  # an unsaved controller - `create` permission checked
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

Register the task schedule in `my_crm/hooks.py`:

```python
scheduler_events = {
    "cron": [
        {"handler": "my_crm.tasks.sync_customers_from_crm", "expression": "0 */6 * * *"},
    ],
}
```
