from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, execute, health, system
from app.core.config import get_settings
from app.core.invariants import validate_startup_invariants
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    settings = get_settings()
    validate_startup_invariants(settings)
    yield


app = FastAPI(title="ZTA Agentic Service", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(admin.router)
app.include_router(system.router)
app.include_router(execute.router)

web_dir = Path(__file__).resolve().parent / "web"
app.mount("/ui", StaticFiles(directory=web_dir, html=True), name="ui")
