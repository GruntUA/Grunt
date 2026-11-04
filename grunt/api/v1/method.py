import functools
import importlib
import inspect
import json
import typing
from inspect import iscoroutinefunction
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import grunt
from grunt import _, log
from grunt.auth.dependencies import _oauth2_scheme_optional, optional_user
from grunt.auth.dependencies import current_user as get_current_user
from grunt.db.session import get_engine as get_engine_dep
from grunt.db.session import get_session
lazy from grunt.auth.session_cookie import cookie_user
lazy from grunt.document.base import BaseDocument
lazy from grunt.errors import forbidden
lazy from grunt.storage.signing import sign_authorized_file_urls

router = APIRouter()


def _string_params(method: Any) -> set[str]:
    """Names of the method's parameters explicitly annotated as ``str``.

    Query params are strings; the coercion below turns ``"123"`` into an int,
    which breaks a method that asked for a string (e.g. a Link search for a
    numeric term). Such params keep their raw value.
    """
    try:
        params = inspect.signature(method).parameters.values()
    except TypeError, ValueError:
        return set()
    # ``from __future__ import annotations`` leaves the annotation as the string
    # "str"; a live import gives the ``str`` type. Accept both.
    return {p.name for p in params if p.annotation in (str, "str")}


def _process_params(params: dict[str, str], method: Any = None) -> dict[str, Any]:
    """Parse JSON strings and convert numeric/bool types in parameters."""
    string_params = _string_params(method) if method is not None else set()

    args = {}
    for key, val in params.items():
        if key in string_params:
            args[key] = val
            continue

        if val.startswith(("{", "[")):
            try:
                args[key] = json.loads(val)
                continue
            except Exception:
                # Looked JSON-ish but wasn't - fall through and keep it as a
                # plain string below. Routine, not an error: debug, not exception.
                log.debug("method.param_not_json", key=key)

        if val.isdigit():
            args[key] = int(val)
        elif val.lower() == "true":
            args[key] = True
        elif val.lower() == "false":
            args[key] = False
        else:
            args[key] = val
    return args


def _documents_as_dicts(value: Any) -> Any:
    """Replace every controller in *value* with its JSON (``doc.as_dict()``).

    A whitelisted method may return a ``Document`` - alone or inside a dict /
    list - instead of calling ``as_dict()`` itself. Encoded as a plain object,
    a controller would ship its internals (``user`` with its secrets,
    ``session``, ``doc_before_save``…) under ``data`` instead of its fields.
    Containers are rebuilt only where a controller sits.
    """
    if isinstance(value, BaseDocument):
        return value.as_dict()
    if isinstance(value, dict):
        changed = {k: v2 for k, v in value.items() if (v2 := _documents_as_dicts(v)) is not v}
        return {**value, **changed} if changed else value
    if isinstance(value, list | tuple):
        items = [_documents_as_dicts(v) for v in value]
        return items if any(a is not b for a, b in zip(items, value, strict=True)) else value
    return value


def _mentions_document(annotation: Any) -> bool:
    if inspect.isclass(annotation) and issubclass(annotation, BaseDocument):
        return True
    return any(_mentions_document(a) for a in typing.get_args(annotation))


@functools.cache
def server_only_params(method: Any) -> frozenset[str]:
    """Parameters typed as a controller (``user: User | None = None``).

    They are for Python callers, who hand over a loaded ``Document``; a request
    can only send JSON, which would reach the method as a dict posing as one.
    The dispatcher refuses them (and `grunt app types` leaves them out).
    """
    try:
        hints = typing.get_type_hints(inspect.unwrap(method))
    except Exception:
        return frozenset()
    return frozenset(n for n, a in hints.items() if n != "return" and _mentions_document(a))


def get_whitelisted_method(method_path: str) -> Any:
    """Dynamically import a method and check if it is whitelisted.

    Supports:
    - module.function
    - module.Class.static_method
    """
    parts = method_path.split(".")
    method = None

    # Try different module/attribute splits
    # e.g. grunt.core.doctypes.file.file.File.upload
    # -> try importing grunt.core.doctypes.file.file
    # -> then getattr(File), then getattr(upload)
    for i in range(len(parts) - 1, 0, -1):
        mod_path = ".".join(parts[:i])
        attr_path = parts[i:]
        try:
            module = importlib.import_module(mod_path)
            obj = module
            for attr in attr_path:
                obj = getattr(obj, attr)
            method = obj  # only assign when all attrs resolved successfully
            break
        except ImportError, AttributeError:
            continue

    if not method:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("Method %(method_path)s not found") % {"method_path": method_path},
        )

    # Check if method is whitelisted
    is_whitelisted = getattr(method, "_whitelisted", False)
    if not is_whitelisted:
        log.warning("method.not_whitelisted", method_path=method_path)

        raise forbidden(
            _("Method %(method_path)s is not whitelisted") % {"method_path": method_path}
        )

    return method


async def _invoke_with_context(
    method: Any,
    args: dict[str, Any],
    request: Request,
    response: Response,
    session: AsyncSession,
    engine: AsyncEngine,
    token: str | None,
):
    """Set grunt context and call the method."""
    allow_guest = getattr(method, "_allow_guest", False)
    # Only a read: the cookie also rides along on requests other sites trigger.
    by_cookie = getattr(method, "_session_cookie", False) and request.method in ("GET", "HEAD")

    # Authenticate user manually using the core logic but passing the token

    user = None
    try:
        if allow_guest or (by_cookie and not token):
            user = await optional_user(token=token, session=session)
        else:
            user = await get_current_user(request=request, token=token, session=session)
    except HTTPException:
        if not allow_guest:
            raise
    if user is None and by_cookie:
        async with grunt.context(session, engine):
            user = await cookie_user(request)
        if user is None and not allow_guest:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=_("Authentication required")
            )

    # Activate context
    async with grunt.context(session, engine, user):
        # Validate required parameters
        # (@grunt.whitelist(roles=..., require=...) enforcement happens inside
        # `method` itself now - see grunt.api.context.whitelist - so it applies
        # uniformly whether `method` is called via this dispatcher or directly.)

        sig = inspect.signature(method)

        if forged := sorted(server_only_params(method) & args.keys()):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_("Parameters %(items)s cannot be passed in a request")
                % {"items": ", ".join(forged)},
            )

        # Methods reached through this dispatcher are called with kwargs only, so
        # a ``request: Request`` parameter never gets FastAPI's native injection.
        # Supply the raw request for methods that ask for it (e.g. building
        # absolute links from the caller's real Host behind a proxy), and the
        # response for those that set cookies on it (the session endpoints).
        if "request" in sig.parameters and "request" not in args:
            args["request"] = request
        if "response" in sig.parameters:
            args["response"] = response

        missing = [
            p.name
            for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty and p.name not in args
        ]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_("Missing required parameters: %(items)s") % {"items": ", ".join(missing)},
            )

        result = await method(**args) if iscoroutinefunction(method) else method(**args)
        # Sign file URLs the caller is authorized to read (never blanket-sign:
        # that turns any echoed field into a signing oracle). A Response is
        # returned verbatim - FileResponse/StreamingResponse, already signed.
        if isinstance(result, Response):
            return result
        result = _documents_as_dicts(result)
        # The signer walks dict/list/str. A method that returns some other
        # object (e.g. a Pydantic model) carrying a private-file URL would
        # otherwise ship it unsigned; reduce it to primitives first (the result
        # is JSON-serialised into the envelope below regardless).
        _walkable = (str, dict, list, tuple, bool, int, float)
        if result is not None and not isinstance(result, _walkable):
            result = jsonable_encoder(result)
        return await sign_authorized_file_urls(result, user)


@router.get("/{path:path}")
async def run_method_get(
    path: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine_dep),
    token: str | None = Depends(_oauth2_scheme_optional),
):
    """Run a whitelisted method via GET."""
    method = get_whitelisted_method(path)

    # Process query params: parse JSON strings and convert numeric types
    args = _process_params(dict(request.query_params), method)

    result = await _invoke_with_context(method, args, request, response, session, engine, token)
    if isinstance(result, Response):
        return result

    return {"success": True, "data": result}


@router.post("/{path:path}")
async def run_method_post(
    path: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine_dep),
    token: str | None = Depends(_oauth2_scheme_optional),
):
    """Run a whitelisted method via POST."""
    method = get_whitelisted_method(path)

    # Merge query params and body / form data
    args = _process_params(dict(request.query_params), method)

    try:
        body = await request.json()
        if isinstance(body, dict):
            args.update(body)
    except Exception:
        try:
            form_data = await request.form()
            args.update(dict(form_data))
        except Exception:
            # No JSON body and no form body - routine for GET-like whitelisted
            # calls made via POST with no payload, not an error: debug, not exception.
            log.debug("method.no_body_or_form", path=path)

    result = await _invoke_with_context(method, args, request, response, session, engine, token)
    if isinstance(result, Response):
        return result

    return {"success": True, "data": result}
