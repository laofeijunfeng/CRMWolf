# 复盘：SSE 请求路径不一致问题

**日期**：2024-06-04
**严重程度**：中等
**影响范围**：AI 配置测试、AI 助手对话、线索解析等 SSE 功能

---

## 问题现象

### 用户报错

```bash
# 本地测试正常
curl 'http://localhost:8000/v1/ai/test' -d '{"test_message":"HI"}'
# ✓ 返回正常 SSE 流式响应

# 生产测试失败
curl 'http://192.168.10.33:8080/v1/ai/test' -d '{"test_message":"HI"}'
# ✗ 405 Not Allowed（nginx 错误）

# 生产测试成功（加了 /api 前缀）
curl 'http://192.168.10.33:8080/api/v1/ai/test' -d '{"test_message":"HI"}'
# ✓ 返回正常
```

### 前端现象

- AI 配置页面点击"测试连接"无响应
- AI 助手对话功能失效
- 线索 AI 解析功能失效

---

## 问题分析

### 表面原因

- 本地直连后端，路径 `/v1/ai/test` 正常
- 生产通过 Nginx，路径 `/v1/ai/test` 缺少 `/api` 前缀，Nginx 无匹配规则，返回 405

### 根本原因

1. **前端 SSE 请求使用动态拼接**：
   ```typescript
   const baseURL = import.meta.env.VITE_API_BASE_URL || ''
   const url = `${baseURL}/v1/ai/test`
   ```

2. **开发环境配置直连后端**：
   ```bash
   VITE_API_BASE_URL=http://localhost:8000
   ```
   结果：`http://localhost:8000/v1/ai/test` ✓（绕过代理）

3. **生产环境变量置空**：
   ```bash
   # VITE_API_BASE_URL=
   ```
   结果：`/v1/ai/test` ✗（缺少 `/api` 前缀）

4. **Nginx 只代理 `/api/` 前缀的请求**：
   ```nginx
   location /api/ {
       proxy_pass http://backend:8000/;
   }
   ```
   `/v1/ai/test` 无匹配 → 405

---

## 成本分析

| 成本类型 | 简单方案 | 成熟方案 |
|----------|----------|----------|
| 实现成本 | 10 分钟（动态拼接） | 20 分钟（固定路径） |
| 排查成本 | 4 小时 × 1 次 = 4 小时 | 0 |
| 总成本 | 4 小时 10 分钟 | 20 分钟 |

**结论**：多花 10 分钟实现成熟方案，节省 4 小时排查时间。

---

## 解决方案

### Phase 1：修改前端配置和路径

1. **删除 .env 直连配置**：
   ```bash
   # 删除 VITE_API_BASE_URL=http://localhost:8000
   # VITE_API_BASE_URL=
   ```

2. **修改 SSE 请求路径**（6 个文件）：
   ```typescript
   // 修改前
   const baseURL = import.meta.env.VITE_API_BASE_URL || ''
   const url = `${baseURL}/v1/ai/test`
   
   // 修改后
   const url = '/api/v1/ai/test'
   ```

3. **涉及文件**：
   - `CRM-Client/src/api/aiConfig.ts`
   - `CRM-Client/src/api/aiAssistant.ts`
   - `CRM-Client/src/api/leadAI.ts`
   - `CRM-Client/src/api/customerAI.ts`
   - `CRM-Client/src/api/aiSkills.ts`（2 处）

### 验证结果

| 环境 | 修改后路径 | 结果 |
|------|------------|------|
| 本地 | `/api/v1/ai/test` → Vite → `localhost:8000/v1/ai/test` | ✓ |
| 生产 | `/api/v1/ai/test` → Nginx → `backend:8000/v1/ai/test` | ✓ |

---

## 教训总结

### 技术层面

1. **特殊请求也要遵循统一配置**：
   - SSE/WebSocket/文件上传等请求，路径格式应与普通 API 一致

2. **动态拼接路径不可靠**：
   - 环境变量变化时，路径可能错误
   - 应使用固定路径 `/api/v1/xxx`

3. **开发环境不应直连后端**：
   - 应通过 Vite 代理，与生产行为一致
   - 直连只能在本地工作，生产失效

### 流程层面

1. **开发时未考虑环境一致性**：
   - 只关注"能跑起来"，未考虑"生产环境怎么工作"

2. **缺少环境一致性检查**：
   - Code Review 未发现硬编码路径问题
   - 无自动化测试覆盖 SSE 路径

---

## 知识库更新

已更新以下文档：

| 文档 | 更新内容 |
|------|----------|
| [frontend/api-requests.md](../frontend/api-requests.md) | SSE 流式请求规范 |
| [deployment/environment.md](../deployment/environment.md) | 环境一致性规范 |
| [decisions.md](../decisions.md) | SSE 请求成本案例 |

---

## 防止复发措施

1. **在 AGENTS.md 添加规范**：
   - 禁止 `${VITE_API_BASE_URL}/v1/xxx` 动态拼接
   - SSE 请求使用 `/api/v1/xxx` 固定路径

2. **Code Review 检查点**：
   - 检查硬编码路径
   - 检查动态拼接 URL
   - 检查只在本地能跑的代码

3. **自动化测试**：
   - 添加 SSE 路径测试
   - 环境一致性集成测试

---

## 相关问题

- [team_id 缺失问题](team_id缺失.md)（如有）
- 其他路径不一致问题

---

## 参考链接

- [api-requests.md](../frontend/api-requests.md) - API 请求规范
- [environment.md](../deployment/environment.md) - 环境一致性规范