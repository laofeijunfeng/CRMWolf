# Docker 配置规范

> Docker 部署必须遵循此规范，确保容器化部署正确。

---

## Dockerfile 规范

### 🟢 推荐做法

```dockerfile
# 前端 Dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

# 后端 Dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS production
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## docker-compose 规范

### 🟢 推荐做法

```yaml
version: '3.8'

services:
  frontend:
    build: ./CRM-Client
    ports:
      - "8080:80"
    depends_on:
      - backend
    environment:
      - NODE_ENV=production

  backend:
    build: ./CRM-Server
    ports:
      - "8000:8000"
    depends_on:
      - mysql
      - redis
    environment:
      - DATABASE_URL=mysql+pymysql://root:password@mysql:3306/crm_db
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - CRM_DEBUG=false

  mysql:
    image: mysql:8.0
    ports:
      - "3306:3306"
    environment:
      - MYSQL_ROOT_PASSWORD=password
      - MYSQL_DATABASE=crm_db
    volumes:
      - mysql_data:/var/lib/mysql

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  mysql_data:
  redis_data:
```

---

## 网络配置

### 🟢 推荐做法

```yaml
services:
  frontend:
    networks:
      - frontend_network
      - backend_network

  backend:
    networks:
      - backend_network

networks:
  frontend_network:
    driver: bridge
  backend_network:
    driver: bridge
    internal: true  # 内部网络，不暴露外部
```

---

## 健康检查

### 🟢 推荐做法

```yaml
services:
  backend:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  mysql:
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5
```

---

## 环境变量管理

### 🟢 推荐做法

```yaml
services:
  backend:
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - SECRET_KEY=${SECRET_KEY}
      - CRM_DEBUG=${CRM_DEBUG:-false}  # 默认值
```

### 🔴 禁止做法

```yaml
# ❌ 禁止硬编码敏感信息
environment:
  - DATABASE_URL=mysql://root:password123@mysql:3306/crm
  - SECRET_KEY=hardcoded-secret-key
```

---

## 数据持久化

### 🟢 推荐做法

```yaml
volumes:
  mysql_data:
    driver: local
  redis_data:
    driver: local

services:
  mysql:
    volumes:
      - mysql_data:/var/lib/mysql
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql  # 初始化脚本

  backend:
    volumes:
      - ./logs:/app/logs  # 日志持久化
```

---

## 日志配置

### 🟢 推荐做法

```yaml
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## 常用命令

```bash
# 构建镜像（docker-compose.yml + override 自动合并）
docker compose build

# 启动服务（本地开发）
docker compose up -d

# 启动服务（服务器部署）
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d

# 启动服务（完整生产环境）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 查看日志
docker compose logs -f backend

# 重启服务
docker compose restart backend

# 停止并清理
docker compose down -v

# 进入容器
docker compose exec backend bash
```

---

## 生产部署建议

| 建议 | 说明 |
|------|------|
| 使用多阶段构建 | 减小镜像大小 |
| 设置健康检查 | 自动重启失败容器 |
| 配置资源限制 | 防止资源耗尽 |
| 使用 volumes | 数据持久化 |
| 分离敏感配置 | 环境变量或 secrets |

---

## 相关文档

- [nginx.md](nginx.md) - Nginx 配置规范
- [environment.md](environment.md) - 环境一致性规范