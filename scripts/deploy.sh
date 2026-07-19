#!/bin/bash
# CRMWolf 自动化部署脚本
# 使用 SSH 密钥认证，一键打包、上传、部署

set -e

# === 配置区 ===
SERVER="root@8.134.219.103"
DEPLOY_DIR="/root/CRMWolf"  # 服务器部署目录
SSH_KEY="$HOME/.ssh/crmwolf_deploy"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="/root/CRMWolf-backups"

# === 颜色输出 ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo "${BLUE}[INFO]${NC} $1"; }
log_success() { echo "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo "${RED}[ERROR]${NC} $1"; }

# === 步骤 1: 本地打包 ===
build_images() {
    log_info "开始构建 Docker 镜像（linux/amd64）..."

    # 确保 buildx 环境
    if ! docker buildx inspect multiarch >/dev/null 2>&1; then
        log_info "创建 multiarch builder..."
        docker buildx create --name multiarch --use
        docker buildx inspect --bootstrap
    fi

    # 构建后端
    log_info "构建后端镜像..."
    cd "$PROJECT_DIR/CRM-Server"
    docker buildx build --platform linux/amd64 --tag crm-backend:amd64 --load .

    # 构建前端
    log_info "构建前端镜像..."
    cd "$PROJECT_DIR/CRM-Client"
    docker buildx build --platform linux/amd64 --tag crm-frontend:amd64 --load .

    cd "$PROJECT_DIR"

    # 导出镜像
    log_info "导出镜像包..."
    docker save crm-backend:amd64 crm-frontend:amd64 -o "$PROJECT_DIR/crm-images.tar"

    SIZE=$(ls -lh "$PROJECT_DIR/crm-images.tar" | awk '{print $5}')
    log_success "镜像包导出完成: crm-images.tar ($SIZE)"
}

# === 步骤 2: 上传到服务器 ===
upload_to_server() {
    log_info "上传镜像和配置文件到服务器..."

    # 使用 SSH 密钥认证
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "mkdir -p $DEPLOY_DIR $BACKUP_DIR"

    # 上传文件（镜像包 + 配置文件 + secrets）
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
        "$PROJECT_DIR/crm-images.tar" \
        "$PROJECT_DIR/docker-compose.yml" \
        "$PROJECT_DIR/docker-compose.server.yml" \
        "$SERVER:$DEPLOY_DIR/"

    # 上传 secrets 目录
    ssh -i "$SSH_KEY" "$SERVER" "mkdir -p $DEPLOY_DIR/secrets"
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
        "$PROJECT_DIR/secrets/db_password.txt" \
        "$PROJECT_DIR/secrets/secret_key.txt" \
        "$SERVER:$DEPLOY_DIR/secrets/"

    ssh -i "$SSH_KEY" "$SERVER" "chmod 600 $DEPLOY_DIR/secrets/*.txt"

    log_success "文件上传完成"
}

# === 步骤 3: 服务器端部署 ===
deploy_on_server() {
    log_info "开始服务器端部署..."

    ssh -i "$SSH_KEY" "$SERVER" << 'REMOTE_SCRIPT'
set -e

DEPLOY_DIR="/root/CRMWolf"
BACKUP_DIR="/root/CRMWolf-backups"

echo "=== 服务器端部署脚本 ==="

# 1. 备份旧版本镜像
if docker images | grep -q "crm-backend.*amd64"; then
    echo "[备份] 保存旧版本镜像..."
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    docker save crm-backend:amd64 crm-frontend:amd64 -o "$BACKUP_DIR/crm-images-backup-$TIMESTAMP.tar" || true
    echo "✅ 旧版本已备份到: $BACKUP_DIR/crm-images-backup-$TIMESTAMP.tar"
fi

# 2. 加载新镜像
echo "[加载] 加载新镜像..."
cd "$DEPLOY_DIR"
docker load -i crm-images.tar

# 3. 重启服务
echo "[重启] 重启 Docker 服务..."
# 使用新版 Docker 内置 compose 命令（docker compose 而非 docker-compose）
# 使用 server 配置文件（依赖外部 mysql8/redis6）
docker compose -f docker-compose.yml -f docker-compose.server.yml down || true
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d

# 4. 等待后端容器启动
echo "[等待] 等待服务启动..."
sleep 10

# 5. 执行数据库迁移（如有）
echo "[迁移] 执行数据库迁移..."
docker exec crm-backend python -m alembic upgrade head

# 6. 健康检查
echo "[检查] 执行健康检查..."
BACKEND_HEALTH=$(docker exec crm-backend curl -sf http://localhost:8000/health -o /dev/null -w "%{http_code}" 2>/dev/null || echo "000")
FRONTEND_HEALTH=$(docker exec crm-frontend curl -sf http://localhost:80/ -o /dev/null -w "%{http_code}" 2>/dev/null || echo "000")

if [ "$BACKEND_HEALTH" = "200" ] && [ "$FRONTEND_HEALTH" = "200" ]; then
    echo "✅ 后端健康检查通过 (HTTP $BACKEND_HEALTH)"
    echo "✅ 前端健康检查通过 (HTTP $FRONTEND_HEALTH)"
    echo ""
    echo "=== 部署成功 ==="
    echo "访问地址: http://$(curl -sf ifconfig.me 2>/dev/null || echo '服务器IP')"
else
    echo "❌ 健康检查失败:"
    echo "   后端: HTTP $BACKEND_HEALTH"
    echo "   前端: HTTP $FRONTEND_HEALTH"
    echo ""
    echo "=== 部署失败，请检查日志 ==="
    docker logs crm-backend --tail 50
    docker logs crm-frontend --tail 50
    exit 1
fi
REMOTE_SCRIPT

    log_success "服务器端部署完成"
}

# === 步骤 4: 清理本地临时文件 ===
cleanup() {
    log_info "清理本地临时文件..."
    rm -f "$PROJECT_DIR/crm-images.tar"
    log_success "清理完成"
}

# === 主流程 ===
main() {
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║   CRMWolf 自动化部署脚本              ║"
    echo "║   目标: $SERVER                      ║"
    echo "╚════════════════════════════════════════╝"
    echo ""

    # 检查 SSH 密钥
    if [ ! -f "$SSH_KEY" ]; then
        log_error "SSH 密钥不存在: $SSH_KEY"
        log_info "请先运行: ssh-keygen -t ed25519 -f $SSH_KEY -N ''"
        exit 1
    fi

    # 执行部署流程
    build_images
    upload_to_server
    deploy_on_server
    cleanup

    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║   ✅ 部署完成                         ║"
    echo "╚════════════════════════════════════════╝"
    echo ""
}

# 运行主流程
main "$@"
