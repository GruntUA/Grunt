"""Development-only route wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt import log
from grunt.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI


VITE_SERVER_URL = "http://localhost:5173"


def register_dev_proxy(app: FastAPI) -> None:
    """Proxy Vite dev-server paths to the running Vite server.

    No-op unless ``settings.debug`` - in production the built assets are
    served as static files instead.
    """
    if not settings.debug:
        return

    import httpx
    from fastapi import HTTPException, Request
    from fastapi.responses import StreamingResponse

    @app.get("/frontend/{path:path}")
    @app.get("/@vite/{path:path}")
    @app.get("/@id/{path:path}")
    @app.get("/@fs/{path:path}")
    @app.get("/node_modules/{path:path}")
    async def vite_proxy(request: Request):
        path = request.url.path
        query = request.url.query
        target_url = f"{VITE_SERVER_URL}{path}{'?' + query if query else ''}"

        async with httpx.AsyncClient() as client:
            # Skip content-length so StreamingResponse can set it.
            headers = {
                k: v
                for k, v in request.headers.items()
                if k.lower() not in ("host", "content-length")
            }
            try:
                v_res = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=await request.body(),
                    follow_redirects=True,
                )
                return StreamingResponse(
                    v_res.aiter_raw(),
                    status_code=v_res.status_code,
                    headers=dict(v_res.headers),
                )
            except Exception as e:
                log.warning("vite.proxy.error", url=target_url, error=str(e))
                raise HTTPException(status_code=502, detail="Vite server unreachable") from e
