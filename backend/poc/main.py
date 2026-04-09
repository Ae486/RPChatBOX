"""Minimal FastAPI backend for mobile PoC."""
import os
import sys

# Patch stdout/stderr for embedded Python (serious_python _LogcatWriter)
for stream in (sys.stdout, sys.stderr):
    if not hasattr(stream, 'isatty'):
        stream.isatty = lambda: False
    if not hasattr(stream, 'fileno'):
        stream.fileno = lambda: -1

import traceback

try:
    from fastapi import FastAPI
    import uvicorn

    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "poc-1.0.0"}

    @app.post("/api/shutdown")
    async def shutdown():
        import asyncio
        asyncio.get_event_loop().call_later(
            0.5, lambda: os._exit(0)
        )
        return {"status": "shutting_down"}

    port = int(os.environ.get("CHATBOX_BACKEND_PORT", "8765"))
    host = os.environ.get("CHATBOX_BACKEND_HOST", "127.0.0.1")
    print(f"Starting backend on {host}:{port}")

    config = uvicorn.Config(app, host=host, port=port, loop="asyncio", log_level="info")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    server.run()

except Exception as e:
    print(f"FATAL: {e}")
    traceback.print_exc()
