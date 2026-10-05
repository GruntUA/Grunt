"""Tests for grunt.print.filters - name formatting and Ukrainian declension."""

from __future__ import annotations

from grunt.print.filters import (
    decline_dept_genitive,
    decline_name,
    decline_position,
    name_format,
)

# name_format


class TestNameFormat:
    def test_full_name(self):
        assert name_format("Синягівський Ярослав Миколайович") == "Ярослав СИНЯГІВСЬКИЙ"

    def test_two_parts(self):
        assert name_format("Петренко Іван") == "Іван ПЕТРЕНКО"

    def test_single_part(self):
        assert name_format("Коваль") == "КОВАЛЬ"

    def test_empty(self):
        assert name_format("") == ""
        assert name_format(None) == ""


# decline_name


class TestDeclineName:
    def test_nominative_passthrough(self):
        name = "Синягівський Ярослав Миколайович"
        assert decline_name(name, "nominative") == name

    def test_empty(self):
        assert decline_name(None, "dative") == ""
        assert decline_name("", "dative") == ""

    # Masculine regular surname
    def test_dative_masculine_regular(self):
        result = decline_name("Коваленко Михайло Іванович", "dative")
        parts = result.split()
        assert parts[1] == "Михайлу"
        assert parts[2] == "Івановичу"

    # Adjective-form surname (-ський) - shevchenko 1.0.0 bug, pymorphy3 fallback
    def test_dative_masculine_adjective_surname(self):
        result = decline_name("Синягівський Ярослав Миколайович", "dative")
        family, given, patronymic = result.split()
        assert family == "Синягівському", f"Expected 'Синягівському', got {family!r}"
        assert given == "Ярославу"
        assert patronymic == "Миколайовичу"

    def test_dative_masculine_adjective_surname_2(self):
        result = decline_name("Вишневський Андрій Степанович", "dative")
        assert result.split()[0] == "Вишневському"

    def test_genitive_masculine_adjective_surname(self):
        result = decline_name("Синягівський Ярослав Миколайович", "genitive")
        assert result.split()[0] == "Синягівського"

    # Feminine surname
    def test_dative_feminine(self):
        result = decline_name("Петренко Наталія Василівна", "dative")
        parts = result.split()
        assert parts[1] == "Наталії"
        assert parts[2] == "Василівні"

    # Combined with name_format
    def test_name_format_after_decline(self):
        result = name_format(decline_name("Синягівський Ярослав Миколайович", "dative"))
        assert result == "Ярославу СИНЯГІВСЬКОМУ"


# decline_position


class TestDeclinePosition:
    def test_nominative_passthrough(self):
        pos = "Начальник відділу"
        assert decline_position(pos, "nominative") == pos

    def test_empty(self):
        assert decline_position(None, "dative") == ""
        assert decline_position("", "dative") == ""

    def test_single_noun_dative_short_form(self):
        # Must use short -у form, not -ові
        result = decline_position("Директор", "dative")
        assert result == "Директору", f"Expected short dative 'Директору', got {result!r}"

    def test_noun_with_complement_dative_short_form(self):
        result = decline_position("Начальник відділу", "dative")
        assert result == "Начальнику відділу", f"Unexpected: {result!r}"

    def test_adjective_noun_dative(self):
        result = decline_position("Головний спеціаліст", "dative")
        assert result.startswith("Головному"), f"Unexpected: {result!r}"
        # Head noun should also use short dative
        assert result in ("Головному спеціалісту",), f"Unexpected: {result!r}"

    def test_complex_complement_preserved(self):
        result = decline_position("Заступник начальника управління", "dative")
        assert result == "Заступнику начальника управління", f"Unexpected: {result!r}"

    def test_capitalisation_preserved(self):
        result = decline_position("Начальник управління з оборонної роботи", "dative")
        assert result[0].isupper(), f"First char should be uppercase: {result!r}"
        assert result.startswith("Начальнику"), f"Unexpected: {result!r}"

    def test_full_position_emp0132(self):
        pos = (
            "Начальник управління з оборонної роботи виконавчого комітету "
            "Мелітопольської міської ради Запорізької області"
        )
        result = decline_position(pos, "dative")
        assert result.startswith("Начальнику "), f"Expected 'Начальнику', got {result!r}"
        assert "управління з оборонної роботи" in result
        assert "Мелітопольської" in result


# decline_dept_genitive


class TestDeclineDeptGenitive:
    def test_empty(self):
        assert decline_dept_genitive("") == ""

    def test_noun_only(self):
        result = decline_dept_genitive("Управління з оборонної роботи")
        assert "з оборонної роботи" in result, f"Complement should be preserved: {result!r}"

    def test_adjective_noun(self):
        result = decline_dept_genitive("Виконавчий комітет")
        assert result == "виконавчого комітету", f"Unexpected: {result!r}"

    def test_proper_geographic_name(self):
        result = decline_dept_genitive("Мелітопольська міська рада Запорізької області")
        assert result.startswith("Мелітопольської"), f"Unexpected: {result!r}"
        assert "міської ради" in result
        assert "Запорізької" in result

    def test_viddil(self):
        result = decline_dept_genitive("Відділ кадрового забезпечення")
        assert result.startswith("відділу"), f"Unexpected: {result!r}"

    def test_viddil_complex(self):
        result = decline_dept_genitive("Відділ інформаційних технологій та захисту інформації")
        assert result.startswith("відділу"), f"Unexpected: {result!r}"
        assert "інформаційних технологій та захисту інформації" in result

    def test_another_city(self):
        result = decline_dept_genitive("Харківська міська рада")
        assert result.startswith("Харківської"), f"Unexpected: {result!r}"
        assert "міської ради" in result


# Integration: full addressee for EMP-0132


class TestFullAddresseeEmp0132:
    """Integration test reproducing the expected output for EMP-0132."""

    DEPT_CHAIN = [
        "Управління з оборонної роботи",
        "Виконавчий комітет",
        "Мелітопольська міська рада Запорізької області",
    ]
    POSITION_HEAD = "Начальник"
    FULL_NAME = "Синягівський Ярослав Миколайович"

    def _build_position_text(self) -> str:
        parts = [self.POSITION_HEAD] + [decline_dept_genitive(d) for d in self.DEPT_CHAIN]
        return " ".join(parts)

    def test_position_text_built(self):
        pos_text = self._build_position_text()
        assert "управління з оборонної роботи" in pos_text
        assert "виконавчого комітету" in pos_text
        assert "Мелітопольської міської ради" in pos_text

    def test_position_declined_dative(self):
        pos_text = self._build_position_text()
        result = decline_position(pos_text, "dative")
        assert result.startswith("Начальник"), f"Unexpected: {result!r}"

    def test_name_dative_format(self):
        result = name_format(decline_name(self.FULL_NAME, "dative"))
        assert result == "Ярославу СИНЯГІВСЬКОМУ", f"Unexpected: {result!r}"
