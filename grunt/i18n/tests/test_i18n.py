"""Tests for the i18n module (PO/gettext runtime + provider seam)."""

from pathlib import Path

from grunt.i18n.service import TranslationService, _parse_po_file, translation_service

LOCALES_DIR = Path(__file__).parent.parent / "locales"


class TestPoParser:
    def test_parse_uk_po(self):
        po_path = LOCALES_DIR / "uk" / "LC_MESSAGES" / "grunt.po"
        catalog = _parse_po_file(po_path)

        # Simple translation
        assert catalog["Document not found"] == "Документ не знайдено"
        assert catalog["Yes"] == "Так"

        # Context-aware translation
        assert catalog["button\x04Save"] == "Зберегти"
        assert catalog["button\x04Delete"] == "Видалити"
        assert catalog["label\x04Search"] == "Пошук"

    def test_parse_plural_forms(self):
        po_path = LOCALES_DIR / "uk" / "LC_MESSAGES" / "grunt.po"
        catalog = _parse_po_file(po_path)

        # Plural forms stored as msgid\x00index
        assert catalog["%(count)d document\x000"] == "%(count)d документ"
        assert catalog["%(count)d document\x001"] == "%(count)d документи"
        assert catalog["%(count)d document\x002"] == "%(count)d документів"


class TestTranslationService:
    def setup_method(self):
        self.svc = TranslationService()
        self.svc.reload()  # Clear cache

    def test_translate_uk(self):
        result = self.svc.translate("Document not found", lang="uk")
        assert result == "Документ не знайдено"

    def test_translate_en_passthrough(self):
        result = self.svc.translate("Document not found", lang="en")
        assert result == "Document not found"

    def test_translate_missing_returns_source(self):
        result = self.svc.translate("This string has no translation", lang="uk")
        assert result == "This string has no translation"

    def test_pgettext(self):
        result = self.svc.pgettext("button", "Save", lang="uk")
        assert result == "Зберегти"

    def test_pgettext_different_context(self):
        result = self.svc.pgettext("label", "Search", lang="uk")
        assert result == "Пошук"

    def test_ngettext_singular(self):
        result = self.svc.ngettext("%(count)d document", "%(count)d documents", 1, lang="uk")
        assert result == "%(count)d документ"

    def test_ngettext_few(self):
        result = self.svc.ngettext("%(count)d document", "%(count)d documents", 3, lang="uk")
        assert result == "%(count)d документи"

    def test_ngettext_many(self):
        result = self.svc.ngettext("%(count)d document", "%(count)d documents", 5, lang="uk")
        assert result == "%(count)d документів"

    def test_ngettext_format(self):
        count = 5
        result = self.svc.ngettext(
            "%(count)d document", "%(count)d documents", count, lang="uk"
        ) % {"count": count}
        assert result == "5 документів"

    def test_get_all_translations(self):
        all_trans = self.svc.get_all_translations("uk")
        assert isinstance(all_trans, dict)
        assert "Document not found" in all_trans
        assert all_trans["Document not found"] == "Документ не знайдено"


class TestRuntimeProvider:
    def teardown_method(self):
        # Drop the test provider so it can't leak into other tests.
        import grunt.i18n.service as svc

        svc._provider = None
        translation_service.invalidate()

    def test_provider_beats_po_and_source(self):
        translation_service.register_provider(
            lambda locale: {"Brand new string": "З провайдера"} if locale == "uk" else {}
        )
        assert translation_service.translate("Brand new string", lang="uk") == "З провайдера"
        # PO still wins where the provider is silent
        assert (
            translation_service.translate("Document not found", lang="uk")
            == "Документ не знайдено"
        )

    def test_provider_context_key(self):
        translation_service.register_provider(lambda _l: {"meta:Foo|Bar": "Бар"})
        assert translation_service.pgettext("meta:Foo", "Bar", lang="uk") == "Бар"

    def test_provider_included_in_bundle(self):
        translation_service.register_provider(lambda _l: {"Bundle key": "У бандлі"})
        assert translation_service.get_all_translations("uk")["Bundle key"] == "У бандлі"

    def test_invalidate_bumps_version(self):
        before = translation_service.catalog_version("uk")
        translation_service.invalidate()
        assert translation_service.catalog_version("uk") != before


class TestSupportedLangs:
    def test_defaults_present(self):
        assert {"uk", "en"} <= translation_service.supported_langs()

    def test_set_supported_keeps_defaults_and_normalizes(self):
        translation_service.set_supported(["de-DE", "FR", "uk"])
        langs = translation_service.supported_langs()
        assert {"de", "fr", "uk", "en"} <= langs
        translation_service.set_supported(["uk", "en"])  # restore


class TestConvenienceFunctions:
    def test_underscore_function(self):
        from grunt.i18n import _, ngettext, pgettext
        from grunt.i18n.service import translation_service

        translation_service.set_lang("uk")
        assert _("Document not found") == "Документ не знайдено"
        assert pgettext("button", "Save") == "Зберегти"

        result = ngettext("%(count)d record", "%(count)d records", 2) % {"count": 2}
        assert result == "2 записи"
