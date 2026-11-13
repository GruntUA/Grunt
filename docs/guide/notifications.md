# Notifications

All notifications are configured in **Notification** rules. A rule defines:

- **When** it fires: an event on a document, or an event raised from code.
- **Who** receives it: rows in its **Recipients** table.
- **What** they receive: a Jinja subject and message.
- **How** it is delivered: rows in its **Channels** table.

Each delivery is logged in **Notification Delivery**: one row per recipient and channel, with a status (Sent, Queued, Skipped with a reason, or Error).

## Events

| Event | Fires |
|---|---|
| `after_insert`, `after_save` | when a document of the rule's type is created or saved |
| `on_transition` | on a workflow transition (only the **Workflow actions** listed, if any); templates also get `action`, `from_state`, `to_state`, `from_label`, `to_label`, `comment` |
| `days_before`, `days_after` | once a day, N days before or after a date field |
| `code` | when code triggers the rule's **Code event** (`event_key`) |

## Recipients

Each row in the **Recipients** table adds recipients of one kind:

- **Author**: the document's owner.
- **Role**: every active user with the role.
- **User**: one user.
- **Document field**: the user or email address in a field of the document. The value can also come through a link, e.g. `client.email`.
- **Email**: a literal email address.
- **Assignees**: users with open ToDos on the document.
- **Followers**: users who follow the document.
- **Previous actor**: on a workflow transition, whoever performed the previous workflow action.
- **Next actors**: on a workflow transition, users who can take the next step and can read the document.
- **Event recipients**: the users the code passes when it triggers the event.

A row may have a condition, e.g. `doc.priority == 'High'`. Deactivated accounts are skipped unless an **Email** row names them. The user who caused the event is skipped unless **Also notify who did it** is checked.

## Templates

The subject and message are Jinja templates, rendered in a sandbox, in each recipient's language. They can use:

- `doc`: the document;
- `doctype`;
- `event`;
- `title`: the document's title;
- `actor`: the name of the user who caused the event;
- `actor_email`;
- `url`: a link to the document;
- the event's own variables.

`{{ _('…') }}`, `ngettext` and `pgettext` translate. A channel row can override the text, e.g. with a short SMS message.

## Code events

Code does not compose a notification itself. It triggers an event, and the event's rules decide everything else:

```python
from grunt.notification.events import trigger

await trigger(
    "my_app.order.paid",
    doc=order, doctype="Order",
    recipients=[order["customer_email"]],   # "Event recipients"
    extra={"amount": order["total"]},        # template variables
)
```

Any value in `extra` may be a callable. A callable is evaluated in each recipient's language, which is useful for text the code builds itself.

An app registers its events in `hooks.py`:

```python
notification_events = [
    {"key": "my_app.order.paid", "label": "Order paid", "doctype": "Order", "variables": ["amount"]},
]
```

It also ships a *standard* rule for each event, in `<module>/records/notification/<name>/<name>.json`. In developer mode, saving the rule in the desk writes this file for you.

If no rule for an event is enabled, the event sends nothing.

### Standard rules on a site

`grunt migrate` brings standard rules in line with the app's files. Two exceptions:

- A rule an administrator edited on the site is marked **Changed on this site**, and migrate keeps it as edited.
- **Reset to standard** discards the local edits and follows the app's files again.

## Channels

The core ships three channels: `in_app` (the bell), `web_push` and `email`. An app can add its own channel in `hooks.py`:

```python
notification_channels = ["my_app.sms.SmsChannel"]
```

A channel subclasses `grunt.notification.channels.Channel`:

- It sets `name` and `label`.
- It implements `send(session, recipient, message, *, delivery)`, which returns an `Outcome`.
- A queued channel settles its delivery row later with `grunt.notification.delivery_log.settle`.
