-- 行业分级表初始化 SQL
-- 直接在 MySQL 中执行此文件

-- 1. 创建行业分级表
CREATE TABLE IF NOT EXISTS \`crm_industries\` (
    \`id\` INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    \`level\` INT NOT NULL COMMENT '层级：1=一级行业，2=二级行业',
    \`parent_id\` INT NULL COMMENT '父行业ID',
    \`code\` VARCHAR(50) NOT NULL UNIQUE COMMENT '行业编码',
    \`name\` VARCHAR(100) NOT NULL COMMENT '行业名称',
    \`sort_order\` INT DEFAULT 0 COMMENT '排序',
    \`is_active\` INT DEFAULT 1 COMMENT '是否启用',
    \`created_time\` DATETIME NOT NULL DEFAULT NOW() COMMENT '创建时间',
    FOREIGN KEY (\`parent_id\`) REFERENCES \`crm_industries\`(\`id\`),
    COMMENT='行业分级表'
);

-- 2. 修复字段长度问题
ALTER TABLE \`crm_customers\` MODIFY COLUMN \`profile_error_message\` TEXT;

-- 3. 插入一级行业数据
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES
(1, NULL, 'finance', '金融', 1, 1),
(1, NULL, 'internet', '互联网', 2, 1),
(1, NULL, 'manufacturing', '制造业', 3, 1),
(1, NULL, 'retail', '零售', 4, 1),
(1, NULL, 'education', '教育', 5, 1),
(1, NULL, 'healthcare', '医疗', 6, 1),
(1, NULL, 'real_estate', '房地产', 7, 1),
(1, NULL, 'government', '政府', 8, 1),
(1, NULL, 'logistics', '物流', 9, 1),
(1, NULL, 'energy', '能源', 10, 1),
(1, NULL, 'telecom', '通信', 11, 1),
(1, NULL, 'construction', '建筑', 12, 1),
(1, NULL, 'agriculture', '农业', 13, 1),
(1, NULL, 'entertainment', '娱乐', 14, 1),
(1, NULL, 'consulting', '咨询', 15, 1),
(1, NULL, 'other', '其他', 16, 1);

-- 4-18. 二级行业数据见完整文件
