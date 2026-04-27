"""
检查当前权限系统状态
"""
import logging
from sqlalchemy import create_engine, text
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
engine = create_engine(str(settings.DATABASE_URL))


def check_permissions():
    """检查权限表"""
    logger.info("\n" + "="*80)
    logger.info("检查权限表（permissions）")
    logger.info("="*80)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) as count FROM permissions"))
            count = result.fetchone()[0]
            logger.info(f"✅ 权限总数: {count}")
            
            if count > 0:
                result = conn.execute(text("""
                    SELECT resource, action, COUNT(*) as count
                    FROM permissions
                    GROUP BY resource, action
                    ORDER BY resource, action
                """))
                logger.info("\n权限分布:")
                for row in result:
                    logger.info(f"  - {row[0]}.{row[1]}: {row[2]}个")
            else:
                logger.warning("⚠️  权限表为空，需要运行迁移脚本")
    except Exception as e:
        logger.error(f"❌ 检查权限表失败: {str(e)}")


def check_roles():
    """检查角色表"""
    logger.info("\n" + "="*80)
    logger.info("检查角色表（roles）")
    logger.info("="*80)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) as count FROM roles"))
            count = result.fetchone()[0]
            logger.info(f"✅ 角色总数: {count}")
            
            if count > 0:
                result = conn.execute(text("SELECT code, name FROM roles ORDER BY code"))
                logger.info("\n角色列表:")
                for row in result:
                    logger.info(f"  - {row[0]}: {row[1]}")
            else:
                logger.warning("⚠️  角色表为空，需要创建角色")
    except Exception as e:
        logger.error(f"❌ 检查角色表失败: {str(e)}")


def check_role_permissions():
    """检查角色权限关联表"""
    logger.info("\n" + "="*80)
    logger.info("检查角色权限关联表（role_permissions）")
    logger.info("="*80)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) as count FROM role_permissions"))
            count = result.fetchone()[0]
            logger.info(f"✅ 角色权限关联总数: {count}")
            
            if count > 0:
                result = conn.execute(text("""
                    SELECT r.code, r.name, COUNT(rp.permission_id) as perm_count
                    FROM roles r
                    LEFT JOIN role_permissions rp ON r.id = rp.role_id
                    GROUP BY r.id, r.code, r.name
                    ORDER BY r.code
                """))
                logger.info("\n各角色权限数量:")
                for row in result:
                    logger.info(f"  - {row[0]} ({row[1]}): {row[2]}个权限")
            else:
                logger.warning("⚠️  角色权限关联表为空，需要运行角色权限分配脚本")
    except Exception as e:
        logger.error(f"❌ 检查角色权限关联表失败: {str(e)}")


def check_user_roles():
    """检查用户角色关联表"""
    logger.info("\n" + "="*80)
    logger.info("检查用户角色关联表（user_roles）")
    logger.info("="*80)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) as count FROM user_roles"))
            count = result.fetchone()[0]
            logger.info(f"✅ 用户角色关联总数: {count}")
            
            if count > 0:
                result = conn.execute(text("""
                    SELECT u.name, r.code, r.name
                    FROM user_roles ur
                    JOIN users u ON ur.user_id = u.id
                    JOIN roles r ON ur.role_id = r.id
                    ORDER BY u.name, r.code
                """))
                logger.info("\n用户角色分配:")
                for row in result:
                    logger.info(f"  - {row[0]}: {row[1]} ({row[2]})")
            else:
                logger.warning("⚠️  用户角色关联表为空")
    except Exception as e:
        logger.error(f"❌ 检查用户角色关联表失败: {str(e)}")


def main():
    logger.info("="*80)
    logger.info("飞书轻量化CRM - 权限系统状态检查")
    logger.info("="*80)
    
    check_permissions()
    check_roles()
    check_role_permissions()
    check_user_roles()
    
    logger.info("\n" + "="*80)
    logger.info("✅ 检查完成！")
    logger.info("="*80)


if __name__ == "__main__":
    main()
