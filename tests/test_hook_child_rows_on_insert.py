"""Child rows a lifecycle hook fills in on insert are stored, as on update.

The insert used to write child tables from the request payload only - a
``validate`` that computed the rows (esign: signature checks) lost them.
"""

import pytest

import grunt
from grunt.document.base import Document

_PARENT = {
    "name": "HcReport",
    "label": "Hc Report",
    "module": "core",
    "autoname": "field:code",
    "fields": [
        {"fieldname": "code", "label": "Code", "fieldtype": "Data", "required": True},
        {"fieldname": "checks", "label": "Checks", "fieldtype": "Table", "options": "HcCheck"},
    ],
}

_CHILD = {
    "name": "HcCheck",
    "label": "Hc Check",
    "module": "core",
    "is_child": True,
    "fields": [{"fieldname": "check", "label": "Check", "fieldtype": "Data"}],
}


class HcReport(Document):
    async def validate(self) -> None:
        self.checks = [{"check": "integrity"}, {"check": "signature"}]


@pytest.fixture
async def report_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**_CHILD, "__is_new": True})
    await save_doctype(doctype_data={**_PARENT, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_rows_set_by_validate_are_stored(ctx, report_doctype):
    doc = HcReport(
        doctype="HcReport", data={"code": "a"}, user=grunt.get_user(), session=grunt.get_session()
    )
    await doc.insert()

    stored = await grunt.get_doc("HcReport", "a")
    assert [r["check"] for r in stored["checks"]] == ["integrity", "signature"]
