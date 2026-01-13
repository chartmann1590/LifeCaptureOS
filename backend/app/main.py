"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db, engine, Base
from app.routers import device, media, web, chat
from app.routers import settings as settings_router
from app.ollama_service import OllamaService
from app.scheduler import get_scheduler

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting LifeCaptureOS Backend Server...")

    # Ensure storage directories exist
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    settings.media_path.mkdir(parents=True, exist_ok=True)
    settings.thumbs_path.mkdir(parents=True, exist_ok=True)
    settings.videos_path.mkdir(parents=True, exist_ok=True)
    (settings.storage_path / "temp").mkdir(parents=True, exist_ok=True)

    # Initialize database
    logger.info(f"Initializing database at {settings.db_path}")
    init_db()

    # Check Ollama connectivity
    logger.info(f"Checking Ollama connection at {settings.ollama_base_url}")
    ollama = OllamaService()
    try:
        healthy = await ollama.health_check()
        if healthy:
            logger.info(f"Ollama connected. Model: {settings.ollama_vision_model}")
        else:
            logger.warning(
                f"Ollama health check failed. "
                f"AI analysis will not work until Ollama is configured. "
                f"Make sure {settings.ollama_vision_model} model is available."
            )
    except Exception as e:
        logger.warning(f"Could not connect to Ollama: {e}")
        logger.warning("AI analysis will not be available.")

    # Start daily summary scheduler
    try:
        scheduler = get_scheduler()
        scheduler.start(generation_time=settings.summary_generation_time)
        logger.info("Daily summary scheduler started")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        logger.warning("Daily summaries will not be automatically generated")

    logger.info(f"Server ready on http://{settings.host}:{settings.port}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    
    # Stop scheduler
    try:
        scheduler = get_scheduler()
        scheduler.stop()
        logger.info("Daily summary scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")


# Create FastAPI app
app = FastAPI(
    title="LifeCaptureOS Backend API",
    description="Backend server for LifeCaptureOS ESP32-CAM wearable camera system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware (for web UI if needed)
# WARNING: allow_origins=["*"] is insecure for production.
# In production, specify a list of allowed origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "ok": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error"
            }
        }
    )


# Include routers (API routes first)
app.include_router(device.router)
app.include_router(media.router)
app.include_router(chat.router)
app.include_router(settings_router.router)

# Daily summaries router
from app.routers import daily_summaries
app.include_router(daily_summaries.router)

# Mount static files for React app (before web router)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include web router last (catch-all for SPA)
app.include_router(web.router)


# Root endpoint
@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "ok": True,
        "service": "LifeCaptureOS Backend API",
        "version": "1.0.0",
        "endpoints": {
            "device": "/device/*",
            "media": "/media/*",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    # Check database
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        db_healthy = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_healthy = False

    # Check Ollama
    ollama = OllamaService()
    try:
        ollama_healthy = await ollama.health_check()
    except:
        ollama_healthy = False

    overall_healthy = db_healthy

    return {
        "ok": overall_healthy,
        "status": "healthy" if overall_healthy else "degraded",
        "components": {
            "database": "healthy" if db_healthy else "unhealthy",
            "ollama": "healthy" if ollama_healthy else "unavailable",
            "storage": "healthy" if settings.storage_path.exists() else "unhealthy"
        },
        "config": {
            "ollama_url": settings.ollama_base_url,
            "ollama_model": settings.ollama_vision_model,
            "storage_dir": str(settings.storage_path)
        }
    }


# CLI utilities
if __name__ == "__main__":
    import uvicorn
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "init-db":
            # Initialize database
            print("Initializing database...")
            init_db()
            print(f"Database initialized at {settings.db_path}")

        elif command == "create-device":
            # Create a new device
            from app.models import Device
            from app.database import SessionLocal
            from app.auth import generate_device_token, hash_token

            if len(sys.argv) < 3:
                print("Usage: python -m app.main create-device <device_id> [name]")
                sys.exit(1)

            device_id = sys.argv[2]
            name = sys.argv[3] if len(sys.argv) > 3 else None

            token = generate_device_token()
            token_hash = hash_token(token)

            db = SessionLocal()
            device = Device(
                device_id=device_id,
                name=name,
                token_hash=token_hash
            )
            db.add(device)
            db.commit()

            print(f"Device created successfully!")
            print(f"Device ID: {device_id}")
            print(f"Device Token: {token}")
            print(f"\nStore this token securely. It will be used by the ESP32.")

        else:
            print(f"Unknown command: {command}")
            print("Available commands: init-db, create-device")

    else:
        # Run server
        uvicorn.run(
            "app.main:app",
            host=settings.host,
            port=settings.port,
            reload=settings.debug
        )
