"""Controllers extended by other apps: ``doctype_mixins`` and ``override_doctype_class``."""

import pytest

from grunt.document.base import Document
from grunt.document.registry import DocumentRegistry

MOD = __name__


class AssetBase(Document):
    def describe(self) -> list[str]:
        return ["base"]


class AuditMixin:
    def describe(self) -> list[str]:
        return ["audit", *super().describe()]  # type: ignore[misc]


class FinanceMixin:
    def describe(self) -> list[str]:
        return ["finance", *super().describe()]  # type: ignore[misc]

    def finance_only(self) -> str:
        return "cf"


class OtherAsset(Document):
    pass


class MixinTarget(Document):
    """Named after its DocType - ``get_doc(cls)`` takes the DocType name from the class."""


def _registry(**index: str) -> DocumentRegistry:
    reg = DocumentRegistry()
    reg._index.update(index)
    return reg


def test_mixins_of_several_apps_wrap_the_controller():
    reg = _registry(Asset=f"{MOD}.AssetBase")
    reg.register_mixins({"Asset": f"{MOD}.AuditMixin"}, app="audit")
    reg.register_mixins({"Asset": [f"{MOD}.FinanceMixin"]}, app="crystal")

    cls = reg.get("Asset")

    assert issubclass(cls, AssetBase)
    assert cls.__name__ == "AssetBase"
    # The later-registered app first; super() runs the whole chain.
    assert cls.describe(object.__new__(cls)) == ["finance", "audit", "base"]
    assert reg.get("Asset") is cls  # composed once


def test_doctype_without_controller_gets_mixins_on_document():
    reg = _registry()
    reg.register_mixins({"Plain": f"{MOD}.FinanceMixin"}, app="crystal")

    cls = reg.get("Plain")

    assert issubclass(cls, Document) and issubclass(cls, FinanceMixin)
    assert reg.get("NoMixins") is Document


def test_mixins_registered_after_load_recompose():
    reg = _registry(Asset=f"{MOD}.AssetBase")
    assert reg.get("Asset") is AssetBase

    reg.register_mixins({"Asset": f"{MOD}.AuditMixin"}, app="audit")
    reg.register_mixins({"Asset": f"{MOD}.AuditMixin"}, app="audit")  # reload: no duplicate

    cls = reg.get("Asset")
    assert cls.describe(object.__new__(cls)) == ["audit", "base"]


def test_broken_mixin_is_skipped():
    reg = _registry(Asset=f"{MOD}.AssetBase")
    reg.register_mixins({"Asset": [f"{MOD}.Missing", "nomodule.X", f"{MOD}.AuditMixin"]}, app="a")

    cls = reg.get("Asset")
    assert cls.describe(object.__new__(cls)) == ["audit", "base"]


def test_second_override_of_a_doctype_is_refused():
    reg = _registry(Asset=f"{MOD}.AssetBase")
    reg.register_overrides({"Asset": f"{MOD}.OtherAsset"}, app="one")
    reg.register_overrides({"Asset": f"{MOD}.AssetBase"}, app="two")
    reg.register_overrides({"Asset": f"{MOD}.OtherAsset"}, app="one")  # reload of the same app

    assert reg.get("Asset") is OtherAsset


def test_override_keeps_the_mixins():
    reg = _registry(Asset=f"{MOD}.AssetBase")
    reg.register_mixins({"Asset": f"{MOD}.FinanceMixin"}, app="crystal")
    reg.register_overrides({"Asset": f"{MOD}.OtherAsset"}, app="one")

    cls = reg.get("Asset")
    assert issubclass(cls, OtherAsset) and issubclass(cls, FinanceMixin)


@pytest.mark.asyncio
async def test_get_doc_by_class_returns_the_extended_controller(ctx, monkeypatch):
    from grunt.api.v1.meta import save_doctype
    from grunt.document.registry import document_registry
    from grunt.metadata.registry import doctype_registry

    if not await doctype_registry.get_or_none("MixinTarget"):
        await save_doctype(
            doctype_data={
                "name": "MixinTarget",
                "label": "Mixin target",
                "module": "core",
                "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
                "__is_new": True,
            }
        )
        await ctx.db._session().commit()

    for attr in ("_controllers", "_bases", "_mixins", "_index"):
        monkeypatch.setattr(document_registry, attr, dict(getattr(document_registry, attr)))
    document_registry._index["MixinTarget"] = f"{MOD}.MixinTarget"
    document_registry.register_mixins({"MixinTarget": f"{MOD}.FinanceMixin"}, app="crystal")

    created = await ctx.new_doc("MixinTarget", {"title": "A"})
    doc = await ctx.get_doc(MixinTarget, created["name"])

    assert isinstance(doc, MixinTarget)
    assert doc.finance_only() == "cf"  # type: ignore[attr-defined]
