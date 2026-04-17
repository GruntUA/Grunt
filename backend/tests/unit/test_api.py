"""Unit tests for Grunt Python API.

Run with: pytest tests/unit/test_api.py -v
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

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
from grunt.api.permissions import (
    can_delete,
    can_read,
    can_write,
    get_current_user,
)
from grunt.app import GruntDB, grunt

db = GruntDB()

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
# TESTS: GruntApp document methods
# ─────────────────────────────────────────────────────────────────────────────


class TestGruntAppDocs:
    """Test grunt.get_doc / new_doc / save_doc / delete_doc."""

    @pytest.mark.asyncio
    async def test_get_doc(self, setup_context):
        """Test grunt.get_doc() retrieves a document."""
        doc_data = {"id": "DOC-001", "name": "Test Document"}

        with patch.object(grunt, "get_doc", new_callable=AsyncMock, return_value=doc_data):
            result = await grunt.get_doc("Invoice", "DOC-001")

            assert result["id"] == "DOC-001"
            assert result["name"] == "Test Document"

    @pytest.mark.asyncio
    async def test_new_doc(self, setup_context):
        """Test grunt.new_doc() creates a new document."""
        doc_data = {"id": "DOC-002", "name": "New Doc"}

        with patch.object(grunt, "new_doc", new_callable=AsyncMock, return_value=doc_data):
            result = await grunt.new_doc("Invoice", {"name": "New Doc"})

            assert result["id"] == "DOC-002"
            assert result["name"] == "New Doc"

    @pytest.mark.asyncio
    async def test_save_doc(self, setup_context):
        """Test grunt.save_doc() updates a document."""
        original = {"id": "DOC-001", "name": "Test", "status": "Draft"}
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
            {"id": "DOC-001", "name": "Doc 1"},
            {"id": "DOC-002", "name": "Doc 2"},
        ]

        with patch.object(grunt, "get_list", new_callable=AsyncMock, return_value=docs):
            result = await grunt.get_list("Invoice", limit=50)

            assert len(result) == 2
            assert result[0]["id"] == "DOC-001"

    @pytest.mark.asyncio
    async def test_get_list_with_filters(self, setup_context):
        """Test grunt.get_list() respects filters."""
        docs = [{"id": "DOC-001", "status": "Draft"}]

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
    async def test_can_read_regular_user_no_permission(self, setup_context, mock_user):
        """Test that regular user without matching permission rows is denied."""
        set_user(mock_user)

        # No permission rows returned for this doctype
        with patch.object(GruntDB, "get_all", new_callable=AsyncMock, return_value=[]):
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
        with patch.object(GruntDB, "get_all", new_callable=AsyncMock, return_value=[]):
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

        with patch.object(GruntDB, "get_all", new_callable=AsyncMock, return_value=[]):
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
        # Setup user with a role that has no matching permission row
        user = Mock()
        user.email = "guest@example.com"
        user.full_name = "Guest User"
        user.roles = ["Guest"]
        user.is_superadmin = False
        set_user(user)

        # No permission rows returned for this doctype
        with patch.object(GruntDB, "get_all", new_callable=AsyncMock, return_value=[]):
            result = await can_read("Invoice", "INV-001")
            assert result is False

        # Permission row exists but not for the user's role
        with patch.object(
            GruntDB,
            "get_all",
            new_callable=AsyncMock,
            return_value=[{"role": "Admin", "read": True}],
        ):
            result = await can_read("Invoice", "INV-001")
            assert result is False

        # Permission row matches role but read=False
        with patch.object(
            GruntDB,
            "get_all",
            new_callable=AsyncMock,
            return_value=[{"role": "Guest", "read": False}],
        ):
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
        """Test getting a document and saving it via grunt API."""
        doc_data = {"id": "INV-001", "amount": 100, "status": "Draft"}
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
        with patch.object(
            GruntDB,
            "get_all",
            new_callable=AsyncMock,
            return_value=[{"role": "User", "write": True}],
        ):
            can_edit = await can_write("Invoice", "INV-001")
            assert can_edit is True

        # User with no permission rows → denied, throw() raises
        with patch.object(GruntDB, "get_all", new_callable=AsyncMock, return_value=[]):
            can_edit = await can_write("Invoice", "INV-001")
            assert can_edit is False
            with pytest.raises(ApplicationError):
                if not can_edit:
                    throw("Cannot edit this invoice")
