# API 请求规范

> 前端所有 HTTP 请求必须遵循此规范，确保开发/生产环境一致。

---

## 普通 API 请求

### 🟢 推荐做法

使用 axios request 实例，路径自动拼接 baseURL：

```typescript
// request.ts 配置
const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000
})

// API 调用（只写相对路径）
request.get('/v1/users/')
request.post('/v1/auth/login', data)
request.put('/v1/users/1', data)
request.delete('/v1/users/1')
```

**路径拼接过程**：
```
request.get('/v1/users/')
    ↓
axios 拼接 baseURL: '/api' + '/v1/users/' = '/api/v1/users/'
    ↓
Vite/Nginx 代理去掉 '/api': → 后端 '/v1/users/'
```

### 🔴 禁止做法

```typescript
// ❌ 禁止硬编码完整 URL
fetch('http://localhost:8000/v1/users')
axios.get('http://192.168.10.33:8080/api/v1/users')

// ❌ 禁止绕过 baseURL
axios.create({ baseURL: 'http://xxx' })

// ❌ 禁止动态拼接 baseURL
const baseURL = import.meta.env.VITE_API_BASE_URL || ''
axios.get(`${baseURL}/v1/users`)
```

---

## SSE 流式请求

### 🟢 推荐做法

使用完整路径 `/api/v1/xxx`，与普通 API 格式一致：

```typescript
// SSE 流式请求
const url = '/api/v1/ai/test'
const response = await fetch(url, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify(data)
})
```

**路径处理过程**：
```
fetch('/api/v1/ai/test')
    ↓
Vite/Nginx 代理去掉 '/api': → 后端 '/v1/ai/test'
```

### 🔴 禁止做法

```typescript
// ❌ 禁止动态拼接 baseURL（baseURL 为空时路径错误）
const baseURL = import.meta.env.VITE_API_BASE_URL || ''
const url = `${baseURL}/v1/ai/test`  // → '/v1/ai/test'，缺少 /api 前缀

// ❌ 禁止直连后端
const url = 'http://localhost:8000/v1/ai/test'
```

---

## 问题对比

| 做法 | 本地开发 | 生产环境 | 问题 |
|------|----------|----------|------|
| `request.get('/v1/xxx')` | `/api/v1/xxx` → `/v1/xxx` ✓ | `/api/v1/xxx` → `/v1/xxx` ✓ | 无 |
| `${baseURL}/v1/xxx` | `localhost:8000/v1/xxx` ✓ | `/v1/xxx` ✗ | 生产 405 |
| `/api/v1/xxx`（SSE） | `/api/v1/xxx` → `/v1/xxx` ✓ | `/api/v1/xxx` → `/v1/xxx` ✓ | 无 |

---

## 原因说明

### 为什么不能直连后端？

| 环境 | 直连后端 | 通过代理 |
|------|----------|----------|
| 本地 | `localhost:8000/v1/xxx` ✓ | `/api/v1/xxx` → `localhost:8000/v1/xxx` ✓ |
| 生产 | `localhost:8000` ✗（后端不在本地） | `/api/v1/xxx` → `backend:8000/v1/xxx` ✓ |

**结论**：直连后端只能在本地工作，生产环境失效。

### 为什么 SSE 不能用 `${baseURL}/v1/xxx`？

| 环境 | VITE_API_BASE_URL | 拼接结果 |
|------|-------------------|----------|
| 本地 | `http://localhost:8000` | `http://localhost:8000/v1/xxx` ✓（直连） |
| 生产 | 空（删除了） | `/v1/xxx` ✗（缺少 /api 前缀） |

**结论**：环境变量变化时，路径可能错误。使用固定 `/api/v1/xxx` 格式更可靠。

---

## 文件上传请求

### 🟢 推荐做法

```typescript
// 文件上传也使用 axios request
const formData = new FormData()
formData.append('file', file)

request.post('/v1/files/upload', formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})
```

### 🔴 禁止做法

```typescript
// ❌ 禁止硬编码上传 URL
const url = 'http://localhost:8000/v1/files/upload'
```

---

## WebSocket 连接

### 🟢 推荐做法

```typescript
// WebSocket 使用相对路径，让浏览器自动处理
const wsUrl = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}${location.host}/ws/chat`
const ws = new WebSocket(wsUrl)
```

### 🔴 禁止做法

```typescript
// ❌ 禁止硬编码 WebSocket 地址
const ws = new WebSocket('ws://localhost:8000/ws/chat')
```

---

## 相关配置

### .env 配置

```bash
# 禁止设置直连后端
# VITE_API_BASE_URL=http://localhost:8000

# 推荐：删除或置空，让 baseURL 默认为 '/api'
# VITE_API_BASE_URL=
```

### vite.config.ts

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true  // 去掉 /api 前缀转发
    }
  }
}
```

---

## 相关文档

- [environment.md](../deployment/environment.md) - 环境一致性配置
- [nginx.md](../deployment/nginx.md) - Nginx 代理配置