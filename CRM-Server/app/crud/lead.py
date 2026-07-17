from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timedelta, time
from enum import Enum
from app.models.lead import Lead, LeadFollowUp, LeadStatus, LeadSource, CompanyScale
from app.schemas.lead import LeadCreate, LeadUpdate, LeadFollowUpCreate


class LeadCRUD:
    def get_by_id(self, db: Session, lead_id: int, team_id: Optional[int] = None) -> Optional[Lead]:
        query = db.query(Lead).filter(Lead.id == lead_id)
        if team_id is not None:
            query = query.filter(Lead.team_id == team_id)
        return query.first()

    def get_by_contact_phone(self, db: Session, contact_phone: str, team_id: Optional[int] = None) -> Optional[Lead]:
        query = db.query(Lead).filter(Lead.contact_phone == contact_phone)
        if team_id is not None:
            query = query.filter(Lead.team_id == team_id)
        return query.first()

    def get_multi(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        status: Optional[LeadStatus] = None,
        source: Optional[str] = None,
        city: Optional[str] = None,
        owner_id: Optional[str] = None,
        creator_id: Optional[str] = None,
        keyword: Optional[str] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
        order_by: Optional[str] = None,
        order_dir: Optional[str] = None
    ) -> Tuple[List[Lead], int]:
        query = db.query(Lead).filter(Lead.team_id == team_id)

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
        if filters:
            query = self._apply_filters(query, filters)

        total = query.count()

        allowed_sort_fields = ['created_time', 'lead_name', 'city', 'status', 'last_modified_time']
        if order_by and order_dir and order_by in allowed_sort_fields:
            order_column = getattr(Lead, order_by)
            if order_dir.lower() == 'desc':
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())
        else:
            query = query.order_by(Lead.created_time.desc())

        leads = query.offset(skip).limit(limit).all()

        return leads, total

    def _apply_filters(self, query, filters: List[Dict[str, Any]]):
        field_map = {
            "lead_name": (Lead.lead_name, "text"),
            "contact_name": (Lead.contact_name, "text"),
            "contact_phone": (Lead.contact_phone, "text"),
            "city": (Lead.city, "text"),
            "source": (Lead.source, "source"),
            "company_scale": (Lead.company_scale, "company_scale"),
            "status": (Lead.status, "status"),
            "owner_id": (Lead.owner_id, "text"),
            "created_time": (Lead.created_time, "date"),
            "last_modified_time": (Lead.last_modified_time, "date"),
            "score": (Lead.score, "number"),
        }

        for condition in filters:
            field = condition.get("field")
            op = condition.get("op")
            value = condition.get("value")

            if field not in field_map or not op:
                continue

            column, field_type = field_map[field]

            if op == "is_empty":
                if field_type in {"text", "source", "company_scale"}:
                    query = query.filter(or_(column.is_(None), column == ""))
                else:
                    query = query.filter(column.is_(None))
                continue

            if op == "is_not_empty":
                if field_type in {"text", "source", "company_scale"}:
                    query = query.filter(and_(column.is_not(None), column != ""))
                else:
                    query = query.filter(column.is_not(None))
                continue

            parsed_value = self._parse_filter_value(field_type, value)
            if parsed_value is None:
                continue

            if field_type == "date":
                if op == "eq":
                    start = datetime.combine(parsed_value.date(), time.min)
                    end = datetime.combine(parsed_value.date(), time.max)
                    query = query.filter(and_(column >= start, column <= end))
                elif op == "before":
                    query = query.filter(column < parsed_value)
                elif op == "after":
                    query = query.filter(column > parsed_value)
                continue

            if isinstance(parsed_value, list):
                filter_values = [
                    item.name if isinstance(item, Enum) else item
                    for item in parsed_value
                ]
                if len(filter_values) == 0:
                    continue

                if op in {"eq", "contains"}:
                    query = query.filter(column.in_(filter_values))
                elif op in {"neq", "not_contains"}:
                    query = query.filter(column.notin_(filter_values))
                continue

            filter_value = parsed_value.name if isinstance(parsed_value, Enum) else parsed_value

            if op == "eq":
                query = query.filter(column == filter_value)
            elif op == "neq":
                query = query.filter(column != filter_value)
            elif op == "contains" and field_type == "text":
                query = query.filter(column.like(f"%{parsed_value}%"))
            elif op == "not_contains" and field_type == "text":
                query = query.filter(column.notlike(f"%{parsed_value}%"))

        return query

    def _parse_filter_value(self, field_type: str, value: Any):
        if value is None or value == "":
            return None

        if isinstance(value, list):
            parsed_values = [
                self._parse_filter_value(field_type, item)
                for item in value
            ]
            return [item for item in parsed_values if item is not None]

        try:
            if field_type == "status":
                return self._parse_enum_value(LeadStatus, value)
            if field_type == "source":
                return self._parse_enum_value(LeadSource, value)
            if field_type == "company_scale":
                return self._parse_enum_value(CompanyScale, value)
            if field_type == "number":
                return int(value)
            if field_type == "date":
                value_text = str(value)
                if len(value_text) == 10:
                    return datetime.fromisoformat(f"{value_text}T00:00:00")
                return datetime.fromisoformat(value_text)
        except (TypeError, ValueError):
            return None

        return str(value).strip()

    def _parse_enum_value(self, enum_class, value: Any):
        value_text = str(value).strip()

        for member in enum_class:
            if value == member.value or value_text == str(member.value) or value_text == member.name:
                return member

        return None

    def create(self, db: Session, obj_in: LeadCreate, creator_id: str, team_id: int) -> Lead:
        lead_data = obj_in.model_dump()
        lead_data['creator_id'] = creator_id
        lead_data['owner_id'] = creator_id  # 创建人自动成为负责人
        lead_data['status'] = LeadStatus.FOLLOWING  # 有负责人，状态应为跟进中
        lead_data['team_id'] = team_id

        db_obj = Lead(**lead_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)

        # 触发热力值初始计算
        from app.triggers.score_triggers import score_trigger
        score_trigger.on_lead_created(db, db_obj.id, team_id)

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
        """删除线索，同时删除关联的跟进记录

        注意：已转化的线索无法删除（需先删除对应的客户）
        """
        obj = db.query(Lead).filter(Lead.id == lead_id).first()
        if not obj:
            return None

        # 检查是否已转化
        if obj.status == LeadStatus.CONVERTED:
            # 检查是否有对应的客户
            from app.models.customer import Customer
            customer = db.query(Customer).filter(Customer.source_lead_id == lead_id).first()
            if customer:
                raise ValueError(f"该线索已转化为客户「{customer.account_name}」，无法直接删除。请先删除客户。")

        # 删除关联的跟进记录
        follow_ups = db.query(LeadFollowUp).filter(LeadFollowUp.lead_id == lead_id).all()
        for follow_up in follow_ups:
            db.delete(follow_up)

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

    def claim(self, db: Session, lead_id: int, user_id: str, team_id: int) -> Optional[Lead]:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.owner_id = user_id
            lead.status = LeadStatus.FOLLOWING
            lead.version += 1
            db.commit()
            db.refresh(lead)

            # 触发热力值更新（公海操作）
            from app.triggers.score_triggers import score_trigger
            score_trigger.on_lead_pool_operation(db, lead_id, team_id)

        return lead

    def return_to_pool(self, db: Session, lead_id: int, team_id: int) -> Optional[Lead]:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.owner_id = None
            lead.status = LeadStatus.NEW
            lead.version += 1
            db.commit()
            db.refresh(lead)

            # 触发热力值更新（公海操作）
            from app.triggers.score_triggers import score_trigger
            score_trigger.on_lead_pool_operation(db, lead_id, team_id)

        return lead
        return lead

    def convert(self, db: Session, lead_id: int) -> Optional[Lead]:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.status = LeadStatus.CONVERTED
            lead.version += 1
            db.commit()
            db.refresh(lead)
        return lead

    def mark_invalid(self, db: Session, lead_id: int, reason: str, operator_id: Optional[str] = None, operator_name: Optional[str] = None, team_id: Optional[int] = None) -> Optional[Lead]:
        """标记线索为无效，记录无效原因"""
        from app.services.operation_log_service import operation_log_service

        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.status = LeadStatus.INVALID
            lead.invalid_reason = reason
            lead.version += 1
            db.commit()
            db.refresh(lead)

            operation_log_service.log(
                db=db,
                event_type="LEAD_MARKED_INVALID",
                event_action="UPDATE",
                resource_type="LEAD",
                resource_id=lead.id,
                operator_id=operator_id or "system",
                operator_name=operator_name,
                team_id=team_id or lead.team_id,
                content={
                    "leadName": lead.lead_name,
                    "invalidReason": reason
                }
            )

        return lead

    def get_leads_by_owner(
        self,
        db: Session,
        team_id: int,
        owner_id: str,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[List[Lead], int]:
        query = db.query(Lead).filter(
            and_(
                Lead.team_id == team_id,
                Lead.owner_id == owner_id,
                Lead.status != LeadStatus.CONVERTED
            )
        )
        if filters:
            query = self._apply_filters(query, filters)
        total = query.count()
        leads = query.order_by(Lead.created_time.desc()).offset(skip).limit(limit).all()
        return leads, total

    def get_public_leads(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[List[Lead], int]:
        query = db.query(Lead).filter(
            and_(
                Lead.team_id == team_id,
                Lead.owner_id.is_(None),
                Lead.status != LeadStatus.CONVERTED
            )
        )
        if filters:
            query = self._apply_filters(query, filters)
        total = query.count()
        leads = query.order_by(Lead.created_time.desc()).offset(skip).limit(limit).all()
        return leads, total

    def get_leads_need_follow_up(self, db: Session, team_id: int, user_id: str, days: int = 7) -> List[Lead]:
        cutoff_date = datetime.now() - timedelta(days=days)
        return db.query(Lead).filter(
            and_(
                Lead.team_id == team_id,
                Lead.owner_id == user_id,
                Lead.status == LeadStatus.FOLLOWING,
                Lead.last_modified_time < cutoff_date
            )
        ).order_by(Lead.last_modified_time.asc()).all()

    def get_statistics(self, db: Session, team_id: int, owner_id: Optional[str] = None) -> dict:
        from sqlalchemy import case

        query = db.query(
            func.count(Lead.id).label('total'),
            func.sum(case((Lead.status == LeadStatus.NEW, 1), else_=0)).label('new'),
            func.sum(case((Lead.status == LeadStatus.FOLLOWING, 1), else_=0)).label('following'),
            func.sum(case((Lead.status == LeadStatus.CONVERTED, 1), else_=0)).label('converted'),
            func.sum(case((Lead.status == LeadStatus.INVALID, 1), else_=0)).label('invalid')
        ).filter(Lead.team_id == team_id)

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

    def create(
        self,
        db: Session,
        obj_in: LeadFollowUpCreate,
        lead_id: int,
        creator_id: str,
        team_id: int,
        operator_name: Optional[str] = None
    ) -> LeadFollowUp:
        from app.services.operation_log_service import operation_log_service

        follow_up_data = obj_in.model_dump()
        follow_up_data['lead_id'] = lead_id
        follow_up_data['creator_id'] = creator_id
        follow_up_data['team_id'] = team_id

        db_obj = LeadFollowUp(**follow_up_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)

        # 记录操作日志
        operation_log_service.log_lead_follow_up(
            db=db,
            lead_id=lead_id,
            follow_up_content=db_obj.content,
            method=db_obj.method,
            operator_id=creator_id,
            operator_name=operator_name,
            next_follow_time=db_obj.next_follow_time.strftime("%Y-%m-%d") if db_obj.next_follow_time else None,
            next_action=db_obj.next_action,
            team_id=team_id,
            follow_up_id=db_obj.id
        )

        # 触发热力值更新（跟进记录创建）
        from app.triggers.score_triggers import score_trigger
        score_trigger.on_lead_follow_up_created(db, lead_id, team_id)

        return db_obj

    def delete(self, db: Session, follow_up_id: int) -> Optional[LeadFollowUp]:
        obj = db.query(LeadFollowUp).filter(LeadFollowUp.id == follow_up_id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def get_upcoming_follow_ups(self, db: Session, team_id: int, user_id: str, days: int = 7) -> List[LeadFollowUp]:
        cutoff_date = datetime.now() + timedelta(days=days)
        return db.query(LeadFollowUp).join(Lead, Lead.id == LeadFollowUp.lead_id).filter(
            and_(
                Lead.team_id == team_id,
                Lead.owner_id == user_id,
                LeadFollowUp.next_follow_time.isnot(None),
                LeadFollowUp.next_follow_time <= cutoff_date
            )
        ).order_by(LeadFollowUp.next_follow_time.asc()).all()

    def get_latest_by_lead_id(self, db: Session, lead_id: int) -> Optional[LeadFollowUp]:
        """获取线索的最新一条跟进记录"""
        return db.query(LeadFollowUp).filter(
            LeadFollowUp.lead_id == lead_id
        ).order_by(LeadFollowUp.created_time.desc()).first()

    def update_next_time(
        self,
        db: Session,
        db_obj: LeadFollowUp,
        next_follow_time: datetime,
        next_action: Optional[str] = None
    ) -> LeadFollowUp:
        """更新跟进记录的下次跟进时间和下一步动作"""
        db_obj.next_follow_time = next_follow_time
        if next_action:
            db_obj.next_action = next_action
        db.commit()
        db.refresh(db_obj)
        return db_obj


lead_crud = LeadCRUD()
lead_follow_up_crud = LeadFollowUpCRUD()
