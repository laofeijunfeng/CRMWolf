
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateRecordError
from app.crud.child_dedupe import persist_guarding_duplicate
from app.models.deployment import DeploymentInfo
from app.schemas.deployment import DeploymentInfoInternalCreate, DeploymentInfoUpdate
from app.utils.dedupe_normalizer import server_address_dedupe_key


class DeploymentInfoCRUD:
    """部署信息 CRUD 操作类"""

    @staticmethod
    def find_duplicate(
        db: Session, *, customer_id: int, team_id: int, server_address: str | None, exclude_id: int | None = None
    ) -> DuplicateRecordError | None:
        """Return the error for an existing deployment of this customer with the same normalized address."""
        key = server_address_dedupe_key(server_address)
        if key is None:
            return None
        query = db.query(DeploymentInfo.id, DeploymentInfo.deployment_name).filter(
            DeploymentInfo.team_id == team_id,
            DeploymentInfo.customer_id == customer_id,
            DeploymentInfo.server_address_dedupe_key == key,
        )
        if exclude_id is not None:
            query = query.filter(DeploymentInfo.id != exclude_id)
        existing = query.order_by(DeploymentInfo.id).first()
        if existing is None:
            return None
        return DuplicateRecordError(
            entity="deployment_info",
            existing_id=existing.id,
            existing_name=existing.deployment_name,
            detail=f"该客户下已有这个服务器地址的部署信息：{existing.deployment_name}",  # noqa: RUF001
        )

    def create(
        self,
        db: Session,
        team_id: int,
        obj_in: DeploymentInfoInternalCreate,
        *,
        commit: bool = True,
    ) -> DeploymentInfo:
        """
        创建部署信息

        Args:
            db: 数据库会话
            team_id: 团队ID
            obj_in: 创建请求数据

        Returns:
            DeploymentInfo: 创建的部署信息
        """
        deployment_data = obj_in.model_dump()
        customer_id = deployment_data['customer_id']
        server_address = deployment_data['server_address']

        def find_duplicate() -> DuplicateRecordError | None:
            return self.find_duplicate(db, customer_id=customer_id, team_id=team_id, server_address=server_address)

        duplicate = find_duplicate()
        if duplicate is not None:
            raise duplicate

        # 如果设置为默认部署,先清除该客户的其他默认部署
        if deployment_data.get('is_default', False):
            db.query(DeploymentInfo).filter(
                DeploymentInfo.team_id == team_id,
                DeploymentInfo.customer_id == deployment_data['customer_id'],
                DeploymentInfo.is_default == True
            ).update({'is_default': False})

        db_obj = DeploymentInfo(
            team_id=team_id,
            **deployment_data
        )
        db.add(db_obj)
        persist_guarding_duplicate(db, commit=commit, find_duplicate=find_duplicate)
        if commit:
            db.refresh(db_obj)
        return db_obj

    def get(
        self,
        db: Session,
        team_id: int,
        deployment_id: int
    ) -> DeploymentInfo | None:
        """
        获取单个部署信息

        Args:
            db: 数据库会话
            team_id: 团队ID
            deployment_id: 部署信息ID

        Returns:
            Optional[DeploymentInfo]: 部署信息，不存在则返回 None
        """
        return db.query(DeploymentInfo).filter(
            DeploymentInfo.id == deployment_id,
            DeploymentInfo.team_id == team_id
        ).first()

    def get_by_customer(
        self,
        db: Session,
        team_id: int,
        customer_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[list[DeploymentInfo], int]:
        """
        获取客户的部署信息列表

        Args:
            db: 数据库会话
            team_id: 团队ID
            customer_id: 客户ID
            skip: 跳过记录数
            limit: 返回记录数上限

        Returns:
            Tuple[List[DeploymentInfo], int]: 部署信息列表和总数
        """
        query = db.query(DeploymentInfo).filter(
            DeploymentInfo.team_id == team_id,
            DeploymentInfo.customer_id == customer_id
        )

        total = query.count()
        deployments = query.order_by(
            DeploymentInfo.is_default.desc(),
            DeploymentInfo.created_time.desc()
        ).offset(skip).limit(limit).all()

        return deployments, total

    def update(
        self,
        db: Session,
        team_id: int,
        deployment_id: int,
        obj_in: DeploymentInfoUpdate
    ) -> DeploymentInfo | None:
        """
        更新部署信息

        Args:
            db: 数据库会话
            team_id: 团队ID
            deployment_id: 部署信息ID
            obj_in: 更新请求数据

        Returns:
            Optional[DeploymentInfo]: 更新后的部署信息，不存在则返回 None
        """
        deployment = self.get(db, team_id, deployment_id)
        if not deployment:
            return None

        update_data = obj_in.model_dump(exclude_unset=True)
        customer_id = int(deployment.customer_id)
        server_address = update_data.get('server_address')
        check_address = (
            server_address is not None
            and server_address_dedupe_key(server_address) != deployment.server_address_dedupe_key
        )

        def find_duplicate() -> DuplicateRecordError | None:
            if not check_address:
                return None
            return self.find_duplicate(
                db, customer_id=customer_id, team_id=team_id, server_address=server_address, exclude_id=deployment_id
            )

        duplicate = find_duplicate()
        if duplicate is not None:
            raise duplicate

        # 如果设置为默认部署,先清除该客户的其他默认部署
        if update_data.get('is_default') is True:
            db.query(DeploymentInfo).filter(
                DeploymentInfo.team_id == team_id,
                DeploymentInfo.customer_id == deployment.customer_id,
                DeploymentInfo.id != deployment_id,
                DeploymentInfo.is_default == True
            ).update({'is_default': False})

        for field, value in update_data.items():
            setattr(deployment, field, value)

        persist_guarding_duplicate(db, commit=True, find_duplicate=find_duplicate)
        db.refresh(deployment)
        return deployment

    def delete(
        self,
        db: Session,
        team_id: int,
        deployment_id: int
    ) -> bool:
        """
        删除部署信息（硬删除）

        Args:
            db: 数据库会话
            team_id: 团队ID
            deployment_id: 部署信息ID

        Returns:
            bool: 是否成功删除
        """
        deployment = self.get(db, team_id, deployment_id)
        if not deployment:
            return False

        db.delete(deployment)
        db.commit()
        return True

    def set_default(
        self,
        db: Session,
        team_id: int,
        customer_id: int,
        deployment_id: int
    ) -> DeploymentInfo | None:
        """
        设置默认部署

        Args:
            db: 数据库会话
            team_id: 团队ID
            customer_id: 客户ID
            deployment_id: 部署信息ID

        Returns:
            Optional[DeploymentInfo]: 更新后的部署信息，不存在则返回 None
        """
        deployment = self.get(db, team_id, deployment_id)
        if not deployment:
            return None

        # 验证部署信息属于该客户
        if deployment.customer_id != customer_id:
            return None

        # 清除该客户的其他默认部署
        db.query(DeploymentInfo).filter(
            DeploymentInfo.team_id == team_id,
            DeploymentInfo.customer_id == customer_id,
            DeploymentInfo.is_default == True
        ).update({'is_default': False})

        # 设置当前部署为默认
        deployment.is_default = True
        db.commit()
        db.refresh(deployment)
        return deployment

    def get_default(
        self,
        db: Session,
        team_id: int,
        customer_id: int
    ) -> DeploymentInfo | None:
        """
        获取客户的默认部署信息

        Args:
            db: 数据库会话
            team_id: 团队ID
            customer_id: 客户ID

        Returns:
            Optional[DeploymentInfo]: 默认部署信息，不存在则返回 None
        """
        return db.query(DeploymentInfo).filter(
            DeploymentInfo.team_id == team_id,
            DeploymentInfo.customer_id == customer_id,
            DeploymentInfo.is_default == True
        ).first()


# 创建全局实例
deployment_info_crud = DeploymentInfoCRUD()

# 独立函数导出(供 API 直接导入)
def create_deployment_info(db: Session, team_id: int, obj_in: DeploymentInfoInternalCreate) -> DeploymentInfo:
    return deployment_info_crud.create(db, team_id, obj_in)

def get_deployment_info(db: Session, team_id: int, deployment_id: int) -> DeploymentInfo | None:
    return deployment_info_crud.get(db, team_id, deployment_id)

def get_deployment_infos_by_customer(db: Session, team_id: int, customer_id: int) -> list[DeploymentInfo]:
    deployments, _ = deployment_info_crud.get_by_customer(db, team_id, customer_id)
    return deployments


def update_deployment_info(
    db: Session, team_id: int, deployment_id: int, obj_in: DeploymentInfoUpdate
) -> DeploymentInfo | None:
    return deployment_info_crud.update(db, team_id, deployment_id, obj_in)

def delete_deployment_info(db: Session, team_id: int, deployment_id: int) -> bool:
    return deployment_info_crud.delete(db, team_id, deployment_id)

def set_default_deployment_info(
    db: Session,
    team_id: int,
    customer_id: int,
    deployment_id: int,
) -> DeploymentInfo | None:
    return deployment_info_crud.set_default(db, team_id, customer_id, deployment_id)
