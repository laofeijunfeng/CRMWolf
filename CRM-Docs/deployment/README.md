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
5. 执行 Alembic 数据库结构迁移。
6. 执行销售承诺/跟进任务历史数据回填。
7. 检查前后端健康状态。

## 前置条件

- 本机已安装 Docker，并可使用 `docker buildx`。
- 本机存在 SSH 密钥：`~/.ssh/crmwolf_deploy`。
- 本目录存在真实密钥文件：
  - `CRM-Docs/deployment/secrets/db_password.txt`
  - `CRM-Docs/deployment/secrets/secret_key.txt`
  - `CRM-Docs/deployment/secrets/customer_evidence_embedding_api_key.txt`
- 服务器已有外部 Docker 网络 `crmwolf-network`。
- 服务器已有容器或服务名：
  - `mysql8`
  - `redis6`
- Qdrant 由本目录的 Docker Compose 自动创建：
  - 容器名：`crm-qdrant-dev`
  - 服务名：`qdrant`
  - 数据卷：`crm-qdrant-dev-data`
- 客户知识库语义检索还需要 Embedding API Key。服务器部署默认从 Docker secret 读取：
  - `/run/secrets/customer_evidence_embedding_api_key`
  - 本地来源文件是 `CRM-Docs/deployment/secrets/customer_evidence_embedding_api_key.txt`

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
QDRANT_VECTOR_SIZE=1024
CUSTOMER_EVIDENCE_EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
CUSTOMER_EVIDENCE_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
CUSTOMER_EVIDENCE_EMBEDDING_DIMENSIONS=1024
CUSTOMER_EVIDENCE_EMBEDDING_API_KEY_FILE=/run/secrets/customer_evidence_embedding_api_key
CUSTOMER_EVIDENCE_SYNC_ENABLED=true
CUSTOMER_INTELLIGENCE_BACKFILL_ENABLED=true
CUSTOMER_INTELLIGENCE_BACKFILL_BATCH_SIZE=20
CUSTOMER_INTELLIGENCE_BACKFILL_INTERVAL_SECONDS=300
CUSTOMER_EVIDENCE_SYNC_BATCH_SIZE=50
CUSTOMER_EVIDENCE_SYNC_INTERVAL_SECONDS=30
```

`CUSTOMER_EVIDENCE_EMBEDDING_DIMENSIONS` 必须和 `QDRANT_VECTOR_SIZE` 一致。当前默认使用 SiliconFlow 的 `Qwen/Qwen3-Embedding-0.6B`，向量维度是 `1024`。后端兼容历史变量名 `CUSTOMER_EVIDENCE_EMBEDDING_API_HOST` 和单数 `CUSTOMER_EVIDENCE_EMBEDDING_DIMENSION`，但部署文档统一使用 `CUSTOMER_EVIDENCE_EMBEDDING_BASE_URL` / `CUSTOMER_EVIDENCE_EMBEDDING_DIMENSIONS`。

当前 `docker-compose.yml` 和 `docker-compose.server.yml` 已提供 Qdrant 与 Embedding 默认 host/model/dimensions；密钥必须由 Docker secret 或环境变量注入，不能提交到仓库。上线后只要 Qdrant 容器正常、Embedding API Key 有效、后端服务正常，历史客户会按批次自动补：

- 没有客户智能概况的客户，会进入客户智能档案补件。
- 已有客户智能概况但客户 profile 向量证据版本旧的客户，会自动重建向量证据。
- 重建后的证据会标记为待同步，再由向量同步任务写入 Qdrant。
- 如果没有配置 Embedding API Key，客户智能档案的结构化事实仍可生成和展示，但 Qdrant 语义证据同步、简称召回、跨客户语义搜索会不可用。

上线验证命令：

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'crm-backend|crm-qdrant-dev'
docker logs crm-backend --since 10m | grep -E '客户智能历史补档|客户证据向量同步|Qdrant'
```

如果日志里能看到“客户智能历史补档调度已启动”和“客户证据向量同步调度已启动”，说明自动补件链路已经启动；后续看到“客户智能历史补档已调度”或“客户证据向量同步完成”，说明历史数据正在分批补齐。

## 销售承诺/跟进任务上线检查

销售承诺/跟进任务包含两类迁移，不能只执行 Alembic：

1. 结构迁移：`python -m alembic upgrade head`，创建任务、承诺、事件、投影运行等表。
2. 数据回填：`python scripts/backfill_follow_up_tasks.py --days 90 --limit 1000 --confirm`，把最近 90 天客户活动中每个客户、每个 owner 最新 1 条明确下一步时间的活动投影为任务。

`deploy.sh` 已在 Alembic 成功后自动执行历史回填。回填脚本可重复执行，投影层按来源活动和任务 hash 幂等处理，不应重复制造任务。

上线后可用以下命令确认：

```bash
docker exec crm-backend python -c "from app.core.database import SessionLocal; from app.models.sales_commitment import FollowUpTask, SalesCommitment, FollowUpTaskProjectionRun; db=SessionLocal(); print('follow_up_tasks', db.query(FollowUpTask).count()); print('sales_commitments', db.query(SalesCommitment).count()); print('projection_runs', db.query(FollowUpTaskProjectionRun).count()); db.close()"
```

## 文件说明

- `deploy.sh`：远程服务器一键部署脚本。
- `docker-compose.yml`：服务器部署基础服务定义。
- `docker-compose.server.yml`：服务器环境覆盖配置，依赖本目录 `docker-compose.yml`。
- `secrets/`：本地部署密钥目录，只用于部署上传，不能提交到 git。

已废弃的完整生产 compose 和手工打包脚本不再保留。
