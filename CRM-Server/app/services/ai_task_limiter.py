"""Shared concurrency limit for background AI generation tasks."""
import asyncio


ai_generation_semaphore = asyncio.Semaphore(2)
