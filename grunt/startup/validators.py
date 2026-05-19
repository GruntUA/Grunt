"""Startup — discover and load field validators.

Scans:
  1. grunt/validators/          — built-in validators shipped with the framework
  2. {bench}/apps/{app}/{app}/validators/  — per-app custom validators
"""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger()

_GRUNT_ROOT = Path(__file__).parent.parent  # grunt/startup/ → grunt/


def _find_validator_dirs() -> list[Path]:
    """Return all validator directories: grunt/validators/ + app validators/."""
    dirs: list[Path] = []

    grunt_validators = _GRUNT_ROOT / "validators"
    if grunt_validators.is_dir():
        dirs.append(grunt_validators)

    from grunt.site.manager import site_manager  # noqa: PLC0415

    bench_dir = site_manager.bench_dir
    if bench_dir:
        apps_dir = bench_dir / "apps"
        if apps_dir.is_dir():
            for app_dir in sorted(apps_dir.iterdir()):
                if (
                    not app_dir.is_dir()
                    or app_dir.name in ("grunt",)
                    or app_dir.name.startswith((".", "_"))
                ):
                    continue
                # Convention: {app}/{app}/validators/
                candidate = app_dir / app_dir.name / "validators"
                if candidate.is_dir():
                    dirs.append(candidate)
                # Also support flat: {app}/validators/
                candidate2 = app_dir / "validators"
                if candidate2.is_dir() and candidate2 != candidate:
                    dirs.append(candidate2)

    return dirs


def load_validators() -> int:
    """Discover and register all validators. Returns total count loaded."""
    from grunt.document.validators import load_from_dir  # noqa: PLC0415

    total = 0
    for validator_dir in _find_validator_dirs():
        count = load_from_dir(validator_dir)
        if count:
            logger.info("validators.loaded", dir=str(validator_dir), count=count)
        total += count

    logger.info("validators.total", count=total)
    return total
