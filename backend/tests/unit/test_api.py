"""Unit tests for Grunt Python API.

Run with: pytest tests/unit/test_api.py -v
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Any

# Import API modules
from grunt.api.context import (
    set_session,
    get_session,
    set_user,
    get_user,
    set_engine,
    get_engine,
    clear_context,
)
from grunt.api.document import Doc, DocProxy
from grunt.api.database import Database, db
from grunt.api.messages import msgprint, throw, ApplicationError
from grunt.api.permissions import (
    can_read,
    can_write,
    can_submit,
    can_delete,
    can_create,
    get_current_user,
)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session():
    """Mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def mock_user():
    """Mock GruntUser."""
    user = Mock()
    user.id = "test-user-id"
    user.email = "test@example.com"
    user.full_name = "Test User"
    user.roles = ["User"]
    user.is_superadmin = False
    return user


@pytest.fixture
def superadmin_user():
    """Mock superadmin user."""
    user = Mock()
    user.id = "admin-id"
    user.email = "admin@example.com"
    user.full_name = "Admin"
    user.roles = ["Admin"]
    user.is_superadmin = True
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

    def test_get_user_without_context_returns_system_user(self):
        """Test that get_user() returns system user if none set."""
        clear_context()
        user = get_user()
        assert user.email == "system"
        assert user.is_superadmin is True

    def test_clear_context(self, mock_session, mock_user):
        """Test clearing context."""
        set_session(mock_session)
        set_user(mock_user)
        clear_context()

        # After clear, should return system user/new session
        user = get_user()
        assert user.email == "system"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: DocProxy
# ─────────────────────────────────────────────────────────────────────────────


class TestDocProxy:
    """Test DocProxy class."""

    def test_create_docproxy(self):
        """Test creating a DocProxy."""
        data = {"id": "DOC-001", "name": "Test", "status": "Draft"}
        doc = DocProxy("Invoice", data)

        assert doc.doctype == "Invoice"
        assert doc.data == data

    def test_dict_like_access(self):
        """Test dictionary-like access to DocProxy."""
        data = {"id": "DOC-001", "name": "Test", "amount": 1000}
        doc = DocProxy("Invoice", data)

        # Read
        assert doc["name"] == "Test"
        assert doc["amount"] == 1000

        # Write
        doc["status"] = "Active"
        assert doc["status"] == "Active"

    def test_docproxy_repr(self):
        """Test DocProxy string representation."""
        doc = DocProxy("Invoice", {"id": "INV-001"})
        assert "Invoice" in str(doc)
        assert "INV-001" in str(doc)

    @pytest.mark.asyncio
    async def test_docproxy_save(self, setup_context):
        """Test DocProxy.save() method."""
        data = {"id": "DOC-001", "name": "Test"}
        doc = DocProxy("Invoice", data)

        with patch("grunt.api.document.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.update_document = AsyncMock(return_value=data)

            await doc.save()

            # Verify DocumentService was called
            MockService.assert_called_once()
            mock_svc.update_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_docproxy_submit(self, setup_context):
        """Test DocProxy.submit() method."""
        data = {"id": "DOC-001", "docstatus": 0}
        doc = DocProxy("Invoice", data)

        with patch("grunt.api.document.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.update_document = AsyncMock(return_value={**data, "docstatus": 1})

            await doc.submit()

            # Verify docstatus was set to 1
            assert doc.data["docstatus"] == 1

    @pytest.mark.asyncio
    async def test_docproxy_delete(self, setup_context):
        """Test DocProxy.delete() method."""
        data = {"id": "DOC-001"}
        doc = DocProxy("Invoice", data)

        with patch("grunt.api.document.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.delete_document = AsyncMock()

            await doc.delete()

            mock_svc.delete_document.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Doc (static)
# ─────────────────────────────────────────────────────────────────────────────


class TestDoc:
    """Test Doc class static methods."""

    @pytest.mark.asyncio
    async def test_doc_get(self, setup_context):
        """Test Doc.get() retrieves a document."""
        doc_data = {"id": "DOC-001", "name": "Test Document"}

        with patch("grunt.api.document.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.get_document = AsyncMock(return_value=doc_data)

            result = await Doc.get("Invoice", "DOC-001")

            assert isinstance(result, DocProxy)
            assert result["name"] == "Test Document"
            mock_svc.get_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_doc_create(self, setup_context):
        """Test Doc.create() creates a new document."""
        doc_data = {"id": "DOC-002", "name": "New Doc"}

        with patch("grunt.api.document.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.create_document = AsyncMock(return_value=doc_data)

            result = await Doc.create("Invoice", {"name": "New Doc"})

            assert isinstance(result, DocProxy)
            mock_svc.create_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_doc_list(self, setup_context):
        """Test Doc.list() returns list of documents."""
        docs = [
            {"id": "DOC-001", "name": "Doc 1"},
            {"id": "DOC-002", "name": "Doc 2"},
        ]

        with patch("grunt.api.document.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.list_documents = AsyncMock(return_value=docs)

            result = await Doc.list("Invoice", limit=50)

            assert len(result) == 2
            assert all(isinstance(d, DocProxy) for d in result)

    @pytest.mark.asyncio
    async def test_doc_exists(self, setup_context):
        """Test Doc.exists() checks if document exists."""
        with patch("grunt.api.document.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.get_document = AsyncMock(return_value={"id": "DOC-001"})

            exists = await Doc.exists("Invoice", "DOC-001")
            assert exists is True

    @pytest.mark.asyncio
    async def test_doc_exists_returns_false(self, setup_context):
        """Test Doc.exists() returns False if document not found."""
        with patch("grunt.api.document.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.get_document = AsyncMock(side_effect=Exception("Not found"))

            exists = await Doc.exists("Invoice", "NONEXISTENT")
            assert exists is False


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Database
# ─────────────────────────────────────────────────────────────────────────────


class TestDatabase:
    """Test Database class."""

    @pytest.mark.asyncio
    async def test_db_get_value(self, setup_context):
        """Test db.get_value()."""
        with patch("grunt.api.database.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.get_document = AsyncMock(
                return_value={"id": "USER-001", "full_name": "John Doe"}
            )

            result = await db.get_value("User", "USER-001", "full_name")
            assert result == "John Doe"

    @pytest.mark.asyncio
    async def test_db_get_value_returns_none_if_not_found(self, setup_context):
        """Test db.get_value() returns None if field not found."""
        with patch("grunt.api.database.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.get_document = AsyncMock(side_effect=Exception("Not found"))

            result = await db.get_value("User", "NONEXISTENT", "full_name")
            assert result is None

    @pytest.mark.asyncio
    async def test_db_set_value(self, setup_context):
        """Test db.set_value()."""
        with patch("grunt.api.database.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.get_document = AsyncMock(
                return_value={"id": "USER-001", "status": "Active"}
            )
            mock_svc.update_document = AsyncMock()

            await db.set_value("User", "USER-001", "status", "Inactive")

            mock_svc.update_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_exists(self, setup_context):
        """Test db.exists()."""
        with patch("grunt.api.database.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.get_document = AsyncMock(return_value={"id": "USER-001"})

            exists = await db.exists("User", "USER-001")
            assert exists is True

    @pytest.mark.asyncio
    async def test_db_exists_returns_false(self, setup_context):
        """Test db.exists() returns False if document not found."""
        with patch("grunt.api.database.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.get_document = AsyncMock(side_effect=Exception("Not found"))

            exists = await db.exists("User", "NONEXISTENT")
            assert exists is False


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Messages
# ─────────────────────────────────────────────────────────────────────────────


class TestMessages:
    """Test message functions."""

    def test_msgprint(self):
        """Test msgprint() doesn't raise."""
        msgprint("Test message", type="info")
        msgprint("Success", type="success")
        msgprint("Warning", type="warning")

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


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Permissions
# ─────────────────────────────────────────────────────────────────────────────


class TestPermissions:
    """Test permission checking functions."""

    @pytest.mark.asyncio
    async def test_can_read_superadmin(self, setup_context):
        """Test that superadmin can always read."""
        set_user(Mock(is_superadmin=True))
        result = await can_read("Invoice", "INV-001")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_read_regular_user_no_permission(self, setup_context, mock_user, mock_session):
        """Test that regular user without permission is denied."""
        set_user(mock_user)

        # Mock empty result - user has no permissions
        mock_result = AsyncMock()
        mock_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("grunt.api.permissions.doctype_registry") as mock_registry:
            mock_doctype = Mock()
            mock_registry.get_doctype.return_value = mock_doctype

            with patch("grunt.api.permissions.compile_doctype_to_table") as mock_compile:
                mock_table = Mock()
                mock_table.c.doctype_name = "doctype_name"
                mock_table.c.role = "role"
                mock_compile.return_value = mock_table

                result = await can_read("Invoice", "INV-001")
                assert result is False

    @pytest.mark.asyncio
    async def test_can_write_superadmin(self, setup_context):
        """Test that superadmin can always write."""
        set_user(Mock(is_superadmin=True))
        result = await can_write("Invoice", "INV-001")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_delete_only_superadmin(self, setup_context, mock_user):
        """Test that only superadmin can delete."""
        set_user(mock_user)
        result = await can_delete("Invoice", "INV-001")
        assert result is False

        set_user(Mock(is_superadmin=True))
        result = await can_delete("Invoice", "INV-001")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_current_user(self, setup_context, mock_user):
        """Test get_current_user() returns user from context."""
        set_user(mock_user)
        user = await get_current_user()
        assert user == mock_user

    @pytest.mark.asyncio
    async def test_doctype_permission_simple_logic(self, setup_context):
        """Test permission check logic with simplification (without full DB mocking)."""
        # Test that can_delete only allows superadmin
        user = Mock()
        user.email = "regular@example.com"
        user.full_name = "Regular User"
        user.roles = ["User"]
        user.is_superadmin = False
        set_user(user)

        result = await can_delete("Invoice", "INV-001")
        assert result is False

        # Superadmin should be able to delete
        admin = Mock()
        admin.email = "admin@example.com"
        admin.full_name = "Admin"
        admin.roles = ["Admin"]
        admin.is_superadmin = True
        set_user(admin)

        result = await can_delete("Invoice", "INV-001")
        assert result is True

    @pytest.mark.asyncio
    async def test_doctype_permission_no_permission(self, setup_context, mock_session):
        """Test that user without permission is denied."""
        # Empty result - no matching permissions
        mock_result = AsyncMock()
        mock_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Setup user with role that has no read permission
        user = Mock()
        user.email = "guest@example.com"
        user.full_name = "Guest User"
        user.roles = ["Guest"]
        user.is_superadmin = False
        set_user(user)

        # Mock doctype_registry and compile_doctype_to_table
        with patch("grunt.api.permissions.doctype_registry") as mock_registry:
            mock_doctype = Mock()
            mock_registry.get_doctype.return_value = mock_doctype

            with patch("grunt.api.permissions.compile_doctype_to_table") as mock_compile:
                mock_table = Mock()
                mock_table.c.doctype_name = "doctype_name"
                mock_table.c.role = "role"
                mock_compile.return_value = mock_table

                # User should be denied
                result = await can_read("Invoice", "INV-001")
                assert result is False

    @pytest.mark.asyncio
    async def test_system_user_always_allowed(self, setup_context, mock_session):
        """Test that system user is always allowed."""
        # System user should bypass permission checks
        user = Mock()
        user.email = "system"
        user.full_name = "System"
        user.roles = []
        user.is_superadmin = False
        set_user(user)

        # Don't mock the session - system user should return True immediately
        result = await can_read("Invoice", "INV-001")
        assert result is True

        result = await can_write("Invoice", "INV-001")
        assert result is True

    @pytest.mark.asyncio
    async def test_user_with_no_roles(self, setup_context, mock_session):
        """Test that user with no roles is denied."""
        # User with empty roles should be denied
        mock_result = AsyncMock()
        mock_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        user = Mock()
        user.email = "nouser@example.com"
        user.full_name = "No Roles User"
        user.roles = []  # No roles
        user.is_superadmin = False
        set_user(user)

        # Should be denied
        result = await can_read("Invoice", "INV-001")
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION TESTS
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests combining multiple API components."""

    @pytest.mark.asyncio
    async def test_get_and_save_workflow(self, setup_context):
        """Test getting a document and saving it."""
        doc_data = {"id": "INV-001", "amount": 100, "status": "Draft"}

        with patch("grunt.api.document.DocumentService") as MockService:
            mock_svc = AsyncMock()
            MockService.return_value = mock_svc
            mock_svc.get_document = AsyncMock(return_value=doc_data)
            mock_svc.update_document = AsyncMock(return_value=doc_data)

            # Get document
            doc = await Doc.get("Invoice", "INV-001")
            assert doc["amount"] == 100

            # Modify and save
            doc["status"] = "Active"
            await doc.save()

            assert doc["status"] == "Active"

    @pytest.mark.asyncio
    async def test_permission_check_before_operation(self, setup_context, mock_user):
        """Test checking permissions before operation."""
        set_user(mock_user)

        # Check permission
        can_edit = await can_write("Invoice", "INV-001")

        if not can_edit:
            throw("Cannot edit this invoice")
        else:
            # Proceed with edit
            pass

        # Regular user should be able to write (for now)
        assert can_edit is True
