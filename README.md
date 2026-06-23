# CRMWolf - 智能客户关系管理系统

AI 驱动的企业级 CRM 系统，支持线索管理、客户档案、商机推进、合同审批等全流程业务场景。

---

## 技术栈

| 层级 | 技术栈 | 版本 |
|------|--------|------|
| 前端 | Vue + TypeScript + Element Plus + Pinia + Vite | 3.5 / 5.7 |
| 后端 | FastAPI + SQLAlchemy + Pydantic | 0.115 |
| 数据库 | MySQL + Redis | 8.0 / 7.x |
| AI | LangChain + Claude API | - |

---

## 项目结构

```
CRMWolf/
├── CRM-Client/          # Vue 3 前端应用
│   ├── src/             # 源代码
│   └── docs/            # 前端开发规范
│
├── CRM-Server/          # FastAPI 后端应用
│   ├── app/             # 应用代码
│   └── tests/           # 测试代码
│
├── CRM-Docs/            # 项目文档
│   ├── system/          # 系统说明
│   ├── standards/       # 开发规范
│   ├── requirements/    # 需求文档
│   └── plans/           # 实施计划
│
├── README.md            # 项目说明（本文件）
└── CONTRIBUTING.md      # 贡献指南（开发规范）
```

---

## 快速开始

### 前端启动

```bash
cd CRM-Client
npm install
npm run dev              # 启动开发服务器（http://localhost:5173）
npm run lint             # ESLint 校验
npm run type-check       # TypeScript 类型检查
npm run test:unit        # 运行单元测试
```

### 后端启动

```bash
cd CRM-Server
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
./run.sh                  # 启动服务（http://localhost:8000)
ruff check app/           # Python lint
mypy app/                 # 类型检查
pytest tests/unit -v      # 运行单元测试
```

### 数据库迁移

```bash
cd CRM-Server
alembic revision -m "描述变更内容"  # 创建迁移文件
alembic upgrade head               # 执行迁移
alembic current                    # 验证版本
```

---

## 开发指引

### 新人入门

1. **阅读贡献指南**：`CONTRIBUTING.md`（开发红线 + 规范）
2. **快速上手**：`CRM-Docs/standards/QUICK-START.md`（5 分钟掌握规范）
3. **系统说明**：`CRM-Docs/system/SYSTEM-DESCRIPTION.md`（功能全貌）

### 核心规范

| 需要什么 | 查阅位置 |
|----------|----------|
| TypeScript 类型定义 | `CRM-Client/docs/TYPESCRIPT.md` |
| Vue 组件规范 | `CRM-Client/docs/COMPONENTS.md` |
| Pinia Store 规范 | `CRM-Client/docs/STATE-MANAGEMENT.md` |
| 后端 CRUD 模板 | `CRM-Docs/best-practices/backend/crud-patterns.md` |
| team_id 隔离架构 | `CRM-Docs/best-practices/backend/team-isolation.md` |
| 权限码/状态枚举 | `CRM-Docs/system/GLOSSARY.md` |
| API 接口清单 | `CRM-Docs/system/BUSINESS-CHAIN-API.md` |

### 分支纪律

```bash
# 创建新特性分支
git checkout main
git checkout -b feat/功能名称

# 开发完成后合并
git checkout main
git merge feat/功能名称
git push origin main
```

---

## 核心功能

| 模块 | 功能 |
|------|------|
| 线索管理 | 线索创建、跟进、转化、公海池 |
| 客户管理 | 客户档案、联系人、公海池、AI 智能档案 |
| 商机管理 | 商机创建、阶段推进、赢单/输单 |
| 合同管理 | 合同创建、审批流程、状态管理 |
| 回款管理 | 回款登记、分期管理、关联合同 |
| 发票管理 | 发票申请、审批、开具 |
| AI 助手 | 智能对话、意图识别、自动操作 |

详细功能说明：`CRM-Docs/system/modules/`

---

## 贡献指南

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解：
- 开发红线（TypeScript 四禁令、分支纪律）
- 前端/后端开发规范
- 测试覆盖率要求
- 提交规范

---

## 文档导航

完整文档索引：`CRM-Docs/README.md`

---

## License

Private - Internal Use Only

---

> **维护团队**：CRMWolf 开发团队
> **最后更新**：2026-06-23