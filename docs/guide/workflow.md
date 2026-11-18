# Workflow: states, approvals and review

A **Workflow** document (`document_type` = the DocType it governs) turns one
field of that DocType (`workflow_state_field`, usually `status`) into a state
machine. The form shows the state read-only and a button per transition the
user may take.

## Rules the framework enforces

While a DocType has an active workflow:

- **The state moves only by transitions.** A new document starts in the
  initial state; a save that changes the state field is rejected (403). The
  internal system user — fixtures, imports, migrations — is exempt.
- **A transition is a regular save.** It runs through the full update
  pipeline: `validate`/`before_save`/`after_save`, hooks, versions, write
  permission and role scopes. Inside it, `current_transition()` tells the
  controller which transition is being applied:

  ```python
  from grunt.workflow.transition import current_transition


  async def validate(self):
      if (t := current_transition()) and t.to_state == "Approved":
          self.approved_by = self.user  # the session user's email
  ```

- After it: an `ActivityLog` entry (`action="Workflow"`), the comment (if any)
  on the document's comment thread, the `on_transition` Notification rules,
  the `on_transition` hook.

## State options

| Field | Effect |
|---|---|
| `edit_roles` | Only these roles may edit or delete the document in this state (transitions are not affected). Empty — anyone with write permission. |
| `update_field` / `update_value` | On entering the state, the value is written into the field — e.g. `published = 1`. |
| `message` | Shown as a banner over the form while the document is in this state, in the state's `color` — e.g. “Awaiting review, editing is locked”. |

## Transition options

| Field | Effect |
|---|---|
| `allowed_roles` | Who sees the button / may apply it (System Manager always may). |
| `condition` | `simpleeval` expression over `doc` and `user`. A condition that fails to evaluate closes the transition (logged as `workflow.condition_eval_failed`). |
| `prompt_fields` | Fields to fill in a dialog before applying. |
| `require_comment` | The dialog asks for a comment (`values["__comment"]` over RPC). |
| `on_edit` | Not a button: when a user allowed this transition **edits** the document in `from_state`, the edit is saved as this transition. Such a user also can't delete the document in that state. |
| `deny_self_approval` | The document's author (`owner`) cannot take it, whatever their roles — someone else has to approve. **Next actors** leave the author out too. |
| `confirm` | Ask “are you sure?” before applying — for archiving, rejecting and other steps that are hard to undo. |

## Notifications

A transition does not notify anyone by itself. Notifications come from **Notification** rules with the event `on_transition` (see [notifications.md](notifications.md)):

- **Workflow actions**: the transitions the rule reacts to, one button label per line. Leave it empty to react to every transition.
- **Recipients**:
  - **Author**: the document's author.
  - **Previous actor**: whoever performed the previous workflow action.
  - **Next actors**: users who can take a button transition out of the new state *and* can read this document. Roles, their scopes (a role held for one department counts only for that department's documents) and `match` rules all count.
  - Any other recipient kind, e.g. a role or a document field.
- **Template variables**: `action`, `from_state`, `to_state`, `from_label`, `to_label`, `comment` and `title`.

The rules run inside the transition's transaction. The user who made the transition is not notified unless the rule says so.

## Awaiting my action

The **My work** panel on the home page (`/app`) has an **Awaiting me** tab: the workflow documents the user can move on now, newest first, with the state and the buttons waiting for them. When there are any, the panel opens on that tab. The list comes from `get_my_work` (`awaiting`, `counts.awaiting`), built by `grunt.workflow.inbox.awaiting_actions` from the transitions themselves, with no table of its own:

- A document counts only when a button transition out of its state has `allowed_roles` and the user actually holds one of those roles. A System Manager without the role is not shown every document on the site. This is the same rule as **Next actors**.
- A scoped role counts only for the documents in its scope. The user must be able to read the document, and on a `deny_self_approval` transition their own document is not shown as awaiting them.
- `condition` is not checked: a transition waiting for a field to be filled is still the user's work.

## Actions on a transition

- In an app: the `on_transition` hook (`hooks.py`), with `doc`, `from_state`, `to_state`, `action`, `comment` and `user`.
- Without code: a **Server Script** of type *DocType Event* with the event `on_transition`. Besides `doc`, the script sees `transition` — a dict with `action`, `from_state`, `to_state` and `comment`:

```python
if transition["to_state"] == "Approved":
    grunt.db.set_value("Contract", doc["name"], "approved_by", grunt.session.user)
```

## Example: publication with review

Authors (role *Writer*) draft and send for review; editors publish or send
back with a comment; an author's edit of a published article takes it off
the site until it is reviewed again.

```json
{
  "document_type": "Article",
  "workflow_state_field": "status",
  "states": [
    {"state": "Draft", "is_initial": 1, "update_field": "published", "update_value": "0"},
    {"state": "Review", "edit_roles": "Editor", "update_field": "published", "update_value": "0"},
    {"state": "Rework", "update_field": "published", "update_value": "0"},
    {"state": "Published", "update_field": "published", "update_value": "1"}
  ],
  "transitions": [
    {"from_state": "Draft", "to_state": "Review", "action": "Send for review",
     "allowed_roles": "Writer"},
    {"from_state": "Review", "to_state": "Published", "action": "Publish",
     "allowed_roles": "Editor"},
    {"from_state": "Review", "to_state": "Rework", "action": "Send back",
     "allowed_roles": "Editor", "require_comment": 1},
    {"from_state": "Rework", "to_state": "Review", "action": "Send for review",
     "allowed_roles": "Writer"},
    {"from_state": "Published", "to_state": "Review", "action": "Edited by author",
     "allowed_roles": "Writer", "on_edit": 1}
  ]
}
```

Ship it with the app as a fixture (`fixtures/02_workflow.json` with
`"doctype": "Workflow"` and `"sync": true`) and apply it with
`grunt migrate`. Ship the notifications as standard records:
`records/notification/…`, written for you when you save a rule with
**Standard** checked in developer mode.

There are two rules for this example:

- *Send for review* and *Edited by author* go to **Next actors**.
- *Publish* and *Send back* go to **Previous actor**.

A real-world case is `apps/mlt_portal`: its workflow is in `fixtures/02_workflow.json` and its rules are in `records/notification/`. Authors there hold their role within their sections (scoped roles), so **Next actors** reaches only the reviewers of that section.
