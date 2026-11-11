"""Deleting a ``GruntInstalledApp`` removes the app's directory under ``apps/`` -
never a same-named directory elsewhere in the bench."""

from grunt.site import bench
from grunt.startup.doctypes.GruntInstalledApp.grunt_installed_app import GruntInstalledApp


async def test_after_delete_removes_only_apps_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "_bench_dir", tmp_path)
    (tmp_path / "apps" / "shop").mkdir(parents=True)
    (tmp_path / "shop").mkdir()  # a same-named directory at the bench root

    async def no_workspaces(*_a, **_kw):
        return []

    from grunt.document.api import documents

    monkeypatch.setattr(documents, "get_list", no_workspaces)
    await GruntInstalledApp("GruntInstalledApp", {"name": "shop"}).after_delete()

    assert not (tmp_path / "apps" / "shop").exists()
    assert (tmp_path / "shop").exists()
