"""Running a ``Notification`` rule against a document.

A rule says *when* (its event + condition), *who* (``recipients`` rows -
:class:`~grunt.notification.doctypes.NotificationRecipient`), *what* (Jinja
subject and message) and *how* (``channels`` rows, each optionally with its
own text). :func:`run` resolves all that and hands the result to the
dispatcher (:func:`grunt.notification.delivery.deliver`).
"""

from collections.abc import Iterable
from typing import Any

from jinja2 import TemplateError
from sqlalchemy.ext.asyncio import AsyncSession
lazy from jinja2.sandbox import SandboxedEnvironment

from grunt.db.api import GruntDB
from grunt.i18n import use_language
from grunt.i18n.jinja import install as install_i18n
from grunt.local import system_context
from grunt.log import log
from grunt.notification.channels import Message, desk_url
from grunt.notification.delivery import deliver
lazy from grunt.metadata.registry import doctype_registry
lazy from grunt.site.manager import current_site

_db = GruntDB()  # stateless: reads through the context's session

RECIPIENT_DOCTYPE = "NotificationRecipient"
CHANNEL_DOCTYPE = "NotificationChannel"

_env: SandboxedEnvironment | None = None


def _jinja() -> SandboxedEnvironment:
    """A sandbox: a rule is written in the desk - no ``__`` attributes, no unsafe calls."""
    global _env
    if _env is None:
        # An empty field prints nothing, not "None".
        _env = SandboxedEnvironment(
            autoescape=False, enable_async=True, finalize=lambda v: "" if v is None else v
        )
        install_i18n(_env)
    return _env


async def render(template: str, context: dict[str, Any]) -> str:
    """Render a rule's Jinja *template*; a broken one is logged and returned as is."""
    if not template or ("{{" not in template and "{%" not in template):
        return template or ""
    try:
        return await _jinja().from_string(template).render_async(**context)
    except TemplateError, ValueError, TypeError, AttributeError:
        log.warning("notification.template_failed", template=template[:200], exc_info=True)
        return template


async def check_template(template: str) -> str | None:
    """The syntax error in *template*, or None - for the rule form's validation."""
    try:
        _jinja().parse(template or "")
    except TemplateError as exc:
        return str(exc)
    return None


def eval_condition(condition: str | None, doc: dict[str, Any], user: str) -> bool:
    """A rule's / a recipient row's Python condition; an error counts as False
    (a typo must not mail everybody)."""
    if not condition or not condition.strip():
        return True
    try:
        from simpleeval import simple_eval

        return bool(simple_eval(condition, names={"doc": _Doc(doc), "user": user}))
    except Exception:  # noqa: BLE001 - any failure of a user-written expression
        log.warning("notification.condition_failed", condition=condition[:200], exc_info=True)
        return False


class _Doc(dict):
    """``doc.field`` as well as ``doc['field']`` / ``doc.get('field')`` in conditions."""

    def __getattr__(self, key: str) -> Any:
        return self.get(key)


async def load_rows(rule: dict[str, Any]) -> dict[str, Any]:
    """*rule* with its ``recipients`` and ``channels`` rows (a raw row lacks them)."""
    if isinstance(rule.get("recipients"), list) and isinstance(rule.get("channels"), list):
        return rule
    name = rule.get("name")
    rows: dict[str, list[dict[str, Any]]] = {}
    for field, doctype in (("recipients", RECIPIENT_DOCTYPE), ("channels", CHANNEL_DOCTYPE)):
        rows[field] = (
            await _db.get_all(
                doctype,
                filters={"parent_name": name, "parent_doctype": "Notification"},
                order_by="idx",
                order="asc",
                limit=None,
            )
            if name
            else []
        )
    return {**rule, **rows}


async def _user_email(user: str) -> str | None:
    """A ``User`` link value (account id or email) -> the email notifications go to."""
    if not user:
        return None
    if "@" in user and await _db.exists("User", {"email": user}):
        return user
    email = await _db.get_value("User", user, "email")
    return str(email) if email else (user if "@" in user else None)


async def _role_users(role: str) -> list[str]:
    rows = await _db.get_all(
        "UserRole",
        filters={"role_name": role, "parent_doctype": "User"},
        fields=["parent_name"],
        limit=None,
    )
    ids = sorted({r["parent_name"] for r in rows})
    if not ids:
        return []
    users = await _db.get_all(
        "User",
        filters={"name__in": ids, "is_active": True},
        fields=["email"],
        limit=None,
    )
    return [u["email"] for u in users if u.get("email")]


async def _field_value(doctype: str, doc: dict[str, Any], path: str) -> str | None:
    """``field`` or ``link_field.target_field`` of *doc*."""
    path = (path or "").strip()
    if "." not in path:
        value = doc.get(path)
        return str(value) if value else None
    link_field, target = path.split(".", 1)
    meta = await doctype_registry.get_meta(doctype)
    fdef = meta.get_field(link_field) if meta else None
    if not (fdef and fdef.has_trait("link") and fdef.options and doc.get(link_field)):
        return None
    value = await _db.get_value(fdef.options, doc[link_field], target)
    return str(value) if value else None


async def _assignees(doctype: str, doc_id: str) -> list[str]:
    rows = await _db.get_all(
        "ToDo",
        filters={
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "status__in": ["Open", "In Progress"],
        },
        fields=["assigned_to"],
        limit=None,
    )
    return [r["assigned_to"] for r in rows if r.get("assigned_to")]


async def _followers(doctype: str, doc_id: str) -> list[str]:
    rows = await _db.get_all(
        "DocFollow",
        filters={"reference_doctype": doctype, "reference_id": doc_id},
        fields=["user"],
        limit=None,
    )
    return [r["user"] for r in rows if r.get("user")]


async def resolve_recipients(
    rule: dict[str, Any],
    doctype: str,
    doc: dict[str, Any],
    actor: str,
    *,
    event_recipients: Iterable[str] = (),
) -> list[str]:
    """The emails *rule* notifies about *doc* - without *actor* unless ``notify_actor``.

    *event_recipients* - who the code that triggered the event names
    (the ``Event recipients`` rows)."""
    found: list[str] = []
    literal: set[str] = set()  # Email rows - addresses, not accounts
    doc_id = str(doc.get("name") or "")
    for row in rule.get("recipients") or []:
        if not eval_condition(row.get("condition"), doc, actor):
            continue
        kind = row.get("kind")
        if kind == "Author":
            found.append(str(doc.get("owner") or ""))
        elif kind == "Role" and row.get("role"):
            found += await _role_users(row["role"])
        elif kind == "User" and row.get("user"):
            found.append(await _user_email(row["user"]) or "")
        elif kind == "Document field" and row.get("field"):
            value = await _field_value(doctype, doc, row["field"])
            found.append((await _user_email(value) or "") if value else "")
        elif kind == "Email" and row.get("email"):
            literal.add(row["email"].strip())
            found.append(row["email"].strip())
        elif kind == "Assignees" and doc_id:
            found += await _assignees(doctype, doc_id)
        elif kind == "Followers" and doc_id:
            found += await _followers(doctype, doc_id)
        elif kind == "Event recipients":
            found += [await _user_email(r) or "" for r in event_recipients]
    emails = [e for e in dict.fromkeys(found) if e]
    if not rule.get("notify_actor"):
        emails = [e for e in emails if e != actor]
    # A deactivated account is told nothing - wherever its address came from
    # (an old ToDo, a follow, a document field), except an Email row naming it.
    inactive = await _inactive(set(emails) - literal)
    return [e for e in emails if e not in inactive]


async def _inactive(emails: set[str]) -> set[str]:
    if not emails:
        return set()
    rows = await _db.get_all(
        "User",
        filters={"email__in": sorted(emails), "is_active": False},
        fields=["email"],
        limit=None,
    )
    return {r["email"] for r in rows}


async def form_url(doctype: str, doc_id: str) -> str:
    """The document's form - absolute when the site is named by its domain."""
    path = await desk_url(doctype, doc_id) or ""
    site = current_site.get()
    return f"https://{site}{path}" if path and "." in site else path


async def context(
    doctype: str,
    doc: dict[str, Any],
    *,
    event: str,
    actor: str,
    link: tuple[str, str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """What a rule's templates see (callables in *extra* are not run yet - see
    :func:`_localized`)."""
    actor_name = ""
    if actor:
        actor_name = str(await _db.get_value("User", {"email": actor}, "full_name") or actor)
    return {
        "doc": _Doc(doc),
        "doctype": doctype,
        "event": event,
        "actor": actor_name,
        "actor_email": actor,
        "url": await form_url(*link),
        **(extra or {}),
    }


def _localized(ctx: dict[str, Any]) -> dict[str, Any]:
    """*ctx* with its callables run - inside the recipient's language."""
    return {k: (v() if callable(v) else v) for k, v in ctx.items()}


async def _languages(recipients: list[str]) -> dict[str | None, list[str]]:
    """Recipients grouped by their UI language (None - no preference or no account)."""
    try:
        rows = await _db.get_all(
            "User",
            filters={"email__in": sorted(set(recipients))},
            fields=["email", "language"],
            limit=None,
        )
        language = {r["email"]: r.get("language") or None for r in rows}
    except Exception:  # noqa: BLE001 - no language is no reason to stay silent
        log.warning("notification.languages_failed", exc_info=True)
        language = {}
    groups: dict[str | None, list[str]] = {}
    for email in recipients:
        groups.setdefault(language.get(email), []).append(email)
    return groups


async def run(
    session: AsyncSession,
    rule: dict[str, Any],
    doctype: str,
    doc: dict[str, Any],
    *,
    actor: str,
    event: str,
    extra: dict[str, Any] | None = None,
    event_recipients: Iterable[str] = (),
    link: tuple[str, str] | None = None,
) -> int:
    """Run *rule* on *doc*: condition, recipients, text, channels. Returns how
    many recipients a channel reached (0 - the condition said no, nobody to
    tell, or every channel failed).

    *link* - the document the notification opens, when not *doc* itself (a
    task's notification opens the task's document). The text is rendered in
    each recipient's language.
    """
    doc_id = str(doc.get("name") or "")
    link = link if link and link[0] and link[1] else (doctype, doc_id)
    async with system_context(session):
        rule = await load_rows(rule)
        if not eval_condition(rule.get("condition"), doc, actor):
            return 0
        recipients = await resolve_recipients(
            rule, doctype, doc, actor, event_recipients=event_recipients
        )
        if not recipients:
            return 0
        ctx = await context(doctype, doc, event=event, actor=actor, link=link, extra=extra)
        groups = await _languages(recipients)

    base = {
        "ref_doctype": link[0],
        "doc_id": link[1],
        "url": await desk_url(*link),
        "notification": rule.get("name"),
        "event_key": event if rule.get("event") == "code" else None,
    }
    reached: set[str] = set()
    for language, people in groups.items():
        with use_language(language):
            local = _localized(ctx)
            subject = await render(rule.get("subject_template") or "", local)
            message = await render(rule.get("message_template") or "", local)
            # Channels sharing the rule's text go out together; one with its own text alone.
            shared: list[str] = []
            for row in rule.get("channels") or []:
                channel = row.get("channel")
                if not channel:
                    continue
                if not row.get("subject") and not row.get("message"):
                    shared.append(channel)
                    continue
                own = Message(
                    subject=await render(row["subject"], local) if row.get("subject") else subject,
                    body=await render(row["message"], local) if row.get("message") else message,
                    **base,
                )
                reached |= (await deliver(session, people, own, [channel])).reached
            if shared:
                message_ = Message(subject=subject, body=message, **base)
                reached |= (await deliver(session, people, message_, shared)).reached
    return len(reached)
