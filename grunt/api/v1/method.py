from __future__ import annotations

import importlib
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from grunt.app import grunt as grunt_app
from grunt.auth.dependencies import _oauth2_scheme_optional, optional_user
from grunt.db.session import get_engine as get_engine_dep
from grunt.db.session import get_session
from grunt.i18n import _
from grunt.log import log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

router = APIRouter()


def _string_params(method: Any) -> set[str]:
    """Names of the method's parameters explicitly annotated as ``str``.

    Query params are strings; the coercion below turns ``"123"`` into an int,
    which breaks a method that asked for a string (e.g. a Link search for a
    numeric term). Such params keep their raw value.
    """
    import inspect

    try:
        params = inspect.signature(method).parameters.values()
    except TypeError, ValueError:
        return set()
    # ``from __future__ import annotations`` leaves the annotation as the string
    # "str"; a live import gives the ``str`` type. Accept both.
    return {p.name for p in params if p.annotation in (str, "str")}


def _process_params(params: dict[str, str], method: Any = None) -> dict[str, Any]:
    """Parse JSON strings and convert numeric/bool types in parameters."""
    import json

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
                # Looked JSON-ish but wasn't — fall through and keep it as a
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
        from grunt.errors import forbidden

        raise forbidden(
            _("Method %(method_path)s is not whitelisted") % {"method_path": method_path}
        )

    return method


async def _invoke_with_context(
    method: Any,
    args: dict[str, Any],
    request: Request,
    session: AsyncSession,
    engine: AsyncEngine,
    token: str | None,
):
    """Set grunt context and call the method."""
    allow_guest = getattr(method, "_allow_guest", False)

    # Authenticate user manually using the core logic but passing the token
    from grunt.auth.dependencies import current_user as get_current_user

    user = None
    try:
        if allow_guest:
            user = await optional_user(token=token, session=session)
        else:
            user = await get_current_user(request=request, token=token, session=session)
    except HTTPException:
        if not allow_guest:
            raise

    # Activate context
    async with grunt_app.context(session, engine, user):
        # Validate required parameters
        # (@grunt.whitelist(roles=..., require=...) enforcement happens inside
        # `method` itself now — see grunt.api.context.whitelist — so it applies
        # uniformly whether `method` is called via this dispatcher or directly.)
        import inspect

        sig = inspect.signature(method)

        # Methods reached through this dispatcher are called with kwargs only, so
        # a ``request: Request`` parameter never gets FastAPI's native injection.
        # Supply the raw request for methods that ask for it (e.g. building
        # absolute links from the caller's real Host behind a proxy).
        if "request" in sig.parameters and "request" not in args:
            args["request"] = request

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

        if iscoroutinefunction(method):
            return await method(**args)
        return method(**args)


@router.get("/{path:path}")
async def run_method_get(
    path: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine_dep),
    token: str | None = Depends(_oauth2_scheme_optional),
):
    """Run a whitelisted method via GET."""
    method = get_whitelisted_method(path)

    # Process query params: parse JSON strings and convert numeric types
    args = _process_params(dict(request.query_params), method)

    result = await _invoke_with_context(method, args, request, session, engine, token)
    if isinstance(result, Response):
        return result

    return {"success": True, "data": result}


@router.post("/{path:path}")
async def run_method_post(
    path: str,
    request: Request,
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
            # No JSON body and no form body — routine for GET-like whitelisted
            # calls made via POST with no payload, not an error: debug, not exception.
            log.debug("method.no_body_or_form", path=path)

    result = await _invoke_with_context(method, args, request, session, engine, token)
    if isinstance(result, Response):
        return result

    return {"success": True, "data": result}
