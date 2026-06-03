-- Phase 1.1: 添加 account_name_norm 归一化列（R-ST-02）
-- 执行前请确认 pg_trgm 扩展已安装

-- 1. 启用 pg_trgm 扩展（如果未安装）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. 添加归一化列
ALTER TABLE crm_customers
ADD COLUMN account_name_norm VARCHAR(255) COMMENT '归一化客户名称（去后缀/括号）';

-- 3. 创建 GIN 索引（pg_trgm 三字母相似度）
CREATE INDEX idx_account_name_norm_gin
ON crm_customers
USING gin (account_name_norm gin_trgm_ops);

-- 4. 商机表同理（可选，如需商机名称归一化）
-- ALTER TABLE crm_opportunities
-- ADD COLUMN opportunity_name_norm VARCHAR(255);
-- CREATE INDEX idx_opportunity_name_norm_gin
-- ON crm_opportunities USING gin (opportunity_name_norm gin_trgm_ops);

-- 验证索引
-- SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'crm_customers';