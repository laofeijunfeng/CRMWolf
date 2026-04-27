"""
Service 示例 - 类型安全实现

Description: 展示如何按照规范实现类型安全的 Python Service
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from app.crud.customer import CustomerCRUD
from app.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse
from app.core.exceptions import NotFoundException, ConflictException
from app.models.customer import Customer


class CustomerService:
    """客户服务示例"""

    @staticmethod
    def get_list(
        db: Session,
        skip: int = 0,
        limit: int = 20,
        owner_id: Optional[str] = None
    ) -> tuple[List[CustomerResponse], int]:
        """
        获取客户列表

        Args:
            db: 数据库会话
            skip: 跳过数量
            limit: 返回数量
            owner_id: 负责人 ID（可选）

        Returns:
            tuple: (客户列表, 总数)
        """
        customers, total = CustomerCRUD.get_multi(
            db,
            skip=skip,
            limit=limit,
            owner_id=owner_id
        )

        # 转换为响应 Schema
        return [
            CustomerResponse.model_validate(c) for c in customers
        ], total

    @staticmethod
    def get_by_id(db: Session, customer_id: int) -> CustomerResponse:
        """
        根据 ID 获取客户

        Args:
            db: 数据库会话
            customer_id: 客户 ID

        Returns:
            CustomerResponse: 客户详情

        Raises:
            NotFoundException: 客户不存在
        """
        customer = CustomerCRUD.get(db, id=customer_id)

        if customer is None:
            raise NotFoundException(f"客户 {customer_id} 不存在")

        return CustomerResponse.model_validate(customer)

    @staticmethod
    def create(
        db: Session,
        data: CustomerCreate,
        creator_id: str
    ) -> CustomerResponse:
        """
        创建客户

        Args:
            db: 数据库会话
            data: 创建数据
            creator_id: 创建人 ID

        Returns:
            CustomerResponse: 创建的客户

        Raises:
            ConflictException: 客户名称已存在
        """
        # 检查名称是否已存在
        existing = CustomerCRUD.get_by_name(db, name=data.account_name)
        if existing:
            raise ConflictException(f"客户名称 '{data.account_name}' 已存在")

        # 创建客户
        customer = CustomerCRUD.create_with_owner(
            db,
            obj_in=data,
            owner_id=creator_id,
            creator_id=creator_id
        )

        return CustomerResponse.model_validate(customer)

    @staticmethod
    def update(
        db: Session,
        customer_id: int,
        data: CustomerUpdate
    ) -> CustomerResponse:
        """
        更新客户

        Args:
            db: 数据库会话
            customer_id: 客户 ID
            data: 更新数据

        Returns:
            CustomerResponse: 更新后的客户

        Raises:
            NotFoundException: 客户不存在
        """
        customer = CustomerCRUD.get(db, id=customer_id)

        if customer is None:
            raise NotFoundException(f"客户 {customer_id} 不存在")

        updated = CustomerCRUD.update(db, db_obj=customer, obj_in=data)

        return CustomerResponse.model_validate(updated)


# ===== 错误示例（禁止） =====

"""
❌ 禁止示例 1：函数参数无类型注解

# 错误
def get_list(db, skip=0, limit=20):
    ...

# 正确
def get_list(db: Session, skip: int = 0, limit: int = 20) -> tuple[List[CustomerResponse], int]:
    ...
"""

"""
❌ 禁止示例 2：返回值无类型注解

# 错误
def get_by_id(db: Session, customer_id: int):
    return customer

# 正确
def get_by_id(db: Session, customer_id: int) -> CustomerResponse:
    return CustomerResponse.model_validate(customer)
"""

"""
❌ 禁止示例 3：使用裸 dict

# 错误
def create(db: Session, data: dict) -> dict:
    ...

# 正确：使用 Pydantic Schema
def create(db: Session, data: CustomerCreate) -> CustomerResponse:
    ...
"""

"""
❌ 禁止示例 4：跨层调用（Service 调用 API）

# 错误
from app.api.customers import router  # 跨层导入

# 正确：Service 只依赖 CRUD 和 Schema
from app.crud.customer import CustomerCRUD
from app.schemas.customer import CustomerCreate
"""