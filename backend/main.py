"""ChatBoxApp Python Backend - FastAPI Entry Point."""
import logging
import os
import sys
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from api import api_router
from config import get_settings
from services.database import create_db_and_tables
from services.langgraph_checkpoint_store import ensure_langgraph_checkpoint_schema


def _configure_application_logging() -> None:
    """Enable INFO-level application logs for manual backend verification."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(name)s: %(message)s",
        force=True,
    )


def _patch_embedded_streams() -> None:
    """Patch stdout/stderr for embedded Python runtimes (e.g. serious_python)."""
    for _stream in (sys.stdout, sys.stderr):
        if _stream is not None:
            if not hasattr(_stream, "isatty"):
                _stream.isatty = lambda: False
            if not hasattr(_stream, "fileno"):
                _stream.fileno = lambda: -1


def create_app() -> FastAPI:
    """Create FastAPI app without starting the server."""
    settings = get_settings()
    app = FastAPI(
        title="ChatBoxApp Backend",
        description="LLM Proxy with MCP and RAG support",
        version=settings.version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.on_event("startup")
    async def startup_event():
        settings.ensure_dirs()
        create_db_and_tables()
        ensure_langgraph_checkpoint_schema()

    @app.post("/api/shutdown")
    async def shutdown():
        import asyncio
        import signal
        import threading

        if threading.current_thread() is threading.main_thread():
            asyncio.get_event_loop().call_later(
                0.5, lambda: os.kill(os.getpid(), signal.SIGTERM)
            )
        else:
            asyncio.get_event_loop().call_later(0.5, lambda: os._exit(0))
        return {"status": "shutting_down"}

    return app


app = create_app()


def run() -> None:
    """Run the backend server."""
    _patch_embedded_streams()
    _configure_application_logging()
    settings = get_settings()
    print(f"[PROD] Starting backend on {settings.host}:{settings.port}")
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        loop="asyncio",
        log_level="info",
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    server.run()


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"[PROD] FATAL ERROR: {e}")
        traceback.print_exc()
