"""
创建 API Key 和 API 调用日志表的迁移脚本
"""
from app.core.database import SessionLocal
from sqlalchemy import text


def upgrade():
    db = SessionLocal()
    try:
        print("开始迁移：创建 API Key 和 API 调用日志表...")

        # 创建 API Key 表
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_api_keys (
                id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
                key_id VARCHAR(32) NOT NULL UNIQUE COMMENT 'API Key ID（对外展示）',
                api_key_hash VARCHAR(64) NOT NULL UNIQUE COMMENT 'API Key哈希值（SHA-256）',
                app_name VARCHAR(100) NOT NULL COMMENT '应用名称',
                description TEXT NULL COMMENT '应用描述',
                permissions JSON NULL COMMENT '权限列表，如：[\"customer:read\", \"customer:list\"]',
                ip_whitelist JSON NULL COMMENT 'IP白名单列表',
                rate_limit_tps INT NOT NULL DEFAULT 100 COMMENT '每秒请求限制（TPS）',
                status ENUM('active', 'inactive', 'revoked') NOT NULL DEFAULT 'active' COMMENT '状态',
                expires_at DATETIME NULL COMMENT '过期时间（NULL表示永不过期）',
                last_used_at DATETIME NULL COMMENT '最后使用时间',
                created_by BIGINT NULL COMMENT '创建人ID',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_key_id (key_id),
                INDEX idx_status (status),
                INDEX idx_app_name (app_name),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='API Key管理表'
        """))
        print("✓ crm_api_keys 表已创建")

        # 创建 API 调用日志表
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_api_call_logs (
                id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
                key_id VARCHAR(32) NOT NULL COMMENT 'API Key ID',
                app_name VARCHAR(100) NULL COMMENT '应用名称',
                request_method VARCHAR(10) NOT NULL COMMENT '请求方法（GET/POST/PUT/PATCH/DELETE）',
                request_path VARCHAR(255) NOT NULL COMMENT '请求路径',
                request_params JSON NULL COMMENT '请求参数（脱敏后）',
                request_body TEXT NULL COMMENT '请求体（脱敏后）',
                response_code INT NOT NULL COMMENT '响应码',
                response_body TEXT NULL COMMENT '响应体（脱敏后）',
                client_ip VARCHAR(50) NULL COMMENT '客户端IP',
                user_agent VARCHAR(255) NULL COMMENT 'User-Agent',
                duration_ms INT NOT NULL COMMENT '请求耗时（毫秒）',
                request_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '请求时间',
                INDEX idx_key_id (key_id),
                INDEX idx_request_path (request_path),
                INDEX idx_request_time (request_time),
                INDEX idx_response_code (response_code),
                INDEX idx_app_name (app_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='API调用日志表'
        """))
        print("✓ crm_api_call_logs 表已创建")

        db.commit()
        print("迁移完成！")

    except Exception as e:
        print(f"迁移失败: {e}")
        db.rollback()
    finally:
        db.close()


def downgrade():
    db = SessionLocal()
    try:
        print("开始回滚：删除 API Key 和 API 调用日志表...")

        db.execute(text("DROP TABLE IF EXISTS crm_api_call_logs"))
        print("✓ crm_api_call_logs 表已删除")

        db.execute(text("DROP TABLE IF EXISTS crm_api_keys"))
        print("✓ crm_api_keys 表已删除")

        db.commit()
        print("回滚完成！")

    except Exception as e:
        print(f"回滚失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()