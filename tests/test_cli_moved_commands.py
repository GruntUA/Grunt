"""Commands moved here from grunt-cli: doctype show/export/scaffold/sync, db rollback, aliases."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from grunt.cli import cli
from grunt.cli import db as db_cli
from grunt.cli import doctype as doctype_cli
from grunt.cli import fixtures as fixtures_cli


@pytest.fixture
def bench(tmp_path, monkeypatch):
    """A bench with app `shop` (module `shop`) holding DocType Thing; no core DocTypes."""
    dt_dir = tmp_path / "apps" / "shop" / "shop" / "doctypes" / "Thing"
    dt_dir.mkdir(parents=True)
    fields = [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data", "required": True},
        {"fieldname": "sb", "label": "", "fieldtype": "Section"},
    ]
    (dt_dir / "Thing.json").write_text(
        json.dumps({"name": "Thing", "label": "A thing", "module": "shop", "fields": fields})
    )
    (tmp_path / "apps" / "grunt").mkdir()
    monkeypatch.setattr(doctype_cli, "site_manager", SimpleNamespace(bench_dir=tmp_path))
    monkeypatch.setattr(doctype_cli, "_find_doctype_dirs", list)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_show_lists_fields_without_layout(bench):
    result = CliRunner().invoke(doctype_cli.doctype_show, ["Thing"])

    assert result.exit_code == 0, result.output
    assert "Module: shop" in result.output
    assert "title" in result.output
    assert "Section" not in result.output


def test_show_unknown_doctype(bench):
    result = CliRunner().invoke(doctype_cli.doctype_show, ["Nope"])

    assert result.exit_code == 1
    assert "not found" in result.output


def test_export_writes_doctype_wrapper(bench):
    result = CliRunner().invoke(doctype_cli.doctype_export, ["Thing", "-o", "out.json"])

    assert result.exit_code == 0, result.output
    assert json.loads((bench / "out.json").read_text())["doctype"]["name"] == "Thing"


def test_scaffold_follows_the_app_layout(bench):
    result = CliRunner().invoke(doctype_cli.doctype_scaffold, ["Order"])  # the only app: shop

    assert result.exit_code == 0, result.output
    dt_dir = bench / "apps" / "shop" / "shop" / "doctypes" / "Order"
    meta = json.loads((dt_dir / "Order.json").read_text())
    assert meta["module"] == "shop"
    assert "# begin: auto-generated types" in (dt_dir / "Order.py").read_text()
    assert (dt_dir / "Order.js").exists()
    assert (dt_dir / "__init__.py").exists()


def test_scaffold_py_only_regenerates_the_controller(bench):
    py = bench / "apps" / "shop" / "shop" / "doctypes" / "Thing" / "Thing.py"

    result = CliRunner().invoke(doctype_cli.doctype_scaffold, ["Thing", "--py-only"])

    assert result.exit_code == 0, result.output
    assert "title: str" in py.read_text()


def test_scaffold_unknown_module(bench):
    result = CliRunner().invoke(
        doctype_cli.doctype_scaffold, ["Order", "--app", "shop", "--module", "nope"]
    )

    assert result.exit_code == 1
    assert "module package" in result.output


@pytest.fixture
def synced(bench, monkeypatch):
    """Fake DB side of `doctype sync`: record which DocTypes would be synced."""
    names: list[str] = []

    @asynccontextmanager
    async def session(site):
        yield SimpleNamespace(), SimpleNamespace()

    async def ensure_table(session):
        pass

    async def sync_one(name, session, eng):
        names.append(name)
        return name != "Broken"

    monkeypatch.setattr(doctype_cli, "_site_session", session)
    monkeypatch.setattr(doctype_cli, "store", SimpleNamespace(ensure_table=ensure_table))
    monkeypatch.setattr(doctype_cli, "_sync_one", sync_one)
    return names


def test_sync_app_collects_its_doctypes(synced):
    result = CliRunner().invoke(doctype_cli.doctype_sync, ["--app", "shop"])

    assert result.exit_code == 0, result.output
    assert synced == ["Thing"]


def test_sync_fails_if_any_doctype_failed(synced):
    result = CliRunner().invoke(doctype_cli.doctype_sync, ["Thing", "Broken"])

    assert result.exit_code == 1
    assert synced == ["Thing", "Broken"]


def test_sync_needs_a_target(synced):
    result = CliRunner().invoke(doctype_cli.doctype_sync, [])

    assert result.exit_code == 1
    assert synced == []


def _command(path) -> click.Command:
    cmd: click.Command | None = cli
    ctx = click.Context(cli)
    for name in path:
        assert isinstance(cmd, click.Group)
        cmd = cmd.get_command(ctx, name)
    assert cmd is not None
    return cmd


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (["sites"], ["site"]),
        (["site", "new"], ["site", "create"]),
        (["site", "drop"], ["site", "delete"]),
        (["doctype", "apply"], ["doctype", "sync"]),
    ],
)
def test_grunt_cli_names_still_work(old, new):
    """`grunt sites new` etc. used to live in grunt-cli; they are aliases now."""
    assert _command(old) is _command(new)


def test_site_delete_accepts_the_old_force_flag():
    [yes] = [p for p in _command(["site", "delete"]).params if p.name == "yes"]
    assert "--force" in yes.opts


def test_db_rollback_downgrades_the_site(monkeypatch):
    calls = []
    monkeypatch.setattr(db_cli, "resolve_site", lambda site: site or "active")
    monkeypatch.setattr(
        db_cli, "site_manager", SimpleNamespace(get_database_url=lambda s: f"sqlite:///{s}.db")
    )
    from alembic import command

    monkeypatch.setattr(command, "downgrade", lambda cfg, rev: calls.append((cfg, rev)))

    result = CliRunner().invoke(db_cli.db_rollback, ["2", "--site", "s1"])

    assert result.exit_code == 0, result.output
    [(cfg, rev)] = calls
    assert rev == "-2"
    assert cfg.attributes["target_db_url"] == "sqlite:///s1.db"


def test_fixtures_load_rejects_a_file_without_records(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"doctype": "Thing"}))

    result = CliRunner().invoke(fixtures_cli.fixtures_load, [str(bad)])

    assert result.exit_code == 1
    assert "'doctype' and 'records'" in result.output
