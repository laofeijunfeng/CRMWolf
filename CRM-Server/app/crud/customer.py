from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional, List, Tuple
from datetime import date, datetime, time, timedelta

from app.models.customer import Customer, Contact, CustomerMember
from app.models.lead import Lead, LeadStatus
from app.models.contract import Contract
from app.models.opportunity import Opportunity
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerStatusEnum,
    ContactCreate,
    ContactUpdate
)
from app.crud.operation_log import operation_log_crud


def _split_csv(value: Optional[str]) -> List[str]:
    if value is None:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _split_int_csv(value: Optional[str]) -> List[int]:
    values = []
    for item in _split_csv(value):
        try:
            values.append(int(item))
        except ValueError:
            continue
    return values


class CustomerCRUD:
    def get_by_id(self, db: Session, customer_id: int, team_id: Optional[int] = None) -> Optional[Customer]:
        query = db.query(Customer).filter(Customer.id == customer_id)
        if team_id is not None:
            query = query.filter(Customer.team_id == team_id)
        return query.first()

    def get_by_name(self, db: Session, account_name: str, team_id: Optional[int] = None) -> Optional[Customer]:
        query = db.query(Customer).filter(Customer.account_name == account_name)
        if team_id is not None:
            query = query.filter(Customer.team_id == team_id)
        return query.first()

    def get_by_source_lead_id(self, db: Session, lead_id: int, team_id: Optional[int] = None) -> Optional[Customer]:
        query = db.query(Customer).filter(Customer.source_lead_id == lead_id)
        if team_id is not None:
            query = query.filter(Customer.team_id == team_id)
        return query.first()

    def get_multi(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        status_exclude: Optional[str] = None,
        industry: Optional[str] = None,
        industry_exclude: Optional[str] = None,
        city: Optional[str] = None,
        source: Optional[str] = None,
        source_exclude: Optional[str] = None,
        company_scale: Optional[str] = None,
        company_scale_exclude: Optional[str] = None,
        owner_id: Optional[str] = None,
        owner_id_exclude: Optional[str] = None,
        keyword: Optional[str] = None,
        created_time_start: Optional[date] = None,
        created_time_end: Optional[date] = None,
        order_by: Optional[str] = None,
        order_dir: Optional[str] = None,
        scope: Optional[str] = None,
        current_user_id: Optional[str] = None,
        include_collaborated: bool = False
    ) -> Tuple[List[Customer], int]:
        query = db.query(Customer).filter(Customer.team_id == team_id)

        current_user_id = str(current_user_id) if current_user_id is not None else None
        if scope == "owned" and current_user_id:
            query = query.filter(Customer.owner_id == current_user_id)
        elif scope == "collaborated" and current_user_id:
            query = query.filter(
                db.query(CustomerMember.id).filter(
                    CustomerMember.team_id == team_id,
                    CustomerMember.customer_id == Customer.id,
                    CustomerMember.user_id == current_user_id,
                    CustomerMember.is_active == True,
                ).exists()
            )
        elif include_collaborated and current_user_id:
            query = query.filter(
                or_(
                    Customer.owner_id == current_user_id,
                    db.query(CustomerMember.id).filter(
                        CustomerMember.team_id == team_id,
                        CustomerMember.customer_id == Customer.id,
                        CustomerMember.user_id == current_user_id,
                        CustomerMember.is_active == True,
                    ).exists()
                )
            )

        status_values = _split_int_csv(status)
        if status_values:
            query = query.filter(Customer.status.in_(status_values))
        status_exclude_values = _split_int_csv(status_exclude)
        if status_exclude_values:
            query = query.filter(Customer.status.notin_(status_exclude_values))
        if industry:
            query = query.filter(Customer.industry.in_(_split_csv(industry)))
        if industry_exclude:
            query = query.filter(Customer.industry.notin_(_split_csv(industry_exclude)))
        if city:
            query = query.filter(Customer.city == city)
        if source:
            query = query.filter(Customer.source.in_(_split_csv(source)))
        if source_exclude:
            query = query.filter(Customer.source.notin_(_split_csv(source_exclude)))
        if company_scale:
            query = query.filter(Customer.company_scale.in_(_split_csv(company_scale)))
        if company_scale_exclude:
            query = query.filter(Customer.company_scale.notin_(_split_csv(company_scale_exclude)))
        if owner_id:
            query = query.filter(Customer.owner_id.in_(_split_csv(owner_id)))
        if owner_id_exclude:
            query = query.filter(Customer.owner_id.notin_(_split_csv(owner_id_exclude)))
        if keyword:
            query = query.filter(
                or_(
                    Customer.account_name.like(f"%{keyword}%"),
                    Customer.industry.like(f"%{keyword}%"),
                    Customer.city.like(f"%{keyword}%")
                )
            )
        if created_time_start:
            query = query.filter(Customer.created_time >= datetime.combine(created_time_start, time.min))
        if created_time_end:
            query = query.filter(Customer.created_time <= datetime.combine(created_time_end, time.max))

        total = query.count()

        allowed_sort_fields = [
            'created_time',
            'account_name',
            'status',
            'industry',
            'source',
            'city',
            'company_scale',
            'owner_id',
        ]
        if order_by and order_dir and order_by in allowed_sort_fields:
            order_column = getattr(Customer, order_by)
            if order_dir.lower() == 'desc':
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())
        else:
            query = query.order_by(Customer.created_time.desc())

        customers = query.offset(skip).limit(limit).all()

        return customers, total

    def create(self, db: Session, obj_in: CustomerCreate, creator_id: str, team_id: int, operator_name: Optional[str] = None) -> Customer:
        from app.services.operation_log_service import operation_log_service

        customer_data = obj_in.model_dump(exclude={'primary_contact'})
        customer_data['creator_id'] = creator_id
        customer_data['status'] = 0
        customer_data['team_id'] = team_id

        if not customer_data.get('owner_id'):
            customer_data['owner_id'] = creator_id

        db_obj = Customer(**customer_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        
        operation_log_service.log(
            db=db,
            event_type="CUSTOMER_CREATED",
            event_action="CREATE",
            resource_type="CUSTOMER",
            resource_id=db_obj.id,
            operator_id=creator_id,
            operator_name=operator_name,
            content={
                "customerName": db_obj.account_name,
                "industry": db_obj.industry,
                "city": db_obj.city,
                "source": db_obj.source,
                "fromLead": False
            },
            team_id=team_id  # ✅ 必须传递 team_id（团队隔离）
        )

        # 触发热力值初始计算
        from app.triggers.score_triggers import score_trigger
        score_trigger.on_customer_created(db, db_obj.id, team_id)

        return db_obj

    def update(self, db: Session, db_obj: Customer, obj_in: CustomerUpdate) -> Customer:
        update_data = obj_in.model_dump(exclude_unset=True)
        
        if update_data:
            for field, value in update_data.items():
                setattr(db_obj, field, value)
            
            db_obj.version += 1
            db.commit()
            db.refresh(db_obj)
        
        return db_obj

    def update_status(self, db: Session, db_obj: Customer, status: int) -> Customer:
        db_obj.status = status
        db_obj.version += 1
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_industry(self, db: Session, customer_id: int, industry: str) -> Customer:
        """更新客户行业字段"""
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise ValueError("客户不存在")
        customer.industry = industry
        customer.version += 1
        db.commit()
        db.refresh(customer)
        return customer

    def update_profile_status(
        self,
        db: Session,
        customer_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> Customer:
        """更新档案生成状态"""
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise ValueError("客户不存在")

        customer.profile_status = status
        if status == "FAILED" and error_message:
            customer.profile_error_message = error_message
        if status == "COMPLETED":
            customer.profile_generated_time = datetime.now()

        customer.version += 1
        db.commit()
        db.refresh(customer)
        return customer

    def update_profile(
        self,
        db: Session,
        customer_id: int,
        profile_data: dict
    ) -> Customer:
        """更新客户档案信息"""
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise ValueError("客户不存在")

        for field, value in profile_data.items():
            if hasattr(customer, field):
                setattr(customer, field, value)

        customer.version += 1
        db.commit()
        db.refresh(customer)
        return customer

    def update_customer_brief_status(
        self,
        db: Session,
        customer_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> Customer:
        """更新客户概况生成状态"""
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise ValueError("客户不存在")

        customer.customer_brief_status = status
        if status != "FAILED":
            customer.customer_brief_error_message = None
        if status == "FAILED" and error_message:
            customer.customer_brief_error_message = error_message
        if status == "COMPLETED":
            customer.customer_brief_generated_time = datetime.now()

        customer.version += 1
        db.commit()
        db.refresh(customer)
        return customer

    def update_customer_brief(
        self,
        db: Session,
        customer_id: int,
        brief_data: dict
    ) -> Customer:
        """更新客户概况内容"""
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise ValueError("客户不存在")

        for field, value in brief_data.items():
            if hasattr(customer, field):
                setattr(customer, field, value)

        customer.version += 1
        db.commit()
        db.refresh(customer)
        return customer

    def delete(self, db: Session, db_obj: Customer, operator_id: Optional[str] = None, team_id: Optional[int] = None) -> Customer:
        """删除客户，如果客户来源于线索，则恢复线索状态为 FOLLOWING

        注意：删除前会检查是否存在关联合同，如有则抛出异常
        """
        from app.services.operation_log_service import operation_log_service
        from app.crud.contract import contract_crud

        # Use customer's team_id if not provided
        if team_id is None:
            team_id = db_obj.team_id

        # 检查是否存在关联合同
        contracts = db.query(Contract).filter(Contract.customer_id == db_obj.id).count()
        if contracts > 0:
            raise ValueError(f"该客户存在 {contracts} 个关联合同，无法删除。请先删除相关合同。")

        source_lead_id = db_obj.source_lead_id

        if source_lead_id:
            lead = db.query(Lead).filter(Lead.id == source_lead_id).first()
            if lead and lead.status == LeadStatus.CONVERTED:
                lead.status = LeadStatus.FOLLOWING
                lead.version += 1

                operation_log_service.log(
                    db=db,
                    event_type="LEAD_STATUS_RESTORED",
                    event_action="UPDATE",
                    resource_type="LEAD",
                    resource_id=lead.id,
                    operator_id=operator_id or "system",
                    team_id=team_id,
                    content={
                        "leadName": lead.lead_name,
                        "reason": "客户被删除，恢复线索状态",
                        "oldStatus": "CONVERTED",
                        "newStatus": "FOLLOWING",
                        "deletedCustomerId": db_obj.id,
                        "deletedCustomerName": db_obj.account_name
                    }
                )

        customer_name = db_obj.account_name
        customer_id = db_obj.id

        db.delete(db_obj)
        db.commit()

        operation_log_service.log(
            db=db,
            event_type="CUSTOMER_DELETED",
            event_action="DELETE",
            resource_type="CUSTOMER",
            resource_id=customer_id,
            operator_id=operator_id or "system",
            team_id=team_id,
            content={
                "customerName": customer_name,
                "sourceLeadId": source_lead_id,
                "leadRestored": source_lead_id is not None
            }
        )

        return db_obj

    def convert_from_lead(
        self,
        db: Session,
        lead_id: int,
        account_name: Optional[str],
        address: Optional[str],
        creator_id: str,
        team_id: int,
        default_procurement_method_id: Optional[int] = None,
        operator_name: Optional[str] = None
    ) -> Tuple[Customer, Contact]:
        from app.crud.customer_follow_up import customer_follow_up_crud
        from app.services.operation_log_service import operation_log_service

        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise ValueError("线索不存在")

        existing_customer = self.get_by_source_lead_id(db, lead_id)
        if existing_customer:
            raise ValueError("该线索已被转化")

        customer = Customer(
            account_name=account_name or lead.lead_name,
            city=lead.city,
            address=address or None,
            company_scale=lead.company_scale.value if lead.company_scale else None,
            source=lead.source.value,
            status=0,
            owner_id=lead.owner_id or creator_id,
            source_lead_id=lead_id,
            team_id=team_id,
            default_procurement_method_id=default_procurement_method_id,
            creator_id=creator_id,
            profile_status="PENDING"
        )

        db.add(customer)
        db.flush()

        contact = Contact(
            customer_id=customer.id,
            team_id=team_id,
            name=lead.contact_name,
            mobile=lead.contact_phone or '',
            is_primary=True,
            is_decision_maker=True
        )

        db.add(contact)
        db.flush()
        
        customer_follow_up_crud.migrate_from_lead(db, lead_id, customer.id, team_id)
        
        lead.status = LeadStatus.CONVERTED
        lead.version += 1
        
        db.commit()
        db.refresh(customer)
        db.refresh(contact)
        
        operation_log_service.log_lead_converted(
            db=db,
            lead_id=lead_id,
            lead_name=lead.lead_name,
            customer_id=customer.id,
            customer_name=customer.account_name,
            operator_id=creator_id,
            operator_name=operator_name,
            team_id=team_id
        )
        
        operation_log_crud.migrate_lead_logs_to_customer(
            db=db,
            lead_id=lead_id,
            customer_id=customer.id
        )

        # 触发客户热力值初始计算
        from app.triggers.score_triggers import score_trigger
        score_trigger.on_customer_created(db, customer.id, team_id)

        return customer, contact

    def get_statistics(self, db: Session, team_id: int, owner_id: Optional[str] = None) -> dict:
        query = db.query(Customer).filter(Customer.team_id == team_id)

        if owner_id:
            query = query.filter(Customer.owner_id == owner_id)

        customers = query.all()

        return {
            "total": len(customers),
            "following": len([c for c in customers if c.status == 0]),
            "won": len([c for c in customers if c.status == 1]),
            "lost": len([c for c in customers if c.status == 2]),
            "inactive": len([c for c in customers if c.status == 3])
        }

    def get_trend(
        self,
        db: Session,
        team_id: int,
        days: int = 30,
        owner_id: Optional[str] = None
    ) -> List[dict]:
        start_date = datetime.now() - timedelta(days=days)

        query = db.query(Customer).filter(
            Customer.team_id == team_id,
            Customer.created_time >= start_date
        )

        if owner_id:
            query = query.filter(Customer.owner_id == owner_id)
        
        customers = query.all()
        
        trend_data = {}
        for customer in customers:
            date_str = customer.created_time.strftime('%Y-%m-%d')
            trend_data[date_str] = trend_data.get(date_str, 0) + 1
        
        result = []
        for i in range(days):
            date_str = (datetime.now() - timedelta(days=days - 1 - i)).strftime('%Y-%m-%d')
            result.append({
                "date": date_str,
                "count": trend_data.get(date_str, 0)
            })
        
        return result

    def return_to_pool(
        self,
        db: Session,
        customer: Customer,
        return_reason: str,
        team_id: int,
        detailed_reason: Optional[str] = None
    ) -> Customer:
        customer.owner_id = None
        customer.return_reason = return_reason
        if detailed_reason:
            customer.return_reason = f"{return_reason}: {detailed_reason}"
        customer.returned_time = datetime.now()
        customer.version += 1

        db.commit()
        db.refresh(customer)

        # 触发客户热力值更新（公海操作）
        from app.triggers.score_triggers import score_trigger
        score_trigger.on_customer_pool_operation(db, customer.id, team_id)

        return customer

    def get_public_customers(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        status: Optional[int] = None,
        city: Optional[str] = None,
        keyword: Optional[str] = None,
        order_by: Optional[str] = None,
        order_dir: Optional[str] = None
    ) -> Tuple[List[Customer], int]:
        query = db.query(Customer).filter(
            Customer.team_id == team_id,
            Customer.owner_id.is_(None)
        )

        if status is not None:
            query = query.filter(Customer.status == status)
        if city:
            query = query.filter(Customer.city == city)
        if keyword:
            query = query.filter(
                or_(
                    Customer.account_name.like(f"%{keyword}%"),
                    Customer.industry.like(f"%{keyword}%")
                )
            )

        total = query.count()

        allowed_sort_fields = ['returned_time', 'account_name', 'city', 'status', 'created_time']
        if order_by and order_dir and order_by in allowed_sort_fields:
            order_column = getattr(Customer, order_by)
            if order_dir.lower() == 'desc':
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())
        else:
            query = query.order_by(Customer.returned_time.desc())

        customers = query.offset(skip).limit(limit).all()

        return customers, total

    def claim_customer(
        self,
        db: Session,
        customer: Customer,
        owner_id: str,
        team_id: int
    ) -> Customer:
        if customer.owner_id is not None:
            raise ValueError("该客户已有负责人，无法领取")

        customer.owner_id = owner_id
        customer.return_reason = None
        customer.returned_time = None
        customer.version += 1

        db.commit()
        db.refresh(customer)

        # 触发客户热力值更新（公海操作）
        from app.triggers.score_triggers import score_trigger
        score_trigger.on_customer_pool_operation(db, customer.id, team_id)

        return customer
    
    def assign_customer(
        self,
        db: Session,
        customer: Customer,
        new_owner_id: str,
        team_id: int,
        opportunity_transfer_scope: str = "none"
    ) -> Tuple[Customer, int, int]:
        customer.owner_id = new_owner_id

        if customer.status == 3:
            customer.status = 0
            customer.return_reason = None
            customer.returned_time = None

        customer.version += 1
        transferred_opportunities = 0
        transferred_contracts = 0

        if opportunity_transfer_scope in {"following", "all"}:
            opportunity_query = db.query(Opportunity).filter(
                Opportunity.team_id == team_id,
                Opportunity.customer_id == customer.id
            )
            if opportunity_transfer_scope == "following":
                opportunity_query = opportunity_query.filter(Opportunity.status == 0)

            opportunity_ids = [opportunity.id for opportunity in opportunity_query.all()]
            transferred_opportunities = len(opportunity_ids)

            if opportunity_ids:
                db.query(Opportunity).filter(
                    Opportunity.id.in_(opportunity_ids),
                    Opportunity.team_id == team_id
                ).update(
                    {Opportunity.owner_id: new_owner_id},
                    synchronize_session=False
                )

                contract_query = db.query(Contract).filter(
                    Contract.team_id == team_id,
                    Contract.opportunity_id.in_(opportunity_ids)
                )
                transferred_contracts = contract_query.count()
                contract_query.update(
                    {Contract.owner_id: new_owner_id},
                    synchronize_session=False
                )

        db.commit()
        db.refresh(customer)
        return customer, transferred_opportunities, transferred_contracts

    def mark_as_lost(
        self,
        db: Session,
        customer: Customer,
        loss_reason: str,
        operator_id: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> Customer:
        """标记客户为输单，记录输单原因"""
        from app.services.operation_log_service import operation_log_service

        customer.status = 2
        customer.loss_reason = loss_reason
        customer.version += 1

        db.commit()
        db.refresh(customer)

        operation_log_service.log(
            db=db,
            event_type="CUSTOMER_MARKED_LOST",
            event_action="UPDATE",
            resource_type="CUSTOMER",
            resource_id=customer.id,
            operator_id=operator_id or "system",
            operator_name=operator_name,
            content={
                "customerName": customer.account_name,
                "lossReason": loss_reason
            }
        )

        return customer


class ContactCRUD:
    def get_by_id(self, db: Session, contact_id: int, team_id: Optional[int] = None) -> Optional[Contact]:
        """获取联系人详情

        Args:
            db: 数据库 session
            contact_id: 联系人 ID
            team_id: 团队 ID（可选，用于团队隔离）

        Returns:
            联系人对象或 None
        """
        query = db.query(Contact).filter(Contact.id == contact_id)
        if team_id is not None:
            query = query.filter(Contact.team_id == team_id)
        return query.first()

    def get_by_customer_id(self, db: Session, customer_id: int, team_id: Optional[int] = None) -> List[Contact]:
        """获取客户下的联系人列表

        Args:
            db: 数据库 session
            customer_id: 客户 ID
            team_id: 团队 ID（可选，用于团队隔离）

        Returns:
            联系人列表
        """
        query = db.query(Contact).filter(Contact.customer_id == customer_id)
        if team_id is not None:
            query = query.filter(Contact.team_id == team_id)
        return query.all()

    def get_primary_by_customer_id(self, db: Session, customer_id: int, team_id: Optional[int] = None) -> Optional[Contact]:
        """获取客户的主联系人

        Args:
            db: 数据库 session
            customer_id: 客户 ID
            team_id: 团队 ID（可选，用于团队隔离）

        Returns:
            主联系人对象或 None
        """
        query = db.query(Contact).filter(
            and_(Contact.customer_id == customer_id, Contact.is_primary == 1)
        )
        if team_id is not None:
            query = query.filter(Contact.team_id == team_id)
        return query.first()

    def get_by_mobile(self, db: Session, mobile: str, team_id: Optional[int] = None) -> Optional[Contact]:
        """根据手机号获取联系人

        Args:
            db: 数据库 session
            mobile: 手机号
            team_id: 团队 ID（可选，用于团队隔离）

        Returns:
            联系人对象或 None
        """
        query = db.query(Contact).filter(Contact.mobile == mobile)
        if team_id is not None:
            query = query.filter(Contact.team_id == team_id)
        return query.first()

    def create(
        self,
        db: Session,
        obj_in: ContactCreate,
        customer_id: int,
        team_id: int,
        is_primary: bool = False
    ) -> Contact:
        """创建联系人

        Args:
            db: 数据库 session
            obj_in: 联系人创建 schema
            customer_id: 客户 ID
            team_id: 团队 ID
            is_primary: 是否为主联系人

        Returns:
            创建的联系人对象
        """
        contact_data = obj_in.model_dump()
        contact_data['customer_id'] = customer_id
        contact_data['team_id'] = team_id
        contact_data['is_primary'] = 1 if is_primary else 0

        if is_primary:
            existing_primary = self.get_primary_by_customer_id(db, customer_id, team_id)
            if existing_primary:
                existing_primary.is_primary = 0

        db_obj = Contact(**contact_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: Contact, obj_in: ContactUpdate) -> Contact:
        update_data = obj_in.model_dump(exclude_unset=True)

        if update_data:
            for field, value in update_data.items():
                setattr(db_obj, field, value)

            db.commit()
            db.refresh(db_obj)

        return db_obj

    def set_primary(self, db: Session, contact: Contact, team_id: Optional[int] = None) -> Contact:
        """设置联系人为主联系人

        Args:
            db: 数据库 session
            contact: 联系人对象
            team_id: 团队 ID（可选，用于团队隔离）

        Returns:
            更新后的联系人对象
        """
        customer_id = contact.customer_id

        existing_primary = self.get_primary_by_customer_id(db, customer_id, team_id)
        if existing_primary and existing_primary.id != contact.id:
            existing_primary.is_primary = 0

        contact.is_primary = 1
        db.commit()
        db.refresh(contact)
        return contact

    def delete(self, db: Session, db_obj: Contact) -> Contact:
        if db_obj.is_primary:
            raise ValueError("不能删除主联系人")
        
        db.delete(db_obj)
        db.commit()
        return db_obj


customer_crud = CustomerCRUD()
contact_crud = ContactCRUD()
