"""Field validator registry.

Validators are discovered automatically at startup from:
  - grunt/validators/*.py          (built-in)
  - {app}/{app}/validators/*.py    (per-app custom)

Each validator file must define at least one subclass of
``grunt.validators.base.Validator`` with ``name`` and ``label`` set.

Programmatic registration:

    from grunt.document.validators import register_validator
    from grunt.validators.base import RegexValidator

    class PostalCodeValidator(RegexValidator):
        name = "postal_ua"
        label = "Поштовий індекс (UA)"
        message = "Поле '{label}': невірний індекс (5 цифр)"
        pattern = r"^\\d{5}$"

    register_validator(PostalCodeValidator)
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from typing import TYPE_CHECKING

from grunt import _, log
from grunt.validators.base import Validator

if TYPE_CHECKING:
    from pathlib import Path


# name -> Validator instance (singleton per class)
_REGISTRY: dict[str, Validator] = {}


def register_validator(validator: type[Validator] | Validator) -> None:
    """Register a validator class or instance (idempotent)."""
    instance = validator() if isinstance(validator, type) else validator
    if not getattr(instance, "name", None) or not getattr(instance, "label", None):
        raise ValueError(f"Validator {type(instance).__name__} must define 'name' and 'label'")
    _REGISTRY[instance.name] = instance
    log.debug("validator.registered", name=instance.name)


def get_validator(name: str) -> Validator | None:
    return _REGISTRY.get(name)


def list_validators() -> list[dict[str, object]]:
    """Return all validators as ``[{name, label, field_types}]`` sorted by label."""
    return sorted(
        [
            {"name": v.name, "label": _(v.label), "field_types": v.field_types}
            for v in _REGISTRY.values()
        ],
        key=lambda v: v["label"],  # type: ignore[arg-type]
    )


def validate_field_value(validator_name: str, value: object, field_label: str) -> str | None:
    """Run *validator_name* against *value*.

    Returns an error string on failure, ``None`` on success or unknown validator.
    """
    instance = _REGISTRY.get(validator_name)
    if instance is None:
        return None
    return instance.validate(str(value) if value is not None else "", field_label)


def load_from_dir(directory: Path) -> int:
    """Import all ``*.py`` files in *directory*, find ``Validator`` subclasses, register them.

    Skips ``__init__.py``, ``base.py``, and abstract classes (no ``name``/``label``).
    Returns the count of validators successfully registered.
    """
    loaded = 0
    for py_file in sorted(directory.glob("*.py")):
        if py_file.stem.startswith("_") or py_file.stem == "base":
            continue

        module_name = f"_grunt_validator_{directory.parent.name}_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except Exception as exc:
            log.warning("validator.load_error", file=str(py_file), error=str(exc))
            continue

        for _attr_name, obj in inspect.getmembers(mod, inspect.isclass):
            if (
                obj is Validator
                or not issubclass(obj, Validator)
                or not getattr(obj, "name", None)
                or not getattr(obj, "label", None)
            ):
                continue
            try:
                register_validator(obj)
                loaded += 1
            except Exception as exc:
                log.warning(
                    "validator.register_error",
                    cls=obj.__name__,
                    file=str(py_file),
                    error=str(exc),
                )

    return loaded
