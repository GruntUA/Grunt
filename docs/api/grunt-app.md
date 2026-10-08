# The `grunt` API

The `grunt` package is the primary API for app developers. It is available in:

- Controller methods (`validate`, `before_save`, `after_insert`, etc.)
- Hook functions (`@on("after_insert", ...)`)
- Server Scripts (available as `grunt` global)

```python
import grunt
```

One namespace: translation and logging (`from grunt import _, log`), request helpers
(`grunt.whitelist`, `grunt.throw`, `grunt.get_user`, `grunt.get_session`,
`grunt.log_error`) and the document API below (bound from the internal `GruntApp`
singleton). Rarely used plumbing (`set_user`, `clear_context`, `queue_email`, …)
is imported from its own module.

`grunt.get_user()` never invents a user: outside a request or
`grunt.context(...)` / `grunt.system_context(...)` it raises a 401.

---

## Document CRUD

### `grunt.get_doc(doctype, id_or_name)`

Fetch a single document by id or name.

Enforces `read` permission and triggers read hooks (`before_read`, `after_read`).

Pass a doctype name for a plain dict, or a `Document` subclass for a typed
controller instance — same fields as the class declares, with autocomplete:

```python
invoice = await grunt.get_doc("Invoice", "INV-0001")  # dict
print(invoice["amount"])

invoice = await grunt.get_doc(Invoice, "INV-0001")  # typed Invoice instance
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
order = await grunt.new_doc(
    "Order",
    {
        "customer": "CUST-001",
        "status": "Draft",
        "amount": 1500.0,
    },
)
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
    User.objects.filter(is_active=True, is_superadmin=True).order_by("-created_at").limit(20).all()
)

user = await User.objects.filter(email=email).first()  # None if no match
total = await User.objects.filter(is_active=True).count()
taken = await User.objects.filter(email=email).exists()

created = await User.objects.create(email=email, first_name="A", last_name="B")
user, was_created = await User.objects.get_or_create(
    email=email,
    defaults={"first_name": "A", "last_name": "B"},
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

### `grunt.aggregate(doctype, *, filters, group_by, aggregations, order_by, order, limit)`

GROUP BY over the rows the current user may read: read permission, row-level
`match` rules and shares apply, and permission-hidden fields cannot be used.
`group_by` takes fieldnames or a period: `day(f)`, `month(f)`, `quarter(f)`,
`year(f)` (labels `2026-09-23`, `2026-09`, `2026-Q3`, `2026`). Without
`aggregations`, each group gets a `count`.

```python
rows = await grunt.aggregate(
    "Invoice",
    filters={"status": "Paid"},
    group_by="month(posting_date)",
    aggregations={"total": "sum(amount)", "n": "count()"},
    order_by="month(posting_date)",
    order="asc",
)
# [{"month(posting_date)": "2026-09", "total": 4200.0, "n": 7}, ...]
```

`grunt.db.aggregate` takes the same arguments without any permission checks.

### `grunt.bulk_insert(doctype, records)`

Create multiple documents in a single DB round-trip (no hooks).

```python
ids = await grunt.bulk_insert(
    "LogEntry",
    [
        {"level": "info", "message": "Started"},
        {"level": "info", "message": "Done"},
    ],
)
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

## REST API standard — two transports, not one

The HTTP surface has exactly two sanctioned shapes. Every new endpoint must be
one or the other — never a bespoke third pattern.

**1. REST `/api/v1/docs/{doctype}(/{id})`** — the 5 base CRUD verbs, and
*nothing else*:

```
GET    /api/v1/docs/{doctype}             list
GET    /api/v1/docs/{doctype}/{id}        get one
POST   /api/v1/docs/{doctype}             create
PUT    /api/v1/docs/{doctype}/{id}        update
DELETE /api/v1/docs/{doctype}/{id}        delete → 204 No Content, empty body
```

Implemented once, generically, in `grunt/api/v1/docs/crud.py` — it already
works for any registered DocType, no per-doctype code needed.

**2. RPC `/api/v1/method/{dotted.path}`** — everything else: any action that
isn't one of the 5 verbs above, any sub-resource of a document (comments,
bookmarks, versions, tree structure, workflow transitions, link-field search,
export/print, bulk operations, cross-doctype search, reports...), and any
operation that doesn't map to a single resource at all. See "Whitelisted
methods" below — the dotted path is the Python import path to the function
(or `module.Class.method` for a class method/staticmethod — the dispatcher
supports both).

Do **not** invent action verbs in a `/docs/{doctype}/...` path
(`/docs/{doctype}/some-action`) — that used to happen (`link_search`,
`bulk-delete`, `tree/move/{id}`...) and it's why this rule exists now. If an
operation isn't pure CRUD on one document, it's a whitelisted method, full
stop. The dispatcher only exposes `GET`/`POST` — a formerly-PATCH/DELETE
action becomes a `POST` whitelisted method.

Generic (any-doctype) document operations that aren't tied to one specific
DocType's own controller live as `@staticmethod`s on the base `Document`
controller (`grunt/document/mixins/*_rpc.py`, mixed into
`grunt.document.base.Document`) rather than in the `grunt/api/` tree —
`grunt.document.base.Document.get_tree`,
`grunt.document.base.Document.link_search`,
`grunt.document.base.Document.print`, etc. An operation specific to one
DocType (e.g. running a saved `Report`) belongs in *that* DocType's own
controller file instead — `grunt.reports.doctypes.Report.report.run`,
following the same pattern as `grunt.activity.doctypes.ActivityLog
.activity_log.list_activity`.

Name the method for what it does, without repeating context the class/module
already supplies: `Document.get_tree`/`Document.move_tree_node` (not
`Document.get`/`Document.move` — too generic once flattened onto one class,
and `get` would collide with `Document.get(fieldname)`), `Document
.link_search` (not `Document.search` — same reason), `Document
.apply_workflow_transition` (not `Document.apply_transition` — ambiguous
outside the workflow context). Drop a qualifier only when nothing is lost by
dropping it — `Document.get_versions`/`get_activity_log`/`get_timeline`,
`Document.get_comments`/`add_comment`, `Document.get_backlinks`.

### List/query parameter conventions (REST list endpoints)

- **Pagination**: `page` (1-based) + `per_page` — never `limit`/`page_length`.
- **Filtering**: `filter[field__op]=value` / `fast_filter[field__op]=value`
  (`fast_filter` is lower precedence, `filter` overrides it for the same
  key) — parsed by `grunt.api.v1.docs.utils.parse_query_filters`. RPC methods
  take the equivalent as one `filters: dict[str, Any] | None` kwarg (a JSON
  object) instead of bracket-style query keys — Python identifiers can't
  contain `[`/`]`, and the method dispatcher already JSON-decodes any
  query/body value that looks like an object.
- **Search**: `search` (never `q`).
- **Sort**: `sort_by` + `sort_order`, the latter always constrained to
  `^(asc|desc)$`.

### Response envelope

Every JSON response — success or error — uses the helpers in
`grunt/api/v1/schemas/response.py`:

```python
from grunt.api.v1.schemas.response import ok, ok_list

return ok(doc)  # {"success": true, "data": doc}
return ok_list(items, total=n, page=p, per_page=pp)  # + "meta": {...}
return ok(message="Done")  # {"success": true, "message": "Done"}
```

Errors go through `grunt.errors.error_body`/`APIError` —
`{"success": false, "error": {"code", "message", "details"}}`. Never return a
bare Pydantic model or a hand-built dict — both `/api/v1/docs/*` and
`/api/v1/method/*` follow this envelope contract (for method calls the wrapper
is applied by the dispatcher), no exceptions. The dispatcher
already does this wrapping automatically for whitelisted methods (`return`
the raw value, not `ok(...)`) — see below.

The one deliberate exception: binary/streaming responses (CSV/XLSX export,
PDF/HTML print) return a raw `Response`/`StreamingResponse`, unwrapped — the
method dispatcher forwards any `Response` instance verbatim instead of
JSON-wrapping it.

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
    user = grunt.get_user()
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
    user=grunt.get_user().email,
    event="msgprint",
    message="Document saved successfully",
    type="success",
)
```

---

## Current user (`grunt.get_user()`)

```python
user = grunt.get_user()  # the User the request/task runs as; 401 when there is none
user.email
user.full_name
user.roles  # list of role names
user.has_role("Manager", "Accountant")  # bool
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
`grunt.get_session()` instead of threading it through every call:

```python
async def get_user_by_email(email: str) -> User | None:
    async with grunt.system_context(grunt.get_session()):
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

router = GruntRouter()  # requires an authenticated user
router = GruntRouter(optional_auth=True)  # guests allowed; context still set up
```

Routes that still need a *real* user even on an `optional_auth=True` router
keep their own `Depends(current_user)` — `optional_auth` only controls
whether the router activates context for guests, not whether a given route
requires one.

---

## Error handling

### `grunt.throw(message, code="ERROR", title="")`

Raise a user-facing error. `code` picks the HTTP status (`VALIDATION_ERROR` → 422,
`NOT_FOUND` → 404, `PERMISSION_DENIED` → 403, `CONFLICT` → 409, `UNAUTHORIZED` → 401).

```python
if self.amount <= 0:
    grunt.throw("Amount must be greater than zero", code="VALIDATION_ERROR")
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
