from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    assignments_router,
    consistency_router,
    demo_router,
    operations_router,
    reviewer_router,
    submissions_router,
)
from app.config import get_settings
from app.errors import install_error_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Evidence-first, human-approved programming assessment API",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(application)
    application.include_router(assignments_router, prefix=settings.api_prefix)
    application.include_router(consistency_router, prefix=settings.api_prefix)
    application.include_router(submissions_router, prefix=settings.api_prefix)
    application.include_router(reviewer_router, prefix=settings.api_prefix)
    application.include_router(operations_router, prefix=settings.api_prefix)
    application.include_router(demo_router, prefix=settings.api_prefix)

    @application.get(f"{settings.api_prefix}/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
