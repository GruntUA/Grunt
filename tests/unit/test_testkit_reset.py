"""TestSchema empties only the tables written since the last test - and every
table when it can't tell which one a write went to."""

import pytest

from grunt.testkit import _DML_TABLE, _OWN, TestSchema


@pytest.mark.parametrize(
    ("statement", "table"),
    [
        ('INSERT INTO "grunt_a" (x) VALUES (1)', "grunt_a"),
        ("insert or replace into grunt_b values (1)", "grunt_b"),
        ("REPLACE INTO `grunt_c` VALUES (1)", "grunt_c"),
        ("UPDATE ONLY grunt_d SET x = 1", "grunt_d"),
        ('DELETE FROM public."grunt_e" WHERE 1', "grunt_e"),
        ("WITH x AS (SELECT 1) INSERT INTO grunt_f SELECT 1", None),
        ('INSERT INTO "grunt_a-log" VALUES (1)', None),  # not grunt_a
        ("INSERT INTO grunt_g(a) VALUES (1)", "grunt_g"),
    ],
)
def test_written_table_is_told(statement, table):
    m = _DML_TABLE.match(statement)
    assert (m.group(1) if m else None) == table


class _Conn:
    def __init__(self, own: bool = False) -> None:
        self.options = {_OWN: True} if own else {}

    def get_execution_options(self):
        return self.options


def _schema():
    schema = TestSchema.__new__(TestSchema)
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
        schema._watch(_Conn(), None, statement)
    assert schema._written == {"grunt_y", "grunt_z"}
    assert schema._touched == {"grunt_new"}
    assert not schema._unknown_write

    schema._watch(_Conn(), None, "COPY grunt_w FROM STDIN")
    assert schema._unknown_write  # can't tell the table - everything gets emptied


def test_comments_and_case_dont_hide_a_write():
    schema = _schema()
    schema._watch(_Conn(), None, "-- seed\n/* x */ INSERT INTO GRUNT_A VALUES (1)")
    assert schema._written == {"grunt_a"}


def test_only_the_cleanups_own_connections_are_skipped():
    """A test's leftover task writing while the tables are emptied is still noted."""
    schema = _schema()
    schema._watch(_Conn(own=True), None, "DELETE FROM grunt_a")
    schema._watch(_Conn(), None, "INSERT INTO grunt_b VALUES (1)")
    assert schema._written == {"grunt_b"}
