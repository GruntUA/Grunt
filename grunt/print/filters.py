"""Jinja2 filters for print templates."""

from __future__ import annotations

import functools
import json
import re
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from shevchenko import GenderDetectionInput

# Regex to detect adjective-form Ukrainian surnames (-ський/-зький/etc.)
# shevchenko 1.0.0 incorrectly declines these to "-ию" instead of "-ому/-ьому".
_ADJECTIVE_SURNAME_RE = re.compile(
    r"(ський|зький|цький|нський|рський|вський|ській|зькій|цькій|нській|рській|вській)$",
    re.IGNORECASE | re.UNICODE,
)

# Regex to detect proper geographic adjectives: -ська/-зька/-цька etc.
_TOPONYM_RE = re.compile(
    r"(ська|зька|цька|нська|рська|вська|ській|зькій)$", re.IGNORECASE | re.UNICODE
)


def date_format(value: str | date | datetime | None, fmt: str = "%d.%m.%Y") -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return value
        value = parsed
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, date):
        return value.strftime(fmt)
    return str(value)


def datetime_format(value: str | datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            parsed_dt = datetime.fromisoformat(value)
        except ValueError:
            return value
        value = parsed_dt
    if isinstance(value, datetime):
        return value.strftime(fmt)
    return str(value)


def name_format(value: str | None) -> str:
    """Reformat 'Прізвище Ім'я По-батькові' -> 'Ім'я ПРІЗВИЩЕ'."""
    if not value:
        return ""
    parts = value.strip().split()
    if len(parts) == 1:
        return parts[0].upper()
    return f"{parts[1]} {parts[0].upper()}"


def decline_name(full_name: str | None, case: str = "nominative") -> str:
    """Decline Ukrainian full name ('Прізвище Ім'я По-батькові') to a grammatical case.

    Cases: nominative, genitive, dative, accusative, ablative, locative, vocative.
    Uses shevchenko for given/patronymic names; falls back to pymorphy3 for
    adjective-form surnames (-ський/-зький) due to a known shevchenko 1.0.0 bug.
    """
    if not full_name or case == "nominative":
        return full_name or ""

    try:
        import shevchenko

        parts = full_name.strip().split()
        input_data: dict[str, Any] = {}
        if len(parts) >= 1:
            input_data["familyName"] = parts[0]
        if len(parts) >= 2:
            input_data["givenName"] = parts[1]
        if len(parts) >= 3:
            input_data["patronymicName"] = parts[2]

        if not input_data:
            return full_name

        try:
            gender_result = shevchenko.detect_gender(cast("GenderDetectionInput", input_data))
            gender = gender_result.get("gender")
            input_data["gender"] = gender.value if gender else "masculine"
        except Exception:
            input_data["gender"] = "masculine"

        case_fn = {
            "genitive": shevchenko.in_genitive,
            "dative": shevchenko.in_dative,
            "accusative": shevchenko.in_accusative,
            "ablative": shevchenko.in_ablative,
            "locative": shevchenko.in_locative,
            "vocative": shevchenko.in_vocative,
        }.get(case)

        if case_fn is None:
            return full_name

        declined = case_fn(input_data)

        # Fix shevchenko 1.0.0 bug: adjective-form surnames get "-ию" instead of "-ому"
        family_name = input_data.get("familyName", "")
        declined_family = declined.get("familyName") or family_name
        if family_name and _ADJECTIVE_SURNAME_RE.search(family_name):
            fixed = _decline_word_morph(family_name, case)
            if fixed:
                declined_family = fixed

        result_parts = [
            p
            for p in (
                declined_family,
                declined.get("givenName"),
                declined.get("patronymicName"),
            )
            if p
        ]
        return " ".join(result_parts) if result_parts else full_name
    except Exception:
        return full_name


def decline_position(position: str | None, case: str = "nominative") -> str:
    """Decline Ukrainian job title to a grammatical case.

    Inflects the head noun (first nominative noun) and any preceding adjectives;
    the genitive complement is preserved unchanged.
    Preserves the original capitalisation of the first word.
    Cases: nominative, genitive, dative, accusative, ablative, locative, vocative.
    """
    if not position or case == "nominative":
        return position or ""

    case_map = {
        "genitive": "gent",
        "dative": "datv",
        "accusative": "accs",
        "ablative": "ablt",
        "locative": "loct",
        "vocative": "voct",
    }
    morph_case = case_map.get(case)
    if not morph_case:
        return position

    try:
        morph = _morph_uk()
        words = position.split()
        result: list[str] = []
        head_found = False
        first_word_upper = bool(words) and words[0][0].isupper()

        for word in words:
            if head_found:
                result.append(word)
                continue

            parsed = morph.parse(word)
            if not parsed:
                result.append(word)
                continue

            best = parsed[0]
            pos_tag = str(best.tag.POS)
            case_tag = str(best.tag.case)

            if pos_tag == "ADJF":
                inf = best.inflect({morph_case})
                result.append(inf.word if inf else word)
            elif pos_tag == "NOUN" and case_tag in ("nomn", "None"):
                inf = best.inflect({morph_case})
                declined = inf.word if inf else word
                # Prefer short dative -у/-ю over -ові/-еві/-єві
                if morph_case == "datv":
                    declined = _to_short_dative(declined)
                result.append(declined)
                head_found = True
            else:
                # Preposition or already-declined noun -> stop inflecting
                result.append(word)
                head_found = True

        # Restore capitalisation of the first word
        if first_word_upper and result:
            result[0] = result[0][0].upper() + result[0][1:]

        return " ".join(result)
    except Exception:
        return position


def decline_dept_genitive(dept_title: str) -> str:
    """Decline a department/organisation title to genitive case.

    Inflects only the leading adjective+noun group; the rest of the title
    (genitive complements, prepositions) is preserved unchanged.
    Geographic adjectives (-ська/-зька/…) keep their original capitalisation;
    common organisational words are lowercased for mid-phrase use.
    """
    if not dept_title:
        return ""

    try:
        morph = _morph_uk()
        words = dept_title.split()
        result: list[str] = []
        head_found = False

        for word in words:
            if head_found:
                result.append(word)
                continue

            parsed = morph.parse(word)
            if not parsed:
                result.append(word)
                continue

            best = parsed[0]
            pos_tag = str(best.tag.POS)
            is_toponym = _TOPONYM_RE.search(word) is not None

            if pos_tag == "ADJF":
                inf = best.inflect({"gent"})
                declined = inf.word if inf else word
                if is_toponym and word[0].isupper():
                    declined = declined[0].upper() + declined[1:]
                result.append(declined)

            elif pos_tag == "NOUN":
                best_parse = next(
                    (p for p in parsed if str(p.tag.case) in ("nomn", "None")),
                    best,
                )
                inf = best_parse.inflect({"gent"})
                declined = inf.word if inf else word
                result.append(declined)
                head_found = True

            else:
                result.append(word)
                head_found = True

        return " ".join(result)
    except Exception:
        return dept_title


def _to_short_dative(word: str) -> str:
    """Convert long dative -ові/-еві/-єві to short -у/-ю."""
    if word.endswith("ові"):
        return word[:-3] + "у"
    if word.endswith("еві") or word.endswith("єві"):
        return word[:-3] + "ю"
    return word


def _decline_word_morph(word: str, case: str) -> str | None:
    """Decline a single word using pymorphy3 (helper for shevchenko fallback)."""
    case_map = {
        "genitive": "gent",
        "dative": "datv",
        "accusative": "accs",
        "ablative": "ablt",
        "locative": "loct",
        "vocative": "voct",
    }
    morph_case = case_map.get(case)
    if not morph_case:
        return None
    try:
        morph = _morph_uk()
        parsed = morph.parse(word)
        if not parsed:
            return None
        best = next(
            (p for p in parsed if str(p.tag.case) in ("nomn", "None")),
            parsed[0],
        )
        inf = best.inflect({morph_case})
        if not inf:
            return None
        result = inf.word
        if word[0].isupper():
            result = result[0].upper() + result[1:]
        return result
    except Exception:
        return None


@functools.cache
def _morph_uk() -> Any:
    """Return a cached pymorphy3 MorphAnalyzer for Ukrainian."""
    import pymorphy3

    return pymorphy3.MorphAnalyzer(lang="uk")


def striptags(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"<[^>]+>", "", value)


def from_json(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError, TypeError:
        return {}


JINJA_FILTERS = {
    "date_format": date_format,
    "datetime_format": datetime_format,
    "striptags": striptags,
    "from_json": from_json,
    "name_format": name_format,
    "decline_name": decline_name,
    "decline_position": decline_position,
    "decline_dept_genitive": decline_dept_genitive,
}
