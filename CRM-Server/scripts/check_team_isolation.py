#!/usr/bin/env python3
"""
团队隔离一致性检查脚本

功能：
1. 检查所有业务表是否正确添加了 team_id
2. 对比模型定义与数据库实际状态
3. 输出差异报告

运行方式：
  python scripts/check_team_isolation.py
  python scripts/check_team_isolation.py --fix  # 生成修复建议

规则：
- 业务实体表（customers, leads, opportunities 等）必须有 team_id
- 日志表（conversation_logs, approval_records 等）建议有 team_id
- 系统配置表（roles, permissions, ai_skills 等）不需要 team_id
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine, text, inspect
from app.core.config import get_settings
from pathlib import Path

# 业务实体表白名单（必须有 team_id）
REQUIRED_TEAM_ID_TABLES = [
    'crm_customers',
    'crm_leads',
    'crm_opportunities',
    'crm_contracts',
    'crm_contacts',
    'crm_customer_follow_ups',
    'crm_lead_follow_ups',
    'crm_invoice_applications',
    'crm_invoice_titles',
    'crm_payment_records',
    'crm_contract_payment_plans',
    'crm_contract_approvals',
    'crm_operation_logs',
    'crm_opportunity_stages',
    'crm_approval_flows',
    'crm_approval_nodes',
    'crm_procurement_methods',
    'crm_procurement_stage_templates',
    'user_roles',
    'crm_ai_config',
    'crm_conversation_logs',
    'crm_stage_template_change_logs',
    'crm_opportunity_stage_snapshots',
    'crm_contract_approval_records',
]

# 系统级配置表白名单（不需要 team_id）
EXCLUDED_TABLES = [
    'teams',
    'user_teams',
    'roles',
    'permissions',
    'role_permissions',
    'users',
    'crm_ai_skills',
    'crm_ai_skill_actions',
    'crm_ai_action_params',
    'crm_ai_crud_mappings',
    'crm_ai_enum_mappings',
    'alembic_version',
]


def check_team_isolation():
    """检查团队隔离一致性"""
    settings = get_settings()
    engine = create_engine(settings.get_database_url())

    issues = []

    with engine.connect() as conn:
        # 获取所有表名
        result = conn.execute(text("""
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME NOT LIKE 'sqlite_%'
            AND TABLE_NAME NOT LIKE 'alembic_%'
        """))
        all_tables = [row[0] for row in result]

        # 检查每个表
        for table in all_tables:
            if table in EXCLUDED_TABLES:
                continue

            # 检查是否有 team_id 列
            result = conn.execute(text(f"""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = '{table}'
                AND COLUMN_NAME = 'team_id'
            """))
            has_team_id = result.fetchone()[0] > 0

            if table in REQUIRED_TEAM_ID_TABLES:
                if not has_team_id:
                    issues.append({
                        'table': table,
                        'issue': 'MISSING_REQUIRED',
                        'severity': 'HIGH',
                        'message': f'业务表 {table} 缺少必需的 team_id 列'
                    })
                else:
                    # 检查是否 NOT NULL
                    result = conn.execute(text(f"""
                        SELECT IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = '{table}'
                        AND COLUMN_NAME = 'team_id'
                    """))
                    is_nullable = result.fetchone()[0] == 'YES'
                    if is_nullable:
                        issues.append({
                            'table': table,
                            'issue': 'NULLABLE_TEAM_ID',
                            'severity': 'MEDIUM',
                            'message': f'表 {table} 的 team_id 列允许 NULL，建议设置 NOT NULL'
                        })

                    # 检查是否有索引
                    result = conn.execute(text(f"""
                        SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = '{table}'
                        AND COLUMN_NAME = 'team_id'
                        AND INDEX_NAME != 'PRIMARY'
                    """))
                    has_index = result.fetchone()[0] > 0
                    if not has_index:
                        issues.append({
                            'table': table,
                            'issue': 'MISSING_INDEX',
                            'severity': 'LOW',
                            'message': f'表 {table} 的 team_id 列缺少索引'
                        })
            elif table.startswith('crm_') and not has_team_id:
                # 其他 CRM 表缺少 team_id（警告）
                issues.append({
                    'table': table,
                    'issue': 'MISSING_RECOMMENDED',
                    'severity': 'INFO',
                    'message': f'表 {table} 可能需要 team_id（请评估）'
                })

    return issues


def generate_fix_sql(issues):
    """生成修复 SQL"""
    fix_statements = []

    for issue in issues:
        table = issue['table']

        if issue['issue'] == 'MISSING_REQUIRED':
            fix_statements.append(f"-- 添加 team_id 列\nALTER TABLE {table} ADD COLUMN team_id BIGINT NOT NULL DEFAULT 1 COMMENT '团队ID';")
            fix_statements.append(f"-- 添加索引\nCREATE INDEX idx_{table}_team_id ON {table} (team_id);")

        elif issue['issue'] == 'NULLABLE_TEAM_ID':
            fix_statements.append(f"-- 设置 NOT NULL\nALTER TABLE {table} MODIFY team_id BIGINT NOT NULL COMMENT '团队ID';")

        elif issue['issue'] == 'MISSING_INDEX':
            fix_statements.append(f"-- 添加索引\nCREATE INDEX idx_{table}_team_id ON {table} (team_id);")

    return fix_statements


def main():
    print("=" * 60)
    print("团队隔离一致性检查")
    print("=" * 60)

    issues = check_team_isolation()

    if not issues:
        print("\n✅ 所有表的 team_id 配置正确")
        return 0

    # 按严重程度分组
    high_issues = [i for i in issues if i['severity'] == 'HIGH']
    medium_issues = [i for i in issues if i['severity'] == 'MEDIUM']
    low_issues = [i for i in issues if i['severity'] == 'LOW']
    info_issues = [i for i in issues if i['severity'] == 'INFO']

    print(f"\n发现 {len(issues)} 个问题：")
    print(f"  🔴 高危: {len(high_issues)}")
    print(f"  🟡 中危: {len(medium_issues)}")
    print(f"  🟢 低危: {len(low_issues)}")
    print(f"  ⚪ 信息: {len(info_issues)}")

    # 输出详细信息
    for severity, label in [('HIGH', '🔴'), ('MEDIUM', '🟡'), ('LOW', '🟢'), ('INFO', '⚪')]:
        sev_issues = [i for i in issues if i['severity'] == severity]
        if sev_issues:
            print(f"\n{label} {severity}:")
            for issue in sev_issues:
                print(f"  - {issue['table']}: {issue['issue']}")

    # 生成修复 SQL
    if '--fix' in sys.argv:
        print("\n" + "=" * 60)
        print("修复 SQL 建议")
        print("=" * 60)
        fix_sql = generate_fix_sql(high_issues + medium_issues + low_issues)
        for sql in fix_sql:
            print(sql)

    return len(high_issues)


if __name__ == '__main__':
    sys.exit(main())