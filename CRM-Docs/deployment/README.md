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
4. 停止旧版服务，并使用新后端镜像以一次性 Compose 容器执行 Alembic 数据库结构迁移。
5. 迁移成功后，再执行 `docker compose -f docker-compose.yml -f docker-compose.server.yml up -d` 启动新版本。
6. 执行销售承诺/跟进任务历史数据回填。
7. 检查前后端健康状态；检查成功后删除本次替换下来的旧后端、前端镜像（失败时保留，便于回滚）。

先迁移后启动保证新代码依赖的新索引或字段已经存在，避免发布窗口内新后端先运行而查询失败。

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

## 客户初始补全上线检查

客户初始补全是客户主数据 mutation，不是客户智能档案生成的一部分。客户创建事务先成功；后台 durable job 只补 active plan 允许且仍为空的字段（当前 `customer-initial-v1` 仅补 `Customer.industry`），不覆盖人工或既有值。客户档案仍是只读 Projection：首次生成会在有限时间内等待补全第一次真实尝试，超时或第一次技术失败时降级生成无行业档案，后续补全成功再触发档案刷新。补全失败不得回滚客户，档案失败也不得回滚已经补全的主数据。

应用代码默认启用 recovery、backfill 和 reconciliation，适合本地开发及已完成上线门禁的环境；服务器 `docker-compose.yml` 为首次生产发布提供更保守的 rollout 默认值：recovery 仍为 `true`，但 backfill 和 reconciliation 默认为 `false`。以下列表先给出应用默认值，带“生产 Compose 首发默认”的两项以服务器 Compose 为准：

```bash
CUSTOMER_INITIAL_ENRICHMENT_SETTLE_SECONDS=5
CUSTOMER_INITIAL_ENRICHMENT_PROFILE_GATE_MAX_SECONDS=30
CUSTOMER_INITIAL_ENRICHMENT_MAX_ATTEMPTS=3
CUSTOMER_INITIAL_ENRICHMENT_LEASE_SECONDS=120
CUSTOMER_INITIAL_ENRICHMENT_RECOVERY_ENABLED=true
CUSTOMER_INITIAL_ENRICHMENT_RECOVERY_INTERVAL_SECONDS=60
CUSTOMER_INITIAL_ENRICHMENT_BATCH_SIZE=20
CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_ENABLED=true       # 生产 Compose 首发默认 false
CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_BATCH_SIZE=5
CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_INTERVAL_SECONDS=300
CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_ENABLED=true # 生产 Compose 首发默认 false
CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_INTERVAL_SECONDS=300
CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_BATCH_SIZE=50
```

`PROFILE_GATE_MAX_SECONDS` 只限制首次档案等待时间，不是 enrichment job 超时；`RECOVERY_ENABLED` 负责领取新客户与已登记历史任务并恢复到期重试，`BACKFILL_ENABLED` 负责为历史缺失字段登记任务，`RECONCILIATION_ENABLED` 负责补登记遗漏任务、释放到期 gate 和修复缺失的档案刷新 receipt。首次客户每轮默认领取 20 条，历史回填仍保留 5 条配额，不能让历史任务长期饥饿。

首次生产发布必须分阶段执行：

1. 执行 migration，并以生产 Compose 默认值启动后端：`CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_ENABLED=false`、`CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_ENABLED=false`、recovery 保持启用。此时不会在 preview 前扫描历史客户或创建 reconciliation 补偿任务。
2. 先确认 recovery 日志：`docker logs crm-backend --since 10m | grep '客户初始补全任务恢复调度已启动'`。不要把 backfill/reconciliation 未出现“已启动”视为故障；它们此阶段按设计关闭。
3. 使用下方管理员 API 执行 backfill preview 和 reconciliation `dry_run=true`，重点审查 `other_available=true`、`invalid_non_null`、`would_schedule`，并确认 dry-run 的 `errors=0` 及预期 `jobs_created / gates_released / refreshes_repaired`。
4. 审查通过后，在服务器部署环境的 `.env` 中各定义一次且只定义一次：

   ```bash
   CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_ENABLED=true
   CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_ENABLED=true
   ```

5. 使用相同 Compose 文件 recreate 后端：`docker compose -f docker-compose.yml -f docker-compose.server.yml up -d --force-recreate backend`。
6. 再检查三个独立 scheduler 的证据：

   ```bash
   docker logs crm-backend --since 10m | grep -E '客户初始补全任务恢复调度已启动|客户初始补全历史回填调度已启动|客户初始补全对账调度已启动'
   ```

三条“已启动”日志必须同时出现；后续有历史任务登记时还会出现“客户初始补全历史回填已调度”。只看到档案 backfill 或证据向量同步日志，不能证明主数据补全 worker 已启动。

历史回填前先使用具备 `customer:edit:all` 权限的管理员凭证查看团队级 preview；接口均位于统一 `/api` 前缀下：

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$CRM_BASE_URL/api/v1/customers/enrichment/backfill-preview"
```

重点核对 `industry_null`、`existing_jobs`、`would_schedule`、`filled_skip`、`invalid_non_null` 和 `other_available`。`other_available` 必须为 `true`；`invalid_non_null` 只报告，不自动覆盖历史非空值。preview 不登记 job，也不调用模型。

诊断任务状态与运行证据：

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$CRM_BASE_URL/api/v1/customers/enrichment/jobs?limit=200"
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$CRM_BASE_URL/api/v1/customers/enrichment/jobs?status=EXHAUSTED&limit=200"
curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  "$CRM_BASE_URL/api/v1/customers/enrichment/reconciliation/run" \
  -d '{"limit":500,"dry_run":true}'
```

任务诊断返回 purpose、plan、requested fields、attempt/max attempts、`requeue_count`、下一次尝试时间、首次尝试完成时间、`profile_gate_timed_out_at` 和档案刷新 receipt。reconciliation dry-run 返回 `scanned / jobs_created / gates_released / refreshes_repaired / errors`，用于发布前评估而不写入。`profile_gate_timeout` 的 durable 证据是诊断中非空的 `profile_gate_timed_out_at`：它只在创建期任务尚未完成首次尝试、deadline 已过且档案实际解除 gate 时首次写入；不能从聚合 `gates_released` 推断。运行期间应持续观察 `COMPLETED / SKIPPED / RETRY_PENDING / EXHAUSTED`，并结合写入操作日志、`requeue_count`、档案 refresh receipt 和该时间戳形成 scheduled、applied、other、skipped、retry_pending、exhausted、requeued、profile_gate_timeout 证据；技术失败不得伪装为行业 `other`。

`EXHAUSTED` 不会无限自动重试。确认 AI 配置、行业目录和下游故障已修复后，管理员只能对当前 active plan、目标字段仍为空的耗尽任务重新入队：

```bash
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  "$CRM_BASE_URL/api/v1/customers/enrichment/jobs/$JOB_PUBLIC_ID/requeue"
```

成功响应为原 `job_public_id`、`status=QUEUED` 和递增后的 `requeue_count`；系统清除旧 lease/error、重置 attempt，并立即 kick 原任务，不创建第二条 job。非 `EXHAUSTED`、旧 plan 或字段已被人工填写时返回 `409`，不得绕过该保护直接改表。

## 销售承诺/跟进任务上线检查

销售承诺/跟进任务包含两类迁移，不能只执行 Alembic：

1. 结构迁移：`python -m alembic upgrade head`，创建任务、承诺、事件、投影运行等表。
2. 数据回填：`python scripts/backfill_follow_up_tasks.py --days 90 --limit 1000 --confirm`，把最近 90 天客户活动中每个客户、每个 owner 最新 1 条明确下一步时间的活动投影为任务。

`deploy.sh` 已在 Alembic 成功后自动执行历史回填。回填脚本可重复执行，投影层按来源活动和任务 hash 幂等处理，不应重复制造任务。

上线后可用以下命令确认：

```bash
docker exec crm-backend python -c "from app.core.database import SessionLocal; from app.models.sales_commitment import FollowUpTask, SalesCommitment, FollowUpTaskProjectionRun; db=SessionLocal(); print('follow_up_tasks', db.query(FollowUpTask).count()); print('sales_commitments', db.query(SalesCommitment).count()); print('projection_runs', db.query(FollowUpTaskProjectionRun).count()); db.close()"
```

## CRM Agent 架构迁移

Root Orchestrator / Workflow Agent / Query Agent 单版本切换必须先执行 [CRM Agent 单版本架构切换门禁](agent-architecture-migration.md)。`deploy.sh` 不会自动执行历史消息写入或 destructive checkpoint cutover；两项操作必须在停流、固定 `--as-of` inventory、数据库备份与独立恢复演练全部通过后，由明确授权的维护窗口单独执行。若已经发生“schema 提前升级且无升级前备份”的事故，只能按 `agent-architecture-migration.md` 的「强制 schema 升级后的前向恢复」执行带五项显式确认（包括已停止所有写入方）的恢复工具；不得把它用于普通发布。证据不得提交到 Git。

## 文件说明

- `deploy.sh`：远程服务器一键部署脚本。
- `docker-compose.yml`：服务器部署基础服务定义。
- `docker-compose.server.yml`：服务器环境覆盖配置，依赖本目录 `docker-compose.yml`。
- `secrets/`：本地部署密钥目录，只用于部署上传，不能提交到 git。

已废弃的完整生产 compose 和手工打包脚本不再保留。

## Activepieces 自动化 MVP

Activepieces 不属于 CRM 前后端本地开发 Compose，也不由 CRM 主部署脚本隐式创建。其独立部署单元位于 `CRM-Docs/deployment/activepieces/`：使用独立 PostgreSQL，复用服务器已有 `redis6` 的 Redis DB 6，并通过 `crmwolf-network` 调用 CRM 受控 HTTP API。详见该目录的 README；启动前必须确认服务器已有 `redis6` 和 external network，禁止为了绕过前置条件再启动第二个 Redis。
