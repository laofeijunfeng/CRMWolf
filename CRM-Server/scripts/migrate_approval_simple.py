from app.core.database import get_db
from sqlalchemy import text

def create_approval_tables():
    db = next(get_db())
    
    try:
        print("开始创建审批流程表...")
        
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_approval_flows (
                id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                flow_name VARCHAR(100) NOT NULL COMMENT '审批流程名称',
                flow_code VARCHAR(50) NOT NULL COMMENT '流程编码',
                description TEXT COMMENT '流程描述',
                min_amount DECIMAL(12, 2) COMMENT '最小金额（条件）',
                max_amount DECIMAL(12, 2) COMMENT '最大金额（条件）',
                license_type VARCHAR(20) COMMENT '授权类型（条件）',
                is_active INT NOT NULL DEFAULT 1 COMMENT '是否启用：0:否, 1:是',
                created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                last_modified_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后修改时间',
                PRIMARY KEY (id),
                UNIQUE KEY uk_flow_code (flow_code),
                KEY idx_flow_active (is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审批流程模板表'
        """))
        print("✅ 创建 crm_approval_flows 表")
        
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_approval_nodes (
                id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                flow_id BIGINT NOT NULL COMMENT '审批流程ID',
                node_name VARCHAR(100) NOT NULL COMMENT '节点名称',
                node_code VARCHAR(50) NOT NULL COMMENT '节点编码',
                node_order INT NOT NULL COMMENT '节点顺序',
                description TEXT COMMENT '节点描述',
                approve_role VARCHAR(50) COMMENT '审批角色（TEAM_ADMIN, SALES_DIRECTOR等）',
                is_required INT NOT NULL DEFAULT 1 COMMENT '是否必须审批：0:否, 1:是',
                created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                PRIMARY KEY (id),
                KEY idx_node_flow (flow_id),
                KEY idx_node_order (node_order),
                CONSTRAINT fk_node_flow FOREIGN KEY (flow_id) REFERENCES crm_approval_flows (id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审批节点表'
        """))
        print("✅ 创建 crm_approval_nodes 表")
        
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_contract_approvals (
                id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                contract_id BIGINT NOT NULL COMMENT '关联合同ID',
                flow_id BIGINT COMMENT '审批流程模板ID',
                current_node_id BIGINT COMMENT '当前审批节点ID',
                status VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT '审批状态：PENDING, APPROVED, REJECTED, CANCELLED',
                submitter_id VARCHAR(100) NOT NULL COMMENT '提交人飞书用户ID',
                submitter_name VARCHAR(100) COMMENT '提交人姓名',
                created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
                PRIMARY KEY (id),
                KEY idx_approval_contract (contract_id),
                KEY idx_approval_status (status),
                KEY idx_approval_flow (flow_id),
                CONSTRAINT fk_approval_contract FOREIGN KEY (contract_id) REFERENCES crm_contracts (id) ON DELETE CASCADE,
                CONSTRAINT fk_approval_flow FOREIGN KEY (flow_id) REFERENCES crm_approval_flows (id) ON DELETE SET NULL,
                CONSTRAINT fk_approval_current_node FOREIGN KEY (current_node_id) REFERENCES crm_approval_nodes (id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='合同审批实例表'
        """))
        print("✅ 创建 crm_contract_approvals 表")
        
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_contract_approval_records (
                id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                approval_id BIGINT NOT NULL COMMENT '审批实例ID',
                node_id BIGINT COMMENT '审批节点ID',
                approver_id VARCHAR(100) NOT NULL COMMENT '审批人飞书用户ID',
                approver_name VARCHAR(100) COMMENT '审批人姓名',
                action VARCHAR(20) NOT NULL COMMENT '操作：SUBMIT, APPROVE, REJECT, ROLLBACK',
                comment TEXT COMMENT '审批意见',
                created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
                PRIMARY KEY (id),
                KEY idx_record_approval (approval_id),
                KEY idx_record_node (node_id),
                KEY idx_record_approver (approver_id),
                CONSTRAINT fk_record_approval FOREIGN KEY (approval_id) REFERENCES crm_contract_approvals (id) ON DELETE CASCADE,
                CONSTRAINT fk_record_node FOREIGN KEY (node_id) REFERENCES crm_approval_nodes (id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='合同审批记录表'
        """))
        print("✅ 创建 crm_contract_approval_records 表")
        
        db.commit()
        
        print("\n开始插入默认审批流程数据...")
        
        db.execute(text("""
            INSERT IGNORE INTO crm_approval_flows 
            (flow_name, flow_code, description, min_amount, max_amount, license_type, is_active) 
            VALUES 
            ('小额合同审批', 'SMALL_CONTRACT', '金额小于10万的合同，仅需销售总监审批', 0, 100000, NULL, 1),
            ('中等金额合同审批', 'MEDIUM_CONTRACT', '金额10万-50万的合同，需销售总监和财务审批', 100000, 500000, NULL, 1),
            ('大额合同审批', 'LARGE_CONTRACT', '金额大于50万的合同，需销售总监、财务和系统管理员审批', 500000, NULL, NULL, 1)
        """))
        print("✅ 插入审批流程数据")
        
        db.execute(text("""
            INSERT IGNORE INTO crm_approval_nodes (flow_id, node_name, node_code, node_order, description, approve_role, is_required)
            SELECT f.id, '销售总监审批', 'SALES_DIRECTOR_APPROVE', 1, '销售总监审批', 'SALES_DIRECTOR', 1
            FROM crm_approval_flows f WHERE f.flow_code IN ('SMALL_CONTRACT', 'MEDIUM_CONTRACT', 'LARGE_CONTRACT')
        """))
        print("✅ 插入销售总监审批节点")
        
        db.execute(text("""
            INSERT IGNORE INTO crm_approval_nodes (flow_id, node_name, node_code, node_order, description, approve_role, is_required)
            SELECT f.id, '财务审批', 'FINANCE_APPROVE', 2, '财务审批', 'SALES_DIRECTOR', 1
            FROM crm_approval_flows f WHERE f.flow_code IN ('MEDIUM_CONTRACT', 'LARGE_CONTRACT')
        """))
        print("✅ 插入财务审批节点")
        
        db.execute(text("""
            INSERT IGNORE INTO crm_approval_nodes (flow_id, node_name, node_code, node_order, description, approve_role, is_required)
            SELECT f.id, '系统管理员审批', 'ADMIN_APPROVE', 3, '系统管理员审批', 'SALES_DIRECTOR', 1
            FROM crm_approval_flows f WHERE f.flow_code = 'LARGE_CONTRACT'
        """))
        print("✅ 插入系统管理员审批节点")
        
        db.commit()
        
        print("\n验证创建结果...")
        tables = db.execute(text("SHOW TABLES LIKE 'crm_approval%'"))
        print("✅ 创建的审批表：")
        for row in tables:
            print(f"  - {row[0]}")
        
        flows = db.execute(text("SELECT flow_name, flow_code FROM crm_approval_flows"))
        print("\n审批流程列表：")
        for row in flows:
            print(f"  - {row[0]} ({row[1]})")
        
        print("\n✅ 所有审批流程表创建完成！")
        
    except Exception as e:
        print(f"❌ 创建审批表失败: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_approval_tables()
