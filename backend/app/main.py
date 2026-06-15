from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, health, internal, vms
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = get_settings()
    application = FastAPI(title=settings.app_name)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router, prefix=settings.api_prefix)
    application.include_router(auth.router, prefix=settings.api_prefix)
    application.include_router(vms.router, prefix=settings.api_prefix)
    application.include_router(internal.router)
    return application


app = create_app()
