-- Phase 1.1: 添加 account_name_norm 归一化列（R-ST-02）MySQL 版本
-- 注意：MySQL 不支持 pg_trgm 扩展，使用普通索引 + LIKE 搜索

-- 1. 添加归一化列
ALTER TABLE crm_customers
ADD COLUMN account_name_norm VARCHAR(255) COMMENT '归一化客户名称（去后缀/括号）';

-- 2. 创建普通索引（用于 LIKE 搜索）
CREATE INDEX idx_account_name_norm ON crm_customers (account_name_norm);

-- 3. 创建前缀索引（优化 LIKE 'xxx%' 搜索）
-- MySQL 前缀索引：只索引前 N 个字符
CREATE INDEX idx_account_name_norm_prefix ON crm_customers (account_name_norm(20));

-- 验证索引
-- SHOW INDEX FROM crm_customers;

-- 注意：MySQL 全文搜索（FULLTEXT）需要中文分词器插件
-- 当前方案使用 LIKE 搜索 + 三阶降级（性能足够）