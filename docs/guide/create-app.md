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
            users=[grunt.session.user],
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
