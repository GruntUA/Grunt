"""TestSchema empties only the tables written since the last test - and every
table when it can't tell which one a write went to."""

import pytest

from grunt.testkit import _DML_TABLE, TestSchema


@pytest.mark.parametrize(
    ("statement", "table"),
    [
        ('INSERT INTO "grunt_a" (x) VALUES (1)', "grunt_a"),
        ("insert or replace into grunt_b values (1)", "grunt_b"),
        ("REPLACE INTO `grunt_c` VALUES (1)", "grunt_c"),
        ("UPDATE ONLY grunt_d SET x = 1", "grunt_d"),
        ('DELETE FROM public."grunt_e" WHERE 1', "grunt_e"),
        ("WITH x AS (SELECT 1) INSERT INTO grunt_f SELECT 1", None),
    ],
)
def test_written_table_is_told(statement, table):
    m = _DML_TABLE.match(statement)
    assert (m.group(1) if m else None) == table


def _schema():
    schema = TestSchema.__new__(TestSchema)
    schema._own = False
    schema._touched, schema._unknown_ddl = set(), False
    schema._written, schema._unknown_write = set(), False
    return schema


def test_watch_sorts_writes_from_reads_and_ddl():
    schema = _schema()
    for statement in (
        "SELECT * FROM grunt_x",
        'INSERT INTO "grunt_y" VALUES (1)',
        "  update grunt_z set a = 1",
        "CREATE TABLE grunt_new (id int)",
    ):
        schema._watch(None, None, statement)
    assert schema._written == {"grunt_y", "grunt_z"}
    assert schema._touched == {"grunt_new"}
    assert not schema._unknown_write

    schema._watch(None, None, "COPY grunt_w FROM STDIN")
    assert schema._unknown_write  # can't tell the table - everything gets emptied


def test_own_statements_are_not_watched():
    schema = _schema()
    schema._own = True
    schema._watch(None, None, "DELETE FROM grunt_a")
    assert not schema._written
