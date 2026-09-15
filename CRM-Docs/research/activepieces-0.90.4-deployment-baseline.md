# Activepieces 0.90.4 部署基线（2026-09-10）

## 结论

MVP 使用 Activepieces App/Worker + 独立 PostgreSQL；Redis 复用 CRMWolf 既有 `redis6`，通过 `AP_REDIS_DB=6` 与 CRM 的 DB 5 分开。本项目 Compose 不创建第二个 Redis，也不让 Activepieces 访问 CRM MySQL。

## 官方来源（固定 tag）

- Activepieces `0.90.4` 官方 Compose：`https://github.com/activepieces/activepieces/blob/0.90.4/docker-compose.yml`
- Activepieces `0.90.4` 官方环境变量示例：`https://github.com/activepieces/activepieces/blob/0.90.4/.env.example`
- Activepieces `0.90.4` 源码中的密钥校验：`packages/server/api/src/app/helper/system-validator.ts`；要求 `AP_ENCRYPTION_KEY` 为 32 位十六进制字符串，并建议 `openssl rand -hex 16`。
- Activepieces `0.90.4` Redis 连接实现：`packages/server/api/src/app/database/redis/default-redis.ts`；`AP_REDIS_DB` 作为 Redis database index，缺省为 0。
- Activepieces `0.90.4` 健康端点：`packages/server/api/src/app/health/health.module.ts`；`GET /v1/health` 返回 Healthy/Unhealthy，容器 HTTP 暴露路径通常为 `/api/v1/health`。

## 适用范围

这只是 AP-01 部署基线，不代表已经完成真实容器启动、Flow 执行或 API 发布能力验证。运行时验收必须在具备 Docker daemon、外部网络和 `redis6` 的环境中执行。

## 本地运行验收补充（2026-09-10）

固定版本镜像已成功拉取，App、Worker、PostgreSQL 均启动并健康。独立 Worker 不能使用面向浏览器的 `AP_FRONTEND_URL=http://localhost:8080` 访问 App，因为容器内的 localhost 指向 Worker 自身；Compose 对 Worker 覆盖 `AP_FRONTEND_URL=http://app`，App 仍使用用户访问地址。修正后 Worker 健康，App 的 `/api/v1/health` 返回 `{"status":"Healthy"}`。

本次只完成部署和健康检查，尚未创建或执行业务 Flow，也未使用用户账号登录。
