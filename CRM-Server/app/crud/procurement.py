from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Tuple
from datetime import datetime
import json

from app.models.procurement import (
    ProcurementMethod, ProcurementStageTemplate, 
    OpportunityStageSnapshot, StageTemplateChangeLog
)
from app.schemas.procurement import (
    ProcurementMethodCreate, ProcurementMethodUpdate,
    ProcurementStageTemplateCreate, ProcurementStageTemplateUpdate,
    AdvanceStageRequest
)


class ProcurementMethodCRUD:
    """采购方式 CRUD 操作"""

    def get(self, db: Session, id: int) -> Optional[ProcurementMethod]:
        """根据ID获取采购方式"""
        return db.query(ProcurementMethod).filter(ProcurementMethod.id == id).first()

    def get_by_code(self, db: Session, code: str, team_id: Optional[int] = None) -> Optional[ProcurementMethod]:
        """根据编码获取采购方式"""
        query = db.query(ProcurementMethod).filter(ProcurementMethod.code == code)
        if team_id is not None:
            query = query.filter(ProcurementMethod.team_id == team_id)
        return query.first()

    def get_multi(
        self,
        db: Session,
        team_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[int] = None
    ) -> Tuple[List[ProcurementMethod], int]:
        """获取采购方式列表"""
        query = db.query(ProcurementMethod)

        if team_id is not None:
            query = query.filter(ProcurementMethod.team_id == team_id)
        if is_active is not None:
            query = query.filter(ProcurementMethod.is_active == is_active)

        total = query.count()
        items = query.order_by(ProcurementMethod.sort_order).offset(skip).limit(limit).all()

        return items, total

    def create(self, db: Session, obj_in: ProcurementMethodCreate, creator_id: str, team_id: int) -> ProcurementMethod:
        """创建采购方式"""
        # 校验code唯一性（在同一团队内）
        existing = self.get_by_code(db, obj_in.code, team_id)
        if existing:
            raise ValueError(f"采购方式编码 {obj_in.code} 已存在")

        db_obj = ProcurementMethod(
            **obj_in.model_dump(),
            created_by=creator_id,
            team_id=team_id
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(
        self, 
        db: Session, 
        db_obj: ProcurementMethod, 
        obj_in: ProcurementMethodUpdate,
        updater_id: str
    ) -> ProcurementMethod:
        """更新采购方式"""
        # 停用前校验是否有活跃商机
        if obj_in.is_active is not None and obj_in.is_active == 0:
            from app.crud.procurement import procurement_stage_template_crud
            active_count = procurement_stage_template_crud.count_active_opportunities(
                db, db_obj.id
            )
            if active_count > 0:
                raise ValueError(f"该采购方式下还有 {active_count} 个活跃商机，不能停用")
        
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db_obj.updated_by = updater_id
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, id: int) -> bool:
        """删除采购方式（逻辑删除）"""
        obj = self.get(db, id)
        if not obj:
            return False
        
        # 校验是否有使用此方式的商机
        from app.crud.procurement import procurement_stage_template_crud
        active_count = procurement_stage_template_crud.count_active_opportunities(db, id)
        if active_count > 0:
            raise ValueError(f"该采购方式下还有 {active_count} 个商机，不能删除")
        
        db.delete(obj)
        db.commit()
        return True


class ProcurementStageTemplateCRUD:
    """采购阶段模板 CRUD 操作"""

    def get(self, db: Session, id: int) -> Optional[ProcurementStageTemplate]:
        """根据ID获取阶段模板"""
        return db.query(ProcurementStageTemplate).filter(ProcurementStageTemplate.id == id).first()

    def get_by_method(
        self,
        db: Session,
        method_id: int,
        team_id: Optional[int] = None
    ) -> List[ProcurementStageTemplate]:
        """获取采购方式下的所有阶段模板"""
        query = db.query(ProcurementStageTemplate).filter(
            ProcurementStageTemplate.procurement_method_id == method_id
        )
        if team_id is not None:
            query = query.filter(ProcurementStageTemplate.team_id == team_id)
        return query.order_by(ProcurementStageTemplate.sort_order).all()

    def get_default_stage(
        self,
        db: Session,
        method_id: int,
        team_id: Optional[int] = None
    ) -> Optional[ProcurementStageTemplate]:
        """获取采购方式的默认起始阶段"""
        query = db.query(ProcurementStageTemplate).filter(
            ProcurementStageTemplate.procurement_method_id == method_id,
            ProcurementStageTemplate.is_default_start == 1
        )
        if team_id is not None:
            query = query.filter(ProcurementStageTemplate.team_id == team_id)
        return query.first()
    
    def create(
        self,
        db: Session,
        obj_in: ProcurementStageTemplateCreate,
        creator_id: str,
        team_id: Optional[int] = None
    ) -> ProcurementStageTemplate:
        """创建阶段模板"""
        # 校验同一方式下template_code唯一性
        query = db.query(ProcurementStageTemplate).filter(
            ProcurementStageTemplate.procurement_method_id == obj_in.procurement_method_id,
            ProcurementStageTemplate.template_code == obj_in.template_code
        )
        if team_id is not None:
            query = query.filter(ProcurementStageTemplate.team_id == team_id)
        existing = query.first()

        if existing:
            raise ValueError(f"阶段编码 {obj_in.template_code} 已存在")

        # 校验默认起始阶段唯一性
        if obj_in.is_default_start == 1:
            query = db.query(ProcurementStageTemplate).filter(
                ProcurementStageTemplate.procurement_method_id == obj_in.procurement_method_id,
                ProcurementStageTemplate.is_default_start == 1
            )
            if team_id is not None:
                query = query.filter(ProcurementStageTemplate.team_id == team_id)
            existing_default = query.first()

            if existing_default:
                raise ValueError("每个采购方式下只能有一个默认起始阶段")

        db_obj = ProcurementStageTemplate(
            **obj_in.model_dump(),
            created_by=creator_id,
            version=1,
            version_lock=0,
            team_id=team_id
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        
        # 记录创建日志 - 构造字典而不是传入SQLAlchemy对象
        new_data = {
            "stage_name": db_obj.stage_name,
            "win_probability": db_obj.win_probability,
            "sort_order": db_obj.sort_order,
            "is_default_start": db_obj.is_default_start,
            "can_skip": db_obj.can_skip,
            "description": db_obj.description
        }
        self._log_change(
            db, db_obj.id, "CREATE", 
            None, new_data, creator_id, "创建阶段模板"
        )
        
        return db_obj
    
    def update(
        self, 
        db: Session, 
        db_obj: ProcurementStageTemplate, 
        obj_in: ProcurementStageTemplateUpdate,
        updater_id: str,
        reason: Optional[str] = None
    ) -> ProcurementStageTemplate:
        """更新阶段模板"""
        # 乐观锁校验
        if db_obj.version_lock != obj_in.version_lock:
            raise ValueError("数据已被其他人修改，请刷新后重试")
        
        # 记录变更前的数据
        old_data = {
            "template_code": db_obj.template_code,
            "stage_name": db_obj.stage_name,
            "win_probability": db_obj.win_probability,
            "sort_order": db_obj.sort_order,
            "is_default_start": db_obj.is_default_start,
            "can_skip": db_obj.can_skip,
            "description": db_obj.description
        }
        
        # 校验 template_code 唯一性（如果修改了编码）
        if obj_in.template_code is not None and obj_in.template_code != db_obj.template_code:
            existing = db.query(ProcurementStageTemplate).filter(
                ProcurementStageTemplate.procurement_method_id == db_obj.procurement_method_id,
                ProcurementStageTemplate.template_code == obj_in.template_code,
                ProcurementStageTemplate.id != db_obj.id
            ).first()
            
            if existing:
                raise ValueError(f"阶段编码 {obj_in.template_code} 已存在")
        
        # 校验默认起始阶段唯一性
        if obj_in.is_default_start is not None and obj_in.is_default_start == 1:
            if db_obj.is_default_start != 1:
                existing_default = db.query(ProcurementStageTemplate).filter(
                    ProcurementStageTemplate.procurement_method_id == db_obj.procurement_method_id,
                    ProcurementStageTemplate.is_default_start == 1,
                    ProcurementStageTemplate.id != db_obj.id
                ).first()
                
                if existing_default:
                    raise ValueError("每个采购方式下只能有一个默认起始阶段")
        
        # 更新字段
        update_data = obj_in.model_dump(exclude_unset=True, exclude={"version_lock"})
        for field, value in update_data.items():
            if field != "version_lock":
                setattr(db_obj, field, value)
        
        db_obj.version += 1
        db_obj.version_lock += 1
        db_obj.updated_by = updater_id
        
        db.commit()
        db.refresh(db_obj)
        
        # 记录变更日志
        new_data = {
            "template_code": db_obj.template_code,
            "stage_name": db_obj.stage_name,
            "win_probability": db_obj.win_probability,
            "sort_order": db_obj.sort_order,
            "is_default_start": db_obj.is_default_start,
            "can_skip": db_obj.can_skip,
            "description": db_obj.description
        }
        
        self._log_change(
            db, db_obj.id, "UPDATE",
            old_data, new_data, updater_id, reason
        )
        
        return db_obj
    
    def delete(self, db: Session, id: int) -> bool:
        """删除阶段模板（逻辑删除）"""
        obj = self.get(db, id)
        if not obj:
            return False
        
        # 校验是否被商机使用
        used_count = db.query(OpportunityStageSnapshot).filter(
            OpportunityStageSnapshot.procurement_stage_template_id == id,
            OpportunityStageSnapshot.exited_at == None
        ).count()
        
        if used_count > 0:
            raise ValueError(f"该阶段正在被 {used_count} 个商机使用，不能删除")
        
        # 记录删除日志
        old_data = {
            "stage_name": obj.stage_name,
            "win_probability": obj.win_probability,
            "sort_order": obj.sort_order
        }
        
        self._log_change(
            db, id, "DELETE",
            old_data, None, "system", "删除阶段模板"
        )
        
        db.delete(obj)
        db.commit()
        return True
    
    def _log_change(
        self,
        db: Session,
        template_id: int,
        change_type: str,
        old_data: Optional[dict],
        new_data: Optional[dict],
        changed_by: str,
        reason: Optional[str]
    ):
        """记录阶段模板变更日志"""
        log = StageTemplateChangeLog(
            template_id=template_id,
            change_type=change_type,
            old_data=json.dumps(old_data) if old_data else None,
            new_data=json.dumps(new_data) if new_data else None,
            changed_by=changed_by,
            reason=reason
        )
        db.add(log)
    
    def count_active_opportunities(self, db: Session, method_id: int) -> int:
        """统计使用某采购方式的活跃商机数量"""
        from app.models.opportunity import Opportunity
        
        return db.query(Opportunity).filter(
            Opportunity.procurement_method_id == method_id,
            Opportunity.status == 0  # 0: 跟进中
        ).count()
    
    def get_change_logs(
        self, 
        db: Session, 
        template_id: int
    ) -> List[StageTemplateChangeLog]:
        """获取阶段模板的变更日志"""
        return db.query(StageTemplateChangeLog).filter(
            StageTemplateChangeLog.template_id == template_id
        ).order_by(StageTemplateChangeLog.changed_at.desc()).all()


class OpportunityStageSnapshotCRUD:
    """商机阶段快照 CRUD 操作"""
    
    def get_current(self, db: Session, opportunity_id: int) -> Optional[OpportunityStageSnapshot]:
        """获取商机当前阶段快照"""
        return db.query(OpportunityStageSnapshot).filter(
            OpportunityStageSnapshot.opportunity_id == opportunity_id,
            OpportunityStageSnapshot.exited_at == None
        ).first()
    
    def get_history(
        self, 
        db: Session, 
        opportunity_id: int
    ) -> List[OpportunityStageSnapshot]:
        """获取商机阶段历史"""
        return db.query(OpportunityStageSnapshot).filter(
            OpportunityStageSnapshot.opportunity_id == opportunity_id
        ).order_by(OpportunityStageSnapshot.entered_at.desc()).all()
    
    def create(
        self,
        db: Session,
        opportunity_id: int,
        stage_template: ProcurementStageTemplate
    ) -> OpportunityStageSnapshot:
        """创建阶段快照"""
        snapshot = OpportunityStageSnapshot(
            opportunity_id=opportunity_id,
            procurement_stage_template_id=stage_template.id,
            stage_name=stage_template.stage_name,
            win_probability=stage_template.win_probability,
            template_sort_order=stage_template.sort_order,
            template_code=stage_template.template_code,
            snapshot_version=stage_template.version
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return snapshot
    
    def advance_stage(
        self,
        db: Session,
        opportunity_id: int,
        target_stage_template: ProcurementStageTemplate,
        updater_id: str
    ) -> OpportunityStageSnapshot:
        """推进商机到下一阶段"""
        # 获取当前阶段快照
        current = self.get_current(db, opportunity_id)
        if not current:
            raise ValueError("商机没有当前阶段")
        
        # 校验阶段顺序
        if target_stage_template.procurement_method_id != current.procurement_stage_template.procurement_method.procurement_method_id:
            raise ValueError("不能切换到不同采购方式的阶段")
        
        if target_stage_template.sort_order <= current.template_sort_order:
            # 目标阶段不能跳过，则不允许
            if target_stage_template.can_skip != 1:
                raise ValueError("只能向前推进阶段，或跳过允许跳过的阶段")
        
        # 结束当前快照
        current.exited_at = datetime.utcnow()
        
        # 创建新阶段快照
        new_snapshot = self.create(
            db, opportunity_id, target_stage_template
        )
        
        return new_snapshot
    
    def get_available_stages(
        self,
        db: Session,
        opportunity_id: int
    ) -> List[ProcurementStageTemplate]:
        """获取商机可推进到的阶段列表"""
        current = self.get_current(db, opportunity_id)
        if not current:
            return []
        
        method_id = current.procurement_stage_template.procurement_method.procurement_method_id
        
        # 获取该采购方式下所有在当前阶段之后的阶段
        stages = db.query(ProcurementStageTemplate).filter(
            ProcurementStageTemplate.procurement_method_id == method_id,
            ProcurementStageTemplate.sort_order > current.template_sort_order
        ).order_by(ProcurementStageTemplate.sort_order).all()
        
        # 加上可跳过的阶段
        skippable = db.query(ProcurementStageTemplate).filter(
            ProcurementStageTemplate.procurement_method_id == method_id,
            ProcurementStageTemplate.can_skip == 1,
            ProcurementStageTemplate.sort_order != current.template_sort_order
        ).all()
        
        return list(set(stages + skippable))


class ProcurementManagementToolCRUD:
    """采购管理工具 CRUD 操作"""
    
    def assess_template_change_impact(
        self,
        db: Session,
        template_id: int,
        team_id: int
    ) -> dict:
        """评估阶段模板变更的影响

        返回受影响的商机列表
        """
        # 获取阶段模板并验证团队归属
        template = db.query(ProcurementStageTemplate).filter(
            ProcurementStageTemplate.id == template_id,
            ProcurementStageTemplate.team_id == team_id
        ).first()

        if not template:
            raise ValueError(f"阶段模板不存在或不属于当前团队")

        # 查找使用该阶段的活跃商机（限制在当前团队）
        from app.models.opportunity import Opportunity

        active_opportunities = db.query(Opportunity).filter(
            Opportunity.procurement_method_id == template.procurement_method_id,
            Opportunity.team_id == team_id,
            Opportunity.current_stage_snapshot_id == db.query(OpportunityStageSnapshot.id).filter(
                OpportunityStageSnapshot.procurement_stage_template_id == template_id,
                OpportunityStageSnapshot.exited_at == None
            ).subquery()
        ).all()
        
        return {
            "template_id": template_id,
            "template_name": template.stage_name,
            "affected_count": len(active_opportunities),
            "active_opportunities": [
                {
                    "id": opp.id,
                    "opportunity_name": opp.opportunity_name,
                    "customer_id": opp.customer_id,
                    "current_stage": opp.current_stage_name
                }
                for opp in active_opportunities
            ]
        }
    
    def batch_migrate_procurement_method(
        self,
        db: Session,
        source_method_id: int,
        target_method_id: int,
        opportunity_ids: Optional[List[int]] = None,
        operator_id: str = None,
        team_id: int = None
    ) -> dict:
        """批量迁移商机到新采购方式

        Args:
            db: 数据库会话
            source_method_id: 源采购方式ID
            target_method_id: 目标采购方式ID
            opportunity_ids: 要迁移的商机ID列表，为空则迁移所有使用源方式的商机
            operator_id: 操作人ID
            team_id: 团队ID

        Returns:
            迁移结果统计
        """
        # 获取源和目标采购方式（验证团队归属）
        source_method = db.query(ProcurementMethod).filter(
            ProcurementMethod.id == source_method_id,
            ProcurementMethod.team_id == team_id
        ).first()

        target_method = db.query(ProcurementMethod).filter(
            ProcurementMethod.id == target_method_id,
            ProcurementMethod.team_id == team_id
        ).first()

        if not source_method:
            raise ValueError(f"源采购方式不存在或不属于当前团队")
        if not target_method:
            raise ValueError(f"目标采购方式不存在或不属于当前团队")

        # 获取目标采购方式的默认起始阶段
        default_stage = db.query(ProcurementStageTemplate).filter(
            ProcurementStageTemplate.procurement_method_id == target_method_id,
            ProcurementStageTemplate.team_id == team_id,
            ProcurementStageTemplate.is_default_start == 1
        ).first()

        if not default_stage:
            raise ValueError(f"目标采购方式没有设置默认起始阶段")

        # 查询要迁移的商机（限制在当前团队）
        from app.models.opportunity import Opportunity

        query = db.query(Opportunity).filter(
            Opportunity.procurement_method_id == source_method_id,
            Opportunity.team_id == team_id,
            Opportunity.status == 0  # 只迁移跟进中的商机
        )

        if opportunity_ids:
            query = query.filter(Opportunity.id.in_(opportunity_ids))
        
        opportunities = query.all()
        
        migrated_count = 0
        failed_count = 0
        errors = []
        
        for opp in opportunities:
            try:
                # 结束当前阶段快照
                current_snapshot = db.query(OpportunityStageSnapshot).filter(
                    OpportunityStageSnapshot.opportunity_id == opp.id,
                    OpportunityStageSnapshot.exited_at == None
                ).first()
                
                if current_snapshot:
                    current_snapshot.exited_at = datetime.utcnow()
                
                # 创建新的阶段快照
                new_snapshot = OpportunityStageSnapshot(
                    opportunity_id=opp.id,
                    procurement_stage_template_id=default_stage.id,
                    stage_name=default_stage.stage_name,
                    win_probability=default_stage.win_probability,
                    template_sort_order=default_stage.sort_order,
                    template_code=default_stage.template_code,
                    snapshot_version=default_stage.version,
                    team_id=team_id
                )
                db.add(new_snapshot)
                db.flush()
                
                # 更新商机信息
                opp.procurement_method_id = target_method_id
                opp.current_stage_snapshot_id = new_snapshot.id
                opp.current_stage_name = new_snapshot.stage_name
                opp.current_win_probability = new_snapshot.win_probability
                opp.current_stage_entered_at = new_snapshot.entered_at
                
                migrated_count += 1
                
            except Exception as e:
                failed_count += 1
                errors.append({
                    "opportunity_id": opp.id,
                    "error": str(e)
                })
        
        db.commit()
        
        return {
            "total": len(opportunities),
            "migrated": migrated_count,
            "failed": failed_count,
            "errors": errors
        }
    
    def rollback_template_version(
        self,
        db: Session,
        template_id: int,
        target_version: int,
        operator_id: str,
        reason: Optional[str] = None,
        team_id: int = None
    ) -> ProcurementStageTemplate:
        """回滚阶段模板到指定版本

        Args:
            db: 数据库会话
            template_id: 阶段模板ID
            target_version: 目标版本号
            operator_id: 操作人ID
            reason: 回滚原因
            team_id: 团队ID

        Returns:
            回滚后的阶段模板对象
        """
        # 获取当前模板并验证团队归属
        template = db.query(ProcurementStageTemplate).filter(
            ProcurementStageTemplate.id == template_id,
            ProcurementStageTemplate.team_id == team_id
        ).first()

        if not template:
            raise ValueError(f"阶段模板不存在或不属于当前团队")
        
        if template.version == target_version:
            raise ValueError(f"当前版本已经是 {target_version}，无需回滚")
        
        # 查找目标版本的变更日志
        log = db.query(StageTemplateChangeLog).filter(
            StageTemplateChangeLog.template_id == template_id,
            StageTemplateChangeLog.change_type == "UPDATE"
        ).order_by(StageTemplateChangeLog.changed_at.desc()).first()
        
        if not log:
            raise ValueError("没有找到变更历史记录，无法回滚")
        
        # 解析旧数据
        import json
        old_data = json.loads(log.old_data) if log.old_data else None
        
        if not old_data:
            raise ValueError("无法获取历史数据")
        
        # 记录当前状态（用于回滚的变更日志）
        current_data = {
            "stage_name": template.stage_name,
            "win_probability": template.win_probability,
            "sort_order": template.sort_order,
            "is_default_start": template.is_default_start,
            "can_skip": template.can_skip,
            "description": template.description
        }
        
        # 恢复到目标版本的数据
        template.stage_name = old_data.get("stage_name", template.stage_name)
        template.win_probability = old_data.get("win_probability", template.win_probability)
        template.sort_order = old_data.get("sort_order", template.sort_order)
        template.is_default_start = old_data.get("is_default_start", template.is_default_start)
        template.can_skip = old_data.get("can_skip", template.can_skip)
        template.description = old_data.get("description", template.description)
        
        # 更新版本信息
        template.version += 1
        template.version_lock += 1
        template.updated_by = operator_id
        
        # 记录回滚日志
        rollback_log = StageTemplateChangeLog(
            template_id=template_id,
            change_type="ROLLBACK",
            old_data=json.dumps(current_data),
            new_data=json.dumps(old_data),
            changed_by=operator_id,
            reason=reason or f"回滚到版本 {target_version}"
        )
        db.add(rollback_log)
        
        db.commit()
        db.refresh(template)
        
        return template
    
    def get_active_opportunities_by_stage(
        self,
        db: Session,
        stage_template_id: int,
        team_id: int
    ) -> List[dict]:
        """获取使用指定阶段的活跃商机列表"""
        # 验证阶段模板属于当前团队
        template = db.query(ProcurementStageTemplate).filter(
            ProcurementStageTemplate.id == stage_template_id,
            ProcurementStageTemplate.team_id == team_id
        ).first()

        if not template:
            raise ValueError(f"阶段模板不存在或不属于当前团队")

        # 查询当前使用该阶段的商机（限制在当前团队）
        from app.models.opportunity import Opportunity

        opportunities = db.query(Opportunity).filter(
            Opportunity.current_stage_snapshot_id == db.query(OpportunityStageSnapshot.id).filter(
                OpportunityStageSnapshot.procurement_stage_template_id == stage_template_id,
                OpportunityStageSnapshot.exited_at == None
            ).subquery(),
            Opportunity.team_id == team_id,
            Opportunity.status == 0
        ).all()
        
        return [
            {
                "id": opp.id,
                "opportunity_name": opp.opportunity_name,
                "customer_id": opp.customer_id,
                "owner_id": opp.owner_id,
                "current_stage": opp.current_stage_name,
                "win_probability": opp.current_win_probability
            }
            for opp in opportunities
        ]


# 创建全局实例
procurement_method_crud = ProcurementMethodCRUD()
procurement_stage_template_crud = ProcurementStageTemplateCRUD()
opportunity_stage_snapshot_crud = OpportunityStageSnapshotCRUD()
procurement_management_tool_crud = ProcurementManagementToolCRUD()
