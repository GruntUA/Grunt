"""Dashboard widget type registry — the WidgetType counterpart of grunt.metadata.field."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from grunt import log

if TYPE_CHECKING:
    from datetime import datetime


# ── WidgetType base class ───────────────────────────────────────────────────


class WidgetType:
    """Base class for all dashboard widget type implementations.

    Subclass this and set ``name``, then call
    ``register_widget_type_class(MyWidgetType)`` (or define a ``register()``
    function that does so) inside the widget type's Python file — see
    ``frontend/src/components/dashboard/widgets/<Type>/<Type>.py`` for the
    core types.

    Widget types that render entirely client-side (text, clock,
    shortcuts_grid, links) set ``requires_backend_compute = False``; they are
    never dispatched to ``compute()``.
    """

    name: ClassVar[str] = ""
    requires_backend_compute: ClassVar[bool] = True
    # False for "activity" — it aggregates across all doctypes when none is set.
    requires_doctype: ClassVar[bool] = True

    @classmethod
    async def compute(
        cls,
        widget: dict[str, Any],
        dt: Any,
        doctype_name: str,
        since: datetime,
        until: datetime,
        days: int,
        base_filters: dict[str, Any],
    ) -> Any:
        raise NotImplementedError


# ── Registry ──────────────────────────────────────────────────────────────────

_WIDGET_TYPE_REGISTRY: dict[str, type[WidgetType]] = {}


def register_widget_type_class(cls: type[WidgetType]) -> None:
    """Register a :class:`WidgetType` subclass by its ``name`` attribute."""
    _WIDGET_TYPE_REGISTRY[cls.name] = cls


def get_widget_type_class(name: str) -> type[WidgetType] | None:
    """Return the registered :class:`WidgetType` subclass for *name*, if any."""
    return _WIDGET_TYPE_REGISTRY.get(name)


def get_registered_widget_types() -> list[str]:
    """Return every registered widget type name, in registration order."""
    return list(_WIDGET_TYPE_REGISTRY.keys())


# ── Discovery ─────────────────────────────────────────────────────────────────


def _find_bench_dir_for_widgets(start: Path) -> Path | None:
    """Walk up from *start* looking for a directory that contains apps/."""
    check = start if start.is_dir() else start.parent
    for _ in range(8):
        if (check / "apps").is_dir():
            return check
        if check == check.parent:
            break
        check = check.parent
    return None


def discover_widget_types() -> None:
    """Discover and register widget types from all apps in the bench.

    Scans every app directory for a 'dashboard_widgets' folder and registers
    any subdirectories that contain a [WidgetName].py with a register()
    function. Also scans the frontend components/dashboard/widgets for the
    core types — same layout convention as grunt.metadata.field's discovery.
    """
    bench_dir = _find_bench_dir_for_widgets(Path.cwd()) or _find_bench_dir_for_widgets(
        Path(__file__).resolve()
    )
    if not bench_dir:
        return

    scan_paths = [
        bench_dir / "apps/grunt/frontend/src/components/dashboard/widgets",
    ]

    apps_dir = bench_dir / "apps"
    if apps_dir.exists():
        for app_dir in apps_dir.iterdir():
            if not app_dir.is_dir():
                continue
            widgets_path = app_dir / "dashboard_widgets"
            if widgets_path.exists():
                scan_paths.append(widgets_path)

    for base_path in scan_paths:
        if not base_path.exists():
            continue

        for widget_dir in base_path.iterdir():
            if not widget_dir.is_dir():
                continue

            py_file = widget_dir / f"{widget_dir.name}.py"
            if py_file.exists():
                try:
                    spec = importlib.util.spec_from_file_location(
                        f"grunt_widget_{widget_dir.name.lower()}", str(py_file)
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        if hasattr(module, "register"):
                            module.register()
                except Exception:
                    log.exception("suppressed_error")


# Runs once, as an import-time side effect — mirrors grunt.metadata.field's
# discover_field_types(): any `from grunt.metadata.widget import ...` scans
# every app's dashboard_widgets/ dir on disk and registers each plugin's
# WidgetType. Re-running discovery (e.g. after installing an app at runtime)
# means calling discover_widget_types() again explicitly.
discover_widget_types()
