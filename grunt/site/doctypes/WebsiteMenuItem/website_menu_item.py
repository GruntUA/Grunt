"""Controller for WebsiteMenuItem - one node of a site menu tree."""

from __future__ import annotations

from grunt import _
from grunt.document.base import Document
from grunt.utils.slug import slugify
from grunt.website.menu import invalidate


class WebsiteMenuItem(Document):
    async def validate(self) -> None:
        if self.parent_menu_item:
            if self.parent_menu_item == self.name:
                self.grunt.throw(_("A menu item can't be its own parent"))
            # A subtree always belongs to one menu - children follow the parent.
            parent_menu = await self.grunt.db.get_value(
                "WebsiteMenuItem", self.parent_menu_item, "menu"
            )
            if parent_menu:
                self.menu = parent_menu
        if not self.link_doctype:
            self.link_name = None
        if self.route:
            self.route = slugify(str(self.route)) or None

    async def after_save(self) -> None:
        invalidate()

    async def after_delete(self) -> None:
        invalidate()
