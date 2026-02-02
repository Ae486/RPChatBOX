"""ChatBoxApp Python Backend - FastAPI Entry Point."""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import api_router
from config import get_settings

settings = get_settings()

app = FastAPI(
    title="ChatBoxApp Backend",
    description="LLM Proxy with MCP and RAG support",
    version=settings.version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS for local Flutter app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # localhost only in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    settings.ensure_dirs()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
