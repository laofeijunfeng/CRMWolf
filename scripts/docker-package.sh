#!/bin/bash
# CRMWolf Docker 打包脚本
# 用于从 Mac (arm64) 打包部署到 Linux x86_64 服务器

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== CRMWolf Docker 打包脚本 ==="
echo "目标架构: linux/amd64 (x86_64)"
echo ""

# 确认 buildx
echo "[准备] 检查 buildx 环境..."
if ! docker buildx inspect multiarch 2>/dev/null; then
    echo "创建 multiarch builder..."
    docker buildx create --name multiarch --use
    docker buildx inspect --bootstrap
fi

# 构建后端
echo ""
echo "[1/3] 构建后端镜像..."
cd "$PROJECT_DIR/CRM-Server"
docker buildx build --platform linux/amd64 --tag crm-backend:amd64 --load .
cd "$PROJECT_DIR"

# 构建前端
echo ""
echo "[2/3] 构建前端镜像..."
cd "$PROJECT_DIR/CRM-Client"
docker buildx build --platform linux/amd64 --tag crm-frontend:amd64 --load .
cd "$PROJECT_DIR"

# 验证
echo ""
echo "[验证] 检查 shebang..."
docker run --rm --entrypoint "" crm-backend:amd64 head -1 /app/entrypoint.sh

# 导出
echo ""
echo "[3/3] 导出镜像包..."
docker save crm-backend:amd64 crm-frontend:amd64 -o "$PROJECT_DIR/crm-images.tar"

SIZE=$(ls -lh "$PROJECT_DIR/crm-images.tar" | awk '{print $5}')
echo ""
echo "=== 完成 ==="
echo "镜像包: crm-images.tar ($SIZE)"
echo "位置: $PROJECT_DIR/crm-images.tar"
echo ""
echo "部署命令:"
echo "  scp crm-images.tar docker-compose.server.yml user@server:/path/"
echo "  ssh user@server 'docker load -i /path/crm-images.tar && docker compose -f docker-compose.server.yml up -d'"