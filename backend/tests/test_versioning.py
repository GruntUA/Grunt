"""Tests for the Document Versioning module."""

from grunt.core.document.versioning import VersionService


class TestComputeDiff:
    def setup_method(self):
        self.svc = VersionService()

    def test_no_changes(self):
        old = {"name": "A", "title": "Hello"}
        new = {"name": "A", "title": "Hello"}
        assert self.svc._compute_diff(old, new) == []

    def test_field_changed(self):
        old = {"name": "A", "title": "Hello"}
        new = {"name": "A", "title": "World"}
        diff = self.svc._compute_diff(old, new)
        assert len(diff) == 1
        assert diff[0]["field"] == "title"
        assert diff[0]["old"] == "Hello"
        assert diff[0]["new"] == "World"

    def test_multiple_changes(self):
        old = {"a": 1, "b": "x", "c": True}
        new = {"a": 2, "b": "y", "c": True}
        diff = self.svc._compute_diff(old, new)
        assert len(diff) == 2
        fields = [d["field"] for d in diff]
        assert "a" in fields
        assert "b" in fields

    def test_skips_modified_at(self):
        old = {"name": "A", "modified_at": "2026-01-01", "modified_by": "user@test.com"}
        new = {"name": "A", "modified_at": "2026-01-02", "modified_by": "admin@test.com"}
        diff = self.svc._compute_diff(old, new)
        assert len(diff) == 0

    def test_new_field_added(self):
        old = {"name": "A"}
        new = {"name": "A", "status": "Active"}
        diff = self.svc._compute_diff(old, new)
        assert len(diff) == 1
        assert diff[0]["field"] == "status"
        assert diff[0]["old"] is None
        assert diff[0]["new"] == "Active"

    def test_field_removed(self):
        old = {"name": "A", "status": "Active"}
        new = {"name": "A"}
        diff = self.svc._compute_diff(old, new)
        assert len(diff) == 1
        assert diff[0]["old"] == "Active"
        assert diff[0]["new"] is None


class TestBuildRestoreData:
    def setup_method(self):
        self.svc = VersionService()

    def test_restore_to_previous_version(self):
        current = {"name": "Doc", "title": "V3", "status": "Closed"}
        versions = [
            {"version": 3, "changes": [{"field": "status", "old": "Open", "new": "Closed"}]},
            {"version": 2, "changes": [{"field": "title", "old": "V1", "new": "V3"}]},
            {"version": 1, "changes": [{"field": "title", "old": "Draft", "new": "V1"}]},
        ]

        # Restore to version 2 — should undo version 3
        restored = self.svc.build_restore_data(current, versions, target_version=2)
        assert restored["status"] == "Open"
        assert restored["title"] == "V3"  # Not undone — version 2 changed it

    def test_restore_to_version_1(self):
        """Restoring to version 1 undoes versions 3 and 2, keeping v1's state."""
        current = {"name": "Doc", "title": "Final", "status": "Done"}
        versions = [
            {"version": 3, "changes": [{"field": "status", "old": "Active", "new": "Done"}]},
            {"version": 2, "changes": [{"field": "title", "old": "Initial", "new": "Final"}]},
            {"version": 1, "changes": [{"field": "status", "old": "Draft", "new": "Active"}]},
        ]

        # Restore to v1 = undo v3 (status Done→Active) and v2 (title Final→Initial)
        restored = self.svc.build_restore_data(current, versions, target_version=1)
        assert restored["status"] == "Active"  # State after v1 was applied
        assert restored["title"] == "Initial"  # State before v2 was applied

    def test_restore_to_latest_is_noop(self):
        current = {"name": "Doc", "title": "Latest"}
        versions = [
            {"version": 1, "changes": [{"field": "title", "old": "Old", "new": "Latest"}]},
        ]

        restored = self.svc.build_restore_data(current, versions, target_version=1)
        assert restored["title"] == "Latest"
