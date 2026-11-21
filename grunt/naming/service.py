"""NamingService - generates document names from DocType autoname patterns.

Supports:
  - "field:<fieldname>"          -> use a field value as the name
  - "hash"                       -> short random token
  - "prompt"                     -> user supplies name explicitly
  - "PREFIX-.YYYY.-.####"        -> pattern with date tokens and auto-incrementing counter
  - "PREFIX-{field}-.####"       -> a field's value in the name (its own counter per value)
  - "naming_series:"             -> the pattern the user picked in the ``naming_series``
                                    Select field (one of its options)
  - ""  (empty)                  -> falls back to "hash"

Which pattern a new document gets - :func:`NamingService.new_name`:
a matching Document Naming Rule (:mod:`grunt.naming.rules`), then the
caller's own ``name`` (not for a counter series), the controller's
``autoname()``, the DocType's ``autoname``.

Dates in the name are the site's local date (``settings.default_timezone``),
or the document's own date when the DocType sets ``naming_date_field``.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.config import settings
from grunt.errors import not_found, throw
from grunt.i18n import _
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.naming.patterns import (
    MissingFieldValueError,
    build_prefix,
    field_tokens,
    format_name,
    has_counter,
    parse_pattern,
    resolve_simple,
)
from grunt.naming.rules import matching_rule

NAMING_SERIES = "naming_series:"
SERIES_FIELD = "naming_series"

# Taken names skipped in a row before giving up (a counter set far behind).
_MAX_SKIPS = 1000


def local_today() -> date:
    """Today in the site's time zone - the date a name gets by default."""
    return datetime.now(ZoneInfo(settings.default_timezone)).date()


def naming_date(dt: Any, data: dict[str, Any]) -> date:
    """The date for the name's YYYY/MM/DD: the document's ``naming_date_field``
    when the DocType sets one and it's filled in, else today (local)."""
    fieldname = getattr(dt, "naming_date_field", None) if dt is not None else None
    value = data.get(fieldname) if fieldname else None
    if value in (None, ""):
        return local_today()
    text = str(value).strip()
    try:
        return _local_date(value)
    except ValueError:
        throw(
            _("“%(value)s” is not a date the name can be built from") % {"value": text},
            "VALIDATION_ERROR",
        )


def _local_date(value: Any) -> date:
    """*value* (a date, a datetime, their ISO text) as a local calendar date;
    a datetime without a zone is UTC, like the stored ones."""
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(ZoneInfo(settings.default_timezone)).date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) > 10:
        return _local_date(datetime.fromisoformat(text.replace("Z", "+00:00")))
    return date.fromisoformat(text)


def _field(dt: Any, fieldname: str) -> Any:
    return next((f for f in getattr(dt, "fields", None) or [] if f.fieldname == fieldname), None)


def _label(dt: Any, fieldname: str) -> str:
    field = _field(dt, fieldname)
    return _(field.label) if field is not None and field.label else fieldname


def series_options(dt: Any) -> list[str]:
    """The patterns a user may pick in the DocType's ``naming_series`` field."""
    field = _field(dt, SERIES_FIELD)
    raw = str(getattr(field, "options", None) or "") if field is not None else ""
    return [o.split("|", 1)[0].strip() for o in raw.splitlines() if o.strip()]


def series_pattern(dt: Any, data: dict[str, Any]) -> str:
    """The series picked in *data* (the field's default / first option when
    empty), stored back into ``data["naming_series"]``. A value that isn't one
    of the options is refused - it would let anyone count in any series."""
    options = series_options(dt)
    if not options:
        throw(
            _("“%(doctype)s” is named by series but has no “naming_series” field with options")
            % {"doctype": getattr(dt, "name", "")},
            "VALIDATION_ERROR",
        )
    field = _field(dt, SERIES_FIELD)
    chosen = str(data.get(SERIES_FIELD) or getattr(field, "default", None) or options[0]).strip()
    if chosen not in options:
        throw(
            _("Naming series “%(series)s” is not one of the allowed ones") % {"series": chosen},
            "VALIDATION_ERROR",
        )
    data[SERIES_FIELD] = chosen
    return chosen


class NamingService:
    """Generates unique document names based on DocType autoname patterns."""

    async def new_name(
        self,
        dt: Any,
        data: dict[str, Any],
        session: AsyncSession,
        *,
        controller_autoname: Callable[..., Awaitable[str]] | None = None,
        honor_explicit: bool = True,
    ) -> str:
        """The name of a new *dt* document with *data*.

        A caller-supplied ``name`` wins (fixtures and imports rely on stable
        names) - but NOT for a counter series (e.g. "ВХ-.YYYY.-.####"), where
        the counter is the source of truth and must always be consulted.
        Otherwise any caller (a frontend bug, a crafted API request) could
        pass an arbitrary ``name`` and silently hijack the series - the
        counter would never advance and a later, properly-generated name could
        collide with it.
        """
        rule = await matching_rule(dt.name, data)
        pattern = (rule.autoname if rule else dt.autoname) or ""
        pattern = pattern.removeprefix("format:")
        if pattern == NAMING_SERIES:
            pattern = series_pattern(dt, data)

        if honor_explicit and data.get("name") and not has_counter(parse_pattern(pattern)):
            return str(data["name"])
        if rule is None and controller_autoname is not None:
            return await controller_autoname(data, session)
        return await self.generate(pattern, data, session, dt=dt)

    async def generate(
        self,
        autoname: str,
        data: dict[str, Any],
        session: AsyncSession,
        *,
        dt: Any = None,
    ) -> str:
        """Generate a name for a new document.

        Always returns a non-empty string. When autoname is empty or unresolvable,
        falls back to the "hash" pattern (short random token).

        Args:
            autoname: The autoname pattern from the DocType definition.
            data: The document data (for field-based naming).
            session: DB session for counter operations.
            dt: The DocType - for ``naming_series:``, ``naming_date_field``
                and skipping names already taken.

        Returns:
            The generated name.
        """
        # Strip optional "format:" prefix stored by the Studio UI
        autoname = autoname.removeprefix("format:")

        if autoname == NAMING_SERIES:
            autoname = "hash" if dt is None else series_pattern(dt, data)

        # Empty autoname -> use hash as fallback
        if not autoname:
            autoname = "hash"

        # Try simple patterns first (field:, hash, prompt)
        simple = resolve_simple(autoname, data)
        if simple is not None:
            return simple

        # Parse pattern-based autoname
        parts = parse_pattern(autoname)
        if not parts:
            # Unrecognised pattern - fall back to hash
            return resolve_simple("hash", data)  # type: ignore[return-value]

        day = naming_date(dt, data)

        try:
            if not has_counter(parts):
                # Pattern without counter - just format date and field tokens
                return format_name(parts, counter=0, now=day, values=data)

            # Pattern with counter - need atomic increment
            prefix = build_prefix(parts, now=day, values=data)
            for _attempt in range(_MAX_SKIPS):
                counter = await self._next_counter(prefix, session)
                name = format_name(parts, counter=counter, now=day, values=data)
                # The counter was set back, or a document was imported with
                # this name: the next number, not a duplicate-key error.
                if not await _taken(dt, name, session):
                    log.debug("naming.generated", pattern=autoname, prefix=prefix, name=name)
                    return name
                log.info("naming.skipped_taken", prefix=prefix, name=name)
        except MissingFieldValueError as exc:
            throw(
                _("Fill in “%(field)s”: the document's name is built from it")
                % {"field": _label(dt, exc.fieldname)},
                "VALIDATION_ERROR",
            )

        throw(
            _("The next %(count)s names of series “%(prefix)s” are all taken: set its counter")
            % {"count": _MAX_SKIPS, "prefix": prefix},
            "VALIDATION_ERROR",
        )

    async def preview(
        self, dt: Any, pattern: str, data: dict[str, Any] | None, session: AsyncSession
    ) -> dict[str, Any]:
        """What the next name of *pattern* would be - without taking a number.

        ``{pattern, prefix, current, next, fields}``: ``fields`` - the fields
        the pattern needs and *data* lacks (then no ``prefix``/``next``);
        ``prefix``/``current`` are None for a pattern without a counter.
        """
        values = dict(data or {})
        pattern = (pattern or "").removeprefix("format:")
        out: dict[str, Any] = {
            "pattern": pattern,
            "prefix": None,
            "current": None,
            "next": None,
            "fields": [],
        }
        if pattern == NAMING_SERIES:
            options = series_options(dt)
            pattern = str(values.get(SERIES_FIELD) or (options[0] if options else ""))
            out["pattern"] = pattern
        parts = parse_pattern(pattern)
        # field:/hash/prompt - not a series, nothing to preview.
        if not parts or pattern in ("hash", "prompt") or pattern.startswith("field:"):
            return out
        missing = [f for f in field_tokens(parts) if not str(values.get(f) or "").strip()]
        if missing:
            out["fields"] = [{"fieldname": f, "label": _label(dt, f)} for f in missing]
            return out
        day = naming_date(dt, values)
        if not has_counter(parts):
            out["next"] = format_name(parts, counter=0, now=day, values=values)
            return out
        prefix = build_prefix(parts, now=day, values=values)
        current = await self.current(prefix, session)
        counter = current + 1
        name = format_name(parts, counter=counter, now=day, values=values)
        for _attempt in range(_MAX_SKIPS):
            if not await _taken(dt, name, session):
                break
            counter += 1
            name = format_name(parts, counter=counter, now=day, values=values)
        out.update(prefix=prefix, current=current, next=name)
        return out

    async def current(self, prefix: str, session: AsyncSession) -> int:
        """The last number given out under *prefix* (0 - none yet)."""
        table = await _series_table()
        row = (
            await session.execute(select(table.c.current).where(table.c.prefix == prefix))
        ).first()
        return int(row[0] or 0) if row is not None else 0

    async def set_current(self, prefix: str, current: int, session: AsyncSession) -> None:
        """Set the last number given out under *prefix* - the next one is +1."""
        if current < 0:
            throw(_("The counter can't be negative"), "VALIDATION_ERROR")
        table = await _series_table()
        exists = (
            await session.execute(
                select(table.c.prefix).where(table.c.prefix == prefix).with_for_update()
            )
        ).first()
        if exists is not None:
            await session.execute(
                update(table).where(table.c.prefix == prefix).values(current=current)
            )
        else:
            await _insert_series(table, prefix, current, session)
        await session.flush()
        log.info("naming.counter_set", prefix=prefix, current=current)

    async def _next_counter(self, prefix: str, session: AsyncSession) -> int:
        """Atomically increment and return the next counter for a prefix.

        Uses SELECT ... FOR UPDATE to prevent race conditions.
        """
        table = await _series_table()

        # Try to get existing row with lock
        stmt = select(table).where(table.c.prefix == prefix).with_for_update()
        result = await session.execute(stmt)
        row = result.mappings().first()

        if row is not None:
            new_counter = (row["current"] or 0) + 1
            await session.execute(
                update(table).where(table.c.prefix == prefix).values(current=new_counter)
            )
            await session.flush()
            return new_counter

        # First time - insert with counter = 1
        await _insert_series(table, prefix, 1, session)
        await session.flush()
        return 1


async def _series_table() -> Any:
    ns_dt = await doctype_registry.get_meta("NamingSeries")
    if ns_dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": "NamingSeries"})
    return ns_dt.table


async def _insert_series(table: Any, prefix: str, current: int, session: AsyncSession) -> None:
    now = datetime.now(UTC)
    await session.execute(
        table.insert().values(
            name=prefix,
            owner="system",
            created_at=now,
            modified_at=now,
            modified_by="system",
            prefix=prefix,
            current=current,
        )
    )


async def _taken(dt: Any, name: str, session: AsyncSession) -> bool:
    """Whether a *dt* document is already called *name* (False without a table)."""
    if dt is None or not getattr(dt, "has_table", False):
        return False
    table = dt.table
    row = (await session.execute(select(table.c.name).where(table.c.name == name))).first()
    return row is not None


naming_service = NamingService()
