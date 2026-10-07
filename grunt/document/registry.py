from __future__ import annotations

import importlib
import importlib.util
import inspect
from pathlib import Path
from typing import TYPE_CHECKING

from grunt import log
from grunt.startup.doctypes import _find_doctype_dirs
from grunt.utils.strings import to_snake_case

if TYPE_CHECKING:
    from grunt.document.base import BaseDocument


class DocumentRegistry:
    """Registry for DocType controller classes with lazy loading.

    Controllers are never imported at startup. Instead, ``index_*`` methods
    build a name->module_path map, and the actual import happens the first
    time ``get(doctype)`` is called for that DocType.
    """

    def __init__(self) -> None:
        self._controllers: dict[str, type[BaseDocument]] = {}
        # Lazy index: doctype name -> dotted module path to import
        self._index: dict[str, str] = {}
        self._overrides: dict[str, str] = {}

    # Eager registration (used for explicit overrides from hooks)

    def register(self, doctype: str, controller: type[BaseDocument]) -> None:
        """Register an already-imported controller class."""
        self._controllers[doctype] = controller
        log.debug("document.registered", doctype=doctype, controller=controller.__name__)

    def register_overrides(self, overrides: dict[str, str]) -> None:
        """Register controller overrides (mapping: DocType -> 'module.ClassName').

        Overrides are resolved lazily - the module is NOT imported here.
        """
        self._overrides.update(overrides)
        for doctype, path in overrides.items():
            # Store as lazy index entry; the class name is embedded in the path
            self._index[doctype] = path

    # Lazy get

    def get(self, doctype: str) -> type[BaseDocument]:
        """Return the controller for a DocType, importing it on first access."""
        from grunt.document.base import Document

        if doctype not in self._controllers and doctype in self._index:
            self._import_controller(doctype, self._index[doctype])
        return self._controllers.get(doctype, Document)

    def doctype_dir(self, doctype: str) -> Path | None:
        """Directory of *doctype*'s controller module (``…/doctypes/<Name>/``),
        located without importing it; ``None`` when it has no controller file.
        """
        module_path = self._index.get(doctype)
        if not module_path or doctype in self._overrides:
            return None
        spec = importlib.util.find_spec(module_path)
        return Path(spec.origin).parent if spec and spec.origin else None

    def _import_controller(self, doctype: str, module_path: str) -> None:
        """Import a module path and register the controller class found in it.

        Supports two formats:
        - ``grunt.auth.doctypes.User.user``          -> scan module for Document subclass
        - ``myapp.module.MyController``              -> explicit class path (overrides)

        A controller is a subclass of ``Document`` or ``BaseDocument``.
        """
        from grunt.document.base import BaseDocument, Document

        def _is_controller(obj) -> bool:
            return (
                inspect.isclass(obj)
                and issubclass(obj, BaseDocument)
                and obj not in (BaseDocument, Document)
            )

        # Check if it's an explicit class path (override format: "module.ClassName")
        # Heuristic: last segment starts with uppercase -> explicit class reference
        parts = module_path.rsplit(".", 1)
        if len(parts) == 2 and parts[1][0].isupper():
            mod_path, class_name = parts
            try:
                module = importlib.import_module(mod_path)
                controller_cls = getattr(module, class_name, None)
                if controller_cls and _is_controller(controller_cls):
                    self.register(doctype, controller_cls)
                    log.info("document.lazy_loaded", doctype=doctype, controller=module_path)
                    return
            except ImportError as e:
                log.warning(
                    "document.lazy_load_failed", doctype=doctype, module=mod_path, error=str(e)
                )
                return

        # Scan module for a controller class
        try:
            module = importlib.import_module(module_path)
            for _name, obj in inspect.getmembers(module):
                if _is_controller(obj) and obj.__module__ == module.__name__:
                    self.register(doctype, obj)
                    log.debug("document.lazy_loaded", doctype=doctype, controller=_name)
                    return
        except ImportError as e:
            log.warning(
                "document.lazy_load_failed", doctype=doctype, module=module_path, error=str(e)
            )

    # Index builders (no imports, no I/O beyond filesystem stat)

    def index_core_controllers(self) -> None:
        """Index controllers bundled with grunt core (grunt/*/doctypes/{Name}/{snake}.py).

        Prefers snake_case file names; falls back to PascalCase for backwards compatibility.
        No Python modules are imported.
        """
        count = 0
        for doctypes_dir in _find_doctype_dirs():
            # module name from path: grunt/{module}/doctypes -> "module"
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

        log.debug("document.core_indexed", count=count)

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
                    # When the inner package name matches the app dir name
                    # (e.g. apps/car_ua/car_ua/doctypes/…), the app dir is already
                    # on sys.path, so the importable prefix is just `module_name`.
                    if module_name == app_name:
                        module_path = f"{module_name}.doctypes.{dt_dir.name}.{py_file.stem}"
                    else:
                        module_path = (
                            f"{app_name}.{module_name}.doctypes.{dt_dir.name}.{py_file.stem}"
                        )
                    self._index[dt_dir.name] = module_path
                    pascal = "".join(w.capitalize() for w in dt_dir.name.split("_"))
                    self._index[pascal] = module_path
                    count += 1

        log.debug("document.ext_app_indexed", app=app_name, count=count)


document_registry = DocumentRegistry()
