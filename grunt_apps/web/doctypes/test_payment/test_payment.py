"""TestPayment controller.

Бізнес-логіка для DocType TestPayment.
"""

from __future__ import annotations

# begin: auto-generated types
# This code is auto-generated. Do not modify anything in this block.
from typing import TYPE_CHECKING

if TYPE_CHECKING:

	class TestPayment:
		"""Type hints for TestPayment fields."""

		amount: float | None
		payment_date: str | None
		method: str | None
		is_approved: bool | None

# end: auto-generated types



class TestPaymentController:
    """Контроллер для TestPayment документів."""

    async def before_save(self):
        """Викликається перед збереженням."""
        pass

    async def after_save(self):
        """Викликається після збереження."""
        pass

    async def before_delete(self):
        """Викликається перед видаленням."""
        pass
