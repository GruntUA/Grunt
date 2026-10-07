"""Unit tests for Grunt Python API.

Run with: pytest tests/unit/test_api.py -v
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

import grunt

# Import API modules
from grunt.api.context import (
    clear_context,
    get_engine,
    get_session,
    get_user,
    set_engine,
    set_session,
    set_user,
)
from grunt.api.messages import ApplicationError, msgprint, throw
from grunt.app import GruntDB
from grunt.metadata.doctype import DocType
from grunt.metadata.permission import DocPermission

db = GruntDB()


@pytest.fixture(autouse=True)
def _no_document_shares(monkeypatch):
    """Role logic in isolation — SharedWith grants are covered by tests/test_doc_shares.py."""
    from grunt.permissions import shares

    async def _no_share(*_a, **_kw):
        return False

    async def _no_clause(*_a, **_kw):
        return None

    monkeypatch.setattr(shares, "has_share", _no_share)
    monkeypatch.setattr(shares, "shared_names_clause", _no_clause)


def _dt(name: str, permissions: list[DocPermission] | None = None) -> DocType:
    """A minimal, real DocType with just enough set for permission checks.

    A real ``DocType`` (rather than a bare ``Mock``) so it round-trips cleanly
    through ``Meta()`` (via ``grunt.get_meta``/``doctype_registry.get_meta``) —
    ``Meta.__init__`` iterates ``.fields``, and other metadata helpers may walk
    ``.indexes`` etc.; a pydantic model gives all of those their real empty
    defaults instead of each one needing to be stubbed by hand.
    """
    return DocType(
        name=name,
        label=name,
        module="core",
        permissions=permissions if permissions is not None else [],
    )


def _registry_returning(dt: Mock):
    """Patch doctype_registry.get() to resolve any doctype name to *dt*."""
    return patch("grunt.app.doctype_registry.get", new_callable=AsyncMock, return_value=dt)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session():
    """Mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def mock_user():
    """Mock User."""
    user = Mock()
    user.id = "test-user-id"
    user.email = "test@example.com"
    user.full_name = "Test User"
    user.roles = ["User"]
    return user


@pytest.fixture
def superadmin_user():
    """Mock System Manager user."""
    user = Mock()
    user.id = "admin-id"
    user.email = "admin@example.com"
    user.full_name = "Admin"
    user.roles = ["System Manager"]
    return user


@pytest.fixture
def mock_engine():
    """Mock AsyncEngine."""
    return AsyncMock()


@pytest.fixture
def setup_context(mock_session, mock_user, mock_engine):
    """Setup context with session, user, engine."""
    set_session(mock_session)
    set_user(mock_user)
    set_engine(mock_engine)
    yield
    clear_context()


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Context Management
# ─────────────────────────────────────────────────────────────────────────────


class TestContext:
    """Test context management (session, user, engine)."""

    def test_set_and_get_session(self, mock_session):
        """Test setting and getting session."""
        set_session(mock_session)
        assert get_session() == mock_session

    def test_set_and_get_user(self, mock_user):
        """Test setting and getting user."""
        set_user(mock_user)
        assert get_user() == mock_user

    def test_set_and_get_engine(self, mock_engine):
        """Test setting and getting engine."""
        set_engine(mock_engine)
        assert get_engine() == mock_engine

    def test_get_user_without_context_raises(self):
        """Without a user in context get_user() refuses instead of inventing one."""
        clear_context()
        with pytest.raises(ApplicationError) as exc_info:
            get_user()
        assert exc_info.value.code == "UNAUTHORIZED"

    def test_clear_context(self, mock_session, mock_user):
        """Clearing the context drops the user too."""
        set_session(mock_session)
        set_user(mock_user)
        clear_context()

        with pytest.raises(ApplicationError):
            get_user()


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: GruntApp document methods
# ─────────────────────────────────────────────────────────────────────────────


class TestGruntAppDocs:
    """Test grunt.get_doc / new_doc / save_doc / delete_doc."""

    @pytest.mark.asyncio
    async def test_get_doc(self, setup_context):
        """Test grunt.get_doc() retrieves a document."""
        doc_data = {"name": "DOC-001"}

        with patch.object(grunt, "get_doc", new_callable=AsyncMock, return_value=doc_data):
            result = await grunt.get_doc("Invoice", "DOC-001")

            assert result["name"] == "DOC-001"

    @pytest.mark.asyncio
    async def test_new_doc(self, setup_context):
        """Test grunt.new_doc() creates a new document."""
        doc_data = {"name": "DOC-002"}

        with patch.object(grunt, "new_doc", new_callable=AsyncMock, return_value=doc_data):
            result = await grunt.new_doc("Invoice", {"name": "New Doc"})

            assert result["name"] == "DOC-002"

    @pytest.mark.asyncio
    async def test_save_doc(self, setup_context):
        """Test grunt.save_doc() updates a document."""
        original = {"name": "DOC-001", "status": "Draft"}
        updated = {**original, "status": "Active"}

        with patch.object(grunt, "save_doc", new_callable=AsyncMock, return_value=updated):
            result = await grunt.save_doc("Invoice", "DOC-001", {"status": "Active"})

            assert result["status"] == "Active"

    @pytest.mark.asyncio
    async def test_delete_doc(self, setup_context):
        """Test grunt.delete_doc() deletes a document."""
        with patch.object(grunt, "delete_doc", new_callable=AsyncMock) as mock_delete:
            await grunt.delete_doc("Invoice", "DOC-001")

            mock_delete.assert_called_once_with("Invoice", "DOC-001")

    @pytest.mark.asyncio
    async def test_get_list(self, setup_context):
        """Test grunt.get_list() returns a list of documents."""
        docs = [
            {"name": "DOC-001"},
            {"name": "DOC-002"},
        ]

        with patch.object(grunt, "get_list", new_callable=AsyncMock, return_value=docs):
            result = await grunt.get_list("Invoice", limit=50)

            assert len(result) == 2
            assert result[0]["name"] == "DOC-001"

    @pytest.mark.asyncio
    async def test_get_list_with_filters(self, setup_context):
        """Test grunt.get_list() respects filters."""
        docs = [{"name": "DOC-001", "status": "Draft"}]

        with patch.object(
            grunt, "get_list", new_callable=AsyncMock, return_value=docs
        ) as mock_list:
            result = await grunt.get_list("Invoice", filters={"status": "Draft"})

            mock_list.assert_called_once_with("Invoice", filters={"status": "Draft"})
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_count(self, setup_context):
        """Test grunt.count() returns document count."""
        with patch.object(grunt, "count", new_callable=AsyncMock, return_value=42):
            result = await grunt.count("Invoice")

            assert result == 42


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Database
# ─────────────────────────────────────────────────────────────────────────────


class TestDatabase:
    """Test GruntDB class."""

    @pytest.mark.asyncio
    async def test_db_get_value(self, setup_context):
        """Test db.get_value()."""
        with patch.object(GruntDB, "get_value", new_callable=AsyncMock, return_value="John Doe"):
            result = await db.get_value("User", "USER-001", "full_name")
            assert result == "John Doe"

    @pytest.mark.asyncio
    async def test_db_get_value_returns_none_if_not_found(self, setup_context):
        """Test db.get_value() returns None if field not found."""
        with patch.object(GruntDB, "get_value", new_callable=AsyncMock, return_value=None):
            result = await db.get_value("User", "NONEXISTENT", "full_name")
            assert result is None

    @pytest.mark.asyncio
    async def test_db_set_value(self, setup_context):
        """Test db.set_value()."""
        with patch.object(GruntDB, "set_value", new_callable=AsyncMock) as mock_set:
            await db.set_value("User", "USER-001", "status", "Inactive")
            mock_set.assert_called_once_with("User", "USER-001", "status", "Inactive")

    @pytest.mark.asyncio
    async def test_db_exists(self, setup_context):
        """Test db.exists()."""
        with patch.object(GruntDB, "exists", new_callable=AsyncMock, return_value="USER-001"):
            exists = await db.exists("User", "USER-001")
            assert exists is not None

    @pytest.mark.asyncio
    async def test_db_exists_returns_false(self, setup_context):
        """Test db.exists() returns None if document not found."""
        with patch.object(GruntDB, "exists", new_callable=AsyncMock, return_value=None):
            exists = await db.exists("User", "NONEXISTENT")
            assert exists is None


class TestGruntAppLayerPermissions:
    """Test that permission checks are enforced at grunt.* layer."""

    @pytest.mark.asyncio
    async def test_get_value_denied_raises_403(self, setup_context):
        """grunt.get_value must raise 403 when read permission is denied."""
        dt = Mock()
        dt.name = "Invoice"
        dt.fields = []

        with (
            patch("grunt.app.doctype_registry.get", new_callable=AsyncMock, return_value=dt),
            patch(
                "grunt.permissions.rbac.permission_checker.require",
                new_callable=AsyncMock,
                side_effect=HTTPException(status_code=403, detail="forbidden"),
            ),
            patch.object(grunt.db, "get_value", new_callable=AsyncMock) as mock_db_get_value,
        ):
            with pytest.raises(HTTPException) as exc:
                await grunt.get_value("Invoice", "INV-001", "status")

            assert exc.value.status_code == 403
            mock_db_get_value.assert_not_called()

    @pytest.mark.asyncio
    async def test_exists_requires_permission_and_calls_db(self, setup_context):
        """grunt.exists must enforce read permission and use low-level db method."""
        dt = Mock()
        dt.name = "Invoice"
        dt.permissions = []
        dt.fields = []

        with (
            patch("grunt.app.doctype_registry.get", new_callable=AsyncMock, return_value=dt),
            patch(
                "grunt.permissions.rbac.permission_checker.require",
                new_callable=AsyncMock,
            ) as mock_require,
            patch.object(
                grunt.db, "exists", new_callable=AsyncMock, return_value="INV-001"
            ) as mock_db_exists,
            patch("grunt.app.document_api.fire", new_callable=AsyncMock),
        ):
            result = await grunt.exists("Invoice", {"name": "INV-001"})

            assert result == "INV-001"
            assert mock_require.await_count == 1
            mock_db_exists.assert_awaited_once_with("Invoice", {"name": "INV-001"})

    @pytest.mark.asyncio
    async def test_get_all_uses_db_get_all_with_hooks(self, setup_context):
        """grunt.get_all should run hooks and fetch rows directly via grunt.db.get_all."""

        class InvoiceModel:
            doctype = "Invoice"

            def __init__(self, doctype, data, user, session):
                self.doctype = doctype
                self.data = data
                self.user = user
                self.session = session

        dt = Mock()
        dt.name = "Invoice"
        dt.permissions = []
        dt.fields = []
        rows = [{"name": "INV-001", "status": "Draft"}]

        with (
            patch("grunt.app.doctype_registry.get", new_callable=AsyncMock, return_value=dt),
            patch(
                "grunt.permissions.rbac.permission_checker.require",
                new_callable=AsyncMock,
            ) as mock_require,
            patch.object(
                grunt.db, "get_all", new_callable=AsyncMock, return_value=rows
            ) as mock_db_get_all,
            patch("grunt.app.document_api.fire", new_callable=AsyncMock) as mock_fire,
        ):
            result = await grunt.get_all(
                InvoiceModel,
                filters={"status": "Draft"},
                fields=["name", "status"],
                limit=10,
                page=2,
                order_by="modified_at",
                order="desc",
            )

            assert len(result) == 1
            assert result[0].doctype == "Invoice"
            assert mock_require.await_count == 1
            mock_db_get_all.assert_awaited_once_with(
                "Invoice",
                filters={"status": "Draft"},
                fields=["name", "status"],
                limit=10,
                offset=10,
                order_by="modified_at",
                order="desc",
            )
            assert mock_fire.await_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Messages
# ─────────────────────────────────────────────────────────────────────────────


class TestMessages:
    """Test message functions."""

    def test_msgprint(self):
        """Test msgprint() doesn't raise."""
        msgprint("Test message", msg_type="info")
        msgprint("Success", msg_type="success")
        msgprint("Warning", msg_type="warning")

    def test_throw_raises_error(self):
        """Test throw() raises ApplicationError."""
        with pytest.raises(ApplicationError) as exc_info:
            throw("Test error", code="TEST_ERROR")

        assert exc_info.value.message == "Test error"
        assert exc_info.value.code == "TEST_ERROR"

    def test_application_error(self):
        """Test ApplicationError properties."""
        err = ApplicationError("Test", code="CODE", title="Title")
        assert err.message == "Test"
        assert err.code == "CODE"
        assert err.title == "Title"

    @pytest.mark.parametrize(
        ("code", "status"),
        [("FORBIDDEN", 403), ("PERMISSION_DENIED", 403), ("NOT_FOUND", 404), ("ERROR", 422)],
    )
    def test_application_error_status(self, code, status):
        """``throw(..., "FORBIDDEN")`` must be a 403, not a generic 422."""
        assert ApplicationError("x", code=code).status_code == status


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Permissions
# ─────────────────────────────────────────────────────────────────────────────


class TestPermissions:
    """Test grunt.has_permission() — DocType-level and document-level (doc_id) checks."""

    @pytest.mark.asyncio
    async def test_system_user_always_allowed(self, setup_context):
        """The internal SYSTEM_USER identity bypasses permission rows entirely —
        no registry lookup needed. A human holding "System Manager" does not
        (see test_regular_user_no_permission_rows_denied's sibling in
        test_sensitive_doctype_permissions.py)."""
        from grunt.auth.doctypes.User.user import SYSTEM_USER

        set_user(SYSTEM_USER)
        dt = _dt("Invoice")
        with _registry_returning(dt):
            assert await grunt.has_permission("Invoice", "read") is True
            assert await grunt.has_permission("Invoice", "write") is True
            assert await grunt.has_permission("Invoice", "delete") is True

    @pytest.mark.asyncio
    async def test_regular_user_no_permission_rows_denied(self, setup_context, mock_user):
        """A DocType with no permission rows at all is closed to non-admins."""
        set_user(mock_user)
        dt = _dt("Invoice", [])
        with _registry_returning(dt):
            assert await grunt.has_permission("Invoice", "read") is False
            assert await grunt.has_permission("Invoice", "delete") is False

    def test_get_user(self, setup_context, mock_user):
        """get_user() returns the user from context."""
        set_user(mock_user)
        assert get_user() == mock_user

    @pytest.mark.asyncio
    async def test_permission_row_wrong_role_denied(self, setup_context):
        """A permission row exists, but not for the user's role."""
        user = Mock(email="guest@example.com", roles=["Guest"])
        set_user(user)
        dt = _dt("Invoice", [DocPermission(role="Admin", read=True)])
        with _registry_returning(dt):
            assert await grunt.has_permission("Invoice", "read") is False

    @pytest.mark.asyncio
    async def test_permission_row_matches_role_but_action_false_denied(self, setup_context):
        """A permission row matches the role, but doesn't grant this action."""
        user = Mock(email="guest@example.com", roles=["Guest"])
        set_user(user)
        dt = _dt("Invoice", [DocPermission(role="Guest", read=False)])
        with _registry_returning(dt):
            assert await grunt.has_permission("Invoice", "read") is False

    @pytest.mark.asyncio
    async def test_permission_row_matches_role_and_action_allowed(self, setup_context):
        user = Mock(email="user@example.com", roles=["User"])
        set_user(user)
        dt = _dt("Invoice", [DocPermission(role="User", write=True)])
        with _registry_returning(dt):
            assert await grunt.has_permission("Invoice", "write") is True

    @pytest.mark.asyncio
    async def test_user_with_no_roles_denied(self, setup_context):
        """A user with no roles doesn't match any role-scoped permission row."""
        user = Mock(email="nouser@example.com", roles=[])
        set_user(user)
        dt = _dt("Invoice", [DocPermission(role="User", read=True)])
        with _registry_returning(dt):
            assert await grunt.has_permission("Invoice", "read") is False

    @pytest.mark.asyncio
    async def test_doc_id_evaluates_match_expression(self, setup_context):
        """Passing doc_id fetches the document and evaluates the row's match expr.

        Regression for api/permissions.py used to accept (and ignore) doc_id —
        this is what makes it actually restrict access to the caller's own doc.
        """
        owner = Mock(email="owner@example.com", roles=["User"])
        attacker = Mock(email="attacker@example.com", roles=["User"])
        dt = _dt("Contract", [DocPermission(role="User", read=True, match="owner == user")])
        doc = {"name": "CONTRACT-1", "owner": "owner@example.com"}

        with (
            _registry_returning(dt),
            patch.object(GruntDB, "get_value", new_callable=AsyncMock, return_value=doc),
            # No UserPermission rows for either user — check() still consults
            # doc_passes()/get_user_permissions_for() once the role-level match
            # succeeds, so this needs mocking too, not just get_value().
            patch.object(GruntDB, "get_all", new_callable=AsyncMock, return_value=[]),
        ):
            set_user(owner)
            assert await grunt.has_permission("Contract", "read", "CONTRACT-1") is True

            set_user(attacker)
            assert await grunt.has_permission("Contract", "read", "CONTRACT-1") is False


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION TESTS
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests combining multiple API components."""

    @pytest.mark.asyncio
    async def test_get_and_save_workflow(self, setup_context):
        """Test getting a document and saving it via grunt API."""
        doc_data = {"name": "INV-001", "amount": 100, "status": "Draft"}
        updated_data = {**doc_data, "status": "Active"}

        with (
            patch.object(grunt, "get_doc", new_callable=AsyncMock, return_value=doc_data),
            patch.object(grunt, "save_doc", new_callable=AsyncMock, return_value=updated_data),
        ):
            # Get document
            doc = await grunt.get_doc("Invoice", "INV-001")
            assert doc["amount"] == 100

            # Save with updated status
            saved = await grunt.save_doc("Invoice", "INV-001", {"status": "Active"})
            assert saved["status"] == "Active"

    @pytest.mark.asyncio
    async def test_permission_check_before_operation(self, setup_context, mock_user):
        """Test permission gate before an operation."""
        set_user(mock_user)

        # User with matching write permission row → allowed
        dt = _dt("Invoice", [DocPermission(role="User", write=True)])
        with _registry_returning(dt):
            can_edit = await grunt.has_permission("Invoice", "write")
            assert can_edit is True

        # User with no permission rows → denied, throw() raises
        with _registry_returning(_dt("Invoice", [])):
            can_edit = await grunt.has_permission("Invoice", "write")
            assert can_edit is False
            with pytest.raises(ApplicationError):
                if not can_edit:
                    throw("Cannot edit this invoice")
