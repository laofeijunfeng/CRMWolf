from app.core.database import SessionLocal
from app.models.opportunity import OpportunityStage


def init_opportunity_stages():
    db = SessionLocal()
    try:
        existing_stages = db.query(OpportunityStage).count()
        if existing_stages > 0:
            print("销售阶段已初始化，跳过")
            return

        stages_data = [
            {
                "stage_code": "INITIAL_CONTACT",
                "stage_name": "初步接触",
                "win_probability": 10,
                "sort_order": 1,
                "description": "首次与客户建立联系，了解基本情况"
            },
            {
                "stage_code": "NEEDS_ANALYSIS",
                "stage_name": "需求分析",
                "win_probability": 25,
                "sort_order": 2,
                "description": "深入了解客户需求，明确痛点"
            },
            {
                "stage_code": "PROPOSAL_QUOTE",
                "stage_name": "方案报价",
                "win_probability": 50,
                "sort_order": 3,
                "description": "提供解决方案和报价方案"
            },
            {
                "stage_code": "NEGOTIATION",
                "stage_name": "谈判审核",
                "win_probability": 75,
                "sort_order": 4,
                "description": "商务谈判和合同审核阶段"
            },
            {
                "stage_code": "WON",
                "stage_name": "赢单",
                "win_probability": 100,
                "sort_order": 5,
                "description": "成功签约，项目启动"
            }
        ]

        for stage_data in stages_data:
            stage = OpportunityStage(**stage_data)
            db.add(stage)
            print(f"创建销售阶段: {stage.stage_name}")

        db.commit()
        print("销售阶段初始化完成")

    except Exception as e:
        print(f"初始化失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("开始初始化销售阶段...")
    init_opportunity_stages()
    print("销售阶段初始化完成!")
