"""DocType — the central metadata model of the Grunt framework.

A DocType describes a data structure (fields, views, workflow, permissions)
and is the single source of truth for DB tables, REST API and UI forms.
"""

from typing import Any, Literal

from pydantic import BaseModel, model_validator

from grunt.metadata.field import DocField
from grunt.metadata.permission import DocPermission

# ── Workflow sub-models ──────────────────────────────────────────────────


class WorkflowState(BaseModel):
    """Runtime shape of a ``WorkflowState`` child row, as read off a ``Workflow`` document."""

    state: str  # value stored in the target document's state field
    label: str = ""
    color: str = "gray"  # gray, blue, green, yellow, orange, red
    is_initial: bool = False
    is_final: bool = False


class WorkflowTransition(BaseModel):
    """Runtime shape of a ``WorkflowTransition`` child row, as read off a ``Workflow`` document."""

    from_state: str
    to_state: str
    action: str  # button label
    allowed_roles: list[str] = []
    condition: str | None = None  # Python expression
    # Fieldnames on the target DocType to collect in a dialog before applying
    # this transition (e.g. an execution note for a "mark as done" action).
    # When set, `condition` (if any) is checked against the *merged* values
    # at apply time instead of gating the button's visibility.
    prompt_fields: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _split_csv_lists(cls, data: Any) -> Any:
        """``allowed_roles``/``prompt_fields`` are comma-separated ``LongText`` fields.

        A DB row predating the column (or simply never filled in) stores it as
        SQL ``NULL`` — read back as ``None``, which a bare ``list[str]`` field
        rejects, so that must become ``[]`` too rather than only splitting strings.
        """
        if isinstance(data, dict):
            updates = {}
            for key in ("allowed_roles", "prompt_fields"):
                value = data.get(key)
                if isinstance(value, str):
                    updates[key] = [v.strip() for v in value.split(",") if v.strip()]
                elif value is None and key in data:
                    updates[key] = []
            if updates:
                data = {**data, **updates}
        return data


# ── Permission sub-model ─────────────────────────────────────────────────


# ── View configuration sub-models ────────────────────────────────────────

# Quick filters are not configured here: the list/tree toolbar filter set is
# derived entirely from fields flagged ``in_quick_filter`` in the designer
# (see ``buildQuickFiltersFromFields`` on the frontend).


class CalendarSource(BaseModel):
    """One extra document source overlaid on the calendar view — a row of the
    ``calendar_sources`` child table."""

    doctype: str
    date_field: str
    end_date_field: str | None = None
    label_field: str | None = None
    color: str | None = None
    filters: dict[str, Any] | None = None
    recurring: bool = False
    event_type: Literal["default", "birthday"] = "default"
    show_age: bool = False


class DocTypeCalendarView(BaseModel):
    """Resolved calendar-view config. Assembled by ``DocType.calendar_view`` from
    the flat ``calendar_*`` fields + the ``calendar_sources`` table."""

    field: str  # Principal date field
    end_field: str | None = None
    title_field: str = "name"
    sources: list[CalendarSource] = []


class DocTypeTreeView(BaseModel):
    """Resolved tree-view config. Assembled by ``DocType.tree_view`` from the
    flat ``tree_*`` fields — it is not stored directly."""

    parent_field: str  # fieldname of the Link field pointing to the same DocType
    title_field: str = "name"  # field displayed as node label
    as_of_date_field: str | None = (
        None  # Date field for "as-of" filtering; enables the date picker in tree toolbar
    )
    sort_by: str | None = None  # optional default sort field for tree nodes
    sort_order: Literal["asc", "desc"] = "asc"  # optional default sort direction


class DocTypeGanttView(BaseModel):
    """Resolved Gantt-view config. Assembled by ``DocType.gantt_view`` from the
    flat ``gantt_*`` fields — it is not stored directly.

    Needs a start and an end Date/Datetime field. Optional extras: a numeric
    ``progress_field`` (0–100) fills the bar, ``color_field`` + ``color_map``
    tint it by value, and ``dependencies_field`` (comma-separated document names,
    or a Link) draws finish-to-start arrows between bars.
    """

    start_field: str  # Date/Datetime — where the bar starts
    end_field: str  # Date/Datetime — where the bar ends
    title_field: str = "name"  # field shown as the row/bar label
    progress_field: str | None = None  # Float/Percent 0–100 → bar fill
    color_field: str | None = None  # field whose value drives the bar colour
    color_map: dict[str, str] | None = None  # { value: '#hex' } for color_field
    default_color: str | None = None  # fallback bar colour
    dependencies_field: str | None = None  # comma-separated predecessor doc names / Link


class DocTypeMapView(BaseModel):
    """Configuration for the map view — requires a Geolocation field."""

    geo_field: str | None = None  # override auto-detected Geolocation field
    label_field: str | None = None  # field shown in marker popup (defaults to title_field)
    color_field: str | None = None  # field whose value drives marker color
    color_map: dict[str, str] | None = None  # { value: '#hex' } mapping for color_field
    default_color: str | None = None  # fallback marker color


# ── Status indicators ───────────────────────────────────────────────────


class StatusIndicator(BaseModel):
    """Maps a field value to a color and optional icon for status display."""

    value: str  # field value to match
    color: str = "secondary"  # default|secondary|success|info|warn|danger|contrast
    icon: str | None = None  # Lucide icon name, e.g. "circle-check"
    label: str | None = None  # override display label (defaults to value)


# ── Document actions ────────────────────────────────────────────────────


class DocTypeAction(BaseModel):
    """Binds one code-registered document action (see ``grunt.actions``) to a
    DocType, with optional presentation overrides.

    ``action`` is the registry key; everything else overrides the registered
    defaults for this DocType only. ``condition`` is a JS expression evaluated
    against ``doc`` on the client — falsy hides the button.
    """

    action: str = ""  # registered action key (blank row is pruned by DocType)
    label: str = ""  # override registered label
    group: str = ""  # toolbar dropdown group (empty → standalone button)
    variant: str = ""  # button variant override (outline|default|secondary|destructive|success)
    condition: str | None = None  # JS expression on `doc`; falsy → hidden
    hidden: bool = False  # hard off-switch, keeps the row for later

    @model_validator(mode="before")
    @classmethod
    def _blank_none_strings(cls, data: Any) -> Any:
        """The child-table editor sends ``null`` for empty cells — coerce to ``""``."""
        if isinstance(data, dict):
            data = {
                k: ("" if v is None and k in {"action", "label", "group", "variant"} else v)
                for k, v in data.items()
            }
        return data


# ── Document links (Connections tab) ───────────────────────────────────


class DocTypeLink(BaseModel):
    """Declares one related DocType surfaced on the document "Зв'язки" panel.

    * direct: ``link_doctype`` has a Link field ``link_fieldname`` back to this
      document;
    * via child table: ``parent_doctype`` (a child DocType) carries the Link
      field ``link_fieldname``; ``link_doctype`` is the owning parent type and
      ``table_fieldname`` optionally pins which Table field holds those rows.
    """

    link_doctype: str = ""  # related DocType to list/count (blank row is pruned by DocType)
    link_fieldname: str = ""  # Link field on link_doctype (or parent_doctype) → this doc
    parent_doctype: str | None = None  # child DocType, when the link lives on a child row
    table_fieldname: str | None = None  # Table field on link_doctype holding those child rows
    group: str = ""  # section grouping on the panel
    label: str = ""  # override display label (default: link_doctype label)
    hidden: bool = False

    @model_validator(mode="before")
    @classmethod
    def _blank_none_strings(cls, data: Any) -> Any:
        """The child-table editor sends ``null`` for empty cells — coerce to ``""``."""
        if isinstance(data, dict):
            str_keys = {"link_doctype", "link_fieldname", "group", "label"}
            data = {k: ("" if v is None and k in str_keys else v) for k, v in data.items()}
        return data


# ── DocType — main model ─────────────────────────────────────────────────


class DocType(BaseModel):
    """Top-level metadata definition for a document type."""

    name: str  # PascalCase, globally unique
    label: str  # "Договір постачання"
    module: str  # "crm"
    app: str | None = None  # installed app name (e.g. "hrm"); UI convenience, derived from module
    description: str | None = None  # short human description — tooltips, Studio, docs
    icon: str | None = None  # Lucide icon name (kebab-case) — menu & Workspace

    # Flags
    is_child: bool = False  # True → used inside a TABLE field
    is_submittable: bool = False  # adds Submit button
    is_singleton: bool = False  # only one document per DocType
    is_virtual: bool = False  # True → no DB table, data from controller
    is_tree: bool = False  # True → hierarchical; requires tree_view.parent_field
    is_log: bool = False  # True → operational log, excluded from global search index
    log_retention_days: int | None = None  # is_log only; None → DEFAULT_LOG_RETENTION_DAYS
    # to name the self-referential Link
    track_changes: bool = True  # audit log
    track_seen: bool = False  # record which users have opened each document (_seen column)
    track_views: bool = False  # log every document open to ViewLog (throttled 1/user/doc/hour)
    track_deletions: bool = True  # False → skip the restorable DeletedDocument snapshot on delete
    track_activity: bool = True  # False → never write ActivityLog rows (high-churn system doctypes)
    # True → excluded from the GLOBAL feed only, still shown in this doctype's own
    # document timelines (for admin/config records: roles, print formats, etc.)
    hide_from_activity_feed: bool = False
    quick_entry: bool = False  # True → "Create" opens a dialog instead of full form

    # Lifecycle markers (UI-only; no behavioural effect)
    beta: bool = False  # show a "Beta" badge — feature still under development
    deprecated: bool = False  # show a warning banner — kept for compatibility, avoid new use

    # Fields
    fields: list[DocField] = []

    # View configuration
    default_view: str | None = None  # "list" | "kanban" | "calendar" | "gantt" | "tree" | "map"
    form_show_sidebar: bool = True  # False → hide the document detail sidebar on the form
    kanban_column_field: str | None = None  # Select field grouping the kanban columns
    map_view: DocTypeMapView | None = None

    # Calendar view — principal date field + optional extra document sources.
    # The assembled config is exposed via `.calendar_view`.
    calendar_date_field: str | None = None
    calendar_end_date_field: str | None = None
    calendar_title_field: str | None = None  # None → falls back to title_field
    calendar_sources: list[CalendarSource] = []

    # Gantt view — time-scaled bars. Needs start + end Date/Datetime fields;
    # the assembled config is exposed via `.gantt_view`.
    gantt_start_field: str | None = None
    gantt_end_field: str | None = None
    gantt_title_field: str | None = None  # None → falls back to title_field
    gantt_progress_field: str | None = None  # Float/Int/Percent 0–100 → bar fill
    gantt_color_field: str | None = None
    gantt_color_map: dict[str, str] | None = None  # { value: '#hex' }
    gantt_default_color: str | None = None
    gantt_dependencies_field: str | None = None

    # Tree view — hierarchy via a self-referential Link (`tree_parent_field`).
    # Gated by `is_tree`; the assembled config is exposed via `.tree_view`.
    tree_parent_field: str | None = None
    tree_title_field: str | None = None  # node label; None → falls back to title_field
    tree_as_of_date_field: str | None = None  # Date field enabling the "as-of" picker
    tree_sort_by: str | None = None
    tree_sort_order: Literal["asc", "desc"] = "asc"

    # Status display — field whose value is the document status, plus the
    # value → colour/icon/label indicators used by list/form/kanban badges.
    status_field: str | None = None
    status_indicators: list[StatusIndicator] = []

    # Custom document actions — code-registered, bound here (see grunt.actions)
    actions: list[DocTypeAction] = []

    # Related document types shown on the "Зв'язки" panel (see grunt.document.connections)
    links: list[DocTypeLink] = []

    # Business logic
    permissions: list[DocPermission] = []

    # Naming / display
    autoname: str | None = None  # "CONTR-.YYYY.-.####" or "field:title"
    title_field: str = "name"  # field used as document title
    image_field: str | None = None  # field (Image/Attach) used as document avatar

    # Search
    search_fields: list[str] = []

    # Composite (multi-column) indexes — single-column indexes use field.index
    # instead. Each entry is an ordered list of fieldnames, e.g.
    # [["reference_doctype", "reference_id"]].
    indexes: list[list[str]] = []

    # Override physical table name — used to pin core/system DocTypes to their
    # legacy ORM table names (e.g. "grunt_server_script" instead of "grunt_core_server_script").
    table_name: str | None = None

    model_config = {"use_enum_values": True}

    @property
    def calendar_view(self) -> DocTypeCalendarView | None:
        """Assembled calendar-view config from the flat ``calendar_*`` fields +
        ``calendar_sources``, or None when no principal date field is set.
        Read-only — not serialised."""
        if not self.calendar_date_field:
            return None
        return DocTypeCalendarView(
            field=self.calendar_date_field,
            end_field=self.calendar_end_date_field,
            title_field=self.calendar_title_field or self.title_field or "name",
            sources=self.calendar_sources,
        )

    @property
    def gantt_view(self) -> DocTypeGanttView | None:
        """Assembled Gantt-view config from the flat ``gantt_*`` fields, or None
        when no start/end field is set. Read-only — not serialised."""
        if not self.gantt_start_field or not self.gantt_end_field:
            return None
        return DocTypeGanttView(
            start_field=self.gantt_start_field,
            end_field=self.gantt_end_field,
            title_field=self.gantt_title_field or self.title_field or "name",
            progress_field=self.gantt_progress_field,
            color_field=self.gantt_color_field,
            color_map=self.gantt_color_map,
            default_color=self.gantt_default_color,
            dependencies_field=self.gantt_dependencies_field,
        )

    @property
    def tree_view(self) -> DocTypeTreeView | None:
        """Assembled tree-view config from the flat ``tree_*`` fields, or None
        when this DocType isn't a configured tree. Read-only — not serialised."""
        if not self.is_tree or not self.tree_parent_field:
            return None
        return DocTypeTreeView(
            parent_field=self.tree_parent_field,
            title_field=self.tree_title_field or self.title_field or "name",
            as_of_date_field=self.tree_as_of_date_field,
            sort_by=self.tree_sort_by,
            sort_order=self.tree_sort_order,
        )

    @model_validator(mode="after")
    def _prune_incomplete_child_rows(self) -> DocType:
        """Drop half-filled ``actions`` / ``links`` rows left behind in the editor."""
        self.actions = [a for a in self.actions if a.action.strip()]
        self.links = [link for link in self.links if link.link_doctype.strip()]
        return self
