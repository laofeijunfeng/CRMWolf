"""create industries table + fix profile_error_message length

Revision ID: 006_industries
Revises: 005_add_score_system
Create Date: 2026-06-05

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_industries'
down_revision = '005_add_score_system'
branch_labels = None
depends_on = None


def upgrade():
    # 1. 扩展 profile_error_message 字段长度（避免错误信息过长）
    op.execute("ALTER TABLE crm_customers MODIFY COLUMN profile_error_message TEXT")

    # 2. 创建行业分级表
    op.create_table(
        'crm_industries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('level', sa.Integer(), nullable=False, comment='层级：1=一级行业，2=二级行业'),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('crm_industries.id'), nullable=True, comment='父行业ID'),
        sa.Column('code', sa.String(50), nullable=False, comment='行业编码'),
        sa.Column('name', sa.String(100), nullable=False, comment='行业名称'),
        sa.Column('sort_order', sa.Integer(), default=0, comment='排序'),
        sa.Column('is_active', sa.Integer(), default=1, comment='是否启用'),
        sa.Column('created_time', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='创建时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        comment='行业分级表'
    )

    # 插入一级行业数据
    op.execute("""
        INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES
        (1, NULL, 'it', '信息技术', 1, 1),
        (1, NULL, 'finance', '金融', 2, 1),
        (1, NULL, 'manufacture', '制造业', 3, 1),
        (1, NULL, 'healthcare', '医疗健康', 4, 1),
        (1, NULL, 'education', '教育', 5, 1),
        (1, NULL, 'retail', '零售', 6, 1),
        (1, NULL, 'real_estate', '房地产', 7, 1),
        (1, NULL, 'logistics', '物流运输', 8, 1),
        (1, NULL, 'energy', '能源', 9, 1),
        (1, NULL, 'media', '传媒', 10, 1),
        (1, NULL, 'consulting', '咨询', 11, 1),
        (1, NULL, 'government', '政府机构', 12, 1),
        (1, NULL, 'other', '其他', 13, 1)
    """)

    # 插入二级行业数据（信息技术）
    op.execute("""
        INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES
        (2, (SELECT id FROM crm_industries WHERE code='it'), 'it_software', '软件开发', 1, 1),
        (2, (SELECT id FROM crm_industries WHERE code='it'), 'it_hardware', '硬件设备', 2, 1),
        (2, (SELECT id FROM crm_industries WHERE code='it'), 'it_internet', '互联网', 3, 1),
        (2, (SELECT id FROM crm_industries WHERE code='it'), 'it_telecom', '通信', 4, 1),
        (2, (SELECT id FROM crm_industries WHERE code='it'), 'it_ai', '人工智能', 5, 1)
    """)

    # 插入二级行业数据（金融）
    op.execute("""
        INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES
        (2, (SELECT id FROM crm_industries WHERE code='finance'), 'finance_bank', '银行', 1, 1),
        (2, (SELECT id FROM crm_industries WHERE code='finance'), 'finance_security', '证券', 2, 1),
        (2, (SELECT id FROM crm_industries WHERE code='finance'), 'finance_insurance', '保险', 3, 1),
        (2, (SELECT id FROM crm_industries WHERE code='finance'), 'finance_fund', '基金', 4, 1),
        (2, (SELECT id FROM crm_industries WHERE code='finance'), 'finance_leasing', '融资租赁', 5, 1)
    """)

    # 插入二级行业数据（制造业）
    op.execute("""
        INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES
        (2, (SELECT id FROM crm_industries WHERE code='manufacture'), 'manufacture_auto', '汽车制造', 1, 1),
        (2, (SELECT id FROM crm_industries WHERE code='manufacture'), 'manufacture_electronic', '电子制造', 2, 1),
        (2, (SELECT id FROM crm_industries WHERE code='manufacture'), 'manufacture_machinery', '机械制造', 3, 1),
        (2, (SELECT id FROM crm_industries WHERE code='manufacture'), 'manufacture_chemical', '化工', 4, 1)
    """)

    # 插入二级行业数据（医疗健康）
    op.execute("""
        INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES
        (2, (SELECT id FROM crm_industries WHERE code='healthcare'), 'healthcare_hospital', '医院', 1, 1),
        (2, (SELECT id FROM crm_industries WHERE code='healthcare'), 'healthcare_device', '医疗器械', 2, 1),
        (2, (SELECT id FROM crm_industries WHERE code='healthcare'), 'healthcare_pharma', '制药', 3, 1),
        (2, (SELECT id FROM crm_industries WHERE code='healthcare'), 'healthcare_service', '医疗服务', 4, 1)
    """)


def downgrade():
    op.drop_table('crm_industries')