"""Post-commit kicks made inside a turn thread must run on the app loop."""

from __future__ import annotations

import asyncio
import threading

import pytest

from app.core import app_loop


@pytest.fixture
def running_app_loop():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    app_loop.bind_app_loop(loop)
    yield loop
    app_loop.bind_app_loop(None)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
    loop.close()


def test_kick_from_a_turn_loop_lands_on_the_app_loop(running_app_loop):
    seen: list[asyncio.AbstractEventLoop] = []
    done = threading.Event()

    def kick() -> None:
        seen.append(asyncio.get_running_loop())
        done.set()

    def boom() -> None:
        raise RuntimeError("kick failed")

    async def turn() -> asyncio.AbstractEventLoop:
        app_loop.run_on_app_loop(boom, "failing kick")
        app_loop.run_on_app_loop(kick, "test kick")
        return asyncio.get_running_loop()

    result: list[asyncio.AbstractEventLoop] = []
    worker = threading.Thread(target=lambda: result.append(asyncio.run(turn())))
    worker.start()
    worker.join(timeout=5)

    assert done.wait(timeout=5)
    assert seen == [running_app_loop]
    assert result and result[0] is not running_app_loop


def test_job_kicked_inside_a_turn_outlives_the_turn_loop(running_app_loop):
    from types import SimpleNamespace

    from app.services.customer_activity_ai_job_service import CustomerActivityAIJobService

    service = CustomerActivityAIJobService()
    ran_on: list[asyncio.AbstractEventLoop] = []
    finished = threading.Event()

    async def run_guarded(request: object) -> None:
        await asyncio.sleep(0.05)
        ran_on.append(asyncio.get_running_loop())
        finished.set()

    service._run_guarded = run_guarded  # type: ignore[method-assign]

    async def turn() -> None:
        service.kick(SimpleNamespace(job_public_id="job-1"))  # type: ignore[arg-type]

    worker = threading.Thread(target=lambda: asyncio.run(turn()))
    worker.start()
    worker.join(timeout=5)

    assert finished.wait(timeout=5)
    assert ran_on == [running_app_loop]
