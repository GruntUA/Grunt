"""Versions from git tags, required_grunt, `grunt release` and `grunt test --changed`."""

import importlib
import json
import subprocess
from datetime import date
from pathlib import Path

import click
import pytest
from packaging.version import Version

from grunt import version as versions
from grunt.cli.changed_tests import select
from grunt.cli.release import (
    auto_bump,
    changelog_section,
    changelog_version,
    deploy_notes,
    new_migrations,
    next_version,
    prepend_changelog,
)
from grunt.testkit import write_app_manifest

# `grunt.cli.release` is shadowed by the click command of the same name.
rel = importlib.import_module("grunt.cli.release")
deps = importlib.import_module("grunt.cli.release_deps")


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("1")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "first")
    return tmp_path


def test_untagged_repo_counts_from_0_1(repo: Path):
    found = versions.git_version(repo)
    assert found is not None and found.startswith("0.1.dev1+g")


def test_version_on_tag(repo: Path):
    git(repo, "tag", "-a", "v1.2.0", "-m", "v1.2.0")
    assert versions.git_version(repo) == "1.2.0"


def test_version_after_tag_is_next_patch_dev(repo: Path):
    git(repo, "tag", "-a", "v1.2.0", "-m", "v1.2.0")
    (repo / "a.txt").write_text("2")
    git(repo, "commit", "-qam", "second")
    found = versions.git_version(repo)
    assert found is not None and found.startswith("1.2.1.dev1+g")

    (repo / "a.txt").write_text("3")  # uncommitted
    assert versions.git_version(repo).endswith(f".d{date.today():%Y%m%d}")  # type: ignore[union-attr]


def test_non_version_tags_are_ignored(repo: Path):
    git(repo, "tag", "-a", "release-candidate", "-m", "x")
    assert versions.git_version(repo).startswith("0.1.dev1+g")  # type: ignore[union-attr]


def test_app_version_without_git(tmp_path: Path):
    write_app_manifest(tmp_path)
    assert versions.app_version(tmp_path) == "0.0.0"


@pytest.mark.parametrize(
    ("spec", "running", "ok"),
    [
        ("", "0.1.0", True),
        (">=0.5", "0.5.1.dev3+gabc", True),
        (">=0.5,<1", "1.0.0", False),
        ("~=0.4.0", "0.4.7", True),
    ],
)
def test_required_grunt(tmp_path: Path, monkeypatch, spec: str, running: str, ok: bool):
    write_app_manifest(tmp_path, required_grunt=spec)
    monkeypatch.setattr(versions, "framework_version", lambda: running)
    assert (versions.compatibility_error(tmp_path) is None) is ok


def test_malformed_required_grunt_is_reported(tmp_path: Path):
    write_app_manifest(tmp_path, required_grunt="newest")
    assert "invalid" in (versions.compatibility_error(tmp_path) or "")


def test_next_version():
    assert next_version(None, "minor") == Version("0.1.0")
    assert next_version(Version("1.2.3"), "patch") == Version("1.2.4")
    assert next_version(Version("1.2.3"), "minor") == Version("1.3.0")
    assert next_version(Version("1.2.3"), "major") == Version("2.0.0")
    assert next_version(Version("1.2.3"), "1.5.0") == Version("1.5.0")
    with pytest.raises(click.BadParameter):
        next_version(Version("1.2.3"), "1.0.0")
    assert next_version(Version("0.4.2"), "auto", ["fix: x", "feat: y"]) == Version("0.5.0")


@pytest.mark.parametrize(
    ("current", "subjects", "bump"),
    [
        ("0.4.2", ["fix: a", "docs: b"], "patch"),
        ("0.4.2", ["fix: a", "feat(x): b"], "minor"),
        ("0.4.2", ["fix!: a"], "minor"),
        ("1.4.2", ["refactor(db)!: a", "feat: b"], "major"),
        ("1.4.2", ["tidy up"], "patch"),
    ],
)
def test_auto_bump(current: str, subjects: list[str], bump: str):
    assert auto_bump(Version(current), subjects) == bump


def test_deploy_notes():
    notes = deploy_notes(
        [
            ("A", "grunt/x/doctypes/Thing/Thing.json"),
            ("M", "grunt/y/doctypes/Other/Other.json"),
            ("M", "uv.lock"),
            ("M", "grunt/a.py"),
        ],
        ["0030_x"],
    )
    text = "\n".join(notes)
    assert "back up" in text
    assert "grunt migrate" in text
    assert "New DocTypes (Thing)" in text
    assert "uv.lock" in text

    only_doctype = deploy_notes([("M", "grunt/y/doctypes/Other/Other.json")], [])
    assert only_doctype == ["`grunt migrate --dry-run`, then `grunt migrate` on every site."]
    assert deploy_notes([("M", "grunt/a.py")], []) == [
        "No migrations: update the code and restart the services."
    ]


def test_changelog_version():
    assert changelog_version("# Changelog\n\n## v0.3.1 - x\n\n## v0.3.0 - y\n") == Version("0.3.1")
    assert changelog_version("# Changelog\n") is None


def test_changelog_groups_conventional_commits():
    section = changelog_section(
        Version("1.1.0"),
        [
            "feat(auth): passkeys",
            "fix: lockout counter",
            "feat!: drop S3",
            "chore(release): v1.0.0",
            "tidy imports",
        ],
        today=date(2026, 10, 12),
    )
    assert section.startswith("## v1.1.0 - 2026-10-12")
    assert "### Breaking changes\n\n- drop S3" in section
    assert "### Features\n\n- **auth:** passkeys" in section
    assert "### Fixes\n\n- lockout counter" in section
    assert "### Other\n\n- tidy imports" in section
    assert "v1.0.0" not in section

    deps = changelog_section(Version("1.1.1"), ["build(deps): update packages", "fix: x"])
    assert "### Dependencies\n\n- update packages" in deps


def test_changelog_lists_new_migrations(repo: Path):
    git(repo, "tag", "-a", "v1.0.0", "-m", "v1.0.0")
    versions_dir = repo / "grunt" / "db" / "migrations" / "versions"
    versions_dir.mkdir(parents=True)
    (versions_dir / "0002_b.py").write_text("")
    (versions_dir / "0001_a.py").write_text("")
    (repo / "notes.py").write_text("")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "feat: migrations")

    found = new_migrations(repo, "v1.0.0")
    assert found == ["0001_a", "0002_b"]
    section = changelog_section(Version("1.1.0"), ["feat: x"], migrations=found)
    assert "### Database migrations\n\n- `0001_a`\n- `0002_b`" in section
    assert "Database migrations" not in changelog_section(Version("1.1.0"), ["feat: x"])


def test_prepend_changelog_keeps_newest_first(tmp_path: Path):
    path = tmp_path / "CHANGELOG.md"
    prepend_changelog(path, "## v0.1.0\n")
    prepend_changelog(path, "## v0.2.0\n")
    assert path.read_text() == "# Changelog\n\n## v0.2.0\n\n## v0.1.0\n"


@pytest.fixture
def released(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """An app checkout whose origin has master (tagged v0.1.0) and develop."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(seed, "init", "-q", "-b", "master")
    (seed / "a.txt").write_text("1")
    git(seed, "add", ".")
    git(seed, "commit", "-qm", "first")
    git(seed, "tag", "-a", "v0.1.0", "-m", "v0.1.0")
    git(seed, "checkout", "-qb", "develop")
    (seed / "grunt" / "db" / "migrations" / "versions").mkdir(parents=True)
    (seed / "grunt" / "db" / "migrations" / "versions" / "0002_b.py").write_text("")
    git(seed, "add", ".")
    git(seed, "commit", "-qm", "feat(db): new table")
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "-q", "--follow-tags", "origin", "master", "develop")

    apps = tmp_path / "apps"
    apps.mkdir()
    app = apps / "grunt"
    git(tmp_path, "clone", "-q", str(origin), str(app))
    git(app, "config", "user.name", "t")
    git(app, "config", "user.email", "t@t")
    (app / "local.txt").write_text("uncommitted work stays")
    monkeypatch.setattr(rel, "_apps_dir", lambda: apps)
    monkeypatch.setattr(rel.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(rel, "open_release_pr", lambda repo, head, plan: f"PR {head}")
    return app, origin


def test_release_pushes_the_release_commit_to_develop(released):
    app, origin = released
    from click.testing import CliRunner

    dry = CliRunner().invoke(rel.release, ["--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "## v0.2.0" in dry.output and "0002_b" in dry.output and "back up" in dry.output

    result = CliRunner().invoke(rel.release, ["--yes"])
    assert result.exit_code == 0, result.output
    assert "PR develop" in result.output
    log = subprocess.run(
        ["git", "-C", str(origin), "log", "-1", "--format=%s", "develop"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert log == "chore(release): v0.2.0"
    changelog = subprocess.run(
        ["git", "-C", str(origin), "show", "develop:CHANGELOG.md"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert changelog.startswith("# Changelog\n\n## v0.2.0")
    # The checkout is untouched and no worktree is left behind.
    assert (app / "local.txt").exists() and not (app / "CHANGELOG.md").exists()
    assert (
        len(
            subprocess.run(
                ["git", "-C", str(app), "worktree", "list"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.splitlines()
        )
        == 1
    )

    # Until the pull request is merged and tagged, another release is refused.
    again = CliRunner().invoke(rel.release, ["--dry-run"])
    assert again.exit_code != 0 and "not tagged yet" in again.output


def _tree(root: Path, files: dict[str, str]) -> None:
    for name, body in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(body)


def test_changed_tests_selection(tmp_path: Path):
    _tree(
        tmp_path,
        {
            "grunt/auth/login.py": "",
            "grunt/auth/__init__.py": "",
            "grunt/auth/doctypes/User/user.json": "{}",
            "grunt/auth/doctypes/User/tests/test_user.py": "",
            "grunt/print/renderer.py": "",
            "grunt/print/tests/test_filters.py": "",
            "grunt/orphan.py": "",
            "tests/test_by_import.py": "from grunt.auth import login\n",
            "tests/test_by_patch.py": 'patch("grunt.auth.login.issue")\n',
            "tests/test_submodule_only.py": "import grunt.auth.mfa\n",
            "tests/test_doctype.py": 'grunt.get_doc("User", "x")\n',
            "tests/test_unrelated.py": "import grunt\n",
            "frontend/src/a.ts": "",
        },
    )
    changed = [
        tmp_path / p
        for p in (
            "grunt/auth/login.py",
            "grunt/auth/doctypes/User/user.json",
            "grunt/print/renderer.py",
            "grunt/orphan.py",
            "frontend/src/a.ts",
        )
    ]
    sel = select(tmp_path, changed)
    picked = sorted(str(t.relative_to(tmp_path)) for t in sel.tests)
    assert picked == [
        "grunt/auth/doctypes/User/tests/test_user.py",
        "grunt/print/tests/test_filters.py",
        "tests/test_by_import.py",
        "tests/test_by_patch.py",
        "tests/test_doctype.py",
    ]
    assert sel.uncovered == [tmp_path / "grunt/orphan.py"]
    assert sel.frontend == [tmp_path / "frontend/src/a.ts"]
    assert sel.full is None

    # `from grunt.auth import ...` goes through the package; grunt.auth.mfa does not.
    package = select(tmp_path, [tmp_path / "grunt/auth/__init__.py"])
    assert package.tests == {tmp_path / "tests/test_by_import.py"}

    assert select(tmp_path, [tmp_path / "conftest.py"]).full == "conftest.py"
    assert select(tmp_path, [tmp_path / "pyproject.toml"]).full is None


def test_locked_versions_and_changes(tmp_path: Path):
    (tmp_path / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "httpx"\nversion = "0.28.1"\n\n'
        '[[package]]\nname = "grunt"\nsource = { editable = "." }\n'
    )
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "": {"name": "grunt"},
                    "node_modules/vue": {"version": "3.5.0"},
                    "node_modules/@tiptap/core": {"version": "3.1.0"},
                    "node_modules/a/node_modules/vue": {"version": "2.7.0"},
                }
            }
        )
    )
    before = deps.locked_versions(tmp_path)
    assert before == {
        "httpx (python)": "0.28.1",
        "vue (npm)": "3.5.0",
        "@tiptap/core (npm)": "3.1.0",
    }
    after = {**before, "vue (npm)": "3.5.2", "new (npm)": "1.0.0"}
    del after["httpx (python)"]
    assert deps.version_changes(before, after) == [
        "httpx (python) 0.28.1 -> (removed)",
        "new (npm) (new) -> 1.0.0",
        "vue (npm) 3.5.0 -> 3.5.2",
    ]


def test_wait_for_ci(monkeypatch, tmp_path: Path):
    answers = iter(
        [
            [],  # runs not created yet
            [{"name": "CI", "status": "in_progress", "conclusion": ""}],
            [
                {"name": "CI", "status": "completed", "conclusion": "failure"},
                {"name": "CodeQL", "status": "completed", "conclusion": "success"},
            ],
        ]
    )

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, json.dumps(next(answers)), "")

    monkeypatch.setattr(deps.subprocess, "run", fake_run)
    assert deps.wait_for_ci(tmp_path, "abc", sleep=lambda s: None) == (False, ["CI"])
