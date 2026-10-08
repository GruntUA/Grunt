# Service levels (SLA)

A **Service Level** puts a deadline on documents of one DocType, warns before
it and escalates when it is missed. It needs no code: create a `ServiceLevel`
record in Desk.

| Field | Meaning |
|-------|---------|
| Document type | The DocType to track |
| Applies when | Optional expression on `doc` (`doc.get('priority') == 'High'`) |
| Time allowed + Unit | `N` Hours, Days or Working days (Mon–Fri) |
| Count from field | Date/Datetime the clock starts from (default `created_at`) |
| Deadline field | Optional Date/Datetime field of the document. It is filled with the deadline when empty, and a date set by hand there overrides the policy |
| Done statuses / Or done when | Statuses (one per line) or an expression that stop the clock |
| Warn hours before | Early warning; `0` turns it off |
| Notify / Escalate to | Recipients for the warning and the breach (escalation only on breach) |
| Channel | In-app, email or both |

Recipients use the NotificationRule syntax: `owner`, `role:Manager`,
`user@example.com`, `{field:assigned_to}`, plus `{field:executor.user_id}`, which
follows a Link (for example from an Employee to their user account).

## What happens

```
save (condition true) ──► On track ──► At risk ──► Breached
                              │     (warning)   (escalation)
                              └────► Met / Met late  (done status reached)
```

- **On save** (`after_save` on every DocType) the clock starts, follows a
  hand-edited deadline field, or stops once the document is done. A finished
  clock is history: reopening the document does not restart it.
- **Every 10 minutes** `grunt.notification.sla.check_deadlines` moves open
  clocks to *At risk* or *Breached* and sends the notifications, once per state.
- Day-based deadlines end at the close of the local day
  (`DEFAULT_TIMEZONE`, `Europe/Kyiv` by default).

Each clock is a `ServiceLevelStatus` row (list and calendar views, filter by
status). Anyone who can read the document can read its rows.

Example for incoming letters: Document type `IncomingLetter`, 30 Days, Count
from `reg_date`, Deadline field `due_date`, Done statuses `Виконано` and
`Архів`, Notify `{field:executor.user_id}`, Escalate to `role:Канцелярія`.
