"""Regression: the controller type-block sync used to creep indentation.

`sync_controller_types` sliced the source at the marker's `#` (i.e. *after*
the line's leading whitespace) and then prepended `new_block`, which carries
its own indent — so every sync added another level, and once the ``# begin``
marker was no longer at exactly four spaces the "legacy" branch spliced that
stray indent onto the first method below the block. After enough saves the
controller no longer parsed (`IndentationError`).
"""

import ast
import textwrap

from grunt.utils.codegen import (
    _ensure_import,
    build_controller_context,
    render_template,
    sync_controller_types,
)

_CONTROLLER = textwrap.dedent(
    '''\
    from __future__ import annotations

    from grunt.document.base import Document


    class Widget(Document):

        # begin: auto-generated types
        # This code is auto-generated. Do not modify anything in this block.

        old_field: str | None

        # end: auto-generated types

        async def validate(self) -> None:
            """Custom code below the block — must never move."""
            pass

        async def before_save(self) -> None:
            pass
    '''
)


def _fields(n: int) -> list[dict]:
    return [{"fieldname": f"f{i}", "fieldtype": "Data", "label": f"Label {i}"} for i in range(n)]


def test_repeated_sync_does_not_creep_indentation(tmp_path):
    py = tmp_path / "Widget.py"
    py.write_text(_CONTROLLER)

    src = _CONTROLLER
    for i in range(1, 6):
        sync_controller_types(py, "Widget", _fields(i))
        src = py.read_text()
        ast.parse(src)  # must stay valid every iteration

    lines = src.splitlines()
    assert "    # begin: auto-generated types" in lines
    assert "    # end: auto-generated types" in lines
    assert "    async def validate(self) -> None:" in lines
    assert "    async def before_save(self) -> None:" in lines


def test_sync_normalises_an_already_crept_block(tmp_path):
    crept = _CONTROLLER.replace(
        "    # begin: auto-generated types", "            # begin: auto-generated types"
    )
    py = tmp_path / "Widget.py"
    py.write_text(crept)

    sync_controller_types(py, "Widget", _fields(2))
    src = py.read_text()

    ast.parse(src)
    assert "    # begin: auto-generated types" in src.splitlines()


def test_fresh_controller_render_is_valid_python_with_one_field_per_line(tmp_path):
    ctx = build_controller_context(
        "Widget",
        [
            {"fieldname": "a", "fieldtype": "Data", "label": "Назва"},
            {"fieldname": "b", "fieldtype": "Int", "label": "Кількість"},
            {"fieldname": "rows", "fieldtype": "Table", "options": "WidgetRow"},
            {"fieldname": "extra", "fieldtype": "JSON", "label": "Extra"},
            {"fieldname": "due", "fieldtype": "Date"},
        ],
    )
    out = render_template("doctype/controller.py.jinja", ctx)
    ast.parse(out)
    assert "    a: str | None = None  # Назва\n" in out
    assert "    b: int | None = None  # Кількість\n" in out
    assert "    rows: list[dict] = []  # Table: WidgetRow\n" in out
    assert "    extra: Any | None = None  # Extra\n" in out
    assert "from datetime import date\nfrom typing import Any\n" in out


def test_sync_adds_missing_datetime_import(tmp_path):
    py = tmp_path / "Widget.py"
    py.write_text(_CONTROLLER)
    fields = [
        {"fieldname": "start", "fieldtype": "Date"},
        {"fieldname": "at", "fieldtype": "Time"},
    ]

    sync_controller_types(py, "Widget", fields)
    src = py.read_text()
    assert "from datetime import date, time\n\nfrom grunt.document.base" in src

    fields.append({"fieldname": "stamp", "fieldtype": "Datetime"})
    sync_controller_types(py, "Widget", fields)
    src = py.read_text()
    assert src.count("from datetime import") == 1
    assert "from datetime import date, datetime, time\n" in src
    assert sync_controller_types(py, "Widget", fields) is False


def test_sync_adds_any_next_to_an_import_it_cannot_amend(tmp_path):
    """A multi-line or aliased ``from typing import`` stays as it is; the bare
    ``Any`` the block annotates with gets an import of its own."""
    fields = [{"fieldname": "extra", "fieldtype": "JSON"}]
    for head in (
        "from typing import (\n    ClassVar,\n    Literal,\n)\n",
        "from typing import Any as TypingAny\n",
    ):
        py = tmp_path / "widget.py"
        future = "from __future__ import annotations\n"
        py.write_text(_CONTROLLER.replace(future, future + "\n" + head))
        sync_controller_types(py, "Widget", fields)
        src = py.read_text()
        assert head + "from typing import Any\n" in src, src
        ast.parse(src)
        assert sync_controller_types(py, "Widget", fields) is False


def test_fields_hidden_by_controller_attributes_are_not_annotated(tmp_path):
    """``doc.delete`` is a method: annotating such a field would tell the type
    checker the opposite of what happens. ``user`` is a plain field (the session
    user is ``grunt.session_user()``, not an attribute of the document)."""
    py = tmp_path / "widget.py"
    py.write_text(_CONTROLLER)
    fields = [
        {"fieldname": "user", "fieldtype": "Link", "options": "User"},
        {"fieldname": "delete", "fieldtype": "Check"},
        {"fieldname": "title", "fieldtype": "Data"},
    ]

    sync_controller_types(py, "Widget", fields)
    src = py.read_text()
    assert "    title: str | None = None\n" in src
    assert "    user: str | None = None" in src
    assert "    delete:" not in src
    assert 'read it as self.data["delete"]' in src


# Child tables: list[ChildCls]


def _app(tmp_path, child_source: str = "from grunt.document.base import Document\n"):
    """A package ``shop`` (``pyproject.toml`` next to it) with a child DocType
    ``OrderLine`` and a parent ``Order`` - DocType folders without ``__init__``."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'shop'\n")
    pkg = tmp_path / "shop"
    (pkg / "doctypes" / "OrderLine").mkdir(parents=True)
    (pkg / "doctypes" / "Order").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "doctypes" / "__init__.py").write_text("")
    (pkg / "doctypes" / "OrderLine" / "order_line.py").write_text(
        child_source + "\n\nclass OrderLine(Document):\n    pass\n"
    )
    parent = pkg / "doctypes" / "Order" / "order.py"
    parent.write_text(
        "from grunt.document.base import Document\n"
        "from shop.utils import helper\n\n\n"
        "class Order(Document):\n"
        "    # begin: auto-generated types\n"
        "    pass\n"
        "    # end: auto-generated types\n"
    )
    (pkg / "utils.py").write_text("def helper(): ...\n")
    return parent


_TABLE = [
    {"fieldname": "lines", "fieldtype": "Table", "options": "OrderLine", "label": "Lines"},
    {"fieldname": "other", "fieldtype": "Table", "options": "NoController"},
]


def test_sync_types_a_child_table_with_its_controller(tmp_path):
    parent = _app(tmp_path)
    sync_controller_types(parent, "Order", _TABLE)
    src = parent.read_text()
    ast.parse(src)
    assert "    lines: list[OrderLine] = []  # Lines\n" in src
    assert "    other: list[dict] = []  # Table: NoController\n" in src
    # In order among the imports of its package.
    assert (
        "from grunt.document.base import Document\n"
        "from shop.doctypes.OrderLine.order_line import OrderLine\n"
        "from shop.utils import helper\n"
    ) in src
    assert sync_controller_types(parent, "Order", _TABLE) is False  # idempotent


def test_a_child_importing_the_parent_is_imported_under_type_checking(tmp_path):
    parent = _app(
        tmp_path,
        "from grunt.document.base import Document\nfrom shop.doctypes.Order.order import Order\n",
    )
    sync_controller_types(parent, "Order", _TABLE)
    src = parent.read_text()
    ast.parse(src)
    assert "    lines: list[OrderLine] = []  # Lines\n" in src
    assert "from typing import TYPE_CHECKING\n" in src
    assert (
        "\nif TYPE_CHECKING:\n    from shop.doctypes.OrderLine.order_line import OrderLine\n"
    ) in src
    assert "\nfrom shop.doctypes.OrderLine" not in src


def test_fresh_controller_imports_its_child_class(tmp_path):
    parent = _app(tmp_path)
    ctx = build_controller_context("Order", _TABLE, parent)
    out = render_template("doctype/controller.py.jinja", ctx)
    ast.parse(out)
    assert (
        "from grunt.document.base import Document\n"
        "from shop.doctypes.OrderLine.order_line import OrderLine\n"
    ) in out
    assert "    lines: list[OrderLine] = []  # Lines\n" in out


def test_fresh_controller_imports_a_cyclic_child_under_type_checking(tmp_path):
    parent = _app(
        tmp_path,
        "from grunt.document.base import Document\nfrom shop.doctypes.Order.order import Order\n",
    )
    out = render_template(
        "doctype/controller.py.jinja", build_controller_context("Order", _TABLE, parent)
    )
    ast.parse(out)
    assert "from typing import TYPE_CHECKING\n" in out
    assert (
        "\nif TYPE_CHECKING:\n    from shop.doctypes.OrderLine.order_line import OrderLine\n"
    ) in out
    assert "    lines: list[OrderLine] = []  # Lines\n" in out


def test_an_aliased_or_local_child_import_does_not_count(tmp_path):
    parent = _app(
        tmp_path,
        "from grunt.document.base import Document\nfrom shop.doctypes.Order.order import Order\n",
    )
    parent.write_text(
        "from grunt.document.base import Document\n"
        "from shop.doctypes.OrderLine.order_line import OrderLine as OL\n\n\n"
        "def helper():\n"
        "    from shop.doctypes.OrderLine.order_line import OrderLine\n\n\n"
        "class Order(Document):\n"
        "    # begin: auto-generated types\n"
        "    pass\n"
        "    # end: auto-generated types\n"
    )
    sync_controller_types(parent, "Order", _TABLE)
    src = parent.read_text()
    ast.parse(src)
    assert (
        "\nif TYPE_CHECKING:\n    from shop.doctypes.OrderLine.order_line import OrderLine\n"
    ) in src


def test_a_name_merged_into_a_lazy_import_stays_lazy():
    lazy = "import grunt\nlazy from grunt.auth.users import GUEST\n"
    assert "lazy from grunt.auth.users import GUEST, User\n" in _ensure_import(
        lazy, "grunt.auth.users", ["User"]
    )
    both = "lazy from grunt.auth.users import GUEST\nfrom grunt.auth.users import ROLE\n"
    out = _ensure_import(both, "grunt.auth.users", ["User"])
    assert "from grunt.auth.users import ROLE, User\n" in out  # the eager one first
    assert "lazy from grunt.auth.users import GUEST\n" in out
