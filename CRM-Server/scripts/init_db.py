"""
数据库初始化脚本

仅创建数据库表结构和初始角色。
权限初始化由 app.services.init_service.init_roles_permissions() 统一处理。
"""
from app.core.database import engine, Base, SessionLocal
from app.models import User, Role, Permission, UserRole, RolePermission, Lead, LeadFollowUp
from app.models.customer import Customer, Contact
from app.models.customer_follow_up import CustomerFollowUp
from app.constants.permissions import ROLES_DATA
from app.schemas.role import RoleCreate
from app.crud.role import role_crud


def init_database():
    Base.metadata.create_all(bind=engine)
    print("数据库表创建成功")


def init_roles():
    """初始化角色（仅创建角色，权限由 init_service 处理）"""
    db = SessionLocal()
    try:
        existing_roles = db.query(Role).count()
        if existing_roles > 0:
            print("角色已初始化，跳过")
            return

        for role_data in ROLES_DATA:
            role = role_crud.create(db, RoleCreate(**role_data))
            print(f"创建角色: {role.name}")

        print("角色初始化完成")

    except Exception as e:
        print(f"初始化失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("开始初始化数据库...")
    init_database()
    init_roles()
    print("数据库初始化完成!")
