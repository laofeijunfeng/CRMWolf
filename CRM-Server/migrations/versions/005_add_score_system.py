"""Add Score System: Weight configs and score fields

Revision ID: 005_add_score_system
Revises: 004_phase2_tables_team
Create Date: 2026-06-01

迁移内容：
- 创建 crm_score_weight_configs 表（权重配置）
- 创建 crm_score_details 表（计算明细）
- 扩展 crm_leads 表（添加 score、score_updated_at）
- 扩展 crm_customers 表（添加 score、score_updated_at）
- 初始化系统默认权重配置
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = '005_add_score_system'
down_revision: Union[str, None] = '004_phase2_tables_team'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建表和扩展字段"""

    # 1. 创建权重配置表
    op.create_table(
        'crm_score_weight_configs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('team_id', sa.BigInteger(), nullable=True, comment='团队ID（NULL表示系统默认）'),
        sa.Column('module_type', sa.String(20), nullable=False, comment='模块类型：LEAD/CUSTOMER'),
        sa.Column('factor_key', sa.String(50), nullable=False, comment='因子键名'),
        sa.Column('factor_name', sa.String(100), nullable=False, comment='因子显示名称'),
        sa.Column('weight_value', sa.Integer(), nullable=False, comment='权重值（正负整数）'),
        sa.Column('is_enabled', sa.Integer(), nullable=False, default=1, comment='是否启用：1启用，0禁用'),
        sa.Column('condition_rules', sa.Text(), nullable=True, comment='条件规则JSON'),
        sa.Column('sort_order', sa.Integer(), nullable=False, default=0, comment='排序序号'),
        sa.Column('created_by', sa.String(100), nullable=False, comment='创建人'),
        sa.Column('created_time', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_by', sa.String(100), nullable=True, comment='更新人'),
        sa.Column('updated_time', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        comment='热力值权重配置表'
    )

    # 创建索引
    op.create_index('idx_score_weight_team_module', 'crm_score_weight_configs', ['team_id', 'module_type'])
    op.create_index('idx_score_weight_factor_key', 'crm_score_weight_configs', ['factor_key'])

    # 2. 创建热力值明细表
    op.create_table(
        'crm_score_details',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('team_id', sa.BigInteger(), nullable=False, comment='团队ID'),
        sa.Column('module_type', sa.String(20), nullable=False, comment='模块类型：LEAD/CUSTOMER'),
        sa.Column('record_id', sa.BigInteger(), nullable=False, comment='线索或客户ID'),
        sa.Column('factor_key', sa.String(50), nullable=False, comment='因子键名'),
        sa.Column('factor_name', sa.String(100), nullable=False, comment='因子名称'),
        sa.Column('weight_value', sa.Integer(), nullable=False, comment='权重值'),
        sa.Column('actual_value', sa.String(200), nullable=True, comment='实际值'),
        sa.Column('score_change', sa.Integer(), nullable=False, comment='分数变化'),
        sa.Column('reason', sa.String(500), nullable=True, comment='计算原因说明'),
        sa.Column('calculated_time', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        comment='热力值计算明细表'
    )

    # 创建索引
    op.create_index('idx_score_detail_record', 'crm_score_details', ['module_type', 'record_id'])
    op.create_index('idx_score_detail_calculated_time', 'crm_score_details', ['calculated_time'])
    op.create_index('idx_score_detail_team_id', 'crm_score_details', ['team_id'])

    # 3. 扩展 crm_leads 表
    op.add_column('crm_leads', sa.Column('score', sa.Integer(), nullable=True, comment='热力值分数（0-100）'))
    op.add_column('crm_leads', sa.Column('score_updated_at', sa.DateTime(), nullable=True, comment='热力值最后更新时间'))

    # 4. 扩展 crm_customers 表
    op.add_column('crm_customers', sa.Column('score', sa.Integer(), nullable=True, comment='热力值分数（0-100）'))
    op.add_column('crm_customers', sa.Column('score_updated_at', sa.DateTime(), nullable=True, comment='热力值最后更新时间'))

    # 5. 初始化系统默认权重配置
    conn = op.get_bind()

    # 线索权重配置
    lead_weights = [
        # factor_key, factor_name, weight_value, condition_rules, sort_order
        ('source', '线索来源', 10, '{"客户推荐": 20, "市场活动": 12, "线上注册": 15, "展会": 10, "网站咨询": 8, "电话营销": 5, "其他": 3}', 1),
        ('company_scale', '公司规模', 8, '{"1000人以上": 15, "501-1000人": 12, "201-500人": 8, "51-200人": 5, "1-50人": 2}', 2),
        ('status', '状态', 5, '{"FOLLOWING": 10, "NEW": 5, "CONVERTED": 0, "INVALID": 0}', 3),
        ('in_pool', '在公海池', -10, None, 4),
        ('last_follow_up_days', '最近跟进时间', 0, '{"<=7": 5, "7-30": -5, ">30": -10, "none": -10}', 5),
        ('next_follow_time', '下次跟进时间', 5, '{"has_plan": 5, "no_plan": 0}', 6),
    ]

    for factor_key, factor_name, weight_value, condition_rules, sort_order in lead_weights:
        conn.execute(text("""
            INSERT INTO crm_score_weight_configs
            (team_id, module_type, factor_key, factor_name, weight_value, is_enabled, condition_rules, sort_order, created_by, created_time, updated_time)
            VALUES (NULL, 'LEAD', :factor_key, :factor_name, :weight_value, 1, :condition_rules, :sort_order, 'system', NOW(), NOW())
        """), {
            'factor_key': factor_key,
            'factor_name': factor_name,
            'weight_value': weight_value,
            'condition_rules': condition_rules,
            'sort_order': sort_order
        })

    # 客户权重配置
    customer_weights = [
        # factor_key, factor_name, weight_value, condition_rules, sort_order
        ('opportunity_count', '商机数量', 10, '{"max_count": 3, "per_count": 10}', 1),
        ('opportunity_amount', '商机金额', 15, '{"per_100k": 1, "max_score": 30}', 2),
        ('opportunity_win_prob', '商机赢率', 12, '{"weighted_by_probability": true}', 3),
        ('contract_count', '合同数量', 15, '{"max_count": 2, "per_count": 15}', 4),
        ('contract_amount', '合同金额', 20, '{"per_100k": 2, "max_score": 40}', 5),
        ('payment_status', '回款状态', 10, '{"COMPLETED": 15, "PARTIAL": 8, "UNPAID": 0, "OVERDUE": -5}', 6),
        ('decision_maker_count', '决策人数量', 8, '{"has_dm": 8, "no_dm": 0}', 7),
        ('primary_contact', '主联系人', 5, '{"has_primary": 5, "no_primary": 0}', 8),
        ('status', '客户状态', 5, '{"WON": 20, "FOLLOWING": 10, "LOST": -10, "INACTIVE": -15}', 9),
        ('return_count', '退回公海次数', -10, '{"has_return": -10, "no_return": 0}', 10),
    ]

    for factor_key, factor_name, weight_value, condition_rules, sort_order in customer_weights:
        conn.execute(text("""
            INSERT INTO crm_score_weight_configs
            (team_id, module_type, factor_key, factor_name, weight_value, is_enabled, condition_rules, sort_order, created_by, created_time, updated_time)
            VALUES (NULL, 'CUSTOMER', :factor_key, :factor_name, :weight_value, 1, :condition_rules, :sort_order, 'system', NOW(), NOW())
        """), {
            'factor_key': factor_key,
            'factor_name': factor_name,
            'weight_value': weight_value,
            'condition_rules': condition_rules,
            'sort_order': sort_order
        })


def downgrade() -> None:
    """降级：删除表和字段"""

    # 1. 删除扩展字段
    op.drop_column('crm_customers', 'score_updated_at')
    op.drop_column('crm_customers', 'score')
    op.drop_column('crm_leads', 'score_updated_at')
    op.drop_column('crm_leads', 'score')

    # 2. 删除表
    op.drop_index('idx_score_detail_team_id', 'crm_score_details')
    op.drop_index('idx_score_detail_calculated_time', 'crm_score_details')
    op.drop_index('idx_score_detail_record', 'crm_score_details')
    op.drop_table('crm_score_details')

    op.drop_index('idx_score_weight_factor_key', 'crm_score_weight_configs')
    op.drop_index('idx_score_weight_team_module', 'crm_score_weight_configs')
    op.drop_table('crm_score_weight_configs')