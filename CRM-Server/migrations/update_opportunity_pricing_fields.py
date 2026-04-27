"""
更新商机表的价格相关字段
添加用户数量、单价、授权模式、订阅年限等字段
"""
from app.core.database import SessionLocal
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_opportunity_table():
    """迁移商机表结构"""
    db = SessionLocal()
    
    try:
        logger.info("开始迁移商机表结构...")
        
        logger.info("1. 检查当前表结构...")
        columns_query = """
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'crm_opportunities' 
            AND TABLE_SCHEMA = DATABASE()
        """
        existing_columns = [row[0] for row in db.execute(text(columns_query)).fetchall()]
        logger.info(f"现有字段: {existing_columns}")
        
        if 'expected_amount' in existing_columns and 'total_amount' not in existing_columns:
            logger.info("2. 重命名字段 expected_amount -> total_amount")
            db.execute(text(
                "ALTER TABLE crm_opportunities CHANGE COLUMN expected_amount total_amount DECIMAL(12,2) NOT NULL COMMENT '预计总金额'"
            ))
            db.commit()
            logger.info("✓ 字段重命名成功")
        elif 'total_amount' in existing_columns:
            logger.info("✓ total_amount 字段已存在，跳过重命名")
        else:
            logger.warning("⚠ 既没有 expected_amount 也没有 total_amount，需要手动处理")
        
        logger.info("3. 添加新字段...")
        
        new_fields = [
            ("user_count", "INT NOT NULL COMMENT '采购用户数'"),
            ("unit_price", "DECIMAL(10,2) NOT NULL COMMENT '标准单价（系统自动计算）'"),
            ("license_type", "VARCHAR(20) NOT NULL COMMENT '授权模式：SUBSCRIPTION:订阅, PERPETUAL:买断'"),
            ("subscription_years", "INT NULL COMMENT '订阅年限（订阅制时必填）'")
        ]
        
        for field_name, field_definition in new_fields:
            if field_name not in existing_columns:
                logger.info(f"  添加字段: {field_name}")
                db.execute(text(
                    f"ALTER TABLE crm_opportunities ADD COLUMN {field_name} {field_definition}"
                ))
                db.commit()
                logger.info(f"  ✓ {field_name} 字段添加成功")
            else:
                logger.info(f"  ✓ {field_name} 字段已存在，跳过")
        
        logger.info("4. 添加索引...")
        index_name = "idx_license_type"
        indexes_query = """
            SELECT INDEX_NAME 
            FROM INFORMATION_SCHEMA.STATISTICS 
            WHERE TABLE_NAME = 'crm_opportunities' 
            AND TABLE_SCHEMA = DATABASE()
            AND INDEX_NAME = :index_name
        """
        existing_index = db.execute(text(indexes_query), {"index_name": index_name}).first()
        
        if not existing_index:
            logger.info(f"  添加索引: {index_name}")
            db.execute(text(
                "CREATE INDEX idx_license_type ON crm_opportunities(license_type)"
            ))
            db.commit()
            logger.info(f"  ✓ {index_name} 索引添加成功")
        else:
            logger.info(f"  ✓ {index_name} 索引已存在，跳过")
        
        logger.info("5. 更新现有数据...")
        
        check_data_query = "SELECT COUNT(*) FROM crm_opportunities WHERE user_count IS NULL OR user_count = 0"
        null_count = db.execute(text(check_data_query)).scalar()
        
        if null_count > 0:
            logger.info(f"  发现 {null_count} 条记录需要更新默认值")
            
            update_query = """
                UPDATE crm_opportunities 
                SET 
                    user_count = COALESCE(NULLIF(user_count, 0), 1),
                    unit_price = COALESCE(unit_price, 
                                         CASE 
                                            WHEN license_type = 'PERPETUAL' THEN total_amount / GREATEST(user_count, 1) / 5
                                            ELSE total_amount / GREATEST(user_count, 1) / COALESCE(subscription_years, 1)
                                         END
                                        ),
                    license_type = COALESCE(license_type, 'SUBSCRIPTION'),
                    subscription_years = CASE 
                                          WHEN license_type = 'SUBSCRIPTION' THEN COALESCE(subscription_years, 1)
                                          ELSE NULL 
                                       END
                WHERE user_count IS NULL OR user_count = 0
            """
            db.execute(text(update_query))
            db.commit()
            logger.info("  ✓ 现有数据更新完成")
        else:
            logger.info("  ✓ 没有需要更新的数据")
        
        logger.info("6. 验证表结构...")
        updated_columns = db.execute(text(columns_query)).fetchall()
        logger.info(f"更新后的字段: {[col[0] for col in updated_columns]}")
        
        required_fields = ['id', 'opportunity_name', 'customer_id', 'total_amount', 
                          'user_count', 'unit_price', 'license_type', 'subscription_years']
        missing_fields = [field for field in required_fields if field not in [col[0] for col in updated_columns]]
        
        if missing_fields:
            logger.error(f"✗ 缺少必需字段: {missing_fields}")
            return False
        else:
            logger.info("✓ 所有必要字段都存在")
        
        logger.info("=" * 60)
        logger.info("商机表迁移完成！")
        logger.info("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"迁移失败: {str(e)}")
        db.rollback()
        return False
        
    finally:
        db.close()


if __name__ == "__main__":
    success = migrate_opportunity_table()
    if success:
        print("\n✅ 迁移成功完成！")
        print("\n请重启API服务器以应用更改。")
    else:
        print("\n❌ 迁移失败，请检查日志")
