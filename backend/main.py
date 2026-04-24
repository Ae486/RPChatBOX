"""ChatBoxApp Python Backend - FastAPI Entry Point."""
import asyncio
import logging
import os
import sys
import traceback
from contextlib import suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from api import api_router
from config import get_settings
from services.database import create_db_and_tables
from services.langfuse_service import get_langfuse_service
from services.langgraph_checkpoint_store import ensure_langgraph_checkpoint_schema
from services.mcp_manager import get_mcp_manager


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
        _ = get_langfuse_service()
        app.state.mcp_connect_task = asyncio.create_task(
            get_mcp_manager().connect_enabled_servers()
        )
        logging.getLogger(__name__).info(
            "[MCP] scheduled background auto-connect for enabled servers"
        )

    @app.on_event("shutdown")
    async def shutdown_event():
        mcp_connect_task = getattr(app.state, "mcp_connect_task", None)
        if mcp_connect_task is not None and not mcp_connect_task.done():
            mcp_connect_task.cancel()
            with suppress(asyncio.CancelledError):
                await mcp_connect_task
        get_langfuse_service().shutdown()
        await get_mcp_manager().disconnect_all()

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
