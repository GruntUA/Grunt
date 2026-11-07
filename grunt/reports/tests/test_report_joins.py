"""List reports reading through a Link (``customer.region``): a LEFT JOIN with
the target's row-level rules in it, hidden fields left out (also the report
DocType's own)."""

import pytest

from grunt.api.v1.meta import save_doctype
from grunt.reports.engine import report_engine
from tests.support import make_user

CUSTOMER = {
    "name": "JnCustomer",
    "label": "Jn Customer",
    "module": "core",
    "autoname": "prompt",
    "fields": [
        {"fieldname": "region", "label": "Region", "fieldtype": "Data"},
        {"fieldname": "credit", "label": "Credit", "fieldtype": "Float"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True},
        {"role": "Seller", "read": True, "match": "region == 'North'", "hidden_fields": ["credit"]},
    ],
}

INVOICE = {
    "name": "JnInvoice",
    "label": "Jn Invoice",
    "module": "core",
    "autoname": "prompt",
    "fields": [
        {
            "fieldname": "customer",
            "label": "Customer",
            "fieldtype": "Link",
            "options": "JnCustomer",
        },
        {"fieldname": "amount", "label": "Amount", "fieldtype": "Float"},
        {"fieldname": "margin", "label": "Margin", "fieldtype": "Float"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True},
        {"role": "Seller", "read": True, "hidden_fields": ["margin"]},
        {"role": "Clerk", "read": True},
    ],
}

CUSTOMERS = {"C-N": ("North", 100), "C-S": ("South", 200), "C-X": (None, 0)}
# name: (customer, amount, margin)
INVOICES = {
    "I1": ("C-N", 10, 1),
    "I2": ("C-N", 5, 1),
    "I3": ("C-S", 7, 2),
    "I4": (None, 3, 0),
    "I5": ("C-X", 2, 0),
}


@pytest.fixture
async def invoices(ctx):
    for dt in (CUSTOMER, INVOICE):
        await save_doctype(doctype_data={**dt, "__is_new": True})
    for name, (region, credit) in CUSTOMERS.items():
        await ctx.new_doc("JnCustomer", {"name": name, "region": region, "credit": credit})
    for name, (customer, amount, margin) in INVOICES.items():
        await ctx.new_doc(
            "JnInvoice", {"name": name, "customer": customer, "amount": amount, "margin": margin}
        )
    await ctx.db._session().commit()


def _col(fieldname, **kw):
    return {"fieldname": fieldname, "label": fieldname, **kw}


async def _run(ctx, user=None, filters=None, **report):
    return await report_engine._run_list_report(
        "JnInvoice", report, filters or {}, user or ctx.get_user(), ctx.db._session()
    )


def _by(res, key, value):
    return {r[key]: r[value] for r in res["data"]}


SELLER = make_user("seller@x.com", roles=["Seller"])
CLERK = make_user("clerk@x.com", roles=["Clerk"])  # can't read customers at all

TOTAL_BY_REGION = [_col("customer.region"), _col("amount", aggregation="sum")]


@pytest.mark.asyncio
async def test_group_by_a_field_through_the_link(ctx, invoices):
    res = await _run(ctx, columns=TOTAL_BY_REGION)
    # no customer (I4) and a customer without a region (I5) both group as empty
    assert _by(res, "customer.region", "amount") == {"North": 15, "South": 7, None: 5}
    assert [c["fieldname"] for c in res["columns"]] == ["customer.region", "amount"]
    assert "drilldown" not in res["meta"]  # a list can't filter through a Link


@pytest.mark.asyncio
async def test_unreadable_targets_come_back_empty(ctx, invoices):
    """The seller reads every invoice but only North customers: South's
    region is not shown, not even as a group of its own."""
    res = await _run(ctx, SELLER, columns=TOTAL_BY_REGION)
    assert _by(res, "customer.region", "amount") == {"North": 15, None: 12}


@pytest.mark.asyncio
async def test_filtering_through_the_link_reveals_nothing_unreadable(ctx, invoices):
    report = {"columns": [_col("amount")]}
    admin = await _run(ctx, filters={"customer.region": "South"}, **report)
    assert [r["amount"] for r in admin["data"]] == [7]
    seller = await _run(ctx, SELLER, filters={"customer.region": "South"}, **report)
    assert seller["data"] == []
    nulls = await _run(ctx, SELLER, filters={"customer.region__is": "not set"}, **report)
    assert sorted(r["amount"] for r in nulls["data"]) == [2, 3, 7]  # as the viewer sees them


@pytest.mark.asyncio
async def test_fixed_conditions_through_the_link(ctx, invoices):
    res = await _run(
        ctx,
        columns=[_col("amount")],
        conditions=[{"fieldname": "customer.region", "op": "=", "value": "North"}],
    )
    assert sorted(r["amount"] for r in res["data"]) == [5, 10]


@pytest.mark.asyncio
async def test_hidden_fields_are_left_out(ctx, invoices):
    """Field-level permissions hold in reports - the target's hidden ``credit``
    and the report DocType's own hidden ``margin``."""
    columns = [_col("customer"), _col("customer.credit"), _col("margin"), _col("amount")]
    seller = await _run(ctx, SELLER, columns=columns)
    assert [c["fieldname"] for c in seller["columns"]] == ["customer", "amount"]
    assert all(set(r) == {"customer", "amount"} for r in seller["data"])

    # a filter on a field the viewer can't see is skipped, not used as an oracle
    probe = await _run(ctx, SELLER, filters={"margin__gt": 1}, columns=[_col("amount")])
    assert len(probe["data"]) == len(INVOICES)

    admin = await _run(ctx, columns=columns)
    assert [c["fieldname"] for c in admin["columns"]] == [c["fieldname"] for c in columns]


@pytest.mark.asyncio
async def test_no_read_on_the_target_doctype(ctx, invoices):
    res = await _run(ctx, CLERK, columns=[_col("customer"), _col("customer.region")])
    assert [c["fieldname"] for c in res["columns"]] == ["customer"]
    skipped = await _run(ctx, CLERK, filters={"customer.region": "South"}, columns=[_col("amount")])
    assert len(skipped["data"]) == len(INVOICES)


@pytest.mark.asyncio
async def test_one_join_per_link_and_sort_by_a_joined_column(ctx, invoices):
    res = await _run(
        ctx,
        columns=[_col("name"), _col("customer.region"), _col("customer.credit")],
        sort_by="customer.credit",
        sort_order="desc",
    )
    names = [r["name"] for r in res["data"]]
    assert names[0] == "I3" and names[-1] == "I4"  # credit 200 first, no customer last
    assert {r["name"]: r["customer.credit"] for r in res["data"]}["I3"] == 200


@pytest.mark.asyncio
async def test_builder_offers_only_what_the_report_reads(ctx, invoices):
    """The builder's field list follows the same rules as the report source: no
    hidden field (own or the target's), no field of an unreadable target."""
    from grunt.reports.joins import report_fields

    meta = await ctx.get_meta("JnInvoice")

    async def offered(user):
        return {f["fieldname"] for f in await report_fields(meta, user)}

    admin = await offered(ctx.get_user())
    assert {"customer", "amount", "margin", "customer.region", "customer.credit"} <= admin

    seller = await offered(SELLER)
    assert {"customer", "amount", "customer.region"} <= seller
    assert not {"margin", "customer.credit"} & seller

    clerk = await offered(CLERK)
    assert {"customer", "amount", "margin"} <= clerk
    assert not any("." in f for f in clerk)
