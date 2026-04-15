import importlib
from typing import Any, Dict, Optional
from inspect import iscoroutinefunction

from fastapi import APIRouter, Depends, Request, HTTPException, Response, status
from grunt import get_engine, throw
from grunt.app import grunt as grunt_app
from grunt.core.auth.dependencies import current_user, optional_user, _oauth2_scheme_optional
from grunt.core.db.session import get_session, get_engine as get_engine_dep
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

router = APIRouter()

def _process_params(params: dict[str, str]) -> dict[str, Any]:
    """Parse JSON strings and convert numeric/bool types in parameters."""
    import json
    args = {}
    for key, val in params.items():
        if val.startswith(("{", "[")):
            try:
                args[key] = json.loads(val)
                continue
            except: pass
        
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
            method = module
            for attr in attr_path:
                method = getattr(method, attr)
            break
        except (ImportError, AttributeError):
            continue

    if not method:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Method {method_path} not found"
        )

    # Check if method is whitelisted
    is_whitelisted = getattr(method, "_whitelisted", False)
    if not is_whitelisted:
        print(f"DEBUG: Method {method_path} not whitelisted. Obj: {method}, Attrs: {dir(method)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Method {method_path} is not whitelisted"
        )

    return method

async def _invoke_with_context(
    method: Any, 
    args: Dict[str, Any], 
    request: Request, 
    session: AsyncSession, 
    engine: AsyncEngine,
    token: Optional[str],
):
    """Set grunt context and call the method."""
    allow_guest = getattr(method, "_allow_guest", False)
    
    # Authenticate user manually using the core logic but passing the token
    from grunt.core.auth.dependencies import current_user as get_current_user
    
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
        import inspect
        sig = inspect.signature(method)
        missing = [
            p.name for p in sig.parameters.values() 
            if p.default is inspect.Parameter.empty and p.name not in args
        ]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Missing required parameters: {', '.join(missing)}"
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
    token: Optional[str] = Depends(_oauth2_scheme_optional),
):
    """Run a whitelisted method via GET."""
    method = get_whitelisted_method(path)
    
    # Process query params: parse JSON strings and convert numeric types
    args = _process_params(dict(request.query_params))

    result = await _invoke_with_context(method, args, request, session, engine, token)
    if isinstance(result, Response):
        return result
        
    return {
        "success": True,
        "data": result
    }

@router.post("/{path:path}")
async def run_method_post(
    path: str, 
    request: Request,
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine_dep),
    token: Optional[str] = Depends(_oauth2_scheme_optional),
):
    """Run a whitelisted method via POST."""
    method = get_whitelisted_method(path)
    
    # Merge query params and body / form data
    args = _process_params(dict(request.query_params))
    
    try:
        body = await request.json()
        if isinstance(body, dict):
            args.update(body)
    except:
        try:
            form_data = await request.form()
            args.update(dict(form_data))
        except:
            pass
            
    result = await _invoke_with_context(method, args, request, session, engine, token)
    if isinstance(result, Response):
        return result

    return {
        "success": True,
        "data": result
    }
