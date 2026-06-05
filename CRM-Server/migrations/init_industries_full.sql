-- 行业分级表初始化 SQL

-- 1. 创建行业分级表
CREATE TABLE IF NOT EXISTS crm_industries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    level INT NOT NULL,
    parent_id INT NULL,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    sort_order INT DEFAULT 0,
    is_active INT DEFAULT 1,
    created_time DATETIME NOT NULL DEFAULT NOW(),
    FOREIGN KEY (parent_id) REFERENCES crm_industries(id)
);

-- 2. 修复字段长度
ALTER TABLE crm_customers MODIFY COLUMN profile_error_message TEXT;

-- 一级行业
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'finance', '金融', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'internet', '互联网', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'manufacturing', '制造业', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'retail', '零售', 4, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'education', '教育', 5, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'healthcare', '医疗', 6, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'real_estate', '房地产', 7, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'government', '政府', 8, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'logistics', '物流', 9, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'energy', '能源', 10, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'telecom', '通信', 11, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'construction', '建筑', 12, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'agriculture', '农业', 13, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'entertainment', '娱乐', 14, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'consulting', '咨询', 15, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (1, NULL, 'other', '其他', 16, 1);

-- 二级行业
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='consulting'), 'consulting_strategy', '战略咨询', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='entertainment'), 'entertainment_media', '媒体', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='agriculture'), 'agriculture_farming', '种植', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='construction'), 'construction_engineering', '工程建筑', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='telecom'), 'telecom_operator', '运营商', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='energy'), 'energy_oil', '石油', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='logistics'), 'logistics_express', '快递', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='government'), 'government_central', '中央政府', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='real_estate'), 'real_estate_developer', '开发商', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='healthcare'), 'healthcare_hospital', '医院', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='education'), 'education_k12', 'K12教育', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='retail'), 'retail_supermarket', '超市连锁', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='internet'), 'internet_ecommerce', '电商平台', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='finance'), 'finance_bank', '银行', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='manufacturing'), 'manufacturing_auto', '汽车制造', 1, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='government'), 'government_local', '地方政府', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='telecom'), 'telecom_service', '通信服务', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='construction'), 'construction_design', '建筑设计', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='real_estate'), 'real_estate_agent', '中介服务', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='internet'), 'internet_saas', 'SaaS公司', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='agriculture'), 'agriculture_breeding', '养殖', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='logistics'), 'logistics_shipping', '航运', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='healthcare'), 'healthcare_pharma', '制药', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='finance'), 'finance_insurance', '保险', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='entertainment'), 'entertainment_game', '游戏', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='energy'), 'energy_gas', '天然气', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='education'), 'education_higher', '高等教育', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='retail'), 'retail_brand', '品牌零售', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='manufacturing'), 'manufacturing_electronics', '电子制造', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='consulting'), 'consulting_it', 'IT咨询', 2, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='agriculture'), 'agriculture_processing', '农产品加工', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='energy'), 'energy_electric', '电力', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='finance'), 'finance_securities', '证券', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='consulting'), 'consulting_hr', '人力资源咨询', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='entertainment'), 'entertainment_sports', '体育', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='manufacturing'), 'manufacturing_machinery', '机械设备', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='logistics'), 'logistics_warehouse', '仓储', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='government'), 'government_public', '公共机构', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='internet'), 'internet_social', '社交媒体', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='real_estate'), 'real_estate_manage', '物业管理', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='healthcare'), 'healthcare_device', '医疗器械', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='education'), 'education_training', '职业培训', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='retail'), 'retail_online', '网络零售', 3, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='energy'), 'energy_new', '新能源', 4, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='finance'), 'finance_fund', '基金', 4, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='internet'), 'internet_content', '内容平台', 4, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='healthcare'), 'healthcare_service', '医疗服务', 4, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='education'), 'education_online', '在线教育', 4, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='manufacturing'), 'manufacturing_chemical', '化工', 4, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='finance'), 'finance_payment', '支付', 5, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='internet'), 'internet_fintech', '金融科技', 5, 1);
INSERT INTO crm_industries (level, parent_id, code, name, sort_order, is_active) VALUES (2, (SELECT id FROM crm_industries WHERE code='manufacturing'), 'manufacturing_food', '食品加工', 5, 1);

SELECT COUNT(*) FROM crm_industries;
