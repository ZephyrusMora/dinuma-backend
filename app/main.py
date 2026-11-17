from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.scheduler import start_scheduler, shutdown_scheduler
from app.services.db import init_db
from app.services.firebase import init_firebase
from app.services.analytics_service import init_analytics_cache
from app.routers.webhook import router as webhook_router
from app.routers.notifications import router as notifications_router
from app.routers.mahajana_sampatha import router as mahajana_router
from app.routers.dlb import router as dlb_router
from app.routers.analytics import router as analytics_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup and shutdown lifecycle for the FastAPI app."""
    # Startup
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)

    try:
        init_firebase()
        logger.info("Firebase initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize Firebase: %s", e)

    try:
        init_analytics_cache()
        logger.info("Analytics cache initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize analytics cache: %s", e)

    start_scheduler()
    logger.info("Scheduler started")

    yield  # app is running

    # Shutdown
    shutdown_scheduler()


app = FastAPI(title="Dinuma Lottery & Pattern Intelligence API", lifespan=lifespan)

# Enable CORS for web dashboard & mobile clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(mahajana_router)
app.include_router(notifications_router)
app.include_router(webhook_router)
app.include_router(dlb_router)
app.include_router(analytics_router, prefix="/analytics")
app.include_router(analytics_router)


@app.get("/", tags=["health"])
def health_check():
    """Simple health-check endpoint."""
    return {"status": "ok", "service": "Dinuma Lottery & Pattern Intelligence API"}