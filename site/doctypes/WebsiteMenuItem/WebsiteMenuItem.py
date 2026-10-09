"""Controller for WebsiteMenuItem.

Lifecycle hooks — override any method to add custom logic:
  before_insert  — before a NEW document is saved to DB
  after_insert   — after a NEW document is saved to DB
  validate       — runs before every save (insert or update), raise to block
  before_save    — before an EXISTING document is updated
  after_save     — after an EXISTING document is updated
  before_delete  — before document is deleted
  after_delete   — after document is deleted

Access fields:
  self.field_name          — read field value
  self.field_name = value  — set field value
  self.data                — full document dict
  self.doctype             — DocType name ("WebsiteMenuItem")
  self.user                — current User (or None)
  self.session             — async SQLAlchemy session (for advanced queries)
"""

from __future__ import annotations

from grunt.document.base import Document


class WebsiteMenuItem(Document):

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    label: str | None  # Name
    parent_menu_item: str | None  # Parent item
    menu: str | None  # Menu
    enabled: bool | None  # Show
    sequence: int | None  # Order
    open_in_new_tab: bool | None  # Open in a new tab
    link_doctype: str | None  # Document type
    link_name: str | None  # Document
    url: str | None  # URL
    route: str | None  # Section route
    icon: str | None  # Icon
    highlight: bool | None  # Highlight

    # end: auto-generated types

    async def validate(self) -> None:
        """Runs before every save — raise an exception to block."""
        pass

    async def before_save(self) -> None:
        """Runs before an existing document is updated."""
        pass

    async def after_save(self) -> None:
        """Runs after document is saved to the database."""
        pass
