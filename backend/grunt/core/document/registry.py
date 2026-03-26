from __future__ import annotations

import importlib
import inspect
import os
from pathlib import Path
from typing import TYPE_CHECKING, Type

import structlog

from grunt.core.document.base import Document

if TYPE_CHECKING:
    from grunt.config import Settings

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
                if issubclass(controller_cls, Document):
                    self.register(doctype, controller_cls)
                    logger.info("document.overridden", doctype=doctype, controller=path)
            except (ImportError, AttributeError, ValueError) as e:
                logger.warning("document.override_failed", doctype=doctype, path=path, error=str(e))

    def get(self, doctype: str) -> Type[Document]:
        """Return the controller for a DocType, or the base Document class."""
        return self._controllers.get(doctype, Document)

    def discover_controllers(self, apps_path: str | Path) -> None:
        """Search for Document subclasses in the given apps path."""
        apps_path = Path(apps_path)
        if not apps_path.exists():
            return

        for app_dir in apps_path.iterdir():
            if not app_dir.is_dir() or app_dir.name.startswith("."):
                continue

            # Look for controllers in {app}/controllers/*.py
            controllers_dir = app_dir / "controllers"
            if not controllers_dir.exists():
                continue

            for py_file in controllers_dir.glob("*.py"):
                if py_file.name == "__init__.py":
                    continue

                module_name = f"grunt_apps.{app_dir.name}.controllers.{py_file.stem}"
                try:
                    module = importlib.import_module(module_name)
                    for name, obj in inspect.getmembers(module):
                        if (
                            inspect.isclass(obj)
                            and issubclass(obj, Document)
                            and obj is not Document
                        ):
                            # The class name should match the DocType (e.g. SalesOrder)
                            self.register(name, obj)
                except ImportError as e:
                    logger.warning("document.discovery_failed", module=module_name, error=str(e))


document_registry = DocumentRegistry()
