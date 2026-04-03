"""{name} controller.

Бізнес-логіка для DocType {name}.
"""

from __future__ import annotations


class {name}Controller:
    """Контроллер для {name} документів."""

    async def before_save(self):
        """Викликається перед збереженням."""
        pass

    async def after_save(self):
        """Викликається після збереження."""
        pass

    async def before_delete(self):
        """Викликається перед видаленням."""
        pass
