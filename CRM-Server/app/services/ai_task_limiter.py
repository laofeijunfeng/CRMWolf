"""Shared concurrency limit for background AI generation tasks."""
import asyncio

from app.core.config import get_settings

settings = get_settings()
ai_generation_semaphore = asyncio.Semaphore(max(1, settings.AI_GENERATION_CONCURRENCY))
