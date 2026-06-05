"""
客户档案生成问题排查脚本

使用方式：
  python scripts/diagnose_customer_profile.py [customer_id]

如果不传 customer_id，会检查所有异常状态的客户
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.customer import Customer
from app.models.ai_config import AIConfig
from app.crud.ai_config import ai_config_crud
from app.crud.customer import customer_crud
from app.services.customer_profile_service import customer_profile_service
from app.services.ai_service import ai_service


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def diagnose():
    db = SessionLocal()

    # 获取参数
    customer_id = int(sys.argv[1]) if len(sys.argv) > 1 else None

    # ==================== 1. 检查异常状态的客户 ====================
    print_section("1. 检查异常状态的客户")

    if customer_id:
        customers = db.query(Customer).filter(Customer.id == customer_id).all()
    else:
        customers = db.query(Customer).filter(
            Customer.profile_status.in_(['GENERATING', 'PENDING', 'FAILED'])
        ).order_by(Customer.created_time.desc()).limit(10).all()

    if not customers:
        print("✓ 没有异常状态的客户")
        db.close()
        return

    print(f"找到 {len(customers)} 个异常状态的客户:\n")
    for c in customers:
        print(f"ID: {c.id}")
        print(f"  名称: {c.account_name}")
        print(f"  team_id: {c.team_id}")
        print(f"  状态: {c.profile_status}")
        print(f"  错误信息: {c.profile_error_message or '无'}")
        print(f"  生成时间: {c.profile_generated_time or '未生成'}")
        print(f"  创建时间: {c.created_time}")
        print()

    # ==================== 2. 检查 AI 配置 ====================
    print_section("2. 检查 AI 配置")

    all_configs = db.query(AIConfig).all()
    print(f"AI 配置总数: {len(all_configs)}\n")

    for cfg in all_configs:
        print(f"team_id: {cfg.team_id}")
        print(f"  api_host: {cfg.api_host}")
        print(f"  model_name: {cfg.model_name}")
        print(f"  更新时间: {cfg.updated_at}")
        print()

    if not all_configs:
        print("⚠️  没有任何 AI 配置！请先配置 AI 服务")
        db.close()
        return

    # ==================== 3. 检查配置与客户的匹配 ====================
    print_section("3. 检查配置与客户的匹配")

    for c in customers:
        config = ai_config_crud.get_config(db, c.team_id)
        print(f"客户 ID {c.id} (team_id={c.team_id}):")
        if config:
            print(f"  ✓ 有对应配置: {config.api_host}")
            # 测试解密
            try:
                api_key = ai_config_crud.get_decrypted_api_key(db, c.team_id)
                if api_key:
                    print(f"  ✓ API Key 可解密 (长度: {len(api_key)})")
                else:
                    print(f"  ✗ API Key 解密失败")
            except Exception as e:
                print(f"  ✗ API Key 解密异常: {e}")
        else:
            print(f"  ✗ 无对应配置")
            # 查看是否有其他配置可用
            if all_configs:
                print(f"  ⚠️  其他团队有配置: team_ids = {[c.team_id for c in all_configs]}")
        print()

    # ==================== 4. 测试 AI 连接 ====================
    print_section("4. 测试 AI 连接")

    if all_configs:
        cfg = all_configs[0]
        print(f"使用 team_id={cfg.team_id} 的配置测试...\n")

        try:
            api_key = ai_config_crud.get_decrypted_api_key(db, cfg.team_id)
            if not api_key:
                print("✗ 无法获取 API Key")
            else:
                # 测试简单的 AI 调用
                test_result = asyncio.run(ai_service._stream_chat_collect(
                    api_host=cfg.api_host,
                    api_key=api_key,
                    model=cfg.model_name,
                    messages=[
                        {"role": "user", "content": "回复OK"}
                    ],
                    temperature=0.1,
                    max_tokens=10
                ))
                print(f"✓ AI 调用成功，响应: {test_result[:50]}...")
        except Exception as e:
            print(f"✗ AI 调用失败: {e}")

    # ==================== 5. 建议 ====================
    print_section("5. 建议")

    for c in customers:
        config = ai_config_crud.get_config(db, c.team_id)

        if c.profile_status == 'GENERATING':
            print(f"客户 ID {c.id}:")
            print("  - 状态为 GENERATING，可能异步任务卡住")
            print("  - 建议: 重置为 PENDING 并重新触发")
            print(f"  - 命令: UPDATE crm_customers SET profile_status='PENDING' WHERE id={c.id};")
            print()

        elif c.profile_status == 'PENDING':
            print(f"客户 ID {c.id}:")
            print("  - 状态为 PENDING，任务未执行")
            if not config:
                print(f"  - 原因: team_id={c.team_id} 没有 AI 配置")
                print(f"  - 建议: 为 team_id={c.team_id} 配置 AI 服务")
            else:
                print("  - 建议: 手动触发重新生成")
            print()

        elif c.profile_status == 'FAILED':
            print(f"客户 ID {c.id}:")
            print(f"  - 状态为 FAILED: {c.profile_error_message}")
            if "配置" in str(c.profile_error_message):
                print(f"  - 原因: AI 配置问题")
                print(f"  - 建议: 检查 team_id={c.team_id} 的 AI 配置")
            print()

    db.close()


async def regenerate(customer_id: int):
    """手动重新生成档案"""
    db = SessionLocal()

    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        print(f"✗ 客户 ID {customer_id} 不存在")
        db.close()
        return

    print(f"\n重新生成客户 ID {customer_id} 的档案...\n")
    print(f"名称: {customer.account_name}")
    print(f"team_id: {customer.team_id}")

    # 重置状态
    customer_crud.update_profile_status(db, customer_id, 'PENDING')
    print("状态已重置为 PENDING\n")

    db.close()

    # 触发生成
    result = await customer_profile_service.generate_profile(
        customer_id=customer_id,
        account_name=customer.account_name,
        source_lead_id=customer.source_lead_id,
        team_id=customer.team_id
    )

    print("\n结果:")
    print(f"  成功: {result.get('success')}")
    if result.get('success'):
        print(f"  行业: {result.get('industry_code')}")
    else:
        print(f"  错误: {result.get('error')}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "regenerate":
        asyncio.run(regenerate(int(sys.argv[1])))
    else:
        diagnose()