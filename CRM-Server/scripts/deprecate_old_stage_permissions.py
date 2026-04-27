import logging
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    logger.error("环境变量DATABASE_URL未设置，请先设置环境变量")
    sys.exit(1)

engine = create_engine(DATABASE_URL)


def deprecate_permission(code: str, reason: str):
    """标记权限为已废弃"""
    try:
        with engine.connect() as conn:
            update_sql = text("""
                UPDATE permissions 
                SET description = CONCAT('[已废弃] ', COALESCE(description, '')),
                    updated_at = NOW()
                WHERE code = :code
            """)
            result = conn.execute(update_sql, {"code": code})
            conn.commit()
            
            if result.rowcount > 0:
                logger.info(f"✅ 已标记权限为废弃: {code}")
                return True
            else:
                logger.warning(f"⚠️  权限不存在: {code}")
                return False
    except Exception as e:
        logger.error(f"❌ 标记权限失败 {code}: {str(e)}")
        return False


def remove_permission_from_roles(permission_code: str):
    """从所有角色中移除指定权限"""
    try:
        with engine.connect() as conn:
            # 先查询哪些角色有这个权限
            result = conn.execute(text("""
                SELECT r.code, rp.role_id, rp.permission_id
                FROM role_permissions rp
                JOIN roles r ON rp.role_id = r.id
                JOIN permissions p ON rp.permission_id = p.id
                WHERE p.code = :permission_code
            """), {"permission_code": permission_code})
            
            role_perms = result.fetchall()
            if not role_perms:
                logger.info(f"ℹ️  权限 {permission_code} 未分配给任何角色")
                return
            
            # 删除角色权限关联
            delete_sql = text("""
                DELETE FROM role_permissions
                WHERE permission_id = (SELECT id FROM permissions WHERE code = :permission_code)
            """)
            result = conn.execute(delete_sql, {"permission_code": permission_code})
            conn.commit()
            
            logger.info(f"✅ 从 {result.rowcount} 个角色中移除权限: {permission_code}")
            
    except Exception as e:
        logger.error(f"❌ 移除权限分配失败 {permission_code}: {str(e)}")


def get_replacement_mapping():
    """返回旧权限到新权限的映射关系"""
    return {
        "opportunity:stage:create": "procurement_stage:create (基于采购方式创建阶段模板)",
        "opportunity:stage:update": "procurement_stage:update (基于采购方式更新阶段模板)",
        "opportunity:stage:delete": "procurement_stage:delete (基于采购方式删除阶段模板)",
        "opportunity:stage": "procurement_method:view + procurement_stage:view (查看采购方式和阶段模板)",
        "opportunity:stage:manage": "procurement:admin:assess + procurement:admin:migrate (采购管理高级功能)"
    }


def main():
    logger.info("="*80)
    logger.info("飞书轻量化CRM - 废弃旧销售阶段权限")
    logger.info("="*80)
    
    logger.info("\n📋 权限迁移说明:")
    logger.info("-"*80)
    mapping = get_replacement_mapping()
    for old_perm, new_perm in mapping.items():
        logger.info(f"  {old_perm:40} → {new_perm}")
    
    logger.info("\n" + "="*80)
    logger.info("开始废弃旧权限...")
    logger.info("="*80)
    
    old_permissions = [
        "opportunity:stage",
        "opportunity:stage:create",
        "opportunity:stage:update",
        "opportunity:stage:delete",
        "opportunity:stage:manage"
    ]
    
    for perm_code in old_permissions:
        # 从所有角色中移除该权限
        remove_permission_from_roles(perm_code)
        
        # 标记权限为已废弃
        deprecate_permission(perm_code, f"已被采购管理权限替代: {mapping.get(perm_code, '')}")
    
    logger.info("\n" + "="*80)
    logger.info("✅ 旧销售阶段权限废弃完成！")
    logger.info("="*80)
    logger.info("\n📝 后续操作建议:")
    logger.info("  1. 前端系统设置页面应移除【销售阶段管理】相关配置项")
    logger.info("  2. 将【销售阶段】配置入口替换为【采购方式管理】和【阶段模板管理】")
    logger.info("  3. 商机创建/编辑时，先选择采购方式，再根据采购方式显示对应阶段")
    logger.info("  4. 商机详情页的阶段信息应显示当前采购方式下的阶段")
    logger.info("="*80)


if __name__ == "__main__":
    main()
