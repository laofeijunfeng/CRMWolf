# Nginx 配置规范

> Nginx 作为反向代理，必须遵循此规范，确保路径转发正确。

---

## 核心原则

### 🔴 强制要求

**Nginx 透传路径，不做改写（只去掉 /api 前缀）**

```
┌─────────────────────────────────────────────────────────────┐
│                      Nginx 路径处理                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  输入：/api/v1/users                                        │
│  输出：backend:8000/v1/users（去掉 /api，保留 /v1）          │
│                                                             │
│  配置：proxy_pass http://backend:8000/;  // 有尾部斜杠      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## API 代理配置

### 🟢 推荐做法

```nginx
location /api/ {
    proxy_pass http://backend:8000/;  # 有尾部斜杠，去掉 /api 前缀
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

**路径处理说明**：

| proxy_pass 配置 | /api/v1/users 转发结果 |
|-----------------|------------------------|
| `http://backend:8000/` (有尾部斜杠) | backend:8000/v1/users ✓ |
| `http://backend:8000` (无尾部斜杠) | backend:8000/api/v1/users ✗ |

---

## SSE 流式响应配置

### 🟢 推荐做法

```nginx
location /api/ {
    proxy_pass http://backend:8000/;
    
    # SSE 流式响应必需配置
    proxy_buffering off;          # 禁用缓冲
    proxy_cache off;              # 禁用缓存
    proxy_read_timeout 86400s;    # 长连接超时
    
    # 传递原始请求头
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;  # 禁用分块编码
}
```

---

## WebSocket 配置

### 🟢 推荐做法

```nginx
location /ws/ {
    proxy_pass http://backend:8000/ws/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

---

## 静态资源配置

### 🟢 推荐做法

```nginx
location /static/ {
    alias /path/to/static/;  # 使用 alias
    expires 30d;
    add_header Cache-Control "public, immutable";
}

location / {
    root /path/to/frontend/dist;  # 前端静态文件
    try_files $uri $uri/ /index.html;  # SPA 路由支持
}
```

---

## Glue 层代理配置

### 🟢 推荐做法（可选）

如果飞书回调也需要通过 Nginx：

```nginx
location /glue/ {
    proxy_pass http://backend:8000/glue/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

---

## 安全配置

### 🟢 推荐做法

```nginx
# 隐藏版本号
server_tokens off;

# 安全头
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;

# 限制请求大小
client_max_body_size 10M;

# SSL 配置（生产环境）
ssl_protocols TLSv1.2 TLSv1.3;
ssl_prefer_server_ciphers on;
```

---

## 日志配置

### 🟢 推荐做法

```nginx
log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                '$status $body_bytes_sent "$http_referer" '
                '"$http_user_agent" "$http_x_forwarded_for" '
                'upstream: $upstream_addr';

access_log /var/log/nginx/access.log main;
error_log /var/log/nginx/error.log warn;
```

---

## 常见错误

### 🔴 禁止做法

```nginx
# ❌ 禁止去掉整个路径
location /api/ {
    proxy_pass http://backend:8000;  # 无尾部斜杠，路径错误
}

# ❌ 禁止改写路径
location /api/ {
    rewrite ^/api/(.*) /$1 break;  # 不推荐用 rewrite
    proxy_pass http://backend:8000;
}

# ❌ 禁止忘记 SSE 配置
location /api/ {
    proxy_pass http://backend:8000/;
    # 缺少 proxy_buffering off，SSE 响应会被缓冲
}
```

---

## 配置验证

```bash
# 检查配置语法
nginx -t

# 查看转发日志
tail -f /var/log/nginx/access.log

# 测试 SSE 响应
curl -N 'http://production/api/v1/ai/test' -d '{"test_message":"hi"}'
```

---

## 相关文档

- [environment.md](environment.md) - 环境一致性规范
- [docker.md](docker.md) - Docker 配置规范