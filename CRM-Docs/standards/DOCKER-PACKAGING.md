# Docker 打包部署规范

**版本：1.1 | 创建日期：2026-05-28 | 更新：2026-06-02**

---

## 适用场景

从 Mac (arm64) 开发环境打包部署到 Linux x86_64 服务器。

---

## 核心要点

| 问题 | 解决方案 |
|------|----------|
| 架构不匹配导致 "exec format error" | 使用 `docker buildx --platform linux/amd64` |
| Entrypoint shebang 缺失 | Dockerfile 内强制验证/修复 shebang |
| 大文件传输 | 使用 `docker save` 导出为 tar 包 |

---

## 打包流程

### 1. 确认环境

```bash
# 开发机架构
uname -m
# 输出: arm64 (Mac)

# 目标服务器架构
# 输出: x86_64 (Linux)
```

### 2. 启用 buildx（首次需要）

```bash
# 创建并使用 builder实例
docker buildx create --name multiarch --use
docker buildx inspect --bootstrap
```

### 3. 构建后端镜像

```bash
cd CRM-Server

# 构建 amd64 镜像（关键：--platform + --load）
docker buildx build \
  --platform linux/amd64 \
  --tag crm-backend:amd64 \
  --load \
  .
```

**注意**：
- `--platform linux/amd64` 指定目标架构
- `--load` 将镜像加载到本地 Docker（否则只能推送到 registry）

### 4. 构建前端镜像

```bash
cd CRM-Client

# 构建 amd64 镜像
docker buildx build \
  --platform linux/amd64 \
  --tag crm-frontend:amd64 \
  --load \
  .
```

### 5. 导出镜像包

```bash
# 导出到 tar 文件
docker save crm-backend:amd64 crm-frontend:amd64 -o crm-images.tar

# 查看包大小
ls -lh crm-images.tar
# 约 300MB
```

---

## Dockerfile 关键配置

### 后端 Dockerfile（已修复 shebang 问题）

```dockerfile
# Copy entrypoint script
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh && head -1 entrypoint.sh | grep -q "^#!" || (echo "#!/bin/bash" | cat - entrypoint.sh > temp && mv temp entrypoint.sh && chmod +x entrypoint.sh)
```

**原因**：某些构建环境下 entrypoint.sh 第一行可能被截断，导致容器启动失败。

### Entrypoint.sh 规范

```bash
#!/bin/bash
# 必须以 shebang 开头
# 必须使用 Unix LF 行尾（不是 CRLF）

set -e

# 数据库迁移
alembic upgrade head

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 部署流程

### 1. 传输镜像包

```bash
scp crm-images.tar user@server:/path/to/deploy/
```

### 2. 加载镜像

```bash
ssh user@server
cd /path/to/deploy
docker load -i crm-images.tar
```

### 3. 启动服务

使用 docker-compose.yml：

```yaml
version: '3.8'
services:
  backend:
    image: crm-backend:amd64
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=mysql://...
      - REDIS_URL=redis://...
    depends_on:
      - mysql
      - redis

  frontend:
    image: crm-frontend:amd64
    ports:
      - "8080:80"
    depends_on:
      - backend
```

启动命令：

```bash
docker-compose up -d
```

### 4. 验证部署

```bash
# 检查容器状态
docker ps

# 检查后端日志
docker logs -f crm-backend

# 检查健康状态
curl http://localhost:8000/health
```

---

## 常见问题

### Q: "exec format error"

**原因**：镜像架构与服务器不匹配（arm64 → x86_64）

**解决**：使用 `--platform linux/amd64` 重新构建

### Q: 容器启动后立即退出

**原因**：Entrypoint 脚本缺少 shebang 或行尾错误

**解决**：
1. 检查 Dockerfile 是否有 shebang 修复步骤
2. 确保 entrypoint.sh 使用 LF 行尾
3. 验证：`docker run --rm --entrypoint "" crm-backend:amd64 head -1 /app/entrypoint.sh`

### Q: 构建时网络错误（Debian 仓库 404）

**解决**：使用缓存构建（不加 `--no-cache`），或等待网络恢复

### Q: 空数据库迁移失败 "Table doesn't exist"

**原因**：`001_initial` 迁移是空标记，依赖 entrypoint 先创建表再运行迁移

**解决**：entrypoint.sh 已修复，会自动：
1. 检测表是否存在
2. 空库时调用 `Base.metadata.create_all()` 创建所有表
3. Stamp 到 `001_initial` 版本标记
4. 再运行剩余迁移 `002` ~ `005`

**注意**：首次部署到空数据库时，启动日志应显示：
```
Step 2: Checking if tables exist...
No tables found
Creating all tables...
All tables created successfully
Stamping alembic to initial version...
Step 3: Running remaining migrations...
```

---

## 验证清单

打包前：
- [ ] 确认目标服务器架构为 x86_64
- [ ] Dockerfile 包含 shebang 修复步骤
- [ ] entrypoint.sh 使用 LF 行尾

构建时：
- [ ] 使用 `--platform linux/amd64`
- [ ] 使用 `--load` 加载到本地

导出时：
- [ ] 使用 `docker save` 导出为 tar
- [ ] 包含 backend 和 frontend 两个镜像

部署时：
- [ ] 使用 `docker load` 加载镜像
- [ ] 检查容器日志无 "exec format error"
- [ ] 空库部署时确认 "Creating all tables" 日志出现
- [ ] 验证健康检查端点响应正常

---

## 快速命令汇总

```bash
# 一键打包脚本（Mac → Linux x86_64）
cd /Users/eddie/Code/CRMWolf

# 后端
cd CRM-Server && docker buildx build --platform linux/amd64 --tag crm-backend:amd64 --load . && cd ..

# 前端
cd CRM-Client && docker buildx build --platform linux/amd64 --tag crm-frontend:amd64 --load . && cd ..

# 导出
docker save crm-backend:amd64 crm-frontend:amd64 -o crm-images.tar

# 验证
docker run --rm --entrypoint "" crm-backend:amd64 head -1 /app/entrypoint.sh
# 应输出: #!/bin/bash
```

---

## 附录：完整打包脚本

创建 `CRMWolf/scripts/docker-package.sh`：

```bash
#!/bin/bash
set -e

echo "=== CRMWolf Docker 打包脚本 ==="
echo "目标架构: linux/amd64 (x86_64)"

# 确认 buildx
docker buildx inspect multiarch || docker buildx create --name multiarch --use

# 构建后端
echo "[1/3] 构建后端镜像..."
cd CRM-Server
docker buildx build --platform linux/amd64 --tag crm-backend:amd64 --load .
cd ..

# 构建前端
echo "[2/3] 构建前端镜像..."
cd CRM-Client
docker buildx build --platform linux/amd64 --tag crm-frontend:amd64 --load .
cd ..

# 导出
echo "[3/3] 导出镜像包..."
docker save crm-backend:amd64 crm-frontend:amd64 -o crm-images.tar

echo "完成！镜像包: crm-images.tar ($(ls -lh crm-images.tar | awk '{print $5}'))"
```

---

**维护者**：AI Agent | **更新日期**：2026-05-28