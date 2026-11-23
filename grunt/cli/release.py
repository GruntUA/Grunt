"""``grunt version`` and ``grunt release``: versions come from git tags ``vX.Y.Z``
(see :mod:`grunt.version`)."""

import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import click
from packaging.version import InvalidVersion, Version

lazy from grunt.apps.manifest import is_app
lazy from grunt.cli.release_deps import DEPS_TITLE, deps_pr_body, update_locks, wait_for_ci
lazy from grunt.site.manager import site_manager
lazy from grunt.version import app_version, compatibility_error, framework_version

CHANGELOG = "CHANGELOG.md"
RELEASE_BRANCH = "master"
_CONVENTIONAL = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?:\s*(?P<text>.+)"
)
# Changelog section per conventional-commit type; anything else goes to "Other".
_SECTIONS = {"feat": "Features", "fix": "Fixes", "perf": "Performance"}
_SECTION_ORDER = ("Breaking changes", "Features", "Fixes", "Performance", "Dependencies", "Other")
_CHANGELOG_HEADING = re.compile(r"^## v(?P<version>\d+\.\d+\.\d+)\b", re.MULTILINE)
_DOCTYPE_JSON = re.compile(r"(^|/)doctypes/[^/]+/[^/]+\.json$")
_DEPENDENCY_FILES = ("uv.lock", "package-lock.json", "mise.toml")
#: A subject longer than this swallowed its body (no blank line after the title,
#: as a squash merge can leave it): the changelog keeps the part before " - ".
_MAX_SUBJECT = 120


def _apps_dir() -> Path:

    return site_manager.bench_dir / "apps"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _step(repo: Path, *args: str) -> str:
    """``_git`` for a step of the release: a failure stops it with git's own message."""
    try:
        return _git(repo, *args)
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(f"git {' '.join(args)}: {exc.stderr.strip()}") from None


def last_tag(repo: Path, ref: str = "HEAD") -> str | None:
    try:
        return _git(repo, "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", ref) or None
    except subprocess.CalledProcessError:
        return None


def _changed(repo: Path, since: str, ref: str) -> list[tuple[str, str]]:
    """``(status, path)`` of the files changed between ``since`` and ``ref``."""
    out = _git(repo, "diff", "--name-status", "--no-renames", f"{since}..{ref}")
    return [(line[0], line.split("\t", 1)[1]) for line in out.splitlines() if "\t" in line]


def new_migrations(repo: Path, since: str, ref: str = "HEAD") -> list[str]:
    """Names of the Alembic migration files added after the ``since`` tag."""
    out = _git(
        repo,
        "diff",
        "--name-only",
        "--diff-filter=A",
        f"{since}..{ref}",
        "--",
        ":(glob)**/migrations/versions/*.py",
    )
    return sorted(Path(line).stem for line in out.splitlines())


def auto_bump(current: Version | None, subjects: list[str]) -> str:
    """The bump the commits ask for. Before 1.0 a breaking change is a ``minor``
    (CONTRIBUTING.md), from 1.0 on it is a ``major``."""
    kinds = [m for m in map(_CONVENTIONAL.match, subjects) if m]
    if any(m["breaking"] for m in kinds):
        return "major" if current and current.major >= 1 else "minor"
    if any(m["type"] == "feat" for m in kinds):
        return "minor"
    return "patch"


def next_version(current: Version | None, bump: str, subjects: list[str] | None = None) -> Version:
    """``patch`` / ``minor`` / ``major`` after ``current``, an explicit ``X.Y.Z``
    or ``auto`` - picked from the conventional ``subjects``."""
    if bump == "auto":
        bump = auto_bump(current, subjects or [])
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
        raise click.BadParameter(
            f"expected auto, patch, minor, major or X.Y.Z, got {bump!r}"
        ) from None
    if current and target <= current:
        raise click.BadParameter(f"{target} is not newer than {current}")
    return target


def non_conventional(subjects: list[str]) -> list[str]:
    """Subjects that will land under "Other" because they are not conventional commits."""
    return [s for s in subjects if not _CONVENTIONAL.match(s)]


def _headline(text: str) -> str:
    """``text`` cut to its headline when the commit body leaked into the subject."""
    if len(text) <= _MAX_SUBJECT:
        return text
    return text.split(" - ", 1)[0].rstrip()


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
            groups["Other"].append(_headline(subject))
            continue
        if m["type"] == "chore" and m["scope"] == "release":
            continue
        if m["scope"] == "deps" and not m["breaking"]:
            groups["Dependencies"].append(_headline(m["text"]))
            continue
        headline = _headline(m["text"])
        text = f"**{m['scope']}:** {headline}" if m["scope"] else headline
        section = "Breaking changes" if m["breaking"] else _SECTIONS.get(m["type"], "Other")
        groups[section].append(text)
    lines = [f"## v{version} - {(today or date.today()).isoformat()}"]
    for name in _SECTION_ORDER:
        if groups[name]:
            lines += ["", f"### {name}", "", *(f"- {item}" for item in groups[name])]
    if migrations:
        lines += ["", "### Database migrations", "", *(f"- `{m}`" for m in migrations)]
    return "\n".join(lines) + "\n"


def deploy_notes(changes: list[tuple[str, str]], migrations: list[str]) -> list[str]:
    """What a site needs after updating to the release, from the changed files."""
    doctypes = [path for status, path in changes if _DOCTYPE_JSON.search(path)]
    new_doctypes = [
        Path(path).parent.name
        for status, path in changes
        if status == "A" and _DOCTYPE_JSON.search(path)
    ]
    deps = sorted({Path(p).name for _, p in changes if Path(p).name in _DEPENDENCY_FILES})
    notes = []
    if migrations:
        notes.append(
            f"Database migrations ({len(migrations)}): back up first (`grunt db backup`)"
            " - rolling back past this release needs a restore."
        )
    if migrations or doctypes:
        notes.append("`grunt migrate --dry-run`, then `grunt migrate` on every site.")
    if new_doctypes:
        notes.append(f"New DocTypes ({', '.join(sorted(new_doctypes))}): restart the worker.")
    if deps:
        notes.append(f"Dependencies changed ({', '.join(deps)}): `grunt update` installs them.")
    if not notes:
        notes.append("No migrations: update the code and restart the services.")
    return notes


def prepend_changelog(path: Path, section: str) -> None:
    header = "# Changelog\n"
    old = path.read_text() if path.exists() else header
    body = old.removeprefix(header).lstrip("\n")
    path.write_text(f"{header}\n{section}" + (f"\n{body}" if body else ""))


def changelog_version(text: str) -> Version | None:
    """The newest version ``CHANGELOG.md`` has a section for."""
    m = _CHANGELOG_HEADING.search(text)
    return Version(m["version"]) if m else None


@dataclass
class ReleasePlan:
    version: Version
    section: str
    notes: list[str]
    warnings: list[str]


def ensure_released(repo: Path, ref: str) -> None:
    """Refuse while the previous release is prepared but its pull request is not merged."""
    tag = last_tag(repo, ref)
    current = Version(tag[1:]) if tag else None
    pending = _changelog_at(repo, ref)
    if pending and (current is None or pending > current):
        raise click.ClickException(
            f"v{pending} is already in {CHANGELOG} but not tagged yet:"
            f" merge its pull request into {RELEASE_BRANCH} first"
        )


def plan_release(repo: Path, ref: str, bump: str) -> ReleasePlan:
    """What releasing ``ref`` gives: the changelog section and the deploy notes."""
    ensure_released(repo, ref)
    tag = last_tag(repo, ref)
    current = Version(tag[1:]) if tag else None
    if not tag:
        # The first release does not list the whole history.
        version = next_version(None, "minor" if bump == "auto" else bump)
        return ReleasePlan(version, changelog_section(version, ["Initial release"]), [], [])

    subjects = _git(repo, "log", "--no-merges", "--format=%s", f"{tag}..{ref}").splitlines()
    subjects = [s for s in subjects if not s.startswith("chore(release):")]
    if not subjects:
        raise click.ClickException(f"no commits since {tag}")
    version = next_version(current, bump, subjects)
    migrations = new_migrations(repo, tag, ref)
    warnings = [
        f'not a conventional commit, listed under "Other": {s}' for s in non_conventional(subjects)
    ]
    return ReleasePlan(
        version,
        changelog_section(version, subjects, migrations=migrations),
        deploy_notes(_changed(repo, tag, ref), migrations),
        warnings,
    )


def _changelog_at(repo: Path, ref: str) -> Version | None:
    try:
        return changelog_version(_git(repo, "show", f"{ref}:{CHANGELOG}"))
    except subprocess.CalledProcessError:
        return None


def _base_branch(repo: Path) -> str:
    """``develop`` when the repository has one, else the release branch itself."""
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/develop")
        return "develop"
    except subprocess.CalledProcessError:
        return RELEASE_BRANCH


@contextmanager
def _worktree(repo: Path, ref: str) -> Iterator[Path]:
    """A throwaway checkout of ``ref``: the repository's own tree (with its branch
    and uncommitted work) stays untouched."""
    path = Path(tempfile.mkdtemp(prefix="grunt-release-"))
    _step(repo, "worktree", "add", "--quiet", "--detach", str(path), ref)
    try:
        yield path
    finally:
        _git(repo, "worktree", "remove", "--force", str(path))
        shutil.rmtree(path, ignore_errors=True)


def pr_body(plan: ReleasePlan) -> str:
    notes = "\n".join(f"- [ ] {n}" for n in plan.notes)
    return (
        f"{plan.section}\n## Deploy\n\n{notes}\n\n"
        "**Merge with a merge commit, not squash:** master then keeps develop's history"
        " and the next release pull request lists only the new commits.\n\n"
        f"Merging tags the release commit `v{plan.version}` and publishes the GitHub release"
        " (`.github/workflows/release.yml`).\n"
    )


def _gh(repo: Path, *args: str, stdin: str | None = None) -> str:
    try:
        return subprocess.run(
            ["gh", *args], cwd=repo, input=stdin, capture_output=True, text=True, check=True
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(f"gh {args[0]} {args[1]}: {exc.stderr.strip()}") from None


def open_pr(repo: Path, base: str, head: str, title: str, body: str) -> str:
    """The pull request ``head`` -> ``base``: opened, or updated if one is open
    (a release or a dependency update run again)."""
    found = json.loads(_gh(repo, "pr", "list", "--base", base, "--head", head, "--json", "url"))
    if found:
        url = found[0]["url"]
        _gh(repo, "pr", "edit", url, "--title", title, "--body-file", "-", stdin=body)
        return url
    return _gh(
        repo,
        "pr",
        "create",
        "--base",
        base,
        "--head",
        head,
        "--title",
        title,
        "--body-file",
        "-",
        stdin=body,
    )


def open_release_pr(repo: Path, head: str, plan: ReleasePlan) -> str:
    """The release pull request ``head`` -> master."""
    return open_pr(repo, RELEASE_BRANCH, head, f"chore(release): v{plan.version}", pr_body(plan))


@click.command("version")
def version() -> None:
    """Show the framework and app versions."""

    click.echo(f"grunt {framework_version()}")
    for app_dir in sorted(_apps_dir().iterdir()):
        if app_dir.name == "grunt" or not is_app(app_dir):
            continue
        problem = compatibility_error(app_dir)
        suffix = click.style(f"  ({problem})", fg="red") if problem else ""
        click.echo(f"{app_dir.name} {app_version(app_dir)}{suffix}")


@click.command("release")
@click.argument("bump", default="auto")
@click.option("--app", "app_name", default="grunt", show_default=True, help="App to release")
@click.option(
    "--deps",
    is_flag=True,
    help="First update the lock files within the declared ranges (own PR, merged once CI is green)",
)
@click.option("--dry-run", is_flag=True, help="Only show the changelog section and deploy notes")
@click.option("--yes", "-y", is_flag=True, help="Do not ask for confirmation")
def release(bump: str, app_name: str, deps: bool, dry_run: bool, yes: bool) -> None:
    """Prepare a release: CHANGELOG.md section, commit and pull request into master.

    BUMP is auto (default: minor for features and breaking changes before 1.0,
    patch otherwise), patch, minor, major or an explicit X.Y.Z.

    \b
    Works on origin/develop (origin/master if there is no develop) in a
    throwaway worktree - the app's own checkout is not touched:
      0. with --deps: `uv lock --upgrade` and `npm update` (lock files only),
         a pull request into develop, merged once its CI is green;
      1. commit `chore(release): vX.Y.Z` with the new CHANGELOG.md section;
      2. push it to develop (or to a release/vX.Y.Z branch);
      3. open the pull request into master with the deploy notes.
    Merging the pull request tags the commit and publishes the GitHub release
    (.github/workflows/release.yml).
    """
    repo = _apps_dir() / app_name
    if not (repo / ".git").exists():
        raise click.ClickException(f"{repo} is not a git repository")
    if (deps or not dry_run) and not shutil.which("gh"):
        raise click.ClickException("gh is not installed (https://cli.github.com)")

    _step(repo, "fetch", "--quiet", "--tags", "origin")
    base = _base_branch(repo)
    ref = f"origin/{base}"
    ensure_released(repo, ref)

    with ExitStack() as stack:
        changes: list[str] = []
        deps_tree: Path | None = None
        if deps:
            click.echo("Updating the lock files within the declared ranges...")
            deps_tree = stack.enter_context(_worktree(repo, ref))
            changes = update_locks(deps_tree, repo)
            if changes:
                click.echo(f"Dependencies ({len(changes)}), a pull request into {base} first:")
                for line in changes[:15]:
                    click.echo(f"  {line}")
                if len(changes) > 15:
                    click.echo(f"  ... and {len(changes) - 15} more (all in the pull request)")
            else:
                click.echo("Dependencies: already the newest the ranges allow")
            click.echo()

        plan = _show_plan(repo, ref, bump, allow_empty=bool(changes))
        if dry_run:
            return
        what = "update the dependencies, then commit" if changes else "Commit"
        if not yes:
            click.confirm(
                f"\n{what.capitalize()} the release and open the pull request?", abort=True
            )

        if changes and deps_tree:
            ref = _merge_dependencies(repo, deps_tree, base, changes)
            plan = plan_release(repo, ref, bump)
            click.echo(f"\nRelease v{plan.version} now includes the dependencies")

    if plan is None:  # only reachable without dependency changes - already refused
        return
    head = base if base != RELEASE_BRANCH else f"release/v{plan.version}"
    with _worktree(repo, ref) as tree:
        prepend_changelog(tree / CHANGELOG, plan.section)
        _step(tree, "add", CHANGELOG)
        _step(tree, "commit", "--quiet", "-m", f"chore(release): v{plan.version}")
        _step(tree, "push", "--quiet", "origin", f"HEAD:refs/heads/{head}")
    click.secho(f"Pushed chore(release): v{plan.version} to {head}", fg="green")
    click.secho(f"Pull request: {open_release_pr(repo, head, plan)}", fg="green")


def _show_plan(repo: Path, ref: str, bump: str, *, allow_empty: bool) -> ReleasePlan | None:
    """Print what the release will contain. ``allow_empty`` - nothing but the
    dependency update is new: the section is known once it is merged."""
    click.echo(f"Release of {ref} ({_git(repo, 'rev-parse', '--short', ref)})\n")
    try:
        plan = plan_release(repo, ref, bump)
    except click.ClickException as exc:
        if allow_empty and exc.message.startswith("no commits since"):
            click.echo("Only the dependency update is new since the last release.")
            return None
        raise
    click.echo(plan.section)
    if plan.notes:
        click.echo("Deploy:")
        for note in plan.notes:
            click.echo(f"  - {note}")
    for warning in plan.warnings:
        click.secho(f"! {warning}", fg="yellow")
    return plan


def _merge_dependencies(repo: Path, tree: Path, base: str, changes: list[str]) -> str:
    """Push the lock files as their own pull request into ``base``, wait for its CI
    and squash-merge it. The ref to release from."""
    branch = f"deps/{date.today():%Y-%m-%d}"
    _step(tree, "add", "-A")
    _step(tree, "commit", "--quiet", "-m", DEPS_TITLE)
    _step(tree, "push", "--quiet", "--force", "origin", f"HEAD:refs/heads/{branch}")
    sha = _git(tree, "rev-parse", "HEAD")
    url = open_pr(repo, base, branch, DEPS_TITLE, deps_pr_body(changes))
    click.echo(f"Dependencies: {url} - waiting for CI...")
    passed, failed = wait_for_ci(repo, sha)
    if not passed:
        raise click.ClickException(
            f"CI failed on the dependency update ({', '.join(failed)}): {url}\n"
            "Fix it there, or release without --deps."
        )
    _gh(repo, "pr", "merge", url, "--squash", "--delete-branch")
    click.secho("Dependencies merged", fg="green")
    _step(repo, "fetch", "--quiet", "--tags", "origin")
    return f"origin/{base}"
