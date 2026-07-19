from sqlalchemy.orm import Session
from sqlalchemy import and_, func, cast, Integer
from typing import Optional, List, Tuple
from datetime import date, datetime

from app.models.opportunity import Opportunity, OpportunityStage, OpportunityStatus
from app.models.customer import Customer
from app.schemas.opportunity import (
    OpportunityStageCreate,
    OpportunityStageUpdate,
    OpportunityCreate,
    OpportunityUpdate,
    OpportunityStageUpdate as OpportunityStageUpdateRequest,
    OpportunityWin,
    OpportunityLose
)


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


class OpportunityStageCRUD:
    def get_by_id(self, db: Session, stage_id: int) -> Optional[OpportunityStage]:
        return db.query(OpportunityStage).filter(OpportunityStage.id == stage_id).first()

    def get_by_code(self, db: Session, stage_code: str, team_id: Optional[int] = None) -> Optional[OpportunityStage]:
        query = db.query(OpportunityStage).filter(OpportunityStage.stage_code == stage_code)
        if team_id is not None:
            query = query.filter(OpportunityStage.team_id == team_id)
        return query.first()

    def get_all_active(self, db: Session, team_id: Optional[int] = None) -> List[OpportunityStage]:
        query = db.query(OpportunityStage).filter(OpportunityStage.is_active == 1)
        if team_id is not None:
            query = query.filter(OpportunityStage.team_id == team_id)
        return query.order_by(OpportunityStage.sort_order).all()

    def get_multi(
        self,
        db: Session,
        team_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[int] = None
    ) -> Tuple[List[OpportunityStage], int]:
        query = db.query(OpportunityStage)

        if team_id is not None:
            query = query.filter(OpportunityStage.team_id == team_id)
        if is_active is not None:
            query = query.filter(OpportunityStage.is_active == is_active)

        total = query.count()
        stages = query.order_by(OpportunityStage.sort_order).offset(skip).limit(limit).all()

        return stages, total

    def create(self, db: Session, obj_in: OpportunityStageCreate, team_id: int) -> OpportunityStage:
        stage_data = obj_in.model_dump()
        stage_data['team_id'] = team_id
        db_obj = OpportunityStage(**stage_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: OpportunityStage, obj_in: OpportunityStageUpdate) -> OpportunityStage:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, stage_id: int) -> bool:
        stage = self.get_by_id(db, stage_id)
        if stage:
            db.delete(stage)
            db.commit()
            return True
        return False


class OpportunityCRUD:
    def get_by_id(self, db: Session, opportunity_id: int, team_id: Optional[int] = None) -> Optional[Opportunity]:
        query = db.query(Opportunity).filter(Opportunity.id == opportunity_id)
        if team_id is not None:
            query = query.filter(Opportunity.team_id == team_id)
        return query.first()

    def get_by_customer_id(
        self,
        db: Session,
        customer_id: int,
        team_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Opportunity], int]:
        query = db.query(Opportunity).filter(Opportunity.customer_id == customer_id)
        if team_id is not None:
            query = query.filter(Opportunity.team_id == team_id)
        total = query.count()
        opportunities = query.order_by(Opportunity.created_time.desc()).offset(skip).limit(limit).all()
        return opportunities, total

    def search_by_name(
        self,
        db: Session,
        keyword: str,
        team_id: int,
        limit: int = 5,
    ) -> List[Opportunity]:
        """
        按名称关键词搜索商机（Agent 专用）

        Args:
            db: 数据库会话
            keyword: 搜索关键词
            team_id: 团队 ID（必传，遵循规范）
            limit: 返回数量限制

        Returns:
            List[Opportunity]: 商机列表

        遵循规范：
        - CRUD 统一入口
        - team_id 必传
        - 不直接 query
        """
        from sqlalchemy import or_

        query = db.query(Opportunity).filter(
            and_(
                Opportunity.team_id == team_id,
                or_(
                    Opportunity.opportunity_name.like(f"%{keyword}%"),
                    Opportunity.customer.has(Customer.account_name.like(f"%{keyword}%")),
                )
            )
        )

        opportunities = query.order_by(Opportunity.created_time.desc()).limit(limit).all()

        return opportunities

    def get_multi(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        status_exclude: Optional[str] = None,
        stage_id: Optional[int] = None,
        owner_id: Optional[str] = None,
        owner_id_exclude: Optional[str] = None,
        customer_id: Optional[int] = None,
        keyword: Optional[str] = None,
        customer_keyword: Optional[str] = None,
        license_type: Optional[str] = None,
        license_type_exclude: Optional[str] = None,
        purchase_type: Optional[str] = None,
        purchase_type_exclude: Optional[str] = None,
        stage_name: Optional[str] = None,
        expected_closing_date_start: Optional[date] = None,
        expected_closing_date_end: Optional[date] = None,
        order_by: Optional[str] = None,
        order_dir: Optional[str] = None
    ) -> Tuple[List[Opportunity], int]:
        query = db.query(Opportunity).filter(Opportunity.team_id == team_id)

        status_values = _split_int_csv(status)
        if status_values:
            query = query.filter(Opportunity.status.in_(status_values))
        status_exclude_values = _split_int_csv(status_exclude)
        if status_exclude_values:
            query = query.filter(Opportunity.status.notin_(status_exclude_values))
        if stage_id is not None:
            query = query.filter(Opportunity.procurement_stage_id == stage_id)
        if owner_id is not None:
            query = query.filter(Opportunity.owner_id.in_(_split_csv(owner_id)))
        if owner_id_exclude:
            query = query.filter(Opportunity.owner_id.notin_(_split_csv(owner_id_exclude)))
        if customer_id is not None:
            query = query.filter(Opportunity.customer_id == customer_id)
        if keyword:
            query = query.filter(Opportunity.opportunity_name.like(f"%{keyword}%"))
        if customer_keyword:
            query = query.filter(Opportunity.customer.has(Customer.account_name.like(f"%{customer_keyword}%")))
        if license_type:
            query = query.filter(Opportunity.license_type.in_(_split_csv(license_type)))
        if license_type_exclude:
            query = query.filter(Opportunity.license_type.notin_(_split_csv(license_type_exclude)))
        if purchase_type:
            query = query.filter(Opportunity.purchase_type.in_(_split_csv(purchase_type)))
        if purchase_type_exclude:
            query = query.filter(Opportunity.purchase_type.notin_(_split_csv(purchase_type_exclude)))
        if stage_name:
            query = query.filter(Opportunity.current_stage_name.like(f"%{stage_name}%"))
        if expected_closing_date_start:
            query = query.filter(Opportunity.expected_closing_date >= expected_closing_date_start)
        if expected_closing_date_end:
            query = query.filter(Opportunity.expected_closing_date <= expected_closing_date_end)

        total = query.count()

        allowed_sort_fields = ['created_time', 'opportunity_name', 'total_amount', 'status', 'expected_closing_date']
        if order_by and order_dir and order_by in allowed_sort_fields:
            order_column = getattr(Opportunity, order_by)
            if order_dir.lower() == 'desc':
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())
        else:
            query = query.order_by(Opportunity.created_time.desc())

        opportunities = query.offset(skip).limit(limit).all()

        return opportunities, total

    def create(self, db: Session, obj_in: OpportunityCreate, creator_id: str, team_id: int) -> Opportunity:
        db_obj = self.create_without_commit(db, obj_in, creator_id, team_id)
        db.commit()
        db.refresh(db_obj)
        self.log_created(db, db_obj, creator_id, team_id)
        return db_obj

    def create_without_commit(self, db: Session, obj_in: OpportunityCreate, creator_id: str, team_id: int) -> Opportunity:
        from app.crud.opportunity import opportunity_stage_crud
        from app.crud.procurement import procurement_stage_template_crud
        from app.services.pricing import pricing_service
        from app.models.procurement import OpportunityStageSnapshot
        from datetime import datetime
        
        # 1. 确定采购方式
        if obj_in.procurement_method_id is not None:
            procurement_method_id = obj_in.procurement_method_id
        else:
            customer = db.query(Customer).filter(Customer.id == obj_in.customer_id).first()
            if not customer:
                raise ValueError("客户不存在")
            if customer.default_procurement_method_id:
                procurement_method_id = customer.default_procurement_method_id
            else:
                raise ValueError("未指定采购方式，且客户无默认采购方式")
        
        # 2. 确定初始阶段
        if obj_in.stage_id is not None:
            stage = procurement_stage_template_crud.get(db, obj_in.stage_id)
            if not stage:
                raise ValueError("指定的阶段不存在")
            if stage.procurement_method_id != procurement_method_id:
                raise ValueError("指定的阶段不属于所选采购方式")
        else:
            stage = procurement_stage_template_crud.get_default_stage(db, procurement_method_id)
            if not stage:
                raise ValueError(f"采购方式 {procurement_method_id} 没有配置默认起始阶段")
        
        # 3. 创建商机基础数据
        opportunity_data = {
            'opportunity_name': obj_in.opportunity_name,
            'customer_id': obj_in.customer_id,
            'procurement_method_id': procurement_method_id,
            'total_amount': obj_in.total_amount,
            'user_count': obj_in.user_count,
            'license_type': obj_in.license_type.value,
            'subscription_years': obj_in.subscription_years,
            'purchase_type': obj_in.purchase_type.value,
            'decision_maker_count': obj_in.decision_maker_count,
            'expected_closing_date': obj_in.expected_closing_date,
            'owner_id': obj_in.owner_id if obj_in.owner_id else creator_id,  # 创建人自动成为负责人
            'creator_id': creator_id,
            'team_id': team_id,
            'status': 0,
            'win_probability': stage.win_probability
        }
        
        # 4. 计算单价
        unit_price = pricing_service.calculate_unit_price(
            total_amount=obj_in.total_amount,
            user_count=obj_in.user_count,
            license_type=obj_in.license_type,
            subscription_years=obj_in.subscription_years or 1
        )
        opportunity_data['unit_price'] = float(unit_price)
        
        # 5. 创建商机对象
        db_obj = Opportunity(**opportunity_data)
        db.add(db_obj)
        db.flush()
        
        # 6. 创建初始阶段快照
        snapshot = OpportunityStageSnapshot(
            team_id=team_id,
            opportunity_id=db_obj.id,
            procurement_stage_template_id=stage.id,
            stage_name=stage.stage_name,
            win_probability=stage.win_probability,
            template_sort_order=stage.sort_order,
            template_code=stage.template_code,
            snapshot_version=stage.version,
            entered_at=datetime.now()
        )
        db.add(snapshot)
        db.flush()
        
        # 7. 更新商机的当前阶段信息
        db_obj.current_stage_snapshot_id = snapshot.id
        db_obj.current_stage_name = snapshot.stage_name
        db_obj.current_win_probability = snapshot.win_probability
        db_obj.current_stage_entered_at = snapshot.entered_at
        
        return db_obj

    def log_created(self, db: Session, db_obj: Opportunity, creator_id: str, team_id: int) -> None:
        from app.crud.user import user_crud
        from app.services.operation_log_service import operation_log_service

        operator = user_crud.get_by_id(db, int(creator_id))
        operator_name = operator.name if operator else None

        operation_log_service.log(
            db=db,
            event_type="OPPORTUNITY_CREATED",
            event_action="CREATE",
            resource_type="CUSTOMER",
            resource_id=db_obj.customer_id,
            secondary_resource_type="OPPORTUNITY",
            secondary_resource_id=db_obj.id,
            operator_id=creator_id,
            operator_name=operator_name,
            content={
                "opportunityName": db_obj.opportunity_name,
                "expectedAmount": float(db_obj.total_amount),
                "procurementMethodId": db_obj.procurement_method_id,
                "currentStage": db_obj.current_stage_name,
                "customerId": db_obj.customer_id
            },
            team_id=team_id
        )

    def update(self, db: Session, db_obj: Opportunity, obj_in: OpportunityUpdate) -> Opportunity:
        from app.services.pricing import pricing_service
        from decimal import Decimal
        
        update_data = obj_in.model_dump(exclude_unset=True)
        
        pricing_fields = ['total_amount', 'user_count', 'license_type', 'subscription_years']
        should_recalculate = any(field in update_data for field in pricing_fields)
        
        if should_recalculate:
            total_amount = update_data.get('total_amount', db_obj.total_amount)
            user_count = update_data.get('user_count', db_obj.user_count)
            license_type = update_data.get('license_type', db_obj.license_type)
            subscription_years = update_data.get('subscription_years', db_obj.subscription_years)
            
            unit_price = pricing_service.calculate_unit_price(
                total_amount=float(total_amount),
                user_count=int(user_count),
                license_type=str(license_type),
                subscription_years=int(subscription_years) if subscription_years else 1
            )
            update_data['unit_price'] = float(unit_price)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def move_to_stage(
        self,
        db: Session,
        opportunity_id: int,
        target_stage_template_id: int,
        operator_id: str
    ) -> Opportunity:
        """推进商机到新阶段"""
        from app.crud.procurement import procurement_stage_template_crud
        from app.models.procurement import OpportunityStageSnapshot
        from datetime import datetime
        from app.services.operation_log_service import operation_log_service
        from app.crud.user import user_crud
        
        opportunity = self.get_by_id(db, opportunity_id)
        if not opportunity:
            raise ValueError("商机不存在")
        
        target_stage = procurement_stage_template_crud.get(db, target_stage_template_id)
        if not target_stage:
            raise ValueError("目标阶段不存在")
        
        if target_stage.procurement_method_id != opportunity.procurement_method_id:
            raise ValueError("目标阶段不属于商机的采购方式")
        
        current_snapshot = db.query(OpportunityStageSnapshot).filter(
            OpportunityStageSnapshot.id == opportunity.current_stage_snapshot_id
        ).first()
        
        if current_snapshot:
            current_snapshot.exited_at = datetime.now()

        new_snapshot = OpportunityStageSnapshot(
            team_id=opportunity.team_id,
            opportunity_id=opportunity.id,
            procurement_stage_template_id=target_stage.id,
            stage_name=target_stage.stage_name,
            win_probability=target_stage.win_probability,
            template_sort_order=target_stage.sort_order,
            template_code=target_stage.template_code,
            snapshot_version=target_stage.version,
            entered_at=datetime.now()
        )
        db.add(new_snapshot)
        db.flush()
        
        opportunity.current_stage_snapshot_id = new_snapshot.id
        opportunity.current_stage_name = new_snapshot.stage_name
        opportunity.current_win_probability = new_snapshot.win_probability
        opportunity.current_stage_entered_at = new_snapshot.entered_at
        opportunity.win_probability = new_snapshot.win_probability
        
        db.commit()
        db.refresh(opportunity)
        
        operator = user_crud.get_by_id(db, int(operator_id))
        operator_name = operator.name if operator else None
        
        if target_stage.win_probability == 100:
            from app.schemas.opportunity import OpportunityWin
            from datetime import date as date_type
            
            win_data = OpportunityWin(
                actual_amount=float(opportunity.total_amount),
                actual_closing_date=date_type.today()
            )
            
            opportunity.status = OpportunityStatus.WON.value
            opportunity.actual_amount = win_data.actual_amount
            opportunity.actual_closing_date = win_data.actual_closing_date
            opportunity.win_probability = 100
            
            db.commit()
            db.refresh(opportunity)
            
            operation_log_service.log(
                db=db,
                event_type="OPPORTUNITY_AUTO_WON",
                event_action="AUTO_WIN",
                resource_type="OPPORTUNITY",
                resource_id=opportunity.id,
                operator_id=operator_id,
                operator_name=operator_name,
                content={
                    "opportunityName": opportunity.opportunity_name,
                    "actualAmount": float(opportunity.actual_amount),
                    "actualClosingDate": opportunity.actual_closing_date.isoformat() if opportunity.actual_closing_date else None,
                    "stageName": new_snapshot.stage_name,
                    "autoWon": True,
                    "reason": "推进到100%赢率阶段，自动标记为赢单"
                },
                team_id=opportunity.team_id
            )
        else:
            operation_log_service.log(
                db=db,
                event_type="OPPORTUNITY_STAGE_CHANGED",
                event_action="UPDATE",
                resource_type="OPPORTUNITY",
                resource_id=opportunity.id,
                operator_id=operator_id,
                operator_name=operator_name,
                content={
                    "fromStage": current_snapshot.stage_name if current_snapshot else "初始",
                    "toStage": new_snapshot.stage_name,
                    "winProbability": new_snapshot.win_probability
                },
                team_id=opportunity.team_id
            )

        return opportunity

    def set_procurement_method(
        self,
        db: Session,
        opportunity_id: int,
        procurement_method_id: int,
        operator_id: str
    ) -> Opportunity:
        """设置商机采购方式，自动进入默认起始阶段"""
        from app.crud.procurement import (
            procurement_method_crud,
            procurement_stage_template_crud,
            opportunity_stage_snapshot_crud
        )
        from app.services.operation_log_service import operation_log_service
        from app.crud.user import user_crud

        opportunity = self.get_by_id(db, opportunity_id)
        if not opportunity:
            raise ValueError("商机不存在")

        # 检查是否已有阶段
        existing_snapshot = opportunity_stage_snapshot_crud.get_current(db, opportunity_id)
        if existing_snapshot:
            raise ValueError("商机已有阶段，不能修改采购方式")

        # 检查采购方式是否存在
        procurement_method = procurement_method_crud.get(db, procurement_method_id)
        if not procurement_method:
            raise ValueError(f"采购方式 {procurement_method_id} 不存在")

        # 获取默认起始阶段
        default_stage = procurement_stage_template_crud.get_default_stage(
            db, procurement_method_id
        )
        if not default_stage:
            raise ValueError(f"采购方式 {procurement_method_id} 没有设置默认起始阶段")

        # 创建阶段快照
        new_snapshot = opportunity_stage_snapshot_crud.create(
            db, opportunity_id, default_stage
        )

        # 更新商机
        opportunity.procurement_method_id = procurement_method_id
        opportunity.current_stage_snapshot_id = new_snapshot.id
        opportunity.current_stage_name = new_snapshot.stage_name
        opportunity.current_win_probability = new_snapshot.win_probability
        opportunity.current_stage_entered_at = new_snapshot.entered_at

        db.commit()
        db.refresh(opportunity)

        # 记录操作日志
        operator = user_crud.get_by_id(db, int(operator_id))
        operator_name = operator.name if operator else None

        operation_log_service.log(
            db=db,
            event_type="OPPORTUNITY_SET_PROCUREMENT_METHOD",
            event_action="UPDATE",
            resource_type="OPPORTUNITY",
            resource_id=opportunity.id,
            operator_id=operator_id,
            operator_name=operator_name,
            content={
                "opportunityName": opportunity.opportunity_name,
                "procurementMethodId": procurement_method_id,
                "procurementMethodName": procurement_method.name,
                "defaultStageName": default_stage.stage_name,
                "defaultWinProbability": default_stage.win_probability
            },
            team_id=opportunity.team_id
        )

        return opportunity

    def mark_as_won(
        self,
        db: Session,
        db_obj: Opportunity,
        win_data: OpportunityWin,
        operator_id: str
    ) -> Opportunity:
        from app.crud.user import user_crud
        from app.services.operation_log_service import operation_log_service
        
        if db_obj.status == OpportunityStatus.WON.value:
            raise ValueError("商机已经是赢单状态")
        
        if db_obj.status == OpportunityStatus.LOST.value:
            raise ValueError("商机已输单，无法标记为赢单")
        
        won_stage = db.query(OpportunityStage).filter(
            OpportunityStage.stage_code == 'WON'
        ).first()
        
        if won_stage:
            db_obj.stage_id = won_stage.id
        
        db_obj.status = OpportunityStatus.WON.value
        db_obj.actual_amount = win_data.actual_amount
        db_obj.actual_closing_date = win_data.actual_closing_date
        db_obj.win_probability = 100
        db.commit()
        db.refresh(db_obj)
        
        operator = user_crud.get_by_id(db, int(operator_id))
        operator_name = operator.name if operator else None
        
        customer = db.query(Customer).filter(Customer.id == db_obj.customer_id).first()
        
        operation_log_service.log(
            db=db,
            event_type="OPPORTUNITY_WON",
            event_action="WIN",
            resource_type="CUSTOMER",
            resource_id=db_obj.customer_id,
            secondary_resource_type="OPPORTUNITY",
            secondary_resource_id=db_obj.id,
            operator_id=operator_id,
            operator_name=operator_name,
            content={
                "opportunityName": db_obj.opportunity_name,
                "actualAmount": float(db_obj.actual_amount),
                "actualClosingDate": db_obj.actual_closing_date.isoformat() if db_obj.actual_closing_date else None,
                "customerId": db_obj.customer_id,
                "customerName": customer.account_name if customer else None
            },
            team_id=db_obj.team_id
        )
        
        return db_obj

    def mark_as_lost(
        self,
        db: Session,
        db_obj: Opportunity,
        lose_data: OpportunityLose,
        operator_id: str
    ) -> Opportunity:
        from app.crud.user import user_crud
        from app.services.operation_log_service import operation_log_service
        
        if db_obj.status == OpportunityStatus.LOST.value:
            raise ValueError("商机已经是输单状态")
        
        if db_obj.status == OpportunityStatus.WON.value:
            raise ValueError("商机已赢单，无法标记为输单")
        
        db_obj.status = OpportunityStatus.LOST.value
        db_obj.loss_reason = lose_data.loss_reason
        db_obj.win_probability = 0
        db.commit()
        db.refresh(db_obj)
        
        operator = user_crud.get_by_id(db, int(operator_id))
        operator_name = operator.name if operator else None
        
        customer = db.query(Customer).filter(Customer.id == db_obj.customer_id).first()
        
        operation_log_service.log(
            db=db,
            event_type="OPPORTUNITY_LOST",
            event_action="LOSE",
            resource_type="CUSTOMER",
            resource_id=db_obj.customer_id,
            secondary_resource_type="OPPORTUNITY",
            secondary_resource_id=db_obj.id,
            operator_id=operator_id,
            operator_name=operator_name,
            content={
                "opportunityName": db_obj.opportunity_name,
                "lossReason": db_obj.loss_reason,
                "expectedAmount": float(db_obj.total_amount),
                "customerId": db_obj.customer_id,
                "customerName": customer.account_name if customer else None
            },
            team_id=db_obj.team_id
        )
        
        return db_obj

    def delete(self, db: Session, opportunity_id: int) -> bool:
        """删除商机

        注意：存在关联合同的商机无法删除
        """
        from app.models.contract import Contract

        opportunity = self.get_by_id(db, opportunity_id)
        if not opportunity:
            return False

        # 检查是否存在关联合同
        contracts = db.query(Contract).filter(Contract.opportunity_id == opportunity_id).count()
        if contracts > 0:
            raise ValueError(f"该商机存在 {contracts} 个关联合同，无法删除。请先删除相关合同。")

        db.delete(opportunity)
        db.commit()
        return True

    def get_sales_funnel(
        self,
        db: Session,
        owner_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[dict]:
        query = db.query(
            OpportunityStage.id,
            OpportunityStage.stage_code,
            OpportunityStage.stage_name,
            OpportunityStage.win_probability,
            func.count(Opportunity.id).label('opportunity_count'),
            func.sum(Opportunity.total_amount).label('total_amount'),
            func.avg(Opportunity.total_amount).label('average_amount')
        ).join(
            Opportunity,
            OpportunityStage.id == Opportunity.stage_id
        ).filter(
            Opportunity.status == 0
        )
        
        if owner_id:
            query = query.filter(Opportunity.owner_id == owner_id)
        
        if start_date:
            query = query.filter(Opportunity.expected_closing_date >= start_date)
        
        if end_date:
            query = query.filter(Opportunity.expected_closing_date <= end_date)
        
        results = query.group_by(
            OpportunityStage.id,
            OpportunityStage.stage_code,
            OpportunityStage.stage_name,
            OpportunityStage.win_probability
        ).order_by(OpportunityStage.sort_order).all()
        
        return [
            {
                'stage_id': r.id,
                'stage_code': r.stage_code,
                'stage_name': r.stage_name,
                'win_probability': r.win_probability,
                'opportunity_count': r.opportunity_count or 0,
                'total_amount': float(r.total_amount or 0),
                'average_amount': float(r.average_amount or 0)
            }
            for r in results
        ]

    def get_stage_duration(
        self,
        db: Session,
        owner_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[dict]:
        subquery = db.query(
            Opportunity.id,
            Opportunity.stage_id,
            Opportunity.created_time,
            Opportunity.last_modified_time,
            func.datediff(
                cast(Opportunity.last_modified_time, Integer),
                cast(Opportunity.created_time, Integer)
            ).label('duration_days')
        ).filter(
            Opportunity.status == 0
        )
        
        if owner_id:
            subquery = subquery.filter(Opportunity.owner_id == owner_id)
        
        if start_date:
            subquery = subquery.filter(Opportunity.created_time >= datetime.combine(start_date, datetime.min.time()))
        
        if end_date:
            subquery = subquery.filter(Opportunity.created_time <= datetime.combine(end_date, datetime.max.time()))
        
        subquery = subquery.subquery()
        
        query = db.query(
            OpportunityStage.id,
            OpportunityStage.stage_code,
            OpportunityStage.stage_name,
            func.avg(subquery.c.duration_days).label('average_days'),
            func.min(subquery.c.duration_days).label('min_days'),
            func.max(subquery.c.duration_days).label('max_days'),
            func.count(subquery.c.id).label('opportunity_count')
        ).join(
            OpportunityStage,
            OpportunityStage.id == subquery.c.stage_id
        ).group_by(
            OpportunityStage.id,
            OpportunityStage.stage_code,
            OpportunityStage.stage_name
        ).order_by(OpportunityStage.sort_order)
        
        results = query.all()
        
        return [
            {
                'stage_id': r.id,
                'stage_code': r.stage_code,
                'stage_name': r.stage_name,
                'average_days': float(r.average_days or 0),
                'min_days': float(r.min_days or 0),
                'max_days': float(r.max_days or 0),
                'opportunity_count': r.opportunity_count or 0
            }
            for r in results
        ]
    
    def get_available_for_contract(
        self,
        db: Session,
        customer_id: int,
        team_id: Optional[int] = None
    ) -> List[Opportunity]:
        """
        获取客户可创建合同的商机列表

        业务规则：
        - 只返回"已赢单"（status=1）的商机
        - 只返回审批已通过（approval_phase=approved）的商机
        - 排除已经创建合同的商机
        - 不需要分页，返回所有符合条件的商机

        参数：
        - customer_id: 客户ID（必填）
        - team_id: 团队ID（可选，用于团队过滤）
        """
        from app.models.contract import Contract

        query = db.query(Opportunity).filter(
            Opportunity.customer_id == customer_id,
            Opportunity.status == 1,  # 已赢单
            Opportunity.approval_phase == "approved",
        )

        if team_id is not None:
            query = query.filter(Opportunity.team_id == team_id)
        
        # 排除已经创建合同的商机
        opportunity_ids_with_contract = db.query(
            Contract.opportunity_id
        ).filter(
            Contract.opportunity_id.isnot(None)
        ).all()
        
        contract_opportunity_ids = {opp.opportunity_id for opp in opportunity_ids_with_contract}
        
        if contract_opportunity_ids:
            query = query.filter(Opportunity.id.not_in(contract_opportunity_ids))
        
        opportunities = query.order_by(Opportunity.created_time.desc()).all()
        
        return opportunities

opportunity_stage_crud = OpportunityStageCRUD()
opportunity_crud = OpportunityCRUD()
