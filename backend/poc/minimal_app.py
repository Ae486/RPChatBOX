"""Minimal FastAPI backend for PoC testing."""
import os
import signal
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    print("Backend starting...")
    yield
    print("Backend shutting down...")


app = FastAPI(lifespan=lifespan)


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "poc-1.0.0"}


@app.post("/api/shutdown")
async def shutdown():
    """Graceful shutdown endpoint."""
    print("Shutdown requested...")
    # Schedule shutdown after response
    import asyncio
    asyncio.get_event_loop().call_later(0.5, lambda: os.kill(os.getpid(), signal.SIGTERM))
    return {"status": "shutting_down"}


def main():
    """Entry point."""
    port = int(os.environ.get("CHATBOX_BACKEND_PORT", "8765"))
    host = os.environ.get("CHATBOX_BACKEND_HOST", "127.0.0.1")

    print(f"Starting backend on {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        loop="asyncio",  # 不使用 uvloop，兼容移动端
        log_level="info",
    )


if __name__ == "__main__":
    main()
