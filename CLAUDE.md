# CRMWolf 项目指引

**启动时自动加载** - Claude Code 会在每次对话开始时读取此文件

---

## 核心规范入口

**请首先阅读**：`AGENTS.md`

这是 AI + 团队的唯一行为准则入口，包含：
- 红线锁定（不可突破）
- 规范导航索引
- 校验流程说明

---

## 快速开始

1. 阅读 `AGENTS.md` 了解红线和规则
2. 根据任务类型查阅对应规范：
   - 新增 API → `CRM-Client/docs/TYPESCRIPT.md` + `CRM-Docs/ARCHITECTURE.md`
   - 新增组件 → `CRM-Client/docs/COMPONENTS.md`
   - 新增 Store → `CRM-Client/docs/STATE-MANAGEMENT.md`
   - 写单测 → `CRM-Client/docs/TESTING.md`
   - 查权限码 → `CRM-Docs/GLOSSARY.md`

---

## 项目结构

```
CRMWolf/
├── AGENTS.md                    # AI 行为准则入口
├── CRM-Client/                  # Vue 3 前端
├── CRM-Server/                  # FastAPI 后端
├── CRM-Docs/                    # 规范 + 业务文档
└── .claude/                     # Claude 配置
```

---

## 技术栈

- **前端**：Vue 3.5 + TypeScript 5.7 + Element Plus + Pinia + Vite
- **后端**：Python 3.11 + FastAPI + SQLAlchemy + Pydantic
- **数据库**：MySQL 8.0 + Redis 7.x

---

## 开发命令

```bash
# 前端
cd CRM-Client && npm run dev          # 启动开发
npm run lint                          # ESLint 校验
npm run type-check                    # TypeScript 校验
npm run test:unit                     # 单测

# 后端
cd CRM-Server && ./run.sh             # 启动服务
ruff check app/                       # Python lint
mypy app/                             # 类型检查
pytest tests/unit -v                  # 单测
```