"""Backend differences live in ``grunt/db/dialects/`` only (DB_LAYERS_PLAN.md, step 1).

Elsewhere code asks ``dialect_for(x)`` and calls a method instead of comparing
the backend name. ``NOT_YET_MOVED`` lists files still to be migrated - it may
only shrink.
"""

import re
from pathlib import Path

GRUNT = Path(__file__).resolve().parent.parent / "grunt"

_BACKENDS = r"(sqlite|postgresql|postgres|mysql|mariadb)"
FORBIDDEN = re.compile(
    "|".join(
        [
            r"\.dialect\.name\s*(==|!=|in\b)",
            r"get_backend_name\(\)\s*(==|!=|in\b)",
            rf"\bdialect(_name)?\s*(==|!=)\s*[\"']{_BACKENDS}[\"']",
            rf"\bdialect(_name)?\s+in\s*\(\s*[\"']{_BACKENDS}",
            rf"[\"']{_BACKENDS}[\"']\s+in\s+\w*url\b",
        ]
    )
)

NOT_YET_MOVED = {
    "search/service.py",  # FTS5 / tsvector / FULLTEXT, upsert
    "backups/__init__.py",  # backup()/restore() per backend
}


def _offenders() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in GRUNT.rglob("*.py"):
        rel = path.relative_to(GRUNT).as_posix()
        if rel.startswith("db/dialects/") or "/migrations/versions/" in rel or "/tests/" in rel:
            continue
        hits = [
            f"{n}: {line.strip()}"
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if FORBIDDEN.search(line)
        ]
        if hits:
            found[rel] = hits
    return found


def test_backend_names_are_compared_only_in_dialects():
    stray = {rel: hits for rel, hits in _offenders().items() if rel not in NOT_YET_MOVED}
    assert not stray, (
        "Backend-specific branches belong on a Dialect (grunt/db/dialects/):\n"
        + "\n".join(f"  {rel}:{hit}" for rel, hits in stray.items() for hit in hits)
    )


def test_not_yet_moved_list_is_current():
    """A migrated file must leave NOT_YET_MOVED, so the list keeps shrinking."""
    clean = NOT_YET_MOVED - set(_offenders())
    assert not clean, f"No longer branch on the backend - remove from NOT_YET_MOVED: {clean}"
