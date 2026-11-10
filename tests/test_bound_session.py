"""``grunt.local.bound_session``: a session for framework work, on no one's behalf."""

from unittest.mock import Mock

from grunt.local import (
    _engine_ctx,
    _session_ctx,
    _user_ctx,
    bound_session,
    session_user,
)


def test_binds_the_session_without_a_user_and_restores_everything():
    outer_session, outer_engine = Mock(), Mock()
    tokens = (
        _session_ctx.set(outer_session),
        _engine_ctx.set(outer_engine),
        _user_ctx.set(Mock(email="ann@example.com")),
    )
    try:
        session, engine = Mock(), Mock()
        with bound_session(session, engine):
            assert _session_ctx.get() is session
            assert _engine_ctx.get() is engine
            assert session_user() is None

        assert _session_ctx.get() is outer_session
        assert _engine_ctx.get() is outer_engine
        assert session_user() == "ann@example.com"
    finally:
        _session_ctx.reset(tokens[0])
        _engine_ctx.reset(tokens[1])
        _user_ctx.reset(tokens[2])
