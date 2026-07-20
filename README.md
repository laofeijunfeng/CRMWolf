# CRMWolf

CRMWolf 是一套企业内部 CRM 系统，覆盖线索、客户、联系人、商机、合同、回款、发票和审批等销售管理流程。

当前仓库只保留两类稳定入口：

- 本地开发：前端 `npm run dev`，后端 `./run.sh`。
- 服务器部署：通过 `CRM-Docs/deployment/` 下的部署脚本发布到远程服务器。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3、TypeScript、Vite、Pinia、Vue Router |
| 前端 UI | shadcn-vue / Reka UI、Tailwind CSS、lucide-vue-next、项目 V2 设计规范 |
| 后端 | FastAPI、SQLAlchemy 2、Pydantic 2、Alembic |
| 数据库 | MySQL 8、Redis 6/7 |
| 部署 | Docker、Docker Compose、远程服务器脚本部署 |

## 目录结构

```text
CRMWolf/
├── CRM-Client/              # Vue 前端应用
│   ├── src/                 # 前端源码
│   └── tests/               # 前端测试
│
├── CRM-Server/              # FastAPI 后端应用
│   ├── app/                 # 后端应用代码
│   ├── migrations/          # Alembic 数据库迁移
│   ├── scripts/             # 后端维护脚本
│   └── tests/               # 后端测试
│
├── CRM-Docs/                # 项目保留文档
│   ├── design-system/       # V2 设计规范唯一入口
│   └── deployment/          # 服务器部署说明
│
├── CONTRIBUTING.md          # 开发协作约定
└── README.md                # 项目入口说明
```

## 本地开发

### 前端

```bash
cd CRM-Client
npm install
npm run dev
```

常用检查：

```bash
npm run lint
npm run type-check
npm run test:unit
```

前端开发服务器默认地址以 Vite 输出为准，通常是 `http://localhost:5173` 或当前可用端口。

### 后端

```bash
cd CRM-Server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
./run.sh
```

后端默认地址：

- API：`http://localhost:8000`
- Swagger：`http://localhost:8000/docs`
- ReDoc：`http://localhost:8000/redoc`

### 数据库迁移

```bash
cd CRM-Server
alembic current
alembic upgrade head
alembic revision -m "change description"
```

## 服务器部署

远程服务器部署统一从部署目录进入：

```bash
bash CRM-Docs/deployment/deploy.sh
```

部署说明见 [CRM-Docs/deployment/README.md](CRM-Docs/deployment/README.md)。

当前只保留远程服务器部署方案。已废弃的本地 Docker dev、完整生产 compose、手工 Docker 打包脚本和历史部署文档已经移除。

## 设计规范

前端新页面和组件以 V2 设计规范为准：

- [CRM-Docs/design-system/README.md](CRM-Docs/design-system/README.md)
- [列表页规范](CRM-Docs/design-system/patterns/list-page.md)
- [表格规范](CRM-Docs/design-system/components/table.md)
- [Sheet / 弹窗规范](CRM-Docs/design-system/components/modal-sheet.md)
- [ListCard 规范](CRM-Docs/design-system/components/list-card.md)

历史 V1 样式、Element Plus 主题变量、旧 FilterPanel、旧表头筛选、散落实施计划和 Claude Code 相关文件均已废弃。

## 核心业务模块

| 模块 | 范围 |
|------|------|
| 线索管理 | 线索创建、筛选、跟进、转化 |
| 客户管理 | 客户档案、联系人、公海池、详情 Sheet |
| 商机管理 | 商机创建、采购方式、阶段推进、赢单/输单 |
| 合同管理 | 合同创建、审批、付款计划 |
| 回款管理 | 回款登记、实际付款方、回款审批、回款详情 |
| 发票管理 | 发票申请、审批、开票信息 |
| 审批中心 | 合同、回款、发票等业务审批统一入口 |
| 系统设置 | 团队成员、角色权限、采购方式、审批流等 Sheet 化配置 |

## 开发约定

- 代码协作要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 前端 UI 改造优先遵循 `CRM-Docs/design-system/`。
- 后端数据库变更必须通过 Alembic migration 交付。
- 根目录不再新增临时计划、阶段总结、验证报告或一次性测试脚本。
- 一次性排查脚本优先放到临时目录或任务上下文，稳定后再纳入对应模块的 `tests/` 或 `scripts/`。

## 许可证

Private - Internal Use Only
