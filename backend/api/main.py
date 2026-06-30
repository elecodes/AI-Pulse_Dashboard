"""FastAPI application factory for the AI Intelligence Dashboard API.

Usage::

    from backend.api.main import create_app
    app = create_app(config_path="config/feeds.yaml")
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config.config_loader import ConfigLoader
from backend.storage.storage_layer import StorageLayer


def create_app(
    storage: StorageLayer | None = None,
    config_path: str = "config/feeds.yaml",
) -> FastAPI:
    """Create and return a configured FastAPI application.

    Parameters
    ----------
    storage:
        Pre-configured StorageLayer instance (used in tests).  When
        ``None``, the app loads config from *config_path* and creates
        its own storage.
    config_path:
        Path to the YAML configuration file.  Ignored when *storage* is
        provided.
    """
    if storage is None:
        config = ConfigLoader.load(config_path)
        storage = StorageLayer(config.db_path)
        storage.init_db()

    app = FastAPI(title="AI Intelligence Dashboard API")

    # Attach storage eagerly — httpx ASGI transport does not trigger
    # lifespan events, so we cannot rely on lifespan for this.
    app.state.storage = storage

    # Lifespan placeholder — Sprint 5 may move scheduling here.
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield

    app.router.lifespan_context = _lifespan

    # CORS — allow all origins for local development (Sprint 4 tightens this).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Return HTTP 400 instead of FastAPI's default 422 for invalid params.
    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": exc.errors()},
        )

    # Register routers.
    from backend.api.routers.articles import router as articles_router
    from backend.api.routers.trends import router as trends_router
    from backend.api.routers.sources import router as sources_router

    app.include_router(articles_router)
    app.include_router(trends_router)
    app.include_router(sources_router)

    return app


app = create_app()
