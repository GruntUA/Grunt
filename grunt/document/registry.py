from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import structlog

from grunt.document.base import Document
from grunt.utils.strings import to_snake_case

logger = structlog.get_logger()


class DocumentRegistry:
    """Registry for DocType controller classes with lazy loading.

    Controllers are never imported at startup. Instead, ``index_*`` methods
    build a name→module_path map, and the actual import happens the first
    time ``get(doctype)`` is called for that DocType.
    """

    def __init__(self) -> None:
        self._controllers: dict[str, type[Document]] = {}
        # Lazy index: doctype name → dotted module path to import
        self._index: dict[str, str] = {}
        self._overrides: dict[str, str] = {}

    # ── Eager registration (used for explicit overrides from hooks) ───────────

    def register(self, doctype: str, controller: type[Document]) -> None:
        """Register an already-imported controller class."""
        self._controllers[doctype] = controller
        logger.debug("document.registered", doctype=doctype, controller=controller.__name__)

    def register_overrides(self, overrides: dict[str, str]) -> None:
        """Register controller overrides (mapping: DocType -> 'module.ClassName').

        Overrides are resolved lazily — the module is NOT imported here.
        """
        self._overrides.update(overrides)
        for doctype, path in overrides.items():
            # Store as lazy index entry; the class name is embedded in the path
            self._index[doctype] = path

    # ── Lazy get ──────────────────────────────────────────────────────────────

    def get(self, doctype: str) -> type[Document]:
        """Return the controller for a DocType, importing it on first access."""
        if doctype not in self._controllers and doctype in self._index:
            self._import_controller(doctype, self._index[doctype])
        return self._controllers.get(doctype, Document)

    def _import_controller(self, doctype: str, module_path: str) -> None:
        """Import a module path and register the Document subclass found in it.

        Supports two formats:
        - ``grunt.auth.doctypes.User.user``          → scan module for Document subclass
        - ``myapp.module.MyController``              → explicit class path (overrides)

        Accepts both Document and VirtualDocType subclasses.
        """
        from grunt.metadata.virtual import VirtualDocType  # noqa: PLC0415

        def _is_controller(obj) -> bool:
            return inspect.isclass(obj) and (
                (issubclass(obj, Document) and obj is not Document)
                or (issubclass(obj, VirtualDocType) and obj is not VirtualDocType)
            )

        # Check if it's an explicit class path (override format: "module.ClassName")
        # Heuristic: last segment starts with uppercase → explicit class reference
        parts = module_path.rsplit(".", 1)
        if len(parts) == 2 and parts[1][0].isupper():
            mod_path, class_name = parts
            try:
                module = importlib.import_module(mod_path)
                controller_cls = getattr(module, class_name, None)
                if controller_cls and _is_controller(controller_cls):
                    self.register(doctype, controller_cls)
                    logger.info("document.lazy_loaded", doctype=doctype, controller=module_path)
                    return
            except ImportError as e:
                logger.warning(
                    "document.lazy_load_failed", doctype=doctype, module=mod_path, error=str(e)
                )
                return

        # Scan module for Document or VirtualDocType subclass
        try:
            module = importlib.import_module(module_path)
            for _name, obj in inspect.getmembers(module):
                if _is_controller(obj) and obj.__module__ == module.__name__:
                    self.register(doctype, obj)
                    logger.debug("document.lazy_loaded", doctype=doctype, controller=_name)
                    return
        except ImportError as e:
            logger.warning(
                "document.lazy_load_failed", doctype=doctype, module=module_path, error=str(e)
            )

    # ── Index builders (no imports, no I/O beyond filesystem stat) ────────────

    def index_core_controllers(self) -> None:
        """Index controllers bundled with grunt core (grunt/*/doctypes/{Name}/{snake}.py).

        Prefers snake_case file names; falls back to PascalCase for backwards compatibility.
        No Python modules are imported.
        """
        from grunt.startup.doctypes import _find_doctype_dirs  # noqa: PLC0415

        count = 0
        for doctypes_dir in _find_doctype_dirs():
            # module name from path: grunt/{module}/doctypes → "module"
            module_name = doctypes_dir.parent.name
            for dt_dir in doctypes_dir.iterdir():
                if not dt_dir.is_dir() or dt_dir.name.startswith((".", "_")):
                    continue
                pascal = dt_dir.name
                snake = to_snake_case(pascal)
                py_file = dt_dir / f"{snake}.py"
                if not py_file.exists():
                    py_file = dt_dir / f"{pascal}.py"
                if py_file.exists():
                    module_path = f"grunt.{module_name}.doctypes.{pascal}.{py_file.stem}"
                    self._index[pascal] = module_path
                    count += 1

        logger.debug("document.core_indexed", count=count)

    def index_app_controllers(self, apps_path: str | Path) -> None:
        """Index controllers in ``grunt_apps/{app}/{module}/doctypes/{Name}/{Name}.py``."""
        apps_path = Path(apps_path)
        if not apps_path.exists():
            return

        count = 0
        for app_dir in apps_path.iterdir():
            if not app_dir.is_dir() or app_dir.name.startswith("."):
                continue
            for doctypes_dir in app_dir.glob("*/doctypes"):
                if not doctypes_dir.is_dir():
                    continue
                module_name = doctypes_dir.parent.name
                for dt_dir in sorted(doctypes_dir.iterdir()):
                    if not dt_dir.is_dir() or dt_dir.name.startswith((".", "_")):
                        continue
                    py_file = dt_dir / f"{dt_dir.name}.py"
                    if not py_file.exists():
                        py_file = dt_dir / f"{to_snake_case(dt_dir.name)}.py"
                    if py_file.exists():
                        module_path = (
                            f"grunt_apps.{app_dir.name}.{module_name}"
                            f".doctypes.{dt_dir.name}.{py_file.stem}"
                        )
                        self._index[dt_dir.name] = module_path
                        pascal = "".join(w.capitalize() for w in dt_dir.name.split("_"))
                        self._index[pascal] = module_path
                        count += 1

        logger.debug("document.app_indexed", apps=str(apps_path), count=count)

    def index_external_app_controllers(self, app_dir: str | Path) -> None:
        """Index controllers from a single external app (bench/apps/{app}/)."""
        app_dir = Path(app_dir)
        app_name = app_dir.name

        count = 0
        for doctypes_dir in app_dir.glob("*/doctypes"):
            if not doctypes_dir.is_dir():
                continue
            module_name = doctypes_dir.parent.name
            for dt_dir in sorted(doctypes_dir.iterdir()):
                if not dt_dir.is_dir() or dt_dir.name.startswith((".", "_")):
                    continue
                py_file = dt_dir / f"{dt_dir.name}.py"
                if not py_file.exists():
                    py_file = dt_dir / f"{to_snake_case(dt_dir.name)}.py"
                if py_file.exists():
                    module_path = f"{app_name}.{module_name}.doctypes.{dt_dir.name}.{py_file.stem}"
                    self._index[dt_dir.name] = module_path
                    pascal = "".join(w.capitalize() for w in dt_dir.name.split("_"))
                    self._index[pascal] = module_path
                    count += 1

        logger.debug("document.ext_app_indexed", app=app_name, count=count)

    # ── Backwards-compatible aliases ──────────────────────────────────────────

    def discover_core_controllers(self) -> None:
        """Alias for index_core_controllers() — kept for backwards compatibility."""
        self.index_core_controllers()

    def discover_controllers(self, apps_path: str | Path) -> None:
        """Alias for index_app_controllers() — kept for backwards compatibility."""
        self.index_app_controllers(apps_path)

    def discover_controllers_from_app(self, app_dir: str | Path) -> None:
        """Alias for index_external_app_controllers() — kept for backwards compatibility."""
        self.index_external_app_controllers(app_dir)

    # ── Internal (kept for compatibility with _load_controller callers) ───────

    def _load_controller(self, py_file: Path, module_path: str) -> None:
        """Eagerly import a module and register any Document subclass.

        Prefer index_* methods over this — they defer the import until needed.
        """
        try:
            module = importlib.import_module(module_path)
            for _name, obj in inspect.getmembers(module):
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, Document)
                    and obj is not Document
                    and obj.__module__ == module.__name__
                ):
                    self.register(_name, obj)
        except ImportError as e:
            logger.warning("document.discovery_failed", module=module_path, error=str(e))


document_registry = DocumentRegistry()
