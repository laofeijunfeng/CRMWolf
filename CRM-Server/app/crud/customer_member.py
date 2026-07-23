from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.customer import Customer, CustomerMember
from app.models.role import Role
from app.models.team import UserTeam
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.customer import CustomerMemberCreate, CustomerMemberUpdate


ACCESS_LEVEL_RANK = {
    "VIEW": 1,
    "FOLLOW_UP": 2,
    "EDIT": 3,
}


class CustomerMemberCRUD:
    def get_by_id(self, db: Session, member_id: int, team_id: int) -> Optional[CustomerMember]:
        return db.query(CustomerMember).filter(
            CustomerMember.id == member_id,
            CustomerMember.team_id == team_id,
            CustomerMember.is_active == True
        ).first()

    def get_active_member(
        self,
        db: Session,
        team_id: int,
        customer_id: int,
        user_id: str,
    ) -> Optional[CustomerMember]:
        return db.query(CustomerMember).filter(
            CustomerMember.team_id == team_id,
            CustomerMember.customer_id == customer_id,
            CustomerMember.user_id == str(user_id),
            CustomerMember.is_active == True
        ).first()

    def has_access(
        self,
        db: Session,
        team_id: int,
        customer_id: int,
        user_id: str,
        required_level: str,
    ) -> bool:
        member = self.get_active_member(db, team_id, customer_id, str(user_id))
        if not member:
            return False
        return ACCESS_LEVEL_RANK.get(member.access_level, 0) >= ACCESS_LEVEL_RANK.get(required_level, 0)

    def get_by_customer(self, db: Session, team_id: int, customer_id: int) -> List[CustomerMember]:
        return db.query(CustomerMember).filter(
            CustomerMember.team_id == team_id,
            CustomerMember.customer_id == customer_id,
            CustomerMember.is_active == True
        ).order_by(CustomerMember.created_time.asc()).all()

    def create_or_restore(
        self,
        db: Session,
        team_id: int,
        customer_id: int,
        obj_in: CustomerMemberCreate,
        created_by: str,
    ) -> CustomerMember:
        user_id = str(obj_in.user_id)
        existing = db.query(CustomerMember).filter(
            CustomerMember.team_id == team_id,
            CustomerMember.customer_id == customer_id,
            CustomerMember.user_id == user_id,
        ).order_by(CustomerMember.id.desc()).first()

        if existing:
            existing.member_role = obj_in.member_role.value
            existing.access_level = obj_in.access_level.value
            existing.remark = obj_in.remark
            existing.created_by = created_by
            existing.is_active = True
            db.commit()
            db.refresh(existing)
            return existing

        db_obj = CustomerMember(
            team_id=team_id,
            customer_id=customer_id,
            user_id=user_id,
            member_role=obj_in.member_role.value,
            access_level=obj_in.access_level.value,
            remark=obj_in.remark,
            created_by=created_by,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: CustomerMember, obj_in: CustomerMemberUpdate) -> CustomerMember:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(value, "value"):
                value = value.value
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def deactivate(self, db: Session, db_obj: CustomerMember) -> None:
        db_obj.is_active = False
        db.commit()

    def get_candidates(self, db: Session, team_id: int, customer_id: int) -> List[dict]:
        customer = db.query(Customer).filter(
            Customer.team_id == team_id,
            Customer.id == customer_id,
        ).first()
        owner_id = customer.owner_id if customer else None
        active_member_user_ids = {
            item[0]
            for item in db.query(CustomerMember.user_id).filter(
                CustomerMember.team_id == team_id,
                CustomerMember.customer_id == customer_id,
                CustomerMember.is_active == True,
            ).all()
        }

        rows = db.query(User).join(
            UserTeam, User.id == UserTeam.user_id
        ).filter(
            UserTeam.team_id == team_id
        ).order_by(User.name.asc()).all()

        role_rows = db.query(UserRole.user_id, Role.code).join(
            Role, UserRole.role_id == Role.id
        ).filter(UserRole.team_id == team_id).all()
        roles_by_user: dict[str, list[str]] = {}
        for user_id, role_code in role_rows:
            roles_by_user.setdefault(str(user_id), []).append(role_code)

        return [
            {
                "id": str(user.id),
                "name": user.name,
                "avatar_url": user.avatar_url,
                "roles": roles_by_user.get(str(user.id), []),
                "already_member": str(user.id) == owner_id or str(user.id) in active_member_user_ids,
            }
            for user in rows
        ]


customer_member_crud = CustomerMemberCRUD()
