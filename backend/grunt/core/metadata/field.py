"""Field type enum and DocField model for DocType metadata."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class FieldType(str, Enum):
    """Every supported field type in the Grunt metadata engine."""

    # Simple data types
    DATA = "Data"   # varchar(255) — alias used by tools and imported doctypes
    TEXT = "Text"  # varchar(255)
    LONG_TEXT = "LongText"  # text
    INT = "Int"  # integer
    FLOAT = "Float"  # numeric(20,6)
    BOOL = "Check"  # boolean
    DATE = "Date"  # date
    DATETIME = "Datetime"  # timestamp with timezone
    TIME = "Time"  # time

    # Relations
    LINK = "Link"  # FK to another DocType
    MULTI_LINK = "MultiLink"  # many-to-many

    # Media
    ATTACH = "Attach"  # file reference
    IMAGE = "Image"  # image file

    # Layout (non-physical — no DB column)
    SECTION = "Section"  # section divider
    COLUMN = "Column"  # column layout (2/3/4 cols)
    TAB = "Tab"  # tab container
    TABLE = "Table"  # child table (Child DocType)

    # Special
    SELECT = "Select"  # dropdown with options
    RICH_TEXT = "RichText"  # HTML via Tiptap
    JSON = "JSON"  # jsonb
    CODE = "Code"  # code editor
    COLOR = "Color"  # color picker
    SIGNATURE = "Signature"  # signature pad
    GEOLOCATION = "Geolocation"  # coordinates
    BARCODE = "BarCode"  # barcode / QR-code scanner


# Field types that do NOT produce a column in the database
NON_PHYSICAL_FIELDS: frozenset[str] = frozenset(
    {"Section", "Column", "Tab", "Table", "MultiLink"}
)


class DocField(BaseModel):
    """Single field definition inside a DocType."""

    fieldname: str  # snake_case, unique within DocType
    label: str = ""  # human-readable name
    fieldtype: FieldType

    # Validation
    required: bool = False
    unique: bool = False
    read_only: bool = False
    hidden: bool = False

    # Display
    in_list_view: bool = False  # show in list view
    in_filter: bool = False  # available for filtering
    bold: bool = False

    # Type-specific options
    # Select → "Option1\nOption2"; Link → DocType name; Table → Child DocType name
    options: str | None = None
    default: Any = None
    description: str | None = None
    placeholder: str | None = None

    # Layout (for Section/Column/Tab)
    collapsible: bool = False
    columns: int = 12

    # Validation rules
    min_value: float | None = None
    max_value: float | None = None
    max_length: int | None = None
    regex: str | None = None

    # Conditional display (JS expression)
    depends_on: str | None = None  # "eval: doc.status == 'Active'"
    mandatory_depends_on: str | None = None

    model_config = {"use_enum_values": True}
