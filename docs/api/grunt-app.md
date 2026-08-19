# GruntApp SDK

The `grunt` object is the primary API for app developers. It is available in:

- Controller methods (`validate`, `before_save`, `after_insert`, etc.)
- Hook functions (`@on("after_insert", ...)`)
- Server Scripts (available as `grunt` global)

```python
from grunt.app import grunt
```

---

## Document CRUD

### `grunt.get_doc(doctype, id_or_name)`

Fetch a single document by id or name.

Enforces `read` permission and triggers read hooks (`before_read`, `after_read`).

Pass a doctype name for a plain dict, or a `Document` subclass for a typed
controller instance — same fields as the class declares, with autocomplete:

```python
invoice = await grunt.get_doc("Invoice", "INV-0001")   # dict
print(invoice["amount"])

invoice = await grunt.get_doc(Invoice, "INV-0001")      # typed Invoice instance
print(invoice.amount)
```

### `grunt.find_doc(doctype, id_or_name)`

Same as `get_doc`, but returns `None` instead of raising a 404 when the
document doesn't exist. Use this whenever "not found" is an expected outcome
you're about to branch on, not an error to propagate:

```python
existing = await grunt.find_doc("Customer", {"email": email})
if existing is None:
    ...
```

### `grunt.get_doc_instance(doctype, id_or_name)`

Like the typed form of `get_doc`, but for when the doctype is only known as a
string at runtime (e.g. a workflow or task operating on a caller-supplied
doctype name, not a fixed class) — resolves the controller class from the
doctype registry and returns a bound instance:

```python
doc = await grunt.get_doc_instance(doctype_name, doc_id)
await doc.after_save()
```

### `grunt.new_doc(doctype, data)`

Create a new document and return it (runs all lifecycle hooks).

```python
order = await grunt.new_doc("Order", {
    "customer": "CUST-001",
    "status": "Draft",
    "amount": 1500.0,
})
```

### `grunt.save_doc(doctype, id_or_name, data)`

Update an existing document (partial update — omitted fields unchanged).

```python
await grunt.save_doc("Order", order["id"], {"status": "Confirmed"})
```

### `grunt.delete_doc(doctype, id_or_name)`

Delete a document (runs `before_delete` / `after_delete` hooks).

### `grunt.get_list(doctype, *, filters, fields, limit, page, order_by, order, search)`

Fetch a list of documents.

Enforces `read` permission and triggers read hooks (`before_read`, `after_read`).

```python
open_orders = await grunt.get_list(
    "Order",
    filters={"status": "Open", "amount__gte": "1000"},
    fields=["id", "name", "customer", "amount"],
    limit=50,
    order_by="created_at",
    order="desc",
)
```

### `SomeController.objects` — typed query builder

Every `Document` subclass gets a fluent, chainable query builder — a typed
alternative to `get_list`/`db.get_all` for controller and script code:

```python
from grunt.auth.doctypes.User.user import User

active_admins = await (
    User.objects
        .filter(is_active=True, is_superadmin=True)
        .order_by("-created_at")
        .limit(20)
        .all()
)

user = await User.objects.filter(email=email).first()   # None if no match
total = await User.objects.filter(is_active=True).count()
taken = await User.objects.filter(email=email).exists()

created = await User.objects.create(email=email, first_name="A", last_name="B")
user, was_created = await User.objects.get_or_create(
    email=email, defaults={"first_name": "A", "last_name": "B"},
)
```

Filter keys accept the same operator suffixes as `get_list`/`db.get_all`:
`__gt`, `__gte`, `__lt`, `__lte`, `__in`, `__nin`, `__like`, `__ilike`,
`__isnull`, `__ne`.

### `grunt.count(doctype, *, filters)`

Count documents matching filters.

```python
total = await grunt.count("Order", filters={"status": "Open"})
```

### `grunt.bulk_insert(doctype, records)`

Create multiple documents in a single DB round-trip (no hooks).

```python
ids = await grunt.bulk_insert("LogEntry", [
    {"level": "info", "message": "Started"},
    {"level": "info", "message": "Done"},
])
```

### `grunt.bulk_update(doctype, filters, values)`

Update multiple documents matching filters in a single query (no hooks).

```python
count = await grunt.bulk_update(
    "Order",
    filters={"status": "Draft"},
    values={"status": "Cancelled"},
)
```

---

## Database helpers (`grunt.db`)

### `grunt.db.get_value(doctype, filters, fieldname)`

Return a single field value from the first matching document.

Low-level direct DB access: no permission checks and no lifecycle/read hooks.

```python
name = await grunt.db.get_value("Customer", {"email": "a@b.com"}, "full_name")
```

### `grunt.db.set_value(doctype, doc_id, fieldname, value)`

Update a single field on a document.

Low-level direct DB access: no permission checks and no lifecycle/read hooks.

```python
await grunt.db.set_value("Invoice", invoice_id, "status", "Paid")
```

### `grunt.db.exists(doctype, filters)`

Return the document `name` if a match exists, else `None`.

Low-level direct DB access: no permission checks and no lifecycle/read hooks.

```python
if await grunt.db.exists("Customer", {"email": "a@b.com"}):
    grunt.throw("Customer already registered")
```

### `grunt.db.get_all(doctype, *, filters, fields, limit, order_by, order)`

Fetch a list of documents as plain dicts (lower-level than `get_list`).

Low-level direct DB access: no permission checks and no lifecycle/read hooks.

---

## Whitelisted methods (`@grunt.whitelist`)

Any module-level `async def` becomes a callable HTTP RPC endpoint
(`/api/v1/method/<dotted.path>`) when decorated:

```python
@grunt.whitelist()
async def approve_order(order_id: str) -> dict:
    return await grunt.save_doc("Order", order_id, {"status": "Approved"})
```

- `allow_guest=True` — skip authentication; the method runs with `user=None`.
- `roles=[...]` — require the caller to be superadmin or hold at least one of
  the listed roles. Enforced on every call — through the HTTP dispatcher *and*
  when called directly from other Python code (a hook, a script, a test) —
  there's no call path that skips it:

  ```python
  @grunt.whitelist(roles=["superadmin"])
  async def delete_workspace(name: str) -> bool:
      await grunt.delete_doc("AppMenu", name)
      return True
  ```

- `require=predicate` — for checks that aren't a static role list. Receives
  the current user, returns (or awaits to) a bool:

  ```python
  @grunt.whitelist(require=lambda user: user.is_superadmin or user.id == target_id)
  async def reset_own_or_admin(target_id: str) -> None: ...
  ```

`roles=`/`require=` raise `403` before the method body runs. They're for a
genuine *static* gate — permission that depends on the specific document
being acted on (ownership, a flag on the target record) still belongs in the
method body, via `grunt.can_read`/`can_write`/`can_delete`/... or the
permission checks `get_doc`/`save_doc`/`delete_doc` already enforce.

### Response schemas (`Schema`)

Declare once which fields of a document a whitelisted method exposes, instead
of rebuilding the same dict literal in every endpoint:

```python
from grunt.document.schema import Schema

class UserPublic(Schema):
    fields = ("name", "email", "full_name", "roles", "is_superadmin")

@grunt.whitelist()
async def whoami() -> dict:
    user = await grunt.get_current_user()
    return UserPublic.dump(user)

@grunt.whitelist(roles=["superadmin"])
async def list_users_api() -> list[dict]:
    return UserPublic.dump_many(await User.objects.limit(1000).all())
```

`Schema` is a straight identity mapping (output key == field name) — it
doesn't rename or alias fields. If a response needs different key names than
the underlying document, build that dict by hand.

---

## Notifications & real-time

### `grunt.notify(users, subject, message, doctype, doc_id, push)`

Create persistent bell notifications.

```python
await grunt.notify(
    users=["manager@company.com"],
    subject="New order requires approval",
    message=f"Order #{order['name']} is waiting for your approval.",
    doctype="Order",
    doc_id=order["id"],
)
```

### `grunt.publish(user, event, data, message, type)`

Send a transient WebSocket message to one user.

```python
await grunt.publish(
    user=grunt.session.user,
    event="msgprint",
    message="Document saved successfully",
    type="success",
)
```

### `grunt.broadcast(event, data, message, type)`

Broadcast to ALL connected users.

---

## Session info (`grunt.session`)

```python
grunt.session.user          # current user email
grunt.session.full_name     # current user full name
grunt.session.roles         # list of role names
grunt.session.is_superadmin # bool
grunt.session.has_role("Manager", "Accountant")  # bool
```

---

## Context outside a request

Inside a controller method, hook, or whitelisted call, `grunt.get_doc` /
`grunt.db` / `User.objects` / etc. already know which session, engine, and
user to use — it's set up for you before your code ever runs. Writing a CLI
command or a background task means setting that context up yourself first:

```python
async with grunt.context(session, engine, user):
    await grunt.get_doc("Invoice", invoice_id)

# No specific user — run as the internal system identity (bypasses
# per-user permission checks, same as an "All"/no-permissions doctype):
async with grunt.system_context(session):
    await grunt.new_doc("ActivityLog", {...})
```

A helper that's always called from *somewhere* with an already-active context
(the common case — most functions called from a controller or a whitelisted
method) shouldn't take `session` as its own parameter at all. Read it via
`require_session()` instead of threading it through every call:

```python
from grunt.context import require_session

async def get_user_by_email(email: str) -> User | None:
    async with grunt.system_context(require_session()):
        return await User.objects.filter(email=email).first()
```

Reserve an explicit `session` parameter for code that's genuinely called
*without* an active context: a background task with its own freshly-created
session (`async_session_factory()`), a scheduler job, or site bootstrap/
migration code — none of these have anything to read `require_session()` from.

### Public REST routers — `GruntRouter`

Routes defined via `GruntRouter()` (instead of a plain FastAPI `APIRouter()`)
get `grunt.context` activated automatically for the whole request — no manual
`async with grunt.context(...)` needed inside the route body:

```python
from grunt.api.router import GruntRouter

router = GruntRouter()                      # requires an authenticated user
router = GruntRouter(optional_auth=True)    # guests allowed; context still set up
```

Routes that still need a *real* user even on an `optional_auth=True` router
keep their own `Depends(current_user)` — `optional_auth` only controls
whether the router activates context for guests, not whether a given route
requires one.

---

## Error handling

### `grunt.throw(message, title)`

Raise a user-facing error (returned as HTTP 422).

```python
if self.amount <= 0:
    grunt.throw("Amount must be greater than zero", title="Validation Error")
```

---

## Meta

### `grunt.get_meta(doctype)`

Return the DocType definition (Pydantic model).

```python
meta = await grunt.get_meta("Invoice")
field_names = [f.fieldname for f in meta.fields]
```

---

## Translation

### `grunt._(source)`

Translate a string using the current request locale.

```python
msg = grunt._("Document saved")
```
