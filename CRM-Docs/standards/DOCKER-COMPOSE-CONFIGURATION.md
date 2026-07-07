# Docker Compose 配置文件说明

**版本：1.0 | 创建日期：2026-07-07**

---

## 📁 文件结构

```
CRMWolf/
├── docker-compose.yml              # 基础配置（所有环境共享）
├── docker-compose.override.yml     # 本地开发覆盖（不提交 Git）
├── docker-compose.server.yml       # 服务器部署（依赖外部 mysql8/redis6）
├── docker-compose.prod.yml         # 完整生产环境（自包含）
└── secrets/                        # 敏感信息（绝不提交 Git）
    ├── db_password.txt             # 数据库密码
    └── secret_key.txt              # 应用密钥
```

---

## 🎯 使用场景

### 场景 1：本地开发

```bash
# 自动合并 docker-compose.yml + override
docker compose up -d

# 特点：
# - 源码热重载（app/ 和 src/ 目录挂载）
# - 连接本地数据库（host.docker.internal）
# - CRM_DEBUG=true
# - 使用 build 构建（开发最新代码）
```

### 场景 2：服务器部署（已有 mysql8/redis6）

```bash
# 使用预构建镜像 + secrets 管理
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d

# 特点：
# - 使用 crm-backend:amd64 和 crm-frontend:amd64 镜像
# - 依赖外部容器 mysql8 和 redis6
# - 使用 Docker secrets 管理密码
# - 连接 crmwolf-network 网络
# - CRM_DEBUG=false
```

### 场景 3：完整生产环境（全新服务器）

```bash
# 自包含：包含数据库、缓存、应用
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 特点：
# - 包含 mysql 和 redis 服务
# - 内部网络隔离（crm-internal）
# - 健康检查 + 资源限制
# - 数据持久化（volumes）
# - CRM_DEBUG=false
```

---

## 🔒 Secrets 管理

### 本地 secrets 目录

```bash
# 创建 secrets 文件（不提交 Git）
mkdir -p secrets

echo "your_database_password" > secrets/db_password.txt
echo "your_secret_key_at_least_32_chars" > secrets/secret_key.txt

# 设置权限
chmod 600 secrets/*.txt
```

### .gitignore 配置

```gitignore
# Secrets - 绝不提交
secrets/
*.key
*.pem

# Docker 开发配置（本地特有）
docker-compose.override.yml
```

---

## 🚀 部署脚本使用

### scripts/deploy.sh

```bash
# 一键部署到服务器（使用 docker-compose.server.yml）
./scripts/deploy.sh

# 流程：
# 1. 构建镜像（crm-backend:amd64 + crm-frontend:amd64）
# 2. 打包镜像（crm-images.tar）
# 3. 上传镜像 + 配置文件 + secrets 目录
# 4. 服务器加载镜像
# 5. 启动服务（docker compose -f docker-compose.yml -f docker-compose.server.yml up -d）
# 6. 健康检查
```

---

## 📋 配置对比

| 维度 | docker-compose.yml | override.yml | server.yml | prod.yml |
|------|-------------------|--------------|-----------|----------|
| **用途** | 基础定义 | 本地开发 | 服务器部署 | 完整生产 |
| **数据库** | - | host.docker.internal | mysql8（外部） | mysql（自建） |
| **Redis** | - | host.docker.internal | redis6（外部） | redis（自建） |
| **镜像** | crm-*:${IMAGE_TAG} | build: ./ | crm-*:amd64 | build: ./ |
| **Secrets** | - | 环境变量 | Docker secrets | Docker secrets |
| **网络** | - | - | crmwolf-network | crm-internal + public |
| **健康检查** | ✅ | - | - | ✅ |
| **资源限制** | - | - | - | ✅ |
| **CRM_DEBUG** | ${CRM_DEBUG:-false} | true | false | false |

---

## 🔄 迁移说明

### 从旧配置迁移（2026-07-07）

**修改前：**
```
docker-compose.yml          # 混淆：实际用于服务器部署
docker-compose.prod.yml     # 从未使用
```

**修改后：**
```
docker-compose.yml          # 基础配置
docker-compose.server.yml   # 服务器部署（原 docker-compose.yml）
docker-compose.prod.yml     # 完整生产环境（优化）
```

**核心改进：**
- ✅ 命名语义明确
- ✅ Secrets 管理（替代硬编码密码）
- ✅ 三层配置分离（开发/服务器/完整生产）
- ✅ 符合 Docker Compose 最佳实践

---

## ⚠️ 注意事项

### 服务器部署前必须：

1. **确认 mysql8 和 redis6 容器运行正常**
   ```bash
   docker ps | grep -E "mysql8|redis6"
   ```

2. **确认 crmwolf-network 网络存在**
   ```bash
   docker network ls | grep crmwolf-network
   ```

3. **确认 secrets 目录存在且权限正确**
   ```bash
   ls -la /root/CRMWolf/secrets/
   # 应显示：-rw------- (600)
   ```

### secrets 文件内容验证

```bash
# 检查密码是否与 MySQL 一致
docker exec mysql8 mysql -u root -p$(cat secrets/db_password.txt) -e "SELECT 1"
```

---

## 📖 参考文档

- [DEPLOYMENT.md](../docs/DEPLOYMENT.md) - 部署操作手册
- [DOCKER-PACKAGING.md](./DOCKER-PACKAGING.md) - 打包部署规范
- [docker.md](./docker.md) - Docker 配置规范

---

**维护者**：CRMWolf 开发团队 | **更新日期**：2026-07-07