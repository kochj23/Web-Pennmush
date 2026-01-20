"""
Web-Pennmush Main Application
Author: Jordan Koch (GitHub: kochj23)

FastAPI application entry point with WebSocket and REST endpoints.
"""
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.api.rest import router as api_router
from backend.api.websocket import handle_websocket
from backend.database import init_db, close_db
from backend.config import settings
from contextlib import asynccontextmanager
import uvicorn


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.
    Initializes database on startup and cleans up on shutdown.
    """
    # Startup
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"Initializing database...")
    await init_db()
    print(f"Database initialized successfully!")

    # Initialize AI
    print(f"\nInitializing AI backends...")
    from backend.engine.ai_manager import ai_manager
    status = ai_manager.get_status()
    print(f"AI Backend: {status['backend']}")
    if status['is_configured']:
        print(f"✓ AI is ready! NPCs and game guide are functional.")
    else:
        print(f"⚠ No AI backend detected. NPCs will use placeholder responses.")
        print(f"  Install Ollama: https://ollama.ai")
        print(f"  Or MLX (Apple Silicon): pip install mlx-lm")

    print(f"\nServer running at http://{settings.HOST}:{settings.PORT}")
    print(f"WebSocket endpoint: ws://{settings.HOST}:{settings.PORT}/ws")
    print(f"\nNew commands: 'guide <question>' and '@ai/status'")
    yield
    # Shutdown
    print("Shutting down...")
    await close_db()
    print("Goodbye!")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="A modern web-based MUSH server inspired by PennMUSH",
    lifespan=lifespan
)

# Include REST API routes
app.include_router(api_router)


@app.get("/")
async def root():
    """Serve the main HTML page"""
    return FileResponse("frontend/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for MUSH gameplay"""
    await handle_websocket(websocket)


# Mount static files (CSS, JS, assets)
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": settings.APP_VERSION}


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
