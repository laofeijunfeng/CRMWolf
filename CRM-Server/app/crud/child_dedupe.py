"""Persist customer child records, mapping dedupe-key unique violations to DuplicateRecordError."""

from collections.abc import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateRecordError


def persist_guarding_duplicate(
    db: Session,
    *,
    commit: bool,
    find_duplicate: Callable[[], DuplicateRecordError | None],
) -> None:
    """Commit or flush; on a unique violation roll back and report the record that won the race.

    ``find_duplicate`` runs after the rollback, so it must only use plain values captured
    before the write. An IntegrityError unrelated to a dedupe key is re-raised unchanged.
    """
    try:
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        duplicate = find_duplicate()
        if duplicate is None:
            raise
        raise duplicate from exc
