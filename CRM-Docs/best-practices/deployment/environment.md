# 环境一致性规范

> 开发和生产环境必须保持一致，避免"本地正常、生产异常"的问题。

---

## 核心原则

### 🔴 强制要求

**开发环境必须通过代理访问后端，禁止直连**

```
┌─────────────────────────────────────────────────────────────┐
│                      环境一致性架构                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  开发环境                                                    │
│  前端 → /api/v1/xxx → Vite 代理 → localhost:8000/v1/xxx    │
│                                                             │
│  生产环境                                                    │
│  前端 → /api/v1/xxx → Nginx 代理 → backend:8000/v1/xxx     │
│                                                             │
│  两者路径完全一致：/api/v1/xxx                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## .env 配置规范

### 🔴 禁止做法

```bash
# ❌ 禁止直连后端
VITE_API_BASE_URL=http://localhost:8000

# ❌ 禁止硬编码生产地址
VITE_API_BASE_URL=http://192.168.10.33:8080
```

### 🟢 推荐做法

```bash
# 删除或置空，让 baseURL 默认为 '/api'
# VITE_API_BASE_URL=

# 或显式使用代理路径
VITE_API_BASE_URL=/api
```

---

## Vite 代理配置

### 🟢 推荐做法

```typescript
// vite.config.ts
server: {
  port: 5173,
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true  // 去掉 /api 前缀转发
    }
  }
}
```

**路径处理过程**：
```
前端请求：/api/v1/users
    ↓
Vite 代理去掉 '/api'：localhost:8000/v1/users
    ↓
后端接收：/v1/users
```

---

## Nginx 代理配置

### 🟢 推荐做法

```nginx
# CRM-Client/nginx.conf
location /api/ {
    proxy_pass http://backend:8000/;  # 去掉 /api 前缀转发
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    
    # SSE 流式响应支持
    proxy_buffering off;
    proxy_cache off;
}
```

**路径处理过程**：
```
前端请求：/api/v1/users
    ↓
Nginx 代理去掉 '/api'：backend:8000/v1/users
    ↓
后端接收：/v1/users
```

---

## 问题对比

### 直连后端的问题

| 环境 | 直连配置 | 结果 |
|------|----------|------|
| 本地 | `localhost:8000/v1/xxx` | ✓ 正常 |
| 生产 | `localhost:8000/v1/xxx` | ✗ 后端不在本地 |

### 代理方案的效果

| 环境 | 代理配置 | 结果 |
|------|----------|------|
| 本地 | `/api/v1/xxx` → Vite → `localhost:8000/v1/xxx` | ✓ 正常 |
| 生产 | `/api/v1/xxx` → Nginx → `backend:8000/v1/xxx` | ✓ 正常 |

---

## SSE 流式请求

### 🔴 禁止做法

```typescript
// ❌ 禁止动态拼接 baseURL
const baseURL = import.meta.env.VITE_API_BASE_URL || ''
const url = `${baseURL}/v1/ai/test`

// 本地：baseURL = 'http://localhost:8000' → 'http://localhost:8000/v1/ai/test' ✓
// 生产：baseURL = '' → '/v1/ai/test' ✗（缺少 /api 前缀）
```

### 🟢 推荐做法

```typescript
// ✅ 使用固定路径
const url = '/api/v1/ai/test'

// 本地：/api/v1/ai/test → Vite → localhost:8000/v1/ai/test ✓
// 生产：/api/v1/ai/test → Nginx → backend:8000/v1/ai/test ✓
```

---

## axios baseURL 配置

### 🟢 推荐做法

```typescript
// request.ts
const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000
})

// 当 VITE_API_BASE_URL 为空时，baseURL = '/api'
// 前端请求 request.get('/v1/users') → /api/v1/users
```

---

## 环境变量使用原则

### 规则总结

| 类型 | 配置方式 | 禁止做法 |
|------|----------|----------|
| 普通 API | axios + baseURL | 硬编码完整 URL |
| SSE 流式 | `/api/v1/xxx` 固定路径 | `${baseURL}/v1/xxx` 动态拼接 |
| WebSocket | 相对路径 `${location.host}/ws` | 硬编码地址 |

---

## 验证方法

### 开发环境验证

```bash
# 启动前端
cd CRM-Client && npm run dev

# 打开浏览器 DevTools Network 面板
# 检查请求路径应为 /api/v1/xxx
# 检查实际转发应为 localhost:8000/v1/xxx
```

### 生产环境验证

```bash
# curl 测试
curl 'http://production/api/v1/ai/test' -H 'Authorization: Bearer xxx' -d '{"test_message":"hi"}'

# 检查 Nginx 日志
# 应显示转发到 backend:8000/v1/ai/test
```

---

## 相关文档

- [nginx.md](nginx.md) - Nginx 配置规范
- [api-requests.md](../frontend/api-requests.md) - API 请求规范