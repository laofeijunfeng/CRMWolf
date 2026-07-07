# CRMWolf 部署操作手册

## 目录

1. [环境准备](#1-环境准备)
2. [配置说明](#2-配置说明)
3. [首次部署](#3-首次部署)
4. [系统升级](#4-系统升级)
5. [数据备份恢复](#5-数据备份恢复)
6. [常见问题](#6-常见问题)

---

## 1. 环境准备

### 1.1 安装 Docker

**Ubuntu/Debian:**
```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

**CentOS/RHEL:**
```bash
sudo yum install -y docker docker-compose
sudo systemctl start docker
sudo systemctl enable docker
```

**验证安装:**
```bash
docker --version
docker-compose --version
```

### 1.2 克隆代码

```bash
git clone https://github.com/your-org/CRMWolf.git
cd CRMWolf
```

---

## 2. 配置说明

### 2.1 环境变量

创建 `.env` 文件（开发环境）：

```bash
# 数据库配置
DB_PASSWORD=your_secure_password_here

# 应用密钥（JWT）
SECRET_KEY=your_random_secret_key_at_least_32_chars

# AI 配置（可选）
AI_API_URL=https://api.openai.com/v1/chat/completions
AI_API_KEY=sk-your-api-key
AI_MODEL=gpt-3.5-turbo

# 邮件配置（可选）
SMTP_PROVIDER=smtp
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USER=your_email@example.com
SMTP_PASSWORD=your_email_password
SMTP_FROM_EMAIL=your_email@example.com

# 调试模式（生产环境设为 false）
CRM_DEBUG=false
```

### 2.2 生产环境 Secrets

生产环境使用 Docker secrets：

```bash
# 创建 secrets 目录
mkdir -p secrets

# 创建数据库密码文件
echo "your_secure_password" > secrets/db_password.txt

# 创建应用密钥文件
echo "your_random_secret_key_at_least_32_chars" > secrets/secret_key.txt

# 设置权限
chmod 600 secrets/*.txt
```

### 2.3 SSL 配置（生产环境）

```bash
# 创建 SSL 目录
mkdir -p ssl

# 上传证书文件
# ssl/fullchain.pem - 证书链
# ssl/privkey.pem - 私钥
```

---

## 3. 首次部署

### 3.1 开发环境部署

```bash
# 构建镜像（docker-compose.yml + docker-compose.override.yml 自动合并）
docker compose build

# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f

# 检查服务状态
docker compose ps
```

### 3.2 服务器部署（已有 mysql8/redis6）

```bash
# 使用服务器配置文件
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d

# 查看日志
docker compose -f docker-compose.yml -f docker-compose.server.yml logs -f backend
```

### 3.3 完整生产环境部署（全新服务器）

```bash
# 使用完整生产配置构建和启动（包含数据库和缓存）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 查看日志
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend
```

### 3.3 验证部署

```bash
# 检查健康状态
curl http://localhost/health
curl http://localhost:8000/health

# 检查数据库
docker exec -it crm-mysql mysql -u root -p${DB_PASSWORD} -e "SHOW TABLES;" crm_db

# 检查角色初始化
docker exec -it crm-mysql mysql -u root -p${DB_PASSWORD} -e "SELECT * FROM roles;" crm_db
```

### 3.4 创建管理员账户

首次部署后，需要创建管理员账户：

```bash
# 进入后端容器
docker exec -it crm-backend bash

# 创建管理员（需要根据你的注册流程调整）
python -c "
from app.core.database import SessionLocal
from app.models import User, Role, UserRole
from passlib.context import CryptContext

db = SessionLocal()
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

# 创建管理员用户
admin = User(
    username='admin',
    email='admin@example.com',
    hashed_password=pwd_context.hash('admin_password'),
    name='系统管理员',
    status='active'
)
db.add(admin)

# 获取管理员角色
role = db.query(Role).filter(Role.code == 'TEAM_ADMIN').first()
if role:
    user_role = UserRole(user_id=admin.id, role_id=role.id)
    db.add(user_role)

db.commit()
print('管理员账户创建成功')
"
```

---

## 4. 系统升级

### 4.1 代码升级

```bash
# 拉取最新代码
git pull origin main

# 重建镜像
docker-compose build

# 重启服务（自动执行数据库迁移）
docker-compose up -d
```

### 4.2 数据库迁移流程

系统启动时会自动执行迁移：
1. `alembic upgrade head` - 执行所有待执行的迁移
2. 检查 `roles` 表是否为空 - 决定是否初始化数据

**手动迁移（可选）:**

```bash
# 进入后端容器
docker exec -it crm-backend bash

# 查看当前迁移状态
alembic current

# 查看待执行迁移
alembic history

# 执行迁移
alembic upgrade head

# 回滚（谨慎操作）
alembic downgrade -1
```

### 4.3 生成新迁移脚本

当模型发生变化时：

```bash
# 本地开发环境
cd CRM-Server

# 生成迁移脚本（自动检测模型变化）
alembic revision --autogenerate -m "add new field to user table"

# 编辑生成的脚本，确认变更正确
# migrations/versions/xxxx_add_new_field_to_user_table.py

# 执行迁移
alembic upgrade head

# 提交代码
git add migrations/versions/
git commit -m "feat: add new field to user table"
git push
```

---

## 5. 数据备份恢复

### 5.1 数据库备份

```bash
# 备份整个数据库
docker exec crm-mysql mysqldump -u root -p${DB_PASSWORD} crm_db > backup_$(date +%Y%m%d).sql

# 备份到指定目录
mkdir -p backups
docker exec crm-mysql mysqldump -u root -p${DB_PASSWORD} crm_db > backups/crm_db_$(date +%Y%m%d_%H%M%S).sql
```

### 5.2 数据库恢复

```bash
# 从备份文件恢复
docker exec -i crm-mysql mysql -u root -p${DB_PASSWORD} crm_db < backup_20240101.sql
```

### 5.3 定期备份脚本

```bash
#!/bin/bash
# backup.sh - 每日备份脚本

BACKUP_DIR="/var/backups/crm"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# 数据库备份
docker exec crm-mysql mysqldump -u root -p${DB_PASSWORD} crm_db > $BACKUP_DIR/db_$DATE.sql

# 上传文件备份
docker cp crm-backend:/app/uploads $BACKUP_DIR/uploads_$DATE

# 保留最近 30 天备份
find $BACKUP_DIR -type f -mtime +30 -delete

echo "Backup completed: $DATE"
```

**设置定时任务:**

```bash
# 编辑 crontab
crontab -e

# 添加每日备份（凌晨 2 点）
0 2 * * * /path/to/backup.sh >> /var/log/crm_backup.log 2>&1
```

---

## 6. 常见问题

### Q1: 容器启动失败，数据库连接错误

**原因**: MySQL 未就绪，后端过早启动

**解决**: 
```bash
# 检查 MySQL 状态
docker compose logs mysql

# 等待 MySQL 完全启动后重启后端
docker compose restart backend
```

### Q2: 数据库迁移失败

**原因**: 迁移脚本冲突或数据库版本不一致

**解决**:
```bash
# 查看迁移状态
docker exec -it crm-backend alembic current

# 标记当前数据库为最新版本（跳过迁移）
docker exec -it crm-backend alembic stamp head

# 重新启动
docker compose restart backend
```

### Q3: 前端无法访问后端 API

**原因**: Nginx 代理配置或网络问题

**解决**:
```bash
# 检查 Nginx 配置
docker exec -it crm-frontend cat /etc/nginx/conf.d/default.conf

# 测试后端直连
curl http://localhost:8000/health

# 测试前端代理
curl http://localhost/api/auth/me
```

### Q4: 如何查看运行日志

```bash
# 所有服务日志
docker compose logs -f

# 单个服务日志
docker compose logs -f backend
docker compose logs -f mysql

# 应用内部日志（如果配置了文件日志）
docker exec -it crm-backend tail -f /app/logs/app.log
```

### Q5: 如何重置整个系统

**警告**: 此操作会删除所有数据！

```bash
# 停止所有服务
docker compose down

# 删除数据卷
docker compose down -v

# 重新部署
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d --build
```

---

## 附录：服务架构图

```
┌─────────────────────────────────────────────────────────────┐
│                       用户浏览器                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Nginx)                          │
│  - 端口: 80                                                  │
│  - 静态文件托管                                              │
│  - /api/* 反向代理到 Backend                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  - 端口: 8000                                                │
│  - 启动时执行数据库迁移                                       │
│  - 启动时检查初始化数据                                       │
└─────────────────────────────────────────────────────────────┘
                    │                   │
                    ▼                   ▼
┌───────────────────────┐    ┌───────────────────────┐
│      MySQL 8.0        │    │      Redis 6.x        │
│  - 数据持久化          │    │  - 缓存/限流          │
│  - Volume 挂载        │    │  - Volume 挂载        │
└───────────────────────┘    └───────────────────────┘
```

---

**文档版本**: v1.0
**更新日期**: 2024-01-01
**维护者**: CRMWolf 开发团队