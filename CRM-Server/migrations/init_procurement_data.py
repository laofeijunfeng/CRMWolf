"""
初始化采购方式和阶段模板数据
根据PRD，预置7种标准采购方式
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.procurement import ProcurementMethod, ProcurementStageTemplate
from sqlalchemy import text
from datetime import datetime


PROCUREMENT_METHODS = [
    {
        "code": "STANDARD_SALES",
        "name": "标准销售流程",
        "description": "标准的企业销售流程，适用于一般销售场景",
        "sort_order": 1,
        "stages": [
            {"template_code": "LEAD", "stage_name": "线索", "win_probability": 10, "sort_order": 1, "is_default_start": 1, "can_skip": 0},
            {"template_code": "QUALIFIED", "stage_name": "合格线索", "win_probability": 20, "sort_order": 2, "is_default_start": 0, "can_skip": 0},
            {"template_code": "PROPOSAL", "stage_name": "方案阶段", "win_probability": 40, "sort_order": 3, "is_default_start": 0, "can_skip": 0},
            {"template_code": "NEGOTIATION", "stage_name": "商务谈判", "win_probability": 60, "sort_order": 4, "is_default_start": 0, "can_skip": 0},
            {"template_code": "CONTRACT_REVIEW", "stage_name": "合同审核", "win_probability": 80, "sort_order": 5, "is_default_start": 0, "can_skip": 0},
            {"template_code": "WON", "stage_name": "赢单", "win_probability": 100, "sort_order": 6, "is_default_start": 0, "can_skip": 0},
        ]
    },
    {
        "code": "PUBLIC_BIDDING",
        "name": "公开招标",
        "description": "公开招标采购流程，适用于政府、国企等公开招标项目",
        "sort_order": 2,
        "stages": [
            {"template_code": "BID_ANNOUNCEMENT", "stage_name": "招标公告", "win_probability": 5, "sort_order": 1, "is_default_start": 1, "can_skip": 0},
            {"template_code": "BID_REGISTRATION", "stage_name": "投标报名", "win_probability": 10, "sort_order": 2, "is_default_start": 0, "can_skip": 0},
            {"template_code": "BID_DOC_PREP", "stage_name": "标书制作", "win_probability": 20, "sort_order": 3, "is_default_start": 0, "can_skip": 0},
            {"template_code": "BID_SUBMIT", "stage_name": "投标提交", "win_probability": 30, "sort_order": 4, "is_default_start": 0, "can_skip": 0},
            {"template_code": "BID_EVALUATION", "stage_name": "评标", "win_probability": 50, "sort_order": 5, "is_default_start": 0, "can_skip": 0},
            {"template_code": "BID_WON", "stage_name": "中标", "win_probability": 100, "sort_order": 6, "is_default_start": 0, "can_skip": 0},
        ]
    },
    {
        "code": "INVITATIONAL_BIDDING",
        "name": "邀请招标",
        "description": "邀请招标采购流程，受邀供应商参与投标",
        "sort_order": 3,
        "stages": [
            {"template_code": "INVITATION", "stage_name": "邀请", "win_probability": 20, "sort_order": 1, "is_default_start": 1, "can_skip": 0},
            {"template_code": "INV_BID_DOC_PREP", "stage_name": "标书制作", "win_probability": 35, "sort_order": 2, "is_default_start": 0, "can_skip": 0},
            {"template_code": "INV_BID_SUBMIT", "stage_name": "投标提交", "win_probability": 50, "sort_order": 3, "is_default_start": 0, "can_skip": 0},
            {"template_code": "INV_BID_WON", "stage_name": "中标", "win_probability": 100, "sort_order": 4, "is_default_start": 0, "can_skip": 0},
        ]
    },
    {
        "code": "COMPETITIVE_NEGOTIATION",
        "name": "竞争性谈判",
        "description": "竞争性谈判流程，多轮报价和技术商务谈判",
        "sort_order": 4,
        "stages": [
            {"template_code": "NEG_INIT", "stage_name": "初步接触", "win_probability": 25, "sort_order": 1, "is_default_start": 1, "can_skip": 0},
            {"template_code": "NEG_ROUND1", "stage_name": "首轮谈判", "win_probability": 40, "sort_order": 2, "is_default_start": 0, "can_skip": 0},
            {"template_code": "NEG_ROUND2", "stage_name": "二轮谈判", "win_probability": 55, "sort_order": 3, "is_default_start": 0, "can_skip": 1},
            {"template_code": "NEG_ROUND3", "stage_name": "三轮谈判", "win_probability": 70, "sort_order": 4, "is_default_start": 0, "can_skip": 1},
            {"template_code": "NEG_FINAL", "stage_name": "最终谈判", "win_probability": 85, "sort_order": 5, "is_default_start": 0, "can_skip": 0},
            {"template_code": "NEG_WON", "stage_name": "成功", "win_probability": 100, "sort_order": 6, "is_default_start": 0, "can_skip": 0},
        ]
    },
    {
        "code": "SINGLE_SOURCE",
        "name": "单一来源",
        "description": "单一来源采购，直接与供应商谈判",
        "sort_order": 5,
        "stages": [
            {"template_code": "SS_INIT", "stage_name": "需求确认", "win_probability": 50, "sort_order": 1, "is_default_start": 1, "can_skip": 0},
            {"template_code": "SS_NEGOTIATION", "stage_name": "商务谈判", "win_probability": 75, "sort_order": 2, "is_default_start": 0, "can_skip": 0},
            {"template_code": "SS_CONTRACT", "stage_name": "合同签署", "win_probability": 90, "sort_order": 3, "is_default_start": 0, "can_skip": 0},
            {"template_code": "SS_WON", "stage_name": "成交", "win_probability": 100, "sort_order": 4, "is_default_start": 0, "can_skip": 0},
        ]
    },
    {
        "code": "PRICE_COMPARISON",
        "name": "询价比价",
        "description": "询价比价流程，比较价格后选择供应商",
        "sort_order": 6,
        "stages": [
            {"template_code": "PRICE_QUERY", "stage_name": "询价", "win_probability": 30, "sort_order": 1, "is_default_start": 1, "can_skip": 0},
            {"template_code": "PRICE_QUOTE", "stage_name": "报价", "win_probability": 50, "sort_order": 2, "is_default_start": 0, "can_skip": 0},
            {"template_code": "PRICE_COMP", "stage_name": "比价", "win_probability": 70, "sort_order": 3, "is_default_start": 0, "can_skip": 0},
            {"template_code": "PRICE_WON", "stage_name": "成交", "win_probability": 100, "sort_order": 4, "is_default_start": 0, "can_skip": 0},
        ]
    },
    {
        "code": "ONLINE_PURCHASE",
        "name": "电商化采购",
        "description": "电商化采购流程，在线下单和支付",
        "sort_order": 7,
        "stages": [
            {"template_code": "ONLINE_CART", "stage_name": "加购", "win_probability": 40, "sort_order": 1, "is_default_start": 1, "can_skip": 0},
            {"template_code": "ONLINE_ORDER", "stage_name": "下单", "win_probability": 60, "sort_order": 2, "is_default_start": 0, "can_skip": 0},
            {"template_code": "ONLINE_PAY", "stage_name": "支付", "win_probability": 80, "sort_order": 3, "is_default_start": 0, "can_skip": 0},
            {"template_code": "ONLINE_WON", "stage_name": "成交", "win_probability": 100, "sort_order": 4, "is_default_start": 0, "can_skip": 0},
        ]
    },
]


def init_procurement_data():
    """初始化采购方式和阶段模板数据"""
    db = SessionLocal()
    try:
        print("开始初始化采购方式和阶段模板数据...")
        
        # 检查是否已有数据
        result = db.execute(text("SELECT COUNT(*) FROM crm_procurement_methods"))
        existing_count = result.scalar()
        if existing_count > 0:
            print(f"⚠️  已存在 {existing_count} 个采购方式，跳过初始化")
            return
        
        # 获取系统创建人ID（假设使用 admin）
        system_user = "admin"
        
        for method_data in PROCUREMENT_METHODS:
            print(f"\n创建采购方式: {method_data['name']} ({method_data['code']})")
            
            # 创建采购方式
            procurement_method = ProcurementMethod(
                code=method_data['code'],
                name=method_data['name'],
                description=method_data['description'],
                is_active=1,
                sort_order=method_data['sort_order'],
                created_by=system_user,
                updated_by=system_user
            )
            db.add(procurement_method)
            db.flush()  # 获取 ID
            
            print(f"  ✓ 创建了采购方式 ID: {procurement_method.id}")
            
            # 创建阶段模板
            for stage_data in method_data['stages']:
                stage = ProcurementStageTemplate(
                    procurement_method_id=procurement_method.id,
                    template_code=stage_data['template_code'],
                    stage_name=stage_data['stage_name'],
                    win_probability=stage_data['win_probability'],
                    sort_order=stage_data['sort_order'],
                    is_default_start=stage_data['is_default_start'],
                    can_skip=stage_data['can_skip'],
                    version=1,
                    version_lock=0,
                    created_by=system_user,
                    updated_by=system_user
                )
                db.add(stage)
            
            print(f"  ✓ 创建了 {len(method_data['stages'])} 个阶段模板")
        
        db.commit()
        print("\n✅ 初始化完成！")
        print(f"\n总共创建了 {len(PROCUREMENT_METHODS)} 个采购方式")
        total_stages = sum(len(m['stages']) for m in PROCUREMENT_METHODS)
        print(f"总共创建了 {total_stages} 个阶段模板")
        
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_procurement_data()
