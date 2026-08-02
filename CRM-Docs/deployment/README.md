# 部署说明

当前只保留远程服务器部署入口。本地开发直接使用前端 `npm run dev` 和后端 `./run.sh`，不再使用 Docker Compose。

## 本地 dev

前端：

```bash
cd CRM-Client
npm run dev
```

后端：

```bash
cd CRM-Server
./run.sh
```

## 远程服务器部署

服务器部署脚本在本目录：

```bash
bash CRM-Docs/deployment/deploy.sh
```

脚本会完成：

1. 在本地构建 `linux/amd64` 的前后端 Docker 镜像。
2. 导出 `crm-images.tar`。
3. 上传镜像包、本目录 `docker-compose.yml`、`docker-compose.server.yml` 和 `CRM-Docs/deployment/secrets/` 下的密钥文件。
4. 在服务器执行 `docker compose -f docker-compose.yml -f docker-compose.server.yml up -d`。
5. 执行 Alembic 数据库迁移。
6. 检查前后端健康状态。

## 前置条件

- 本机已安装 Docker，并可使用 `docker buildx`。
- 本机存在 SSH 密钥：`~/.ssh/crmwolf_deploy`。
- 本目录存在真实密钥文件：
  - `CRM-Docs/deployment/secrets/db_password.txt`
  - `CRM-Docs/deployment/secrets/secret_key.txt`
- 服务器已有外部 Docker 网络 `crmwolf-network`。
- 服务器已有容器或服务名：
  - `mysql8`
  - `redis6`
- Qdrant 由本目录的 Docker Compose 自动创建：
  - 容器名：`crm-qdrant-dev`
  - 服务名：`qdrant`
  - 数据卷：`crm-qdrant-dev-data`

## 客户智能档案与知识库上线检查

客户智能档案、Agent 客户搜索、简称召回和向量知识库不要靠人工补历史数据。正式服务启动后，后端会自动启动两类后台任务：

1. `customer_intelligence_backfill`：补齐历史客户智能档案，并重建过期的客户 profile 向量证据。
2. `customer_evidence_sync`：把待同步的客户证据写入 Qdrant。

部署时确认以下配置保持启用：

```bash
QDRANT_ENABLED=true
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION_CUSTOMER_EVIDENCE=crm_customer_evidence
CUSTOMER_INTELLIGENCE_BACKFILL_ENABLED=true
CUSTOMER_INTELLIGENCE_BACKFILL_BATCH_SIZE=20
CUSTOMER_INTELLIGENCE_BACKFILL_INTERVAL_SECONDS=300
CUSTOMER_EVIDENCE_SYNC_BATCH_SIZE=50
CUSTOMER_EVIDENCE_SYNC_INTERVAL_SECONDS=30
```

当前 `docker-compose.yml` 和 `docker-compose.server.yml` 已提供 Qdrant 默认值；补件和同步批次使用后端配置默认值。上线后只要 Qdrant 容器正常、后端服务正常，历史客户会按批次自动补：

- 没有客户智能概况的客户，会进入客户智能档案补件。
- 已有客户智能概况但客户 profile 向量证据版本旧的客户，会自动重建向量证据。
- 重建后的证据会标记为待同步，再由向量同步任务写入 Qdrant。

上线验证命令：

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'crm-backend|crm-qdrant-dev'
docker logs crm-backend --since 10m | grep -E '客户智能历史补档|客户证据向量同步|Qdrant'
```

如果日志里能看到“客户智能历史补档调度已启动”和“客户证据向量同步调度已启动”，说明自动补件链路已经启动；后续看到“客户智能历史补档已调度”或“客户证据向量同步完成”，说明历史数据正在分批补齐。

## 文件说明

- `deploy.sh`：远程服务器一键部署脚本。
- `docker-compose.yml`：服务器部署基础服务定义。
- `docker-compose.server.yml`：服务器环境覆盖配置，依赖本目录 `docker-compose.yml`。
- `secrets/`：本地部署密钥目录，只用于部署上传，不能提交到 git。

已废弃的完整生产 compose 和手工打包脚本不再保留。
