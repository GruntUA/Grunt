from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Type

import structlog

from grunt.core.document.base import Document

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class DocumentRegistry:
    """Registry for custom DocType controller classes."""

    def __init__(self) -> None:
        self._controllers: dict[str, Type[Document]] = {}
        self._overrides: dict[str, str] = {}

    def register(self, doctype: str, controller: Type[Document]) -> None:
        """Manually register a controller for a DocType."""
        self._controllers[doctype] = controller
        logger.debug("document.registered", doctype=doctype, controller=controller.__name__)

    def register_overrides(self, overrides: dict[str, str]) -> None:
        """Register controller overrides (mapping: DocType -> 'module.class')."""
        self._overrides.update(overrides)
        for doctype, path in overrides.items():
            try:
                module_path, class_name = path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                controller_cls = getattr(module, class_name)
                if inspect.isclass(controller_cls) and issubclass(controller_cls, Document):
                    self.register(doctype, controller_cls)
                    logger.info("document.overridden", doctype=doctype, controller=path)
            except (ImportError, AttributeError, ValueError) as e:
                logger.warning("document.override_failed", doctype=doctype, path=path, error=str(e))

    def get(self, doctype: str) -> Type[Document]:
        """Return the controller for a DocType, or the base Document class."""
        return self._controllers.get(doctype, Document)

    def discover_controllers(self, apps_path: str | Path) -> None:
        """Search for Document subclasses in ``{app}/{module}/doctypes/{Name}/{Name}.py``."""
        apps_path = Path(apps_path)
        if not apps_path.exists():
            return

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
                    if py_file.exists():
                        self._load_controller(
                            py_file,
                            f"grunt_apps.{app_dir.name}.{module_name}.doctypes.{dt_dir.name}.{dt_dir.name}",
                        )

    def discover_controllers_from_app(self, app_dir: str | Path) -> None:
        """Discover controllers from a single external app directory.

        External apps (under ``bench/apps/``) use their app name as the
        top-level Python package, not ``grunt_apps``.
        """
        app_dir = Path(app_dir)
        app_name = app_dir.name

        for doctypes_dir in app_dir.glob("*/doctypes"):
            if not doctypes_dir.is_dir():
                continue
            module_name = doctypes_dir.parent.name
            for dt_dir in sorted(doctypes_dir.iterdir()):
                if not dt_dir.is_dir() or dt_dir.name.startswith((".", "_")):
                    continue
                py_file = dt_dir / f"{dt_dir.name}.py"
                if py_file.exists():
                    self._load_controller(
                        py_file,
                        f"{app_name}.{module_name}.doctypes.{dt_dir.name}.{dt_dir.name}",
                    )

    def _load_controller(self, py_file: Path, module_path: str) -> None:
        """Import a module and register any Document subclass found in it."""
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
