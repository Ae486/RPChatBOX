"""ChatBoxApp Python Backend - FastAPI Entry Point."""
import os
import sys
import traceback

# Patch stdout/stderr for embedded Python (serious_python on mobile)
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None:
        if not hasattr(_stream, 'isatty'):
            _stream.isatty = lambda: False
        if not hasattr(_stream, 'fileno'):
            _stream.fileno = lambda: -1

try:
    import threading
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from api import api_router
    from config import get_settings

    settings = get_settings()
    _is_main_thread = threading.current_thread() is threading.main_thread()

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

    @app.post("/api/shutdown")
    async def shutdown():
        import asyncio
        if _is_main_thread:
            import signal
            asyncio.get_event_loop().call_later(0.5, lambda: os.kill(os.getpid(), signal.SIGTERM))
        else:
            asyncio.get_event_loop().call_later(0.5, lambda: os._exit(0))
        return {"status": "shutting_down"}

    # Start server
    print(f"[PROD] Starting backend on {settings.host}:{settings.port}")
    config = uvicorn.Config(app, host=settings.host, port=settings.port, loop="asyncio", log_level="info")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    server.run()

except Exception as e:
    print(f"[PROD] FATAL ERROR: {e}")
    traceback.print_exc()
