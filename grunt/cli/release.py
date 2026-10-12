"""``grunt version`` and ``grunt release``: versions come from git tags ``vX.Y.Z``
(see :mod:`grunt.version`)."""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

import click
from packaging.version import InvalidVersion, Version

CHANGELOG = "CHANGELOG.md"
_CONVENTIONAL = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?:\s*(?P<text>.+)"
)
# Changelog section per conventional-commit type; anything else goes to "Other".
_SECTIONS = {"feat": "Features", "fix": "Fixes", "perf": "Performance"}
_SECTION_ORDER = ("Breaking changes", "Features", "Fixes", "Performance", "Other")


def _apps_dir() -> Path:
    from grunt.site.manager import site_manager

    return site_manager.bench_dir / "apps"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def last_tag(repo: Path) -> str | None:
    try:
        return _git(repo, "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*") or None
    except subprocess.CalledProcessError:
        return None


def new_migrations(repo: Path, since: str) -> list[str]:
    """Names of the Alembic migration files added after the ``since`` tag."""
    out = _git(
        repo,
        "diff",
        "--name-only",
        "--diff-filter=A",
        f"{since}..HEAD",
        "--",
        ":(glob)**/migrations/versions/*.py",
    )
    return sorted(Path(line).stem for line in out.splitlines())


def next_version(current: Version | None, bump: str) -> Version:
    """``patch`` / ``minor`` / ``major`` after ``current``, or an explicit ``X.Y.Z``."""
    major, minor, patch = (*(current.release if current else ()), 0, 0, 0)[:3]
    match bump:
        case "major":
            return Version(f"{major + 1}.0.0")
        case "minor":
            return Version(f"{major}.{minor + 1}.0")
        case "patch":
            return Version(f"{major}.{minor}.{patch + 1}")
    try:
        target = Version(bump)
    except InvalidVersion:
        raise click.BadParameter(f"expected patch, minor, major or X.Y.Z, got {bump!r}") from None
    if current and target <= current:
        raise click.BadParameter(f"{target} is not newer than {current}")
    return target


def changelog_section(
    version: Version,
    subjects: list[str],
    today: date | None = None,
    migrations: list[str] | None = None,
) -> str:
    """Markdown section for one release, commits grouped by conventional type.

    ``migrations`` - database migration files added since the previous release:
    rolling back past this release needs a backup restore, so they are listed."""
    groups: dict[str, list[str]] = {name: [] for name in _SECTION_ORDER}
    for subject in subjects:
        m = _CONVENTIONAL.match(subject)
        if not m:
            groups["Other"].append(subject)
            continue
        if m["type"] == "chore" and m["scope"] == "release":
            continue
        text = f"**{m['scope']}:** {m['text']}" if m["scope"] else m["text"]
        section = "Breaking changes" if m["breaking"] else _SECTIONS.get(m["type"], "Other")
        groups[section].append(text)
    lines = [f"## v{version} - {(today or date.today()).isoformat()}"]
    for name in _SECTION_ORDER:
        if groups[name]:
            lines += ["", f"### {name}", "", *(f"- {item}" for item in groups[name])]
    if migrations:
        lines += ["", "### Database migrations", "", *(f"- `{m}`" for m in migrations)]
    return "\n".join(lines) + "\n"


def prepend_changelog(path: Path, section: str) -> None:
    header = "# Changelog\n"
    old = path.read_text() if path.exists() else header
    body = old.removeprefix(header).lstrip("\n")
    path.write_text(f"{header}\n{section}" + (f"\n{body}" if body else ""))


@click.command("version")
def version() -> None:
    """Show the framework and app versions."""
    from grunt.version import app_version, compatibility_error, framework_version

    click.echo(f"grunt {framework_version()}")
    for app_dir in sorted(_apps_dir().iterdir()):
        if app_dir.name == "grunt" or not (app_dir / "app.json").exists():
            continue
        problem = compatibility_error(app_dir)
        suffix = click.style(f"  ({problem})", fg="red") if problem else ""
        click.echo(f"{app_dir.name} {app_version(app_dir)}{suffix}")


@click.command("release")
@click.argument("bump", default="patch")
@click.option("--app", "app_name", default="grunt", show_default=True, help="App to release")
@click.option("--dry-run", is_flag=True, help="Only print the changelog section")
def release(bump: str, app_name: str, dry_run: bool) -> None:
    """Tag a release: CHANGELOG.md section + commit + annotated tag vX.Y.Z.

    BUMP is patch (default), minor, major or an explicit X.Y.Z. Nothing is
    pushed - push with `git push --follow-tags` once the tag looks right.
    """
    repo = _apps_dir() / app_name
    if not (repo / ".git").exists():
        raise click.ClickException(f"{repo} is not a git repository")
    if not dry_run and _git(repo, "status", "--porcelain"):
        raise click.ClickException("the working tree has uncommitted changes")

    tag = last_tag(repo)
    target = next_version(Version(tag[1:]) if tag else None, bump)
    # The first release does not list the whole history.
    subjects = _git(repo, "log", "--no-merges", "--format=%s", f"{tag}..HEAD") if tag else ""
    if tag and not subjects:
        raise click.ClickException(f"no commits since {tag}")

    section = changelog_section(
        target,
        subjects.splitlines() if tag else ["Initial release"],
        migrations=new_migrations(repo, tag) if tag else None,
    )
    click.echo(section)
    if dry_run:
        return

    prepend_changelog(repo / CHANGELOG, section)
    _git(repo, "add", CHANGELOG)
    _git(repo, "commit", "-m", f"chore(release): v{target}")
    _git(repo, "tag", "-a", f"v{target}", "-m", section)
    click.echo(f"Tagged v{target}. Push it: git -C {repo} push --follow-tags")
