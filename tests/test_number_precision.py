"""FRAPPE_GAP #5: fields round to their ``precision`` by the site's
``rounding_method``, through Decimal - the same rules as
frontend/src/core/numbers.ts."""

import pytest

from grunt.metadata.field import DocField
from grunt.site.manager import current_site
from grunt.utils.numbers import HALF_EVEN, HALF_UP, round_number, set_site_rounding


@pytest.mark.parametrize(
    ("value", "precision", "method", "expected"),
    [
        (1.005, 2, HALF_UP, 1.01),  # Python's round() gives 1.0 (binary float)
        (2.675, 2, HALF_UP, 2.68),
        (0.125, 2, HALF_UP, 0.13),
        (0.125, 2, HALF_EVEN, 0.12),
        (0.135, 2, HALF_EVEN, 0.14),
        (-0.125, 2, HALF_UP, -0.13),  # away from zero
        (12.5, 0, HALF_EVEN, 12.0),
        (13.5, 0, HALF_EVEN, 14.0),
        (1.23456, 3, None, 1.235),  # no method -> half up
    ],
)
def test_round_number(value, precision, method, expected):
    assert round_number(value, precision, method) == expected


def test_fields_round_to_their_precision():
    site = current_site.get()
    try:
        set_site_rounding(site, HALF_UP)
        currency = DocField(fieldname="amount", fieldtype="Currency")
        assert currency.coerce("1.005") == 1.01  # 2 by default
        assert DocField(fieldname="a", fieldtype="Currency", precision=3).coerce(1.23456) == 1.235
        # Float / Percent round only when they set a precision.
        assert DocField(fieldname="f", fieldtype="Float").coerce(1.23456789) == 1.23456789
        assert DocField(fieldname="f", fieldtype="Float", precision=1).coerce(2.25) == 2.3
        assert DocField(fieldname="p", fieldtype="Percent", precision=0).coerce("12.5") == 13.0

        set_site_rounding(site, HALF_EVEN)
        assert currency.coerce(0.125) == 0.12
        assert DocField(fieldname="p", fieldtype="Percent", precision=0).coerce("12.5") == 12.0
    finally:
        set_site_rounding(site, None)


def test_currency_column_follows_precision():
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.dialects.postgresql import NUMERIC

    from grunt.db.schema.diff import type_changed

    three = DocField(fieldname="c", fieldtype="Currency", precision=3).to_sa_column().type
    assert (three.precision, three.scale) == (18, 3)
    pg = postgresql.dialect()
    assert type_changed(three, NUMERIC(18, 2), pg)  # precision 2 -> 3: ALTER TYPE
    assert not type_changed(three, NUMERIC(18, 3), pg)
    # SQLite: NUMERIC is an affinity, the scale is meaningless - no table rebuild.
    assert not type_changed(three, NUMERIC(18, 2), sqlite.dialect())


@pytest.mark.asyncio
async def test_a_save_rounds_by_the_site_setting(ctx):
    from grunt.api.v1.meta import save_doctype
    from grunt.site.settings import clear_settings_cache

    await save_doctype(
        doctype_data={
            "name": "PrecisionItem",
            "label": "Precision item",
            "module": "core",
            "__is_new": True,
            "fields": [
                {"fieldname": "amount", "label": "Amount", "fieldtype": "Currency"},
                {"fieldname": "rate", "label": "Rate", "fieldtype": "Float", "precision": 1},
            ],
        }
    )
    await ctx.db._session().commit()
    try:
        await ctx.db.set_value("SystemSettings", "SystemSettings", {"rounding_method": HALF_EVEN})
        clear_settings_cache()
        doc = await ctx.new_doc("PrecisionItem", {"amount": "0.125", "rate": 0.25})
        assert (doc["amount"], doc["rate"]) == (0.12, 0.2)

        await ctx.db.set_value("SystemSettings", "SystemSettings", {"rounding_method": HALF_UP})
        clear_settings_cache()
        doc = await ctx.save_doc("PrecisionItem", doc["name"], {"amount": 0.125, "rate": 0.25})
        assert (doc["amount"], doc["rate"]) == (0.13, 0.3)
    finally:
        clear_settings_cache()
        set_site_rounding(current_site.get(), None)
