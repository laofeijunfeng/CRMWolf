from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from app.models.lead import Lead, LeadFollowUp, LeadStatus
from app.schemas.lead import LeadCreate, LeadUpdate, LeadFollowUpCreate


class LeadCRUD:
    def get_by_id(self, db: Session, lead_id: int) -> Optional[Lead]:
        return db.query(Lead).filter(Lead.id == lead_id).first()

    def get_by_contact_phone(self, db: Session, contact_phone: str) -> Optional[Lead]:
        return db.query(Lead).filter(Lead.contact_phone == contact_phone).first()

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[LeadStatus] = None,
        source: Optional[str] = None,
        city: Optional[str] = None,
        owner_id: Optional[str] = None,
        creator_id: Optional[str] = None,
        keyword: Optional[str] = None
    ) -> Tuple[List[Lead], int]:
        query = db.query(Lead)
        
        if status is not None:
            query = query.filter(Lead.status == status)
        else:
            query = query.filter(Lead.status != LeadStatus.CONVERTED)
        
        if source:
            query = query.filter(Lead.source == source)
        if city:
            query = query.filter(Lead.city == city)
        if owner_id:
            query = query.filter(Lead.owner_id == owner_id)
        if creator_id:
            query = query.filter(Lead.creator_id == creator_id)
        if keyword:
            query = query.filter(
                or_(
                    Lead.lead_name.like(f"%{keyword}%"),
                    Lead.contact_name.like(f"%{keyword}%"),
                    Lead.contact_phone.like(f"%{keyword}%")
                )
            )
        
        total = query.count()
        leads = query.order_by(Lead.created_time.desc()).offset(skip).limit(limit).all()
        
        return leads, total

    def create(self, db: Session, obj_in: LeadCreate, creator_id: str) -> Lead:
        lead_data = obj_in.model_dump()
        lead_data['creator_id'] = creator_id
        lead_data['owner_id'] = creator_id  # 创建人自动成为归属人
        lead_data['status'] = LeadStatus.NEW

        db_obj = Lead(**lead_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: Lead, obj_in: LeadUpdate) -> Lead:
        update_data = obj_in.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db_obj.version += 1
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, lead_id: int) -> Optional[Lead]:
        obj = db.query(Lead).filter(Lead.id == lead_id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def assign(self, db: Session, lead_id: int, owner_id: str) -> Optional[Lead]:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.owner_id = owner_id
            lead.status = LeadStatus.FOLLOWING
            lead.version += 1
            db.commit()
            db.refresh(lead)
        return lead

    def claim(self, db: Session, lead_id: int, user_id: str) -> Optional[Lead]:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.owner_id = user_id
            lead.status = LeadStatus.FOLLOWING
            lead.version += 1
            db.commit()
            db.refresh(lead)
        return lead

    def return_to_pool(self, db: Session, lead_id: int) -> Optional[Lead]:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.owner_id = None
            lead.status = LeadStatus.NEW
            lead.version += 1
            db.commit()
            db.refresh(lead)
        return lead

    def convert(self, db: Session, lead_id: int) -> Optional[Lead]:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.status = LeadStatus.CONVERTED
            lead.version += 1
            db.commit()
            db.refresh(lead)
        return lead

    def mark_invalid(self, db: Session, lead_id: int) -> Optional[Lead]:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.status = LeadStatus.INVALID
            lead.version += 1
            db.commit()
            db.refresh(lead)
        return lead

    def get_leads_by_owner(self, db: Session, owner_id: str, skip: int = 0, limit: int = 100) -> List[Lead]:
        return db.query(Lead).filter(
            and_(
                Lead.owner_id == owner_id,
                Lead.status != LeadStatus.CONVERTED
            )
        ).order_by(Lead.created_time.desc()).offset(skip).limit(limit).all()

    def get_public_leads(self, db: Session, skip: int = 0, limit: int = 100) -> List[Lead]:
        return db.query(Lead).filter(
            and_(
                Lead.owner_id.is_(None),
                Lead.status != LeadStatus.CONVERTED
            )
        ).order_by(Lead.created_time.desc()).offset(skip).limit(limit).all()

    def get_leads_need_follow_up(self, db: Session, user_id: str, days: int = 7) -> List[Lead]:
        cutoff_date = datetime.now() - timedelta(days=days)
        return db.query(Lead).filter(
            and_(
                Lead.owner_id == user_id,
                Lead.status == LeadStatus.FOLLOWING,
                Lead.last_modified_time < cutoff_date
            )
        ).order_by(Lead.last_modified_time.asc()).all()

    def get_statistics(self, db: Session, owner_id: Optional[str] = None) -> dict:
        from sqlalchemy import case
        
        query = db.query(
            func.count(Lead.id).label('total'),
            func.sum(case((Lead.status == LeadStatus.NEW, 1), else_=0)).label('new'),
            func.sum(case((Lead.status == LeadStatus.FOLLOWING, 1), else_=0)).label('following'),
            func.sum(case((Lead.status == LeadStatus.CONVERTED, 1), else_=0)).label('converted'),
            func.sum(case((Lead.status == LeadStatus.INVALID, 1), else_=0)).label('invalid')
        )
        
        if owner_id:
            query = query.filter(Lead.owner_id == owner_id)
        
        result = query.first()
        
        return {
            'total': result.total or 0,
            'new': result.new or 0,
            'following': result.following or 0,
            'converted': result.converted or 0,
            'invalid': result.invalid or 0
        }


class LeadFollowUpCRUD:
    def get_by_id(self, db: Session, follow_up_id: int) -> Optional[LeadFollowUp]:
        return db.query(LeadFollowUp).filter(LeadFollowUp.id == follow_up_id).first()

    def get_by_lead_id(self, db: Session, lead_id: int, skip: int = 0, limit: int = 100) -> List[LeadFollowUp]:
        return db.query(LeadFollowUp).filter(
            LeadFollowUp.lead_id == lead_id
        ).order_by(LeadFollowUp.created_time.desc()).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: LeadFollowUpCreate, lead_id: int, creator_id: str) -> LeadFollowUp:
        follow_up_data = obj_in.model_dump()
        follow_up_data['lead_id'] = lead_id
        follow_up_data['creator_id'] = creator_id
        
        db_obj = LeadFollowUp(**follow_up_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, follow_up_id: int) -> Optional[LeadFollowUp]:
        obj = db.query(LeadFollowUp).filter(LeadFollowUp.id == follow_up_id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def get_upcoming_follow_ups(self, db: Session, user_id: str, days: int = 7) -> List[LeadFollowUp]:
        cutoff_date = datetime.now() + timedelta(days=days)
        return db.query(LeadFollowUp).join(Lead, Lead.id == LeadFollowUp.lead_id).filter(
            and_(
                Lead.owner_id == user_id,
                LeadFollowUp.next_follow_time.isnot(None),
                LeadFollowUp.next_follow_time <= cutoff_date
            )
        ).order_by(LeadFollowUp.next_follow_time.asc()).all()


lead_crud = LeadCRUD()
lead_follow_up_crud = LeadFollowUpCRUD()
