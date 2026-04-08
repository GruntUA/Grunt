"""TestOrder controller.

Бізнес-логіка для DocType TestOrder.
"""

from __future__ import annotations

from grunt.core.document.base import Document


class TestOrder(Document):
    """Контроллер для TestOrder документів."""

    async def before_save(self) -> None:
        """Викликається перед збереженням."""
        pass

    async def after_save(self) -> None:
        """Викликається після збереження."""
        pass

    async def before_delete(self) -> None:
        """Викликається перед видаленням."""
        pass
