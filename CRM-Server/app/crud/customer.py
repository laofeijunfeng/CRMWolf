from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional, List, Tuple
from datetime import datetime, timedelta

from app.models.customer import Customer, Contact
from app.models.lead import Lead, LeadStatus
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerStatusEnum,
    ContactCreate,
    ContactUpdate
)
from app.crud.operation_log import operation_log_crud


class CustomerCRUD:
    def get_by_id(self, db: Session, customer_id: int) -> Optional[Customer]:
        return db.query(Customer).filter(Customer.id == customer_id).first()

    def get_by_name(self, db: Session, account_name: str) -> Optional[Customer]:
        return db.query(Customer).filter(Customer.account_name == account_name).first()

    def get_by_source_lead_id(self, db: Session, lead_id: int) -> Optional[Customer]:
        return db.query(Customer).filter(Customer.source_lead_id == lead_id).first()

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[int] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        owner_id: Optional[str] = None,
        keyword: Optional[str] = None
    ) -> Tuple[List[Customer], int]:
        query = db.query(Customer)
        
        if status is not None:
            query = query.filter(Customer.status == status)
        if industry:
            query = query.filter(Customer.industry == industry)
        if city:
            query = query.filter(Customer.city == city)
        if owner_id:
            query = query.filter(Customer.owner_id == owner_id)
        if keyword:
            query = query.filter(
                or_(
                    Customer.account_name.like(f"%{keyword}%"),
                    Customer.industry.like(f"%{keyword}%")
                )
            )
        
        total = query.count()
        customers = query.order_by(Customer.created_time.desc()).offset(skip).limit(limit).all()
        
        return customers, total

    def create(self, db: Session, obj_in: CustomerCreate, creator_id: str, operator_name: Optional[str] = None) -> Customer:
        from app.services.operation_log_service import operation_log_service
        
        customer_data = obj_in.model_dump()
        customer_data['creator_id'] = creator_id
        customer_data['status'] = 0
        
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
            }
        )
        
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

    def delete(self, db: Session, db_obj: Customer, operator_id: Optional[str] = None) -> Customer:
        """删除客户，如果客户来源于线索，则恢复线索状态为 FOLLOWING"""
        from app.services.operation_log_service import operation_log_service

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
        industry: Optional[str],
        address: Optional[str],
        creator_id: str,
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
            industry=industry or None,
            city=lead.city,
            address=address or None,
            company_scale=lead.company_scale.value if lead.company_scale else None,
            source=lead.source.value,
            status=0,
            owner_id=lead.owner_id or creator_id,
            source_lead_id=lead_id,
            default_procurement_method_id=default_procurement_method_id,
            creator_id=creator_id
        )
        
        db.add(customer)
        db.flush()
        
        contact = Contact(
            customer_id=customer.id,
            name=lead.contact_name,
            mobile=lead.contact_phone,
            is_primary=True,
            is_decision_maker=True
        )
        
        db.add(contact)
        db.flush()
        
        customer_follow_up_crud.migrate_from_lead(db, lead_id, customer.id)
        
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
            operator_name=operator_name
        )
        
        operation_log_crud.migrate_lead_logs_to_customer(
            db=db,
            lead_id=lead_id,
            customer_id=customer.id
        )
        
        return customer, contact

    def get_statistics(self, db: Session, owner_id: Optional[str] = None) -> dict:
        query = db.query(Customer)
        
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
        days: int = 30,
        owner_id: Optional[str] = None
    ) -> List[dict]:
        start_date = datetime.now() - timedelta(days=days)
        
        query = db.query(Customer).filter(Customer.created_time >= start_date)
        
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
        return customer

    def get_public_customers(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[int] = None,
        city: Optional[str] = None,
        keyword: Optional[str] = None
    ) -> Tuple[List[Customer], int]:
        query = db.query(Customer).filter(Customer.owner_id.is_(None))
        
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
        customers = query.order_by(Customer.returned_time.desc()).offset(skip).limit(limit).all()
        
        return customers, total

    def claim_customer(
        self,
        db: Session,
        customer: Customer,
        owner_id: str
    ) -> Customer:
        if customer.owner_id is not None:
            raise ValueError("该客户已有负责人，无法领取")
        
        customer.owner_id = owner_id
        customer.return_reason = None
        customer.returned_time = None
        customer.version += 1
        
        db.commit()
        db.refresh(customer)
        return customer
    
    def assign_customer(
        self,
        db: Session,
        customer: Customer,
        new_owner_id: str
    ) -> Customer:
        old_owner_id = customer.owner_id
        customer.owner_id = new_owner_id
        
        if customer.status == 3:
            customer.status = 0
            customer.return_reason = None
            customer.returned_time = None
        
        customer.version += 1
        
        db.commit()
        db.refresh(customer)
        return customer


class ContactCRUD:
    def get_by_id(self, db: Session, contact_id: int) -> Optional[Contact]:
        return db.query(Contact).filter(Contact.id == contact_id).first()

    def get_by_customer_id(self, db: Session, customer_id: int) -> List[Contact]:
        return db.query(Contact).filter(Contact.customer_id == customer_id).all()

    def get_primary_by_customer_id(self, db: Session, customer_id: int) -> Optional[Contact]:
        return db.query(Contact).filter(
            and_(Contact.customer_id == customer_id, Contact.is_primary == 1)
        ).first()

    def get_by_mobile(self, db: Session, mobile: str) -> Optional[Contact]:
        return db.query(Contact).filter(Contact.mobile == mobile).first()

    def create(
        self,
        db: Session,
        obj_in: ContactCreate,
        customer_id: int,
        is_primary: bool = False
    ) -> Contact:
        contact_data = obj_in.model_dump()
        contact_data['customer_id'] = customer_id
        contact_data['is_primary'] = 1 if is_primary else 0
        
        if is_primary:
            existing_primary = self.get_primary_by_customer_id(db, customer_id)
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

    def set_primary(self, db: Session, contact: Contact) -> Contact:
        customer_id = contact.customer_id
        
        existing_primary = self.get_primary_by_customer_id(db, customer_id)
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
