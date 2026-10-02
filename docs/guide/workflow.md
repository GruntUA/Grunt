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
  permission and User Permissions. Inside it, `current_transition()` tells the
  controller which transition is being applied:

  ```python
  from grunt.workflow.engine import current_transition

  async def validate(self):
      if (t := current_transition()) and t.to_state == "Approved":
          self.approved_by = self.user.email
  ```

- After it: an `ActivityLog` entry (`action="Workflow"`), the comment (if any)
  on the document's comment thread, notifications, the `on_transition` hook.

## State options

| Field | Effect |
|---|---|
| `edit_roles` | Only these roles may edit or delete the document in this state (transitions are not affected). Empty — anyone with write permission. |
| `update_field` / `update_value` | On entering the state, the value is written into the field — e.g. `published = 1`. |

## Transition options

| Field | Effect |
|---|---|
| `allowed_roles` | Who sees the button / may apply it (System Manager always may). |
| `condition` | `simpleeval` expression over `doc` and `user`. |
| `prompt_fields` | Fields to fill in a dialog before applying. |
| `require_comment` | The dialog asks for a comment (`values["__comment"]` over RPC). |
| `on_edit` | Not a button: when a user allowed this transition **edits** the document in `from_state`, the edit is saved as this transition. Such a user also can't delete the document in that state. |
| `notify` | `owner` (author), `previous` (who performed the previous workflow action), `next` (users who can take a button transition out of the new state *and* can read this document — roles, `match` rules, User Permissions). The actor is never notified. |
| `notify_email` | Also send the notification by email. |

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
     "allowed_roles": "Writer", "notify": "next", "notify_email": 1},
    {"from_state": "Review", "to_state": "Published", "action": "Publish",
     "allowed_roles": "Editor", "notify": "previous", "notify_email": 1},
    {"from_state": "Review", "to_state": "Rework", "action": "Send back",
     "allowed_roles": "Editor", "require_comment": 1, "notify": "previous", "notify_email": 1},
    {"from_state": "Rework", "to_state": "Review", "action": "Send for review",
     "allowed_roles": "Writer", "notify": "next", "notify_email": 1},
    {"from_state": "Published", "to_state": "Review", "action": "Edited by author",
     "allowed_roles": "Writer", "on_edit": 1, "notify": "next", "notify_email": 1}
  ]
}
```

Ship it with the app as a fixture (`fixtures/02_workflow.json` with
`"doctype": "Workflow"` and `"sync": true`) and apply it with
`grunt db migrate`. A real-world case: `apps/mlt_portal/mlt_portal/fixtures/02_workflow.json`
(authors scoped to sections by User Permissions — `next` notifies only the
reviewers of that section).
