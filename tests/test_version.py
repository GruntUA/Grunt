"""Versions from git tags, required_grunt, `grunt release` and `grunt test --changed`."""

import subprocess
from datetime import date
from pathlib import Path

import click
import pytest
from packaging.version import Version

from grunt import version as versions
from grunt.cli.changed_tests import select
from grunt.cli.release import changelog_section, new_migrations, next_version, prepend_changelog
from grunt.testkit import write_app_manifest


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
