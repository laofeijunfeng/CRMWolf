"""MySQL locking checks for durable Agent registries."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest

from app.core.database import SessionLocal, engine
from app.models.agent import AgentMessage, AgentMessageRole, AgentSession
from app.models.agent_persistence import AgentUIAction
from app.schemas.agent_persistence import (
    AgentAssistantMessageCreate,
    AgentTurnStart,
    AgentUIActionRegistration,
    AgentUIMessageBody,
)
from app.services.agent.ui.actions import (
    ActionAlreadyConsumedError,
    ActionNotFoundError,
    AgentUIActionRepository,
)
from app.utils.time import business_now

pytestmark = pytest.mark.integration


def _mysql_integration_enabled() -> bool:
    return os.getenv("RUN_MYSQL_INTEGRATION") == "1" and engine.dialect.name == "mysql"


def _create_action(*, suffix: str) -> tuple[int, int, str]:
    db = SessionLocal()
    try:
        session = AgentSession(session_key=f"agent-persistence-integration:{suffix}", team_id=1, user_id=1)
        db.add(session)
        db.flush()
        message = AgentMessage(
            team_id=1,
            user_id=1,
            session_id=session.id,
            role=AgentMessageRole.ASSISTANT,
            content="并发消费测试",
        )
        db.add(message)
        db.flush()
        action = AgentUIActionRepository().register(
            db,
            AgentUIActionRegistration(
                public_id=f"act_{suffix}",
                team_id=1,
                user_id=1,
                session_id=session.id,
                message_id=message.id,
                action_type="start_workflow",
                target={"workflow": "create_follow_up"},
                consumption_mode="ONE_SHOT",
            ),
        )
        session_id = int(session.id)
        message_id = int(message.id)
        db.commit()
        return session_id, message_id, action.public_id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _cleanup_session(session_id: int) -> None:
    db = SessionLocal()
    try:
        session = db.get(AgentSession, session_id)
        if session is not None:
            db.delete(session)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@pytest.mark.skipif(not _mysql_integration_enabled(), reason="requires RUN_MYSQL_INTEGRATION=1 and MySQL")
def test_one_shot_action_allows_only_one_concurrent_request() -> None:
    suffix = uuid4().hex
    session_id, _, public_id = _create_action(suffix=suffix)
    barrier = Barrier(2)

    def claim(request_id: str) -> str:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            try:
                result = AgentUIActionRepository().begin_consumption(
                    db,
                    public_id=public_id,
                    team_id=1,
                    user_id=1,
                    session_id=session_id,
                    client_request_id=request_id,
                )
            except ActionAlreadyConsumedError:
                db.rollback()
                return "ALREADY_CONSUMED"
            db.commit()
            return result.outcome
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        request_ids = [str(uuid4()), str(uuid4())]
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(claim, request_ids))

        assert sorted(outcomes) == ["ACQUIRED", "ALREADY_CONSUMED"]
    finally:
        _cleanup_session(session_id)


@pytest.mark.skipif(not _mysql_integration_enabled(), reason="requires RUN_MYSQL_INTEGRATION=1 and MySQL")
def test_one_shot_action_replays_same_concurrent_request() -> None:
    suffix = uuid4().hex
    session_id, _, public_id = _create_action(suffix=suffix)
    barrier = Barrier(2)
    request_id = str(uuid4())

    def claim() -> str:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            result = AgentUIActionRepository().begin_consumption(
                db,
                public_id=public_id,
                team_id=1,
                user_id=1,
                session_id=session_id,
                client_request_id=request_id,
            )
            db.commit()
            return result.outcome
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: claim(), range(2)))

        assert sorted(outcomes) == ["ACQUIRED", "REPLAY"]
    finally:
        _cleanup_session(session_id)


@pytest.mark.skipif(not _mysql_integration_enabled(), reason="requires RUN_MYSQL_INTEGRATION=1 and MySQL")
def test_terminal_cleanup_and_replay_are_safe_when_concurrent() -> None:
    suffix = uuid4().hex
    session_id, message_id, public_id = _create_action(suffix=suffix)
    request_id = str(uuid4())
    repository = AgentUIActionRepository()
    old_time = business_now() - timedelta(days=31)

    setup_db = SessionLocal()
    try:
        repository.begin_consumption(
            setup_db,
            public_id=public_id,
            team_id=1,
            user_id=1,
            session_id=session_id,
            client_request_id=request_id,
            now=old_time,
        )
        repository.complete_consumption(
            setup_db,
            public_id=public_id,
            team_id=1,
            user_id=1,
            session_id=session_id,
            client_request_id=request_id,
            result_message_id=message_id,
            now=old_time,
        )
        setup_db.commit()
    except Exception:
        setup_db.rollback()
        raise
    finally:
        setup_db.close()

    barrier = Barrier(2)

    def purge() -> str:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            deleted = repository.purge_terminal(db, team_id=1, now=business_now())
            db.commit()
            return f"PURGED:{deleted}"
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def replay() -> str:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            try:
                result = repository.begin_consumption(
                    db,
                    public_id=public_id,
                    team_id=1,
                    user_id=1,
                    session_id=session_id,
                    client_request_id=request_id,
                )
            except ActionNotFoundError:
                db.rollback()
                return "NOT_FOUND"
            db.commit()
            return result.outcome
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            purge_future = executor.submit(purge)
            replay_future = executor.submit(replay)
            outcomes = {purge_future.result(), replay_future.result()}

        assert outcomes & {"REPLAY", "NOT_FOUND"}
        assert outcomes & {"PURGED:0", "PURGED:1"}

        check_db = SessionLocal()
        try:
            remaining = check_db.query(AgentUIAction).filter(AgentUIAction.public_id == public_id).one_or_none()
            if remaining is not None:
                assert remaining.status == "CONSUMED"
        finally:
            check_db.close()
    finally:
        _cleanup_session(session_id)


def _turn_start(*, session_id: int, request_id: str, text: str) -> AgentTurnStart:
    return AgentTurnStart(
        team_id=1,
        user_id=1,
        session_id=session_id,
        client_request_id=request_id,
        input_fingerprint="a" * 64,
        content=text,
        ui=AgentUIMessageBody(
            state="final",
            blocks=[{"id": "b_text", "type": "text", "format": "plain", "text": text}],
            metadata={},
        ),
    )


@pytest.mark.skipif(not _mysql_integration_enabled(), reason="requires RUN_MYSQL_INTEGRATION=1 and MySQL")
def test_turn_begin_is_idempotent_under_mysql_concurrency() -> None:
    from app.services.agent.turns import AgentTurnRepository

    suffix = uuid4().hex
    session_id, _, _ = _create_action(suffix=suffix)
    request_id = str(uuid4())
    barrier = Barrier(2)

    def begin() -> tuple[str, int, str]:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            result = AgentTurnRepository().begin(
                db,
                _turn_start(session_id=session_id, request_id=request_id, text="我在上海有哪些客户"),
            )
            db.commit()
            return result.outcome, result.user_message.id, result.user_message.turn_id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: begin(), range(2)))

        assert sorted(outcome for outcome, _, _ in results) == ["CREATED", "IN_PROGRESS"]
        assert len({message_id for _, message_id, _ in results}) == 1
        assert len({turn_id for _, _, turn_id in results}) == 1
    finally:
        _cleanup_session(session_id)


@pytest.mark.skipif(not _mysql_integration_enabled(), reason="requires RUN_MYSQL_INTEGRATION=1 and MySQL")
def test_turn_begin_rejects_changed_input_under_mysql_concurrency() -> None:
    from app.services.agent.turns import AgentTurnIdempotencyConflictError, AgentTurnRepository

    suffix = uuid4().hex
    session_id, _, _ = _create_action(suffix=suffix)
    request_id = str(uuid4())
    barrier = Barrier(2)

    def begin(text: str) -> str:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            try:
                result = AgentTurnRepository().begin(
                    db,
                    _turn_start(session_id=session_id, request_id=request_id, text=text),
                )
            except AgentTurnIdempotencyConflictError:
                db.rollback()
                return "CONFLICT"
            db.commit()
            return result.outcome
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(begin, ["上海客户", "北京客户"]))

        assert sorted(results) == ["CONFLICT", "CREATED"]
    finally:
        _cleanup_session(session_id)


def _assistant_completion(
    *,
    session_id: int,
    turn_id: str,
    text: str,
) -> AgentAssistantMessageCreate:
    return AgentAssistantMessageCreate(
        team_id=1,
        user_id=1,
        session_id=session_id,
        turn_id=turn_id,
        content=text,
        ui=AgentUIMessageBody(
            state="final",
            blocks=[{"id": "b_text", "type": "text", "format": "plain", "text": text}],
            metadata={},
        ),
        diagnostics={"route": "QUERY"},
    )


@pytest.mark.skipif(not _mysql_integration_enabled(), reason="requires RUN_MYSQL_INTEGRATION=1 and MySQL")
def test_turn_complete_replays_same_output_under_mysql_concurrency() -> None:
    from app.services.agent.turns import AgentTurnRepository

    suffix = uuid4().hex
    session_id, _, _ = _create_action(suffix=suffix)
    repository = AgentTurnRepository()
    setup_db = SessionLocal()
    try:
        started = repository.begin(
            setup_db,
            _turn_start(session_id=session_id, request_id=str(uuid4()), text="我在上海有哪些客户"),
        )
        setup_db.commit()
        turn_id = started.user_message.turn_id
    except Exception:
        setup_db.rollback()
        raise
    finally:
        setup_db.close()

    barrier = Barrier(2)

    def complete() -> tuple[str, int]:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            result = AgentTurnRepository().complete(
                db,
                _assistant_completion(session_id=session_id, turn_id=turn_id, text="共找到 2 个客户"),
            )
            db.commit()
            return result.outcome, result.message.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: complete(), range(2)))

        assert sorted(outcome for outcome, _ in results) == ["CREATED", "REPLAY"]
        assert len({message_id for _, message_id in results}) == 1
    finally:
        _cleanup_session(session_id)


@pytest.mark.skipif(not _mysql_integration_enabled(), reason="requires RUN_MYSQL_INTEGRATION=1 and MySQL")
def test_turn_complete_rejects_changed_output_under_mysql_concurrency() -> None:
    from app.services.agent.turns import AgentTurnIdempotencyConflictError, AgentTurnRepository

    suffix = uuid4().hex
    session_id, _, _ = _create_action(suffix=suffix)
    repository = AgentTurnRepository()
    setup_db = SessionLocal()
    try:
        started = repository.begin(
            setup_db,
            _turn_start(session_id=session_id, request_id=str(uuid4()), text="我在上海有哪些客户"),
        )
        setup_db.commit()
        turn_id = started.user_message.turn_id
    except Exception:
        setup_db.rollback()
        raise
    finally:
        setup_db.close()

    barrier = Barrier(2)

    def complete(text: str) -> str:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            try:
                result = AgentTurnRepository().complete(
                    db,
                    _assistant_completion(session_id=session_id, turn_id=turn_id, text=text),
                )
            except AgentTurnIdempotencyConflictError:
                db.rollback()
                return "CONFLICT"
            db.commit()
            return result.outcome
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(complete, ["共找到 2 个客户", "共找到 3 个客户"]))

        assert sorted(results) == ["CONFLICT", "CREATED"]
    finally:
        _cleanup_session(session_id)
