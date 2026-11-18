"""Conditions of assignment rules - shared by the rule (grunt.assignment.doctypes.
AssignmentRule) and the service that applies it, without either importing the other."""

from typing import Any

# The rule's way of choosing (Select "rule"); empty on rules from before #9.
EVERYONE = "Everyone"


def matches(filters: dict[str, Any], doc: dict[str, Any]) -> bool:
    """Whether *doc* meets *filters* - the format of ``filters``,
    ``unassign_condition`` and ``close_condition``:

        {"status": "Draft"}           -> doc["status"] == "Draft"
        {"total": {">": 1000}}        -> doc["total"] > 1000
        {"status": "Draft", "qty": 5} -> AND по всіх умовах
    """
    for field, condition in filters.items():
        value = doc.get(field)

        if isinstance(condition, dict):
            for op, target in condition.items():
                if (
                    op == ">"
                    and not (value and value > target)
                    or op == ">="
                    and not (value is not None and value >= target)
                    or op == "<"
                    and not (value and value < target)
                    or op == "<="
                    and not (value is not None and value <= target)
                    or op == "!="
                    and value == target
                    or op == "in"
                    and value not in target
                ):
                    return False
        else:
            if value != condition:
                return False

    return True
