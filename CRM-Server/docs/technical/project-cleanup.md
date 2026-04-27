# 项目文件整理说明

本文档记录了CRM项目的文件整理和文档规范工作。

## 📁 新目录结构

```
CRM/
├── app/                    # 应用主目录
│   ├── api/               # API 路由
│   ├── core/              # 核心配置
│   ├── models/            # 数据库模型
│   ├── schemas/           # Pydantic 模式
│   ├── crud/              # 数据库操作层
│   ├── services/          # 业务逻辑层
│   └── main.py            # 应用入口
│
├── docs/                  # 📚 文档目录（新增）
│   ├── business/          # 业务流程文档
│   │   ├── 00-overview.md
│   │   ├── 01-lead-management.md
│   │   ├── 02-customer-management.md
│   │   ├── 03-opportunity-management.md
│   │   └── 04-contract-management.md
│   │
│   ├── technical/         # 技术文档
│   │   ├── 00-development-guide.md
│   │   ├── 02-exception-handling.md
│   │   ├── 03-feishu-login.md
│   │   ├── 04-user-api-optimization.md
│   │   └── 05-approval-workflow.md
│   │
│   └── README.md          # 文档导航
│
├── tests/                 # 🧪 测试脚本（新增）
│   ├── test_leads.py
│   ├── test_customers.py
│   ├── test_opportunities.py
│   ├── test_contracts.py
│   └── test_approval_workflow.py
│
├── scripts/               # 🔧 工具脚本（新增）
│   ├── init_db.py
│   ├── migrate_*.py
│   ├── check_*.py
│   └── fix_*.py
│
├── migrations/            # 数据库迁移
│   └── *.py
│
└── README.md              # 项目说明（新增）
```

## 📝 文档命名规范

### 业务文档（`docs/business/`）

格式：`{编号}-{模块名}-{类型}.md`

- `00` - 概览性文档
- `01-99` - 具体模块文档

示例：
- `00-overview.md` - 业务流程概览
- `01-lead-management.md` - 线索管理流程

### 技术文档（`docs/technical/`）

格式：`{编号}-{主题名}.md`

- `00` - 开发指南等核心文档
- `01-99` - 具体技术主题

示例：
- `00-development-guide.md` - 开发指南
- `05-approval-workflow.md` - 合同审批流程

## 🔄 文件迁移记录

### 根目录文件整理

| 原文件 | 新位置 | 说明 |
|--------|--------|------|
| `*.md` | `docs/technical/` | 技术文档移至技术文档目录 |
| `test_*.py` | `tests/` | 测试脚本统一管理 |
| `check_*.py` | `scripts/` | 检查脚本移至工具目录 |
| `fix_*.py` | `scripts/` | 修复脚本移至工具目录 |
| `migrate_*.py` | `scripts/` | 迁移脚本移至工具目录 |
| `init_*.py` | `scripts/` | 初始化脚本移至工具目录 |
| `*.html` | 删除 | 示例文件已删除 |
| `*.sql` | 删除 | SQL脚本已整合到Python脚本中 |

### 新增文档

| 文档 | 位置 | 说明 |
|------|------|------|
| `README.md` | 根目录 | 项目说明文档 |
| `README.md` | `docs/` | 文档导航索引 |
| `00-overview.md` | `docs/business/` | 业务流程概览 |
| `01-lead-management.md` | `docs/business/` | 线索管理流程 |
| `02-customer-management.md` | `docs/business/` | 客户管理流程 |
| `03-opportunity-management.md` | `docs/business/` | 商机管理流程 |
| `04-contract-management.md` | `docs/business/` | 合同管理流程 |

## 📋 业务文档内容

### 00-overview.md - 业务流程概览

**内容要点：**
- 系统概述和核心模块介绍
- 完整业务流程时序图
- 数据流转关系说明
- 角色与权限说明
- 关键业务规则
- 统计与分析指标
- 飞书集成说明
- 最佳实践和常见问题

**适用人群：** 所有人，特别是新用户

### 01-lead-management.md - 线索管理流程

**内容要点：**
- 线索生命周期（新线索 → 跟进中 → 已转化/已输单）
- 线索状态和来源说明
- 线索分配和领取规则
- 线索跟进要求
- 线索转化条件
- 线索输单处理
- 公海池管理
- 权限控制和数据统计

**适用人群：** 销售人员、销售总监

### 02-customer-management.md - 客户管理流程

**内容要点：**
- 客户生命周期（潜在客户 → 跟进中 → 已成交/已输单）
- 客户状态说明
- 客户创建方式（线索转化、手动创建、批量导入）
- 客户分配规则
- 客户信息管理
- 客户联系人管理
- 客户退回公海
- 权限控制和数据统计

**适用人群：** 销售人员、销售总监

### 03-opportunity-management.md - 商机管理流程

**内容要点：**
- 商机生命周期（创建 → 跟进中 → 赢单/输单）
- 销售阶段定义（5个预置阶段）
- 阶段推进规则
- 商机创建方式
- 商机跟进要求
- 商机赢单条件
- 商机输单处理
- 销售漏斗管理
- 权限控制和数据统计

**适用人群：** 销售人员、销售总监

### 04-contract-management.md - 合同管理流程

**内容要点：**
- 合同生命周期（草稿 → 审批中 → 待签署 → 已签署 → 已完成）
- 合同状态说明
- 合同创建方式（从赢单商机创建、手动创建）
- 合同草稿管理
- 合同提交审批
- 合同审批流程（3个预置流程）
- 合同签署和履行
- 权限控制和数据统计

**适用人群：** 销售人员、销售总监、系统管理员

## 🎯 使用指南

### 新用户入职

1. 阅读 [README.md](../README.md) 了解项目概况
2. 阅读 [业务流程概览](./business/00-overview.md) 理解业务流程
3. 根据角色阅读对应的业务流程文档
4. 参考常见问题快速上手

### 开发人员入职

1. 阅读 [README.md](../README.md) 了解项目概况
2. 阅读 [开发指南](./technical/00-development-guide.md) 搭建开发环境
3. 熟悉项目结构和代码规范
4. 查看技术文档了解实现细节

### 业务人员使用

1. 阅读 [业务流程概览](./business/00-overview.md) 理解整体流程
2. 深入阅读相关业务模块文档
3. 参考最佳实践优化工作流程
4. 查看常见问题解决疑问

## 📚 文档维护

### 维护原则

1. **及时更新**：业务流程变更时及时更新文档
2. **准确完整**：确保文档内容准确、完整
3. **易于理解**：使用清晰的语言和示例
4. **版本控制**：重要变更记录在文档中

### 更新触发条件

- 新增功能时补充文档
- 业务流程变更时更新文档
- 发现文档错误时修正
- 定期review文档准确性

## ✅ 整理成果

### 目录结构优化

- ✅ 创建专门的文档目录 `docs/`
- ✅ 分离业务文档和技术文档
- ✅ 创建测试脚本目录 `tests/`
- ✅ 创建工具脚本目录 `scripts/`

### 文档规范化

- ✅ 统一文档命名规范（kebab-case + 数字编号）
- ✅ 创建文档导航索引
- ✅ 补充业务流程说明文档
- ✅ 更新技术文档

### 项目清理

- ✅ 移除临时测试文件到专门目录
- ✅ 删除无用的HTML和SQL文件
- ✅ 整理迁移和初始化脚本
- ✅ 创建项目根README

### 文档体系

- ✅ 业务文档：5个核心业务流程文档
- ✅ 技术文档：5个技术主题文档
- ✅ 导航文档：文档索引和快速入门
- ✅ 项目文档：根目录README

---

**整理时间**：2025-02-08  
**整理人员**：AI Assistant  
**文档版本**：v1.0
