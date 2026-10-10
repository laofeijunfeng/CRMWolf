"""Vector retirement deletes only prepared points and fails when any remain."""

from types import SimpleNamespace

import pytest

from app.services.customer_profile_vector_retirement_service import (
    VectorRetirementIncomplete,
    customer_profile_vector_retirement_service,
)


class FakeQdrant:
    def __init__(self) -> None:
        self.points: set[str] = set()
        self.deleted: list[str] = []

    def delete_points(self, point_ids: list[str]) -> None:
        for pid in point_ids:
            self.points.discard(pid)
            self.deleted.append(pid)

    def point_exists(self, pid: str) -> bool:
        return pid in self.points


class FakeDocument:
    def __init__(self, status: str, point_id: str) -> None:
        self.sync_status = status
        self.qdrant_point_id = point_id


class FakeQuery:
    def __init__(self, docs: list[FakeDocument]) -> None:
        self.docs = docs

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return [d for d in self.docs if d.sync_status == "DELETE_PENDING"]


class FakeDB:
    def __init__(self, docs: list[FakeDocument]) -> None:
        self.docs = docs

    def query(self, _model):
        return FakeQuery(self.docs)


def test_retires_only_prepared_points_and_verifies_absence() -> None:
    qdrant = FakeQdrant()
    qdrant.points.update({"p1", "p2", "p3"})
    db = FakeDB([
        FakeDocument("DELETE_PENDING", "p1"),
        FakeDocument("DELETE_PENDING", "p2"),
        FakeDocument("SYNCED", "p3"),
    ])

    report = customer_profile_vector_retirement_service.retire_pending_documents(db, qdrant)

    assert report.pending_count == 2
    assert report.deleted_count == 2
    assert report.verified_absent_count == 2
    assert sorted(qdrant.deleted) == ["p1", "p2"]
    # p3 remains because it was not prepared for deletion.
    assert qdrant.points == {"p3"}


def test_fails_when_a_point_survives_deletion() -> None:
    class LeakyQdrant(FakeQdrant):
        def delete_points(self, point_ids: list[str]) -> None:
            self.deleted.extend(point_ids)
            for pid in point_ids[1:]:
                self.points.discard(pid)

    qdrant = LeakyQdrant()
    qdrant.points.update({"p1", "p2"})
    db = FakeDB([FakeDocument("DELETE_PENDING", "p1"), FakeDocument("DELETE_PENDING", "p2")])

    with pytest.raises(VectorRetirementIncomplete):
        customer_profile_vector_retirement_service.retire_pending_documents(db, qdrant)


def test_rejects_client_without_deletion_seam() -> None:
    db = FakeDB([])
    with pytest.raises(VectorRetirementIncomplete):
        customer_profile_vector_retirement_service.retire_pending_documents(db, object())
