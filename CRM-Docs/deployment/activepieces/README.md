# CRMWolf Activepieces 部署单元

这是自动化 MVP 的独立 Activepieces App/Worker + PostgreSQL 部署单元。CRM 仍拥有业务工作流定义、租户隔离、权限、审批事实、幂等和审计；Activepieces 只负责执行。Activepieces 不连接 CRMWolf MySQL。

## 前置条件

- 已部署 CRMWolf 的 `redis6`，并加入外部 Docker 网络 `crmwolf-network`。
- Redis 使用逻辑 DB 6；CRM 继续使用 DB 5。逻辑 DB 不是安全边界，不能替代实例级隔离。
- 本目录的 `.env` 已配置真实密钥和 Activepieces 独立 PostgreSQL 密码。
- 首次使用固定版本 `0.90.4`。升级必须重新核对官方环境变量并执行验收。

## 启动

```bash
cd CRM-Docs/deployment/activepieces
cp .env.example .env
# 编辑 .env；生成 AP_ENCRYPTION_KEY：openssl rand -hex 16
docker compose config
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:8080/api/v1/health
```

默认端口只绑定 `127.0.0.1`，由反向代理暴露时再显式设置 `ACTIVEPIECES_BIND_ADDRESS`。生产环境必须使用 HTTPS，并将 App 的 `AP_FRONTEND_URL` 设置为用户实际访问地址；Compose 会为独立 Worker 覆盖为内部地址 `http://app`，避免 Worker 在容器内错误访问自己的 localhost。

## 组件与边界

```text
Activepieces App / Worker
  ├── 独立 PostgreSQL（仅 Activepieces 数据）
  ├── 既有 redis6（逻辑 DB 6）
  └── 通过 crmwolf-network 调用 CRM 受控 HTTP API
       └── 不直连 CRMWolf MySQL
```

本 Compose **不会创建 Redis 容器或 Redis volume**，也不会默认启动第二个 Redis。`crmwolf-network` 是 external network；如果前置条件不满足，启动应失败，而不是偷偷创建替代基础设施。

## MVP 验证顺序

1. `docker compose config` 成功，且输出只有 `app`、`worker`、`postgres` 三个服务。
2. App、Worker、PostgreSQL 运行并通过健康检查；访问 `/api/v1/health` 返回 `Healthy`。
3. 在 Activepieces Builder 中手工创建 `Webhook Trigger → HTTP Request` Flow；Builder 仅用于研发联调，终端用户不离开 CRM。
4. 使用固定测试事件调用 Webhook，确认 Flow Run 成功。
5. HTTP Request 只调用 CRM 受控的创建跟进任务 API；验证超时、5xx、重试、幂等和服务重启恢复。

## 运维与安全

- `.env` 含密钥，已被 `.gitignore` 忽略，不得提交 Git。
- `AP_ENCRYPTION_KEY` 必须是 32 位十六进制字符串；不要复用 JWT 或数据库密码。
- `AP_EXECUTION_MODE=UNSANDBOXED` 仅用于受控 MVP；不得允许不受信任的任意代码执行。
- `docker compose down` 不删除数据；谨慎使用 `down -v`，它会删除 Activepieces PostgreSQL 数据。
- 生产发布前配置备份、监控、HTTPS、访问控制和回滚方案。
