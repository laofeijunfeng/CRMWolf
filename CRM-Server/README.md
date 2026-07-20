# CRM 客户关系管理系统

基于 FastAPI 的企业级客户关系管理平台，涵盖从线索获取到合同签署的完整销售流程。

## ✨ 核心功能

- **线索管理** - 线索录入、分配、跟进、转化
- **客户管理** - 客户信息、联系人、公海池管理
- **商机管理** - 销售阶段、赢单输单、销售漏斗
- **合同管理** - 合同审批、签署、履行跟踪
- **权限控制** - 基于角色的权限管理
- **飞书集成** - 用户认证、消息通知

## 🚀 快速开始

### 环境要求

- Python 3.11+
- MySQL 8.0+
- Redis 6.0+

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境

```bash
cp .env.example .env
# 编辑 .env 文件，设置数据库连接等信息
```

### 启动服务

```bash
./run.sh
```

服务启动后访问：
- API 文档：http://localhost:8000/docs
- ReDoc 文档：http://localhost:8000/redoc

## 📚 文档

- API 文档：启动服务后访问 `http://localhost:8000/docs`
- 项目开发规范：参考根目录 [README.md](../README.md) 和 [CONTRIBUTING.md](../CONTRIBUTING.md)
- 前端 V2 设计规范：参考 [CRM-Docs/design-system](../CRM-Docs/design-system/README.md)

## 📁 项目结构

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
├── docs/                  # 文档目录
│   ├── business/          # 业务流程文档
│   └── technical/         # 技术文档
├── tests/                 # 测试脚本
├── scripts/               # 工具脚本
├── migrations/            # 数据库迁移
└── requirements.txt       # 依赖包列表
```

## 🧪 测试

运行测试脚本：

```bash
# 测试线索管理
python tests/test_leads.py

# 测试合同审批流程
python tests/test_approval_workflow.py

# 更多测试...
ls tests/
```

## 🔧 开发

### 代码规范

- 遵循 PEP 8 规范
- 使用类型注解
- 编写文档字符串
- 保持代码简洁清晰

### API 开发

1. 在 `app/models/` 创建数据模型
2. 在 `app/schemas/` 创建请求/响应模式
3. 在 `app/crud/` 创建数据库操作
4. 在 `app/api/` 创建 API 路由
5. 在 `app/main.py` 注册路由

详细开发规范请参考根目录 [CONTRIBUTING.md](../CONTRIBUTING.md)。

## 📊 数据库

### 初始化数据库

```bash
python scripts/init_db.py
```

### 数据迁移

```bash
# 创建审批流程表
python scripts/migrate_approval_simple.py

# 初始化商机阶段
python scripts/init_opportunity_stages.py
```

## 🔐 权限说明

### 角色定义

- **销售成员** - 查看和管理自己的数据
- **销售总监** - 查看和管理团队数据，审批合同
- **系统管理员** - 系统配置和全部数据权限

### 权限控制

- 基于角色的访问控制（RBAC）
- 数据级权限控制（只能访问自己的数据）
- API 级权限验证（JWT Token）

## 🔔 飞书集成

### 功能特性

- 飞书扫码登录
- 用户信息同步
- 审批通知推送
- 跟进提醒通知

### 配置说明

飞书应用配置通过环境变量维护，具体以 `app/core/config.py` 和部署环境配置为准。

## 📈 统计分析

系统提供丰富的统计分析功能：

- 线索转化率分析
- 客户价值分析
- 商机赢单率分析
- 销售漏斗分析
- 业绩统计分析
- 审批效率分析

## 🎯 业务流程

### 标准销售流程

```
线索 → 跟进 → 转化客户 → 创建商机 → 推进阶段 → 商机赢单 → 创建合同 → 审批签署 → 完成
```

业务流程以当前 API、数据模型和前端页面实现为准。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 📞 联系方式

如有问题或建议，请通过以下方式联系：

- 提交 Issue
- 发送邮件
- 联系管理员

---

**最后更新**：2025-02-07  
**版本**：v1.0
