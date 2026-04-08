"""ApiTest controller.

Бізнес-логіка для DocType ApiTest.
"""

from __future__ import annotations

# begin: auto-generated types
# This code is auto-generated. Do not modify anything in this block.
from typing import TYPE_CHECKING

if TYPE_CHECKING:

	class ApiTest:
		"""Type hints for ApiTest fields."""

		name: str | None

# end: auto-generated types


class ApiTestController:
    """Контроллер для ApiTest документів."""

    async def before_save(self):
        """Викликається перед збереженням."""
        pass

    async def after_save(self):
        """Викликається після збереження."""
        pass

    async def before_delete(self):
        """Викликається перед видаленням."""
        pass
