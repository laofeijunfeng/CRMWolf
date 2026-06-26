---
title: Frontend Logging System Design
date: 2026-06-26
status: approved
phase: design-approved
---

# Frontend Logging System Design

## Overview

自建前端日志系统，实现完整监控能力（类似 Sentry），包括：
- 分级日志 + 批量发送
- 性能监控
- Session Replay (rrweb)
- CLI 查询工具

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        整体架构                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Phase 1 (基础日志)                                              │
│  Frontend logger.ts → Backend API /v1/logs → File Storage       │
│                                                                  │
│  Phase 2 (性能监控)                                              │
│  Performance Monitor → Metrics API /v1/metrics → PostgreSQL     │
│                                                                  │
│  Phase 3 (Session Replay)                                       │
│  rrweb Recorder → Replay API /v1/replay → Replay Files          │
│                                                                  │
│  CLI 查询工具                                                    │
│  query_logs.py / query_metrics.py                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Phase 1: Basic Logging System

### Frontend (logger.ts)

**Status**: ✅ Mostly implemented, needs supplement

**Current Features**:
- ✅ 分级日志 (debug/info/warn/error)
- ✅ 批量发送 (20 条 / 5 秒)
- ✅ localStorage fallback
- ✅ 指数退避重试
- ✅ 全局错误捕获 (window.onerror, unhandledrejection)
- ✅ sendBeacon (页面关闭发送)
- ✅ Trace 关键路径追踪

**Needs Supplement**:
- 📝 自动获取 userId/teamId (从 Pinia userStore)
- 📝 面包屑日志 (用户操作路径)

### Backend (API + Service)

**New Files**:
- `app/api/frontend_logs.py`
  - POST `/v1/logs/batch` - 批量接收日志
  - POST `/v1/logs/beacon` - sendBeacon 专用端点

- `app/services/frontend_log_service.py`
  - 异步写入日志文件
  - 日志轮转 (每天一个文件)
  - 自动清理 (保留 30 天)

### Log Format (JSON)

```json
{
  "timestamp": 1719320400000,
  "level": "info",
  "context": "[AIAssistant]",
  "action": "restore",
  "data": { "stepsCount": 5, "success": true },
  "sessionId": "sess-abc123",
  "userId": 16,
  "teamId": 1,
  "url": "/ai-assistant",
  "userAgent": "Chrome/125"
}
```

### CLI Query Tool

**File**: `scripts/query_logs.py`

**Usage**:
```bash
# 查看今天的所有日志
python scripts/query_logs.py --date today

# 查看特定 context
python scripts/query_logs.py --context "[AIAssistant]"

# 查看错误日志
python scripts/query_logs.py --level error --date today

# 查看特定用户
python scripts/query_logs.py --user 16
```

## Phase 2: Performance Monitoring

### Frontend (performance.ts)

**New File**: `src/utils/performance.ts`

**Features**:
- 页面加载时间 (DOMContentLoaded, load)
- API 响应时间 (拦截 fetch/axios)
- 路由切换时间 (Vue router afterEach)
- 组件渲染时间 (可选，Performance API)

**Integration**:
- 在 `main.ts` 调用 `performance.init()`
- 拦截全局 fetch，记录响应时间
- 监听 router，记录路由切换时间

### Metrics Types

```json
{
  "type": "page_load",
  "duration": 1234,
  "url": "/ai-assistant",
  "timestamp": 1719320400000
}

{
  "type": "api_response",
  "duration": 256,
  "url": "/v1/customers",
  "method": "GET",
  "status": 200,
  "timestamp": 1719320400000
}

{
  "type": "route_change",
  "duration": 89,
  "from": "/customers",
  "to": "/ai-assistant",
  "timestamp": 1719320400000
}
```

### Backend (API + Model)

**New Files**:
- `app/api/metrics.py`
  - POST `/v1/metrics` - 接收性能指标

- `app/models/performance_metric.py`
  - PostgreSQL 表存储

- `app/services/metrics_service.py`
  - 性能数据聚合统计

**Database Schema**:
```sql
CREATE TABLE performance_metrics (
  id SERIAL PRIMARY KEY,
  type VARCHAR(50),
  duration INTEGER,
  url VARCHAR(255),
  user_id INTEGER,
  team_id INTEGER,
  session_id VARCHAR(50),
  created_at TIMESTAMP
);
```

### CLI Query Tool

**File**: `scripts/query_metrics.py`

**Usage**:
```bash
# 查看今天的 API 性能
python scripts/query_metrics.py --type api_response

# 查看慢请求 (>500ms)
python scripts/query_metrics.py --slow 500

# 性能统计报告
python scripts/query_metrics.py --report
```

## Phase 3: Session Replay (rrweb)

### rrweb Integration

**Library**: rrweb (GitHub 14K+ stars)
```bash
npm install rrweb rrweb-player
```

**Features**:
- ✅ DOM 录制 (MutationObserver)
- ✅ 用户输入录制 (鼠标、键盘、滚动)
- ✅ 网络请求录制
- ✅ 回放引擎
- ✅ 压缩存储

### Frontend (replay.ts)

**New File**: `src/utils/replay.ts`

**Recording Logic**:
- 用户进入页面时启动录制
- 每 10 秒或页面离开时发送片段
- 关键操作时触发发送 (如提交表单、完成对话)

**Integration Code**:
```typescript
import { record } from 'rrweb'

record({
  emit(event) {
    replayLogger.sendChunk([event])
  },
  packFn: rrweb.pack,
  maskAllInputs: true
})
```

### Backend (API + Service)

**New Files**:
- `app/api/replay.py`
  - POST `/v1/replay/chunk` - 接收录制片段
  - GET `/v1/replay/:id` - 获取录制数据
  - GET `/v1/replay/list` - 列出所有录制

- `app/services/replay_service.py`
  - 存储录制文件
  - 会话关联

**Storage**: `logs/replay/sess-abc123.rrweb`

### Replay Viewer (Admin Page)

**New File**: `src/views/admin/ReplayViewer.vue`

**Features**:
- 使用 rrweb-player 播放录制
- 支持时间轴跳转
- 支持播放速度调节
- 显示会话信息 (userId, 时间, 页面)

**Permission**: `admin.replay.view`

### Privacy Handling (Phase 3 Implementation)

```typescript
maskAllInputs: true
maskInputOptions: {
  password: true,
  email: '[email]',
  phone: '[phone]'
}
```

**User Consent** (Optional):
- 首次使用时弹窗同意
- localStorage 记录用户选择
- 用户可随时关闭录制

## File Structure

```
CRM-Client/src/utils/
├── logger.ts            ✅ 已实现 (需补充 userId/teamId)
├── logger.config.ts     📝 新增 (配置项)
├── performance.ts       📝 Phase 2 新增
└── replay.ts            📝 Phase 3 新增

CRM-Server/app/api/
├── frontend_logs.py     📝 Phase 1 新增
├── metrics.py           📝 Phase 2 新增
└── replay.py            📝 Phase 3 新增

CRM-Server/app/services/
├── frontend_log_service.py    📝 Phase 1 新增
├── metrics_service.py         📝 Phase 2 新增
└── replay_service.py          📝 Phase 3 新增

CRM-Server/app/models/
└── performance_metric.py      📝 Phase 2 新增

CRM-Server/logs/
├── frontend-2024-06-26.log    📝 Phase 1 日志文件
└── replay/                    📝 Phase 3 回放文件目录

CRM-Server/scripts/
├── query_logs.py       📝 Phase 1 CLI 查询
└── query_metrics.py    📝 Phase 2 CLI 查询

CRM-Client/src/views/admin/
└── ReplayViewer.vue    📝 Phase 3 回放页面
```

## Implementation Plan

### Phase 1: Basic Logging (1-2 days)

**Day 1**:
- 补充 logger.ts (userId/teamId 自动获取)
- 新增 frontend_logs.py (后端 API)
- 新增 frontend_log_service.py (文件写入)
- 测试日志发送

**Day 2**:
- 新增 query_logs.py (CLI 查询)
- 集成到关键路径 (AIAssistant restore)
- 验收测试

### Phase 2: Performance Monitoring (1 day)

- 新增 performance.ts (前端拦截)
- 新增 metrics.py + metrics_service.py
- 新增 performance_metric 表
- 新增 query_metrics.py
- 验收测试

### Phase 3: Session Replay (2 days)

**Day 1**:
- npm install rrweb rrweb-player
- 新增 replay.ts (前端录制)
- 新增 replay.py + replay_service.py

**Day 2**:
- 新增 ReplayViewer.vue (回放页面)
- 权限配置
- 隐私处理
- 验收测试

**Total**: 4-5 days

## Success Criteria

### A. Debug Tracing ✅
- 能追踪调试问题（如 execution steps 不显示）
- 能在日志中看到完整追踪链路并定位原因

### B. User Behavior Analysis ✅
- 能查看用户操作路径（面包屑日志）
- 能分析常见问题和优化点

### C. Performance Monitoring ✅
- 能看到页面加载时间、API 响应时间
- 能发现性能瓶颈

## Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| 存储方式 | 文件存储 | 简单可靠，无外部依赖 |
| Session Replay | rrweb 开源库 | 成熟方案，无需自研录制引擎 |
| 发送频率 | 20 条 / 5 秒 | 平衡性能和可靠性 |
| 用户关联 | userId + teamId | 自动从 userStore 获取 |
| 日志保留 | 30 天自动清理 | 避免磁盘爆炸 |
| 查询方式 | CLI 脚本 | 先不做 Dashboard |

## Dependencies

- Frontend: 无新增 npm 依赖（Phase 3 需要 rrweb）
- Backend: 无新增依赖（使用现有 logging 系统）

## Risks

| Risk | Mitigation |
|------|------------|
| localStorage 满 | 限制最大暂存数量 (100 条) |
| 网络请求失败 | 指数退避重试 + localStorage fallback |
| 日志文件过大 | 每天轮转 + 30 天自动清理 |
| 性能监控影响性能 | 仅拦截关键 API，配置采样率 |
| Session Replay 隐私 | Phase 3 实现时配置遮罩规则 |

## Next Steps

1. Invoke `writing-plans` skill to create detailed implementation plan
2. Implement Phase 1 (基础日志系统)
3. Verify success criteria
4. Implement Phase 2 and Phase 3 as needed