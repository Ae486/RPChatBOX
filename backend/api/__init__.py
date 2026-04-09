"""API routes package."""
from fastapi import APIRouter

from .health import router as health_router
from .chat import router as chat_router
from .conversations import router as conversations_router
from .conversation_source import router as conversation_source_router
from .providers import router as providers_router
from .provider_models import router as provider_models_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(chat_router, tags=["chat"])
api_router.include_router(conversations_router, tags=["conversations"])
api_router.include_router(conversation_source_router, tags=["conversation-source"])
api_router.include_router(providers_router, tags=["providers"])
api_router.include_router(provider_models_router, tags=["provider-models"])
