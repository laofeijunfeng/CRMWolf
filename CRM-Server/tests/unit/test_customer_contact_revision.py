from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from app.crud.customer import ContactCRUD
from app.models.customer import Contact
from app.schemas.customer import ContactUpdate


def _contact(*, contact_id: int, is_primary: int, revision: int = 1) -> Contact:
    return Contact(
        id=contact_id,
        team_id=2,
        customer_id=101,
        name=f"联系人 {contact_id}",
        mobile=f"1380013800{contact_id % 10}",
        is_primary=is_primary,
        post_commit_revision=revision,
    )


def test_contact_update_advances_revision_only_when_facts_change() -> None:
    crud = ContactCRUD()
    contact = _contact(contact_id=601, is_primary=0)
    db = Mock()

    crud.update(db, contact, ContactUpdate(position="采购负责人"))
    assert contact.post_commit_revision == 2

    crud.update(db, contact, ContactUpdate(position="采购负责人"))
    assert contact.post_commit_revision == 2
    assert db.commit.call_count == 2


def test_set_primary_advances_revision_for_both_contacts_whose_state_changes() -> None:
    crud = ContactCRUD()
    old_primary = _contact(contact_id=601, is_primary=1, revision=4)
    new_primary = _contact(contact_id=602, is_primary=0, revision=7)
    crud.get_primary_by_customer_id = lambda db, customer_id, team_id: old_primary  # type: ignore[method-assign]
    db = SimpleNamespace(commit=Mock(), refresh=Mock())

    result = crud.set_primary(db, new_primary, team_id=2)

    assert result is new_primary
    assert old_primary.is_primary == 0
    assert old_primary.post_commit_revision == 5
    assert new_primary.is_primary == 1
    assert new_primary.post_commit_revision == 8
    db.commit.assert_called_once_with()
