"""Controller for the ``DocField`` DocType."""

from grunt.document.base import Document


class DocField(Document):
    """DocType controller for DocField."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    label: str | None = None  # Label
    fieldname: str  # Fieldname
    fieldtype: str  # Field type
    options: str | None = None  # Options
    precision: int | None = None  # Precision
    required: bool | None = None  # Required
    unique: bool | None = None  # Unique
    no_history: bool | None = None  # No history
    read_only: bool | None = None  # Read-only
    no_copy: bool | None = None  # Don't copy
    set_only_once: bool | None = None  # Set only once
    in_list_view: bool | None = None  # In list view
    in_filter: bool | None = None  # In filters
    hidden: bool | None = None  # Hidden
    print_hide: bool | None = None  # Hide in print
    print_hide_if_no_value: bool | None = None  # Hide in print if empty
    description: str | None = None  # Description
    default: str | None = None  # Default value
    depends_on: str | None = None  # Depends on
    mandatory_depends_on: str | None = None  # Mandatory depends on
    read_only_depends_on: str | None = None  # Read-only depends on

    # end: auto-generated types
