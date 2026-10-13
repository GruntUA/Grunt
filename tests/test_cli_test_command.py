"""`grunt test`: the framework and every app run in their own pytest session."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

# grunt.cli re-exports the `test` command under the module's own name
cli_test = importlib.import_module("grunt.cli.test")


def _bench(tmp_path):
    apps = tmp_path / "apps"
    (apps / "grunt" / "tests").mkdir(parents=True)
    (apps / "grunt" / "tests" / "test_core.py").write_text("")
    shop = apps / "shop"
    (shop / "tests").mkdir(parents=True)
    (shop / "app.json").write_text("{}")
    (shop / "tests" / "test_shop.py").write_text("")
    dt = shop / "shop" / "doctypes" / "Order" / "tests"
    dt.mkdir(parents=True)
    (dt / "test_order.py").write_text("")
    (shop / "node_modules" / "x").mkdir(parents=True)
    (shop / "node_modules" / "x" / "test_vendor.py").write_text("")
    empty = apps / "letter"
    empty.mkdir()
    (empty / "app.json").write_text("{}")
    return tmp_path


def test_paths(tmp_path):
    shop = _bench(tmp_path) / "apps" / "shop"
    assert cli_test._test_paths(shop, None) == [shop]
    assert cli_test._test_paths(shop, "Order") == [shop / "shop" / "doctypes" / "Order" / "tests"]
    assert cli_test._test_paths(tmp_path / "apps" / "letter", None) == []

    only_vendor = tmp_path / "apps" / "vendor_only"
    (only_vendor / "node_modules").mkdir(parents=True)
    (only_vendor / "node_modules" / "test_x.py").write_text("")
    assert cli_test._test_paths(only_vendor, None) == []


@pytest.fixture
def bench(tmp_path, monkeypatch):
    root = _bench(tmp_path)
    import grunt.site.manager as manager

    monkeypatch.setattr(manager, "site_manager", SimpleNamespace(bench_dir=root))
    return root


def test_one_session_per_app(bench, monkeypatch):
    calls = []

    def fake_run(cmd, cwd):
        calls.append((cmd[1:], cwd))
        return SimpleNamespace(returncode=1 if cwd.endswith("shop") else 0)

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/bin/pytest")
    result = CliRunner().invoke(cli_test.test, ["-q"])

    assert result.exit_code == 1, result.output  # shop failed
    assert calls == [
        (["-q"], str(bench / "apps" / "grunt")),
        (["-q"], str(bench / "apps" / "shop")),
    ]
    assert "✗ shop" in result.output and "✓ grunt" in result.output


def test_doctype_runs_only_its_tests(bench, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda cmd, cwd: calls.append((cmd[1:], cwd)) or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr("shutil.which", lambda name: "/bin/pytest")
    result = CliRunner().invoke(cli_test.test, ["shop", "--doctype", "Order", "-q"])

    assert result.exit_code == 0, result.output
    assert calls == [(["shop/doctypes/Order/tests", "-q"], str(bench / "apps" / "shop"))]
