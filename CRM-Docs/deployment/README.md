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

## 文件说明

- `deploy.sh`：远程服务器一键部署脚本。
- `docker-compose.yml`：服务器部署基础服务定义。
- `docker-compose.server.yml`：服务器环境覆盖配置，依赖本目录 `docker-compose.yml`。
- `secrets/`：本地部署密钥目录，只用于部署上传，不能提交到 git。

已废弃的完整生产 compose 和手工打包脚本不再保留。
