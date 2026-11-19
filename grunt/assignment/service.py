"""Assignment Service - automatic assignment of documents (FRAPPE_GAP_PLAN #9).

On every insert and save of a document (grunt/core_events.py):

1. Each enabled rule of the DocType first looks after its own open assignment
   of the document (a ToDo with ``assignment_rule``): ``close_condition``
   matches - closed as done; ``unassign_condition`` matches - cancelled.
2. While some rule's assignment of the document is still open, nothing new is
   assigned. Otherwise the rules are tried by ``priority`` (highest first) and
   the **first** that matches - its ``filters`` and its ``days`` - assigns:

   * ``Everyone`` - every candidate (the rule's behaviour before #9);
   * ``Round Robin`` - the next candidate after ``last_user`` (``weight`` turns
     in a row);
   * ``Load Balancing`` - the candidate with the fewest open assignments per
     unit of ``weight``;
   * ``Based on Field`` - the user in the document's ``field``.

   Candidates: the rule's ``users``, else the holders of ``assign_to_role``
   whose role scope covers the document, else ``assign_to_user``.

So a document that reaches a state later (saved, not only inserted) gets its
assignment then, and only once per rule.
"""

import json
from typing import Any

from grunt.assignment.conditions import EVERYONE, matches
from grunt.db.api import GruntDB
from grunt.local import require_session, system_context
from grunt.log import log
lazy from grunt.assignment.doctypes.AssignmentLog.assignment_log import AssignmentLog
lazy from grunt.document.api import documents
lazy from grunt.metadata.registry import doctype_registry
lazy from grunt.notification.date_rules import local_today
lazy from grunt.permissions.scopes import holders_for
lazy from grunt.tasks.doctypes.ToDo.to_do import auto_assign_note

_db = GruntDB()  # stateless: reads through the context's session

OPEN = ("Open", "In Progress")
_RULE_FIELDS = [
    "name",
    "doctype_target",
    "filters",
    "priority",
    "rule",
    "field",
    "assign_to_role",
    "assign_to_user",
    "last_user",
    "unassign_condition",
    "close_condition",
    "days",
    "due_date_field",
]
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError, TypeError:
        return default


class AssignmentService:
    """Оркестратор правил автоматичного призначення документів."""

    async def evaluate_and_assign(self, doctype: str, doc: dict[str, Any]) -> None:
        """Run the DocType's rules for *doc* - see the module docstring.

        Caller must already have an active grunt context - called from the
        document lifecycle hooks (grunt/core_events.py).
        """
        try:
            rules = await self._get_enabled_rules(doctype)
            if rules:
                await self.apply_matching_rules(doctype, rules, doc)
        except Exception as exc:
            log.exception("assignment.evaluate_error", doctype=doctype, exc_info=exc)

    async def apply_matching_rules(
        self,
        doctype: str,
        rules: list[dict[str, Any]],
        doc: dict[str, Any],
    ) -> None:
        """Close / unassign by every rule, then let the first matching rule assign."""
        doc_id = str(doc.get("name") or doc.get("id") or "")
        still_open = False
        for rule in rules:
            if await self._settle_open(doctype, doc_id, rule, doc):
                still_open = True
        if still_open:
            return
        today = DAYS[local_today().weekday()]
        for rule in rules:
            days = _json(rule.get("days"), [])
            if days and today not in days:
                continue
            if not matches(rule.get("filters") or {}, doc):
                continue
            if await self.apply_rule(doctype, rule, doc):
                return

    async def apply_rule(self, doctype: str, rule: dict[str, Any], doc: dict[str, Any]) -> bool:
        """Assign *doc* by *rule*; True when someone was assigned."""
        emails = await self.pick(doctype, rule, doc, persist=True)
        if not emails:
            log.info("assignment.nobody", doctype=doctype, rule=rule.get("name"))
            return False
        method = rule.get("rule") or EVERYONE
        due = doc.get(rule["due_date_field"]) if rule.get("due_date_field") else None
        for email in emails:
            try:
                await self._create_todo(doctype, doc, email, rule.get("name"), due)
                await AssignmentLog.create(
                    rule_id=rule.get("name"),
                    doctype_affected=doctype,
                    document_id=str(doc.get("name") or ""),
                    assigned_to=email,
                    assignment_method=method,
                    status="Success",
                )
            except Exception as exc:
                log.exception("assignment.assign_error", doctype=doctype, user=email, exc_info=exc)
        log.info(
            "assignment.assigned",
            doctype=doctype,
            doc_id=doc.get("name"),
            rule=rule.get("name"),
            method=method,
            users=emails,
        )
        return True

    async def pick(
        self, doctype: str, rule: dict[str, Any], doc: dict[str, Any], *, persist: bool
    ) -> list[str]:
        """Whom *rule* assigns *doc* to. *persist* - a round robin moves its turn
        (False for a preview)."""
        method = rule.get("rule") or EVERYONE
        if method == "Based on Field":
            user = doc.get(rule.get("field") or "")
            return [str(user)] if user else []
        candidates = await self._candidates(doctype, rule, doc)
        if not candidates or method == EVERYONE:
            return [email for email, _weight in candidates]
        if method == "Round Robin":
            chosen = await self._next_in_turn(rule, candidates)
            if persist:
                async with system_context(require_session()):
                    await _db.set_value("AssignmentRule", rule["name"], "last_user", chosen)
                rule["last_user"] = chosen
            return [chosen]
        if method == "Load Balancing":
            loads = await self._open_counts([email for email, _w in candidates])
            return [min(candidates, key=lambda c: loads.get(c[0], 0) / max(1, c[1]))[0]]
        log.warning("assignment.unknown_method", rule=rule.get("name"), method=method)
        return []

    # Helpers

    async def _candidates(
        self, doctype: str, rule: dict[str, Any], doc: dict[str, Any]
    ) -> list[tuple[str, int]]:
        """``(user, weight)`` in the rule's order: its users, else the role's
        holders covering *doc*, else the single ``assign_to_user``."""
        users = rule.get("users") or []
        if users:
            return [(str(u["user"]), int(u.get("weight") or 1)) for u in users if u.get("user")]
        if rule.get("assign_to_role"):
            async with system_context(require_session()):
                meta = await doctype_registry.get_meta(doctype)
                emails = await holders_for(
                    [str(rule["assign_to_role"])], meta, doc if meta is not None else None
                )
            return [(email, 1) for email in emails]
        if rule.get("assign_to_user"):
            return [(str(rule["assign_to_user"]), 1)]
        return []

    async def _next_in_turn(self, rule: dict[str, Any], candidates: list[tuple[str, int]]) -> str:
        """Round robin: the last user again while they haven't had ``weight``
        turns in a row (counted in the rule's AssignmentLog), else the next one."""
        emails = [email for email, _w in candidates]
        last = rule.get("last_user")
        if last not in emails:
            return emails[0]
        i = emails.index(last)
        weight = max(1, candidates[i][1])
        if weight > 1:
            async with system_context(require_session()):
                recent = await _db.get_all(
                    "AssignmentLog",
                    filters={"rule_id": rule["name"], "assignment_method": "Round Robin"},
                    pluck="assigned_to",
                    order_by="created_at",
                    order="desc",
                    limit=weight,
                )
            streak = next((n for n, email in enumerate(recent) if email != last), len(recent))
            if streak < weight:
                return last
        return emails[(i + 1) % len(emails)]

    async def _open_counts(self, emails: list[str]) -> dict[str, int]:
        """Open assignments of each of *emails* (across all documents)."""
        async with system_context(require_session()):
            rows = await _db.get_all(
                "ToDo",
                filters={"assigned_to__in": emails, "status__in": list(OPEN)},
                fields=["assigned_to"],
                limit=None,
            )
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["assigned_to"]] = counts.get(row["assigned_to"], 0) + 1
        return counts

    async def _settle_open(
        self, doctype: str, doc_id: str, rule: dict[str, Any], doc: dict[str, Any]
    ) -> bool:
        """Close or cancel *rule*'s open assignments of the document by its
        conditions; True when some stay open."""
        async with system_context(require_session()):
            open_todos = await _db.get_all(
                "ToDo",
                filters={
                    "reference_doctype": doctype,
                    "reference_id": doc_id,
                    "assignment_rule": rule["name"],
                    "status__in": list(OPEN),
                },
                fields=["name", "assigned_to"],
                limit=None,
            )
        if not open_todos:
            return False
        close = _json(rule.get("close_condition"), {})
        unassign = _json(rule.get("unassign_condition"), {})
        status = "Closed" if close and matches(close, doc) else None
        if status is None and unassign and matches(unassign, doc):
            status = "Cancel"
        if status is None:
            return True
        async with system_context(require_session()):
            for todo in open_todos:
                await documents.save_doc("ToDo", todo["name"], {"status": status})
                await AssignmentLog.create(
                    rule_id=rule["name"],
                    doctype_affected=doctype,
                    document_id=doc_id,
                    assigned_to=todo["assigned_to"],
                    assignment_method="Closed" if status == "Closed" else "Unassigned",
                    status="Success",
                )
        return False

    async def _get_enabled_rules(self, doctype: str) -> list[dict]:
        """The DocType's enabled rules, highest priority first, with their users."""
        try:
            async with system_context(require_session()):
                rows = await _db.get_all(
                    "AssignmentRule",
                    filters={"doctype_target": doctype, "enabled": True},
                    fields=_RULE_FIELDS,
                    limit=100,
                )
                users = await _db.get_all(
                    "AssignmentRuleUser",
                    filters={
                        "parent_doctype": "AssignmentRule",
                        "parent_name__in": [r["name"] for r in rows] or [""],
                    },
                    fields=["parent_name", "user", "weight", "idx"],
                    order_by="idx",
                    order="asc",
                    limit=None,
                )
        except Exception as exc:
            log.exception("assignment.load_rules_error", doctype=doctype, exc_info=exc)
            return []
        by_rule: dict[str, list[dict[str, Any]]] = {}
        for u in users:
            by_rule.setdefault(u["parent_name"], []).append(u)
        rules = [
            {**row, "filters": _json(row.get("filters"), {}), "users": by_rule.get(row["name"], [])}
            for row in rows
        ]
        rules.sort(key=lambda r: (-(r.get("priority") or 0), r["name"]))
        return rules

    async def _create_todo(
        self,
        doctype: str,
        doc: dict[str, Any],
        owner_email: str,
        rule_id: str | None = None,
        due_date: Any = None,
    ) -> None:
        """Assign *doc* to *owner_email* via a ToDo row (idempotent per doc+user).

        Goes through ``new_doc`` - not ``bulk_insert`` - so the ``ToDo``
        ``after_insert`` hook fires and the assignee gets notified.
        """
        ref_id = doc.get("name") or doc.get("id")
        async with system_context(require_session()):
            already = await _db.exists(
                "ToDo",
                {
                    "reference_doctype": doctype,
                    "reference_id": ref_id,
                    "assigned_to": owner_email,
                    "status": "Open",
                },
            )
            if already:
                return
            await documents.new_doc(
                "ToDo",
                {
                    "description": auto_assign_note(doctype, ref_id),
                    "reference_doctype": doctype,
                    "reference_id": ref_id,
                    "assigned_to": owner_email,
                    "status": "Open",
                    "assignment_rule": rule_id,
                    **({"due_date": due_date} if due_date else {}),
                },
            )


assignment_service = AssignmentService()
