"""
迁移历史跟进记录：从 content 中提取"下一步动作"内容到 next_action 字段

执行方式：
cd CRM-Server && python3 scripts/migrate_next_action_data.py
"""

import sys
sys.path.insert(0, '/Users/eddie/Code/CRMWolf/CRM-Server')

import re
from sqlalchemy.orm.attributes import flag_modified
from app.core.database import SessionLocal
from app.models.lead import LeadFollowUp
from app.models.customer_follow_up import CustomerFollowUp
from app.models.operation_log import OperationLog


def extract_next_action(content: str) -> tuple[str, str | None]:
    """
    从跟进内容中提取"下一步动作"

    返回: (清理后的content, next_action)
    """
    if not content:
        return content, None

    # 匹配模式：下一步动作：xxx 或 下一步动作:xxx
    pattern = r'[，,。\s]*(下一步动作[：:]\s*.*?)(?:\s*$|\.|$)'
    match = re.search(pattern, content, re.IGNORECASE)

    if match:
        # 提取 next_action 内容
        next_action_text = match.group(1)
        # 清理"下一步动作："前缀
        next_action = re.sub(r'下一步动作[：:]\s*', '', next_action_text).strip()

        # 从原 content 中移除这部分
        cleaned_content = content[:match.start()].strip()
        # 清理末尾可能的逗号、句号等
        cleaned_content = re.sub(r'[，,。]\s*$', '', cleaned_content)

        return cleaned_content, next_action

    return content, None


def migrate():
    db = SessionLocal()

    try:
        # 1. 迁移线索跟进记录
        lead_follow_ups = db.query(LeadFollowUp).filter(
            LeadFollowUp.next_action.is_(None),
            LeadFollowUp.content.like('%下一步动作%')
        ).all()

        print(f"找到 {len(lead_follow_ups)} 条线索跟进记录需要迁移")

        for follow_up in lead_follow_ups:
            cleaned_content, next_action = extract_next_action(follow_up.content)
            if next_action:
                follow_up.content = cleaned_content
                follow_up.next_action = next_action
                print(f"  LeadFollowUp ID={follow_up.id}: 提取 next_action='{next_action[:50]}...'")

        # 2. 迁移客户跟进记录
        customer_follow_ups = db.query(CustomerFollowUp).filter(
            CustomerFollowUp.next_action.is_(None),
            CustomerFollowUp.content.like('%下一步动作%')
        ).all()

        print(f"找到 {len(customer_follow_ups)} 条客户跟进记录需要迁移")

        for follow_up in customer_follow_ups:
            cleaned_content, next_action = extract_next_action(follow_up.content)
            if next_action:
                follow_up.content = cleaned_content
                follow_up.next_action = next_action
                print(f"  CustomerFollowUp ID={follow_up.id}: 提取 next_action='{next_action[:50]}...'")

        # 3. 迁移操作日志（跟进记录类型）
        operation_logs = db.query(OperationLog).filter(
            OperationLog.event_type == 'MANUAL_FOLLOW_UP'
        ).all()

        # 手动筛选包含"下一步动作"且没有 next_action 字段的日志
        logs_to_migrate = []
        for log in operation_logs:
            content_dict = log.content
            if isinstance(content_dict, dict):
                # 没有 next_action 字段，且 content 包含"下一步动作"
                if not content_dict.get('next_action') and '下一步动作' in str(content_dict.get('content', '')):
                    logs_to_migrate.append(log)

        print(f"找到 {len(logs_to_migrate)} 条操作日志需要迁移")

        for log in logs_to_migrate:
            content_dict = log.content
            original_content = content_dict.get('content', '')
            cleaned_content, next_action = extract_next_action(original_content)
            if next_action:
                # 创建新的 dict 并赋值（SQLAlchemy JSON 字段需要这样处理）
                new_content = {
                    'method': content_dict.get('method'),
                    'content': cleaned_content,
                    'next_follow_up_date': content_dict.get('next_follow_up_date'),
                    'next_action': next_action
                }
                log.content = new_content
                flag_modified(log, 'content')  # 标记 JSON 字段已修改
                print(f"  OperationLog ID={log.id}: 提取 next_action='{next_action[:50]}...'")

        db.commit()
        print("\n迁移完成！")

    except Exception as e:
        db.rollback()
        print(f"迁移失败: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()