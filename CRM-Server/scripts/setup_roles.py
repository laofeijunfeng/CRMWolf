import logging
from sqlalchemy import create_engine, text
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
engine = create_engine(settings.get_database_url())


def check_role_exists(code: str) -> bool:
    """检查角色是否存在"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT COUNT(*) as count
                FROM roles
                WHERE code = '{code}'
            """))
            exists = result.fetchone()[0] > 0
            return exists
    except Exception as e:
        logger.error(f"检查角色失败: {str(e)}")
        return False


def create_role(code: str, name: str, description: str):
    """创建角色"""
    if check_role_exists(code):
        logger.info(f"✅ 角色 {code} 已存在，跳过创建")
        return
    
    try:
        with engine.connect() as conn:
            insert_sql = text("""
                INSERT INTO roles (code, name, description, created_at, updated_at)
                VALUES (:code, :name, :description, NOW(), NOW())
            """)
            conn.execute(insert_sql, {
                "code": code,
                "name": name,
                "description": description
            })
            conn.commit()
            logger.info(f"✅ 成功创建角色: {code}")
    except Exception as e:
        logger.error(f"❌ 创建角色 {code} 失败: {str(e)}")


def list_roles():
    """列出所有角色"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id, code, name FROM roles ORDER BY id
            """))
            rows = result.fetchall()
            
            logger.info("\n" + "="*80)
            logger.info("当前系统中的角色:")
            logger.info("="*80)
            
            for row in rows:
                logger.info(f"  ID: {row[0]}, 代码: {row[1]}, 名称: {row[2]}")
            
            logger.info("="*80 + "\n")
    except Exception as e:
        logger.error(f"❌ 列出角色失败: {str(e)}")


def main():
    logger.info("="*80)
    logger.info("飞书轻量化CRM - 角色设置")
    logger.info("="*80)
    
    list_roles()
    
    logger.info("\n创建缺失的角色...")
    
    roles_to_create = [
        {
            "code": "admin",
            "name": "系统管理员",
            "description": "系统管理员，拥有所有权限"
        },
        {
            "code": "finance",
            "name": "财务人员",
            "description": "财务人员，负责发票审批、回款确认等财务操作"
        }
    ]
    
    for role in roles_to_create:
        create_role(**role)
    
    logger.info("\n" + "="*80)
    logger.info("✅ 角色设置完成！")
    logger.info("="*80)
    
    list_roles()


if __name__ == "__main__":
    main()
