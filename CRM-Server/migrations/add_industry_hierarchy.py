"""
行业分级体系迁移脚本

功能：
1. 创建 crm_industries 行业表（一级行业 + 二级行业）
2. 初始化行业分级数据

运行方式：
  python migrations/add_industry_hierarchy.py          # 执行迁移
  python migrations/add_industry_hierarchy.py --verify # 验证迁移结果
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import SessionLocal, engine


def create_industry_table():
    """创建行业表"""
    print("\n=== 创建行业表 ===")

    with engine.connect() as conn:
        try:
            # 检查表是否已存在
            result = conn.execute(text("SHOW TABLES LIKE 'crm_industries'"))
            if result.fetchone():
                print("  ⚠️  crm_industries 表已存在，跳过")
                return

            conn.execute(text("""
                CREATE TABLE crm_industries (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
                    level INT NOT NULL COMMENT '层级：1=一级行业，2=二级行业',
                    parent_id INT NULL COMMENT '父行业ID（二级行业关联一级行业）',
                    code VARCHAR(50) NOT NULL COMMENT '行业编码',
                    name VARCHAR(100) NOT NULL COMMENT '行业名称',
                    sort_order INT DEFAULT 0 COMMENT '排序',
                    is_active INT DEFAULT 1 COMMENT '是否启用：1=启用，0=停用',
                    created_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    INDEX idx_level (level),
                    INDEX idx_parent_id (parent_id),
                    INDEX idx_code (code),
                    UNIQUE KEY uk_code (code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业分级表'
            """))
            conn.commit()
            print("  ✓ crm_industries 表创建成功")
        except Exception as e:
            print(f"  ✗ 创建表失败: {e}")
            raise


def init_industry_data():
    """初始化行业分级数据"""
    print("\n=== 初始化行业分级数据 ===")

    # 一级行业 + 二级行业数据
    industries = [
        # 金融
        ("finance", "金融", 1, None, 1),
        ("finance_bank", "银行", 2, "finance", 1),
        ("finance_insurance", "保险", 2, "finance", 2),
        ("finance_securities", "证券", 2, "finance", 3),
        ("finance_fund", "基金", 2, "finance", 4),
        ("finance_payment", "支付", 2, "finance", 5),

        # 互联网
        ("internet", "互联网", 1, None, 2),
        ("internet_ecommerce", "电商平台", 2, "internet", 1),
        ("internet_saas", "SaaS公司", 2, "internet", 2),
        ("internet_social", "社交媒体", 2, "internet", 3),
        ("internet_content", "内容平台", 2, "internet", 4),
        ("internet_fintech", "金融科技", 2, "internet", 5),

        # 制造业
        ("manufacturing", "制造业", 1, None, 3),
        ("manufacturing_auto", "汽车制造", 2, "manufacturing", 1),
        ("manufacturing_electronics", "电子制造", 2, "manufacturing", 2),
        ("manufacturing_machinery", "机械设备", 2, "manufacturing", 3),
        ("manufacturing_chemical", "化工", 2, "manufacturing", 4),
        ("manufacturing_food", "食品加工", 2, "manufacturing", 5),

        # 零售
        ("retail", "零售", 1, None, 4),
        ("retail_supermarket", "超市连锁", 2, "retail", 1),
        ("retail_brand", "品牌零售", 2, "retail", 2),
        ("retail_online", "网络零售", 2, "retail", 3),

        # 教育
        ("education", "教育", 1, None, 5),
        ("education_k12", "K12教育", 2, "education", 1),
        ("education_higher", "高等教育", 2, "education", 2),
        ("education_training", "职业培训", 2, "education", 3),
        ("education_online", "在线教育", 2, "education", 4),

        # 医疗
        ("healthcare", "医疗", 1, None, 6),
        ("healthcare_hospital", "医院", 2, "healthcare", 1),
        ("healthcare_pharma", "制药", 2, "healthcare", 2),
        ("healthcare_device", "医疗器械", 2, "healthcare", 3),
        ("healthcare_service", "医疗服务", 2, "healthcare", 4),

        # 房地产
        ("real_estate", "房地产", 1, None, 7),
        ("real_estate_developer", "开发商", 2, "real_estate", 1),
        ("real_estate_agent", "中介服务", 2, "real_estate", 2),
        ("real_estate_manage", "物业管理", 2, "real_estate", 3),

        # 政府
        ("government", "政府", 1, None, 8),
        ("government_central", "中央政府", 2, "government", 1),
        ("government_local", "地方政府", 2, "government", 2),
        ("government_public", "公共机构", 2, "government", 3),

        # 物流
        ("logistics", "物流", 1, None, 9),
        ("logistics_express", "快递", 2, "logistics", 1),
        ("logistics_shipping", "航运", 2, "logistics", 2),
        ("logistics_warehouse", "仓储", 2, "logistics", 3),

        # 能源
        ("energy", "能源", 1, None, 10),
        ("energy_oil", "石油", 2, "energy", 1),
        ("energy_gas", "天然气", 2, "energy", 2),
        ("energy_electric", "电力", 2, "energy", 3),
        ("energy_new", "新能源", 2, "energy", 4),

        # 通信
        ("telecom", "通信", 1, None, 11),
        ("telecom_operator", "运营商", 2, "telecom", 1),
        ("telecom_service", "通信服务", 2, "telecom", 2),

        # 建筑
        ("construction", "建筑", 1, None, 12),
        ("construction_engineering", "工程建筑", 2, "construction", 1),
        ("construction_design", "建筑设计", 2, "construction", 2),

        # 农业
        ("agriculture", "农业", 1, None, 13),
        ("agriculture_farming", "种植", 2, "agriculture", 1),
        ("agriculture_breeding", "养殖", 2, "agriculture", 2),
        ("agriculture_processing", "农产品加工", 2, "agriculture", 3),

        # 娱乐
        ("entertainment", "娱乐", 1, None, 14),
        ("entertainment_media", "媒体", 2, "entertainment", 1),
        ("entertainment_game", "游戏", 2, "entertainment", 2),
        ("entertainment_sports", "体育", 2, "entertainment", 3),

        # 咨询
        ("consulting", "咨询", 1, None, 15),
        ("consulting_strategy", "战略咨询", 2, "consulting", 1),
        ("consulting_it", "IT咨询", 2, "consulting", 2),
        ("consulting_hr", "人力资源咨询", 2, "consulting", 3),

        # 其他
        ("other", "其他", 1, None, 16),
    ]

    db = SessionLocal()
    try:
        # 先获取父行业ID映射
        parent_id_map = {}

        # 先插入一级行业
        for code, name, level, parent_code, sort_order in industries:
            if level == 1:
                result = db.execute(text("""
                    SELECT id FROM crm_industries WHERE code = :code
                """), {"code": code})
                if result.fetchone():
                    row = db.execute(text("SELECT id FROM crm_industries WHERE code = :code"), {"code": code}).first()
                    parent_id_map[code] = row[0]
                    print(f"  ⚠️  {name}({code}) 已存在，跳过")
                else:
                    db.execute(text("""
                        INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active)
                        VALUES (1, NULL, :code, :name, :sort_order, 1)
                    """), {"code": code, "name": name, "sort_order": sort_order})
                    db.commit()
                    row = db.execute(text("SELECT id FROM crm_industries WHERE code = :code"), {"code": code}).first()
                    parent_id_map[code] = row[0]
                    print(f"  ✓ 一级行业 {name}({code}) 添加成功")

        # 再插入二级行业
        for code, name, level, parent_code, sort_order in industries:
            if level == 2:
                result = db.execute(text("""
                    SELECT id FROM crm_industries WHERE code = :code
                """), {"code": code})
                if result.fetchone():
                    print(f"  ⚠️  {name}({code}) 已存在，跳过")
                else:
                    parent_id = parent_id_map.get(parent_code)
                    if parent_id:
                        db.execute(text("""
                            INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active)
                            VALUES (2, :parent_id, :code, :name, :sort_order, 1)
                        """), {"parent_id": parent_id, "code": code, "name": name, "sort_order": sort_order})
                        db.commit()
                        print(f"  ✓ 二级行业 {name}({code}) 添加成功")
                    else:
                        print(f"  ⚠️  {name}({code}) 父行业不存在，跳过")

        print("\n  行业数据初始化完成")
    except Exception as e:
        print(f"  ✗ 初始化数据失败: {e}")
        raise
    finally:
        db.close()


def verify_migration():
    """验证迁移结果"""
    print("\n=== 验证迁移结果 ===")

    db = SessionLocal()
    try:
        # 检查表存在
        result = db.execute(text("SHOW TABLES LIKE 'crm_industries'"))
        if not result.fetchone():
            print("❌ crm_industries 表不存在")
            return

        print("✓ crm_industries 表存在")

        # 检查一级行业数量
        result = db.execute(text("SELECT COUNT(*) FROM crm_industries WHERE level = 1"))
        count = result.fetchone()[0]
        print(f"✓ 一级行业数量: {count}")

        # 检查二级行业数量
        result = db.execute(text("SELECT COUNT(*) FROM crm_industries WHERE level = 2"))
        count = result.fetchone()[0]
        print(f"✓ 二级行业数量: {count}")

        # 显示一级行业列表
        result = db.execute(text("SELECT code, name FROM crm_industries WHERE level = 1 ORDER BY sort_order"))
        print("\n一级行业列表:")
        for row in result:
            print(f"  - {row[1]} ({row[0]})")

        print("\n✅ 验证成功，迁移完成")
    except Exception as e:
        print(f"❌ 验证失败: {e}")
    finally:
        db.close()


def run_migration():
    """执行完整迁移流程"""
    print("=" * 50)
    print("CRMWolf 行业分级体系迁移")
    print("=" * 50)

    try:
        create_industry_table()
        init_industry_data()
        verify_migration()
        print("\n" + "=" * 50)
        print("迁移完成！")
        print("=" * 50)
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="行业分级体系迁移脚本")
    parser.add_argument("--verify", action="store_true", help="仅验证迁移结果")
    args = parser.parse_args()

    if args.verify:
        verify_migration()
    else:
        run_migration()