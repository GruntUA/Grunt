"""The permissions contract dataset - DocTypes, rows and shares behind
``test_permissions`` and ``test_permission_explain`` (fixture
``permission_data`` in this package's conftest)."""

TEAM = {
    "name": "CpTeam",
    "label": "Cp Team",
    "module": "test",
    "autoname": "prompt",
    "fields": [{"fieldname": "lead", "label": "Lead", "fieldtype": "Data"}],
    "permissions": [{"role": "All", "actions": ["read"]}],
}

STEP = {
    "name": "CpStep",
    "label": "Cp Step",
    "module": "test",
    "is_child": True,
    "fields": [{"fieldname": "label", "label": "Label", "fieldtype": "Data"}],
}

_RULES = {
    "Reader": None,
    "Own": "assignee == user",
    "Open": "status != 'Closed'",
    "Lead": "team.lead == user",
    "NotLead": "team.lead != user",
}

TASK = {
    "name": "CpTask",
    "label": "Cp Task",
    "module": "test",
    "autoname": "prompt",
    "fields": [
        {"fieldname": "assignee", "label": "Assignee", "fieldtype": "Data"},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data"},
        {"fieldname": "team", "label": "Team", "fieldtype": "Link", "options": "CpTeam"},
        {"fieldname": "steps", "label": "Steps", "fieldtype": "Table", "options": "CpStep"},
    ],
    "permissions": [
        {"role": "System Manager", "actions": ["read", "write", "create", "delete"]},
        *(
            {"role": role, "actions": ["read"], **({"match": rule} if rule else {})}
            for role, rule in _RULES.items()
        ),
    ],
}

NOTE = {
    "name": "CpNote",
    "label": "Cp Note",
    "module": "test",
    "autoname": "prompt",
    "access_from": ["task"],
    "fields": [{"fieldname": "task", "label": "Task", "fieldtype": "Link", "options": "CpTask"}],
    "permissions": [{"role": role, "actions": ["read"]} for role in _RULES],
}

TEAMS = {"T1": "alice@x.com", "T2": "bob@x.com", "T3": None}

# name: (assignee, status, team)
TASKS = {
    "K1": ("alice@x.com", "Open", "T1"),
    "K2": ("alice@x.com", "Closed", "T2"),
    "K3": ("bob@x.com", "Open", "T2"),
    "K4": (None, "Closed", None),
    "K5": ("carol@x.com", None, "T3"),
}
ALL = set(TASKS)

NOTES = {"N1": "K1", "N2": "K3", "N3": None}

SHARES = [("K3", "carol@x.com"), ("K1", "erin@x.com")]


async def seed(ctx) -> None:
    """Save the DocTypes and write the dataset."""
    from grunt.api.v1.meta import save_doctype, sync_doctype

    for dt in (TEAM, STEP, TASK, NOTE):
        await save_doctype(doctype_data={**dt, "__is_new": True})
        await sync_doctype(name=dt["name"])
    for name, lead in TEAMS.items():
        await ctx.new_doc("CpTeam", {"name": name, "lead": lead})
    for name, (assignee, status, team) in TASKS.items():
        steps = [{"label": f"{name}-step"}]
        await ctx.new_doc(
            "CpTask",
            {"name": name, "assignee": assignee, "status": status, "team": team, "steps": steps},
        )
    for name, task in NOTES.items():
        await ctx.new_doc("CpNote", {"name": name, "task": task})
    for email in {user for _, user in SHARES}:
        await ctx.new_doc("User", {"email": email, "first_name": "U", "last_name": "Ser"})
    for task, user in SHARES:
        await ctx.new_doc(
            "SharedWith",
            {
                "reference_doctype": "CpTask",
                "reference_id": task,
                "user": user,
                "permission": "Read",
            },
        )
    await ctx.db._session().commit()
