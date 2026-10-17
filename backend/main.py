"""
Web-Pennmush Main Application
Author: Jordan Koch (GitHub: kochj23)

FastAPI application entry point with WebSocket and REST endpoints.
Served behind the Nova Games Caddy at /mush/ (prefix stripped), so every
client URL is relative.
"""
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend import auth
from backend.api.rest import router as api_router
from backend.api.websocket import handle_websocket
from backend.config import settings
from backend.database import init_db, close_db, AsyncSessionLocal
from backend.engine.ai_manager import ai_manager
from backend.relay import build_router as build_relay_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("webpennmush")

MAX_BODY_BYTES = 64 * 1024

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
       "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup and clean up on shutdown."""
    log.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    await init_db()
    status = ai_manager.get_status()
    log.info("AI: %s (relay configured: %s)", status["backend"], status["relay_configured"])
    yield
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="A modern web-based MUSH server inspired by PennMUSH",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    debug=False,
)


@app.middleware("http")
async def hardening_middleware(request: Request, call_next):
    """Body size cap + security headers (same values Caddy sets; set again so a
    direct hit on the container is equally strict)."""
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) > MAX_BODY_BYTES:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Bad Content-Length"}, status_code=400)
    elif request.method in ("POST", "PUT", "PATCH") and request.headers.get("transfer-encoding"):
        return JSONResponse({"detail": "Chunked bodies not accepted"}, status_code=411)
    response = await call_next(request)
    if settings.SECURITY_HEADERS:
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
    if request.url.path.startswith("/api/") or request.url.path == "/admin":
        response.headers["Cache-Control"] = "no-store"
    return response


# REST API + relay pull endpoints (relay endpoints 404 unless RELAY_SECRET_MUSH is set)
app.include_router(api_router)
app.include_router(build_relay_router(ai_manager.queue, ai_manager.relay_secret))


@app.get("/")
async def root():
    """Serve the main HTML page"""
    return FileResponse("frontend/index.html")


@app.get("/admin")
async def admin_dashboard(request: Request):
    """Admin dashboard: only for a logged-in GOD/WIZARD/ROYAL session."""
    pid = auth.verify_token(request.cookies.get(auth.COOKIE_NAME, ""))
    if pid is not None:
        async with AsyncSessionLocal() as session:
            from backend.models import DBObject
            player = await session.get(DBObject, pid)
            if player is not None and auth.is_admin(player) and not auth.is_pending(player):
                return FileResponse("frontend/admin.html")
    return RedirectResponse("./", status_code=303)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for MUSH gameplay"""
    await handle_websocket(websocket)


# Static files (CSS, JS). admin.html/index.html are only served via the routes above.
app.mount("/static/css", StaticFiles(directory="frontend/css", check_dir=False), name="static-css")
app.mount("/static/js", StaticFiles(directory="frontend/js", check_dir=False), name="static-js")


@app.get("/healthz")
async def healthz():
    """Cheap liveness check (no DB, no LLM)."""
    return {"status": "ok"}


@app.get("/health")
async def health_check():
    """Legacy health check"""
    return {"status": "healthy", "version": settings.APP_VERSION}


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level="info",
        ws_max_size=settings.WS_MAX_MESSAGE_BYTES,
        proxy_headers=False,
        server_header=False,
    )
