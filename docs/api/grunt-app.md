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

```python
invoice = await grunt.get_doc("Invoice", "INV-0001")
print(invoice["amount"])
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
