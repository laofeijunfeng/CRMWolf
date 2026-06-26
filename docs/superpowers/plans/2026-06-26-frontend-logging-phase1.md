# Frontend Logging System Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现基础前端日志系统，支持分级日志、批量发送、文件存储、CLI 查询

**Architecture:** Frontend logger.ts 批量发送日志 → Backend API /v1/logs/batch → 异步写入日志文件 → CLI 查询工具 query_logs.py

**Tech Stack:** TypeScript (Vue3/Pinia), Python (FastAPI), JSON file storage

## Global Constraints

From spec `docs/superpowers/specs/2026-06-26-frontend-logging-system-design.md`:

- 发送频率: 20 条或 5 秒发送一次
- 日志保留: 30 天自动清理
- 用户关联: userId + teamId（从 userStore 自动获取）
- 日志格式: 每行一个 JSON，结构化便于查询
- 存储路径: `CRM-Server/logs/frontend-YYYY-MM-DD.log`
- TypeScript: 禁止 `any` `as any` `@ts-ignore` `!`
- Vue 组件: Props/Emits 必须类型化
- Pinia Store: 禁止 any 状态，必须 storeToRefs 解构

---

## File Structure

### Frontend (CRM-Client)

| File | Purpose | Status |
|------|---------|--------|
| `src/utils/logger.ts` | 核心日志类（分级、批量发送、fallback） | ✅ 已存在，需补充 userId/teamId |
| `src/utils/logger.config.ts` | 配置项（endpoint、bufferSize、flushInterval） | 📝 新增 |

### Backend (CRM-Server)

| File | Purpose | Status |
|------|---------|--------|
| `app/api/frontend_logs.py` | API 端点（POST /v1/logs/batch, /v1/logs/beacon） | 📝 新增 |
| `app/services/frontend_log_service.py` | 文件写入、日志轮转、自动清理 | 📝 新增 |
| `app/schemas/frontend_log.py` | Pydantic schema 定义 | 📝 新增 |
| `scripts/query_logs.py` | CLI 查询工具 | 📝 新增 |
| `logs/frontend-YYYY-MM-DD.log` | 日志文件存储 | 📝 运行时生成 |

---

### Task 1: Supplement Frontend logger.ts

**Files:**
- Modify: `CRM-Client/src/utils/logger.ts:50-80` (补充 userId/teamId 获取)
- Create: `CRM-Client/src/utils/logger.config.ts`

**Interfaces:**
- Consumes: `useUserStore()` (userId from `userInfo.id`)
- Consumes: `teamApi.getUserTeams()` (teamId from `current_team_id`)
- Produces: `logger` singleton with `userId/teamId` auto-included in every log entry

- [ ] **Step 1: Read current logger.ts to understand existing structure**

Run: `cat CRM-Client/src/utils/logger.ts | head -100`

Expected: See existing FrontendLogger class with buffer, flush, retry logic

- [ ] **Step 2: Create logger.config.ts with default config**

Create file `CRM-Client/src/utils/logger.config.ts`:

```typescript
/**
 * Logger Configuration
 *
 * Default settings for frontend logging system
 */

export interface LoggerConfig {
  /** 是否启用远程日志（默认：生产环境启用） */
  enabled: boolean
  /** API endpoint */
  endpoint: string
  /** Beacon endpoint (页面关闭时) */
  beaconEndpoint: string
  /** 缓冲区大小（达到此数量立即发送） */
  bufferSize: number
  /** 发送间隔（毫秒） */
  flushInterval: number
  /** 最大重试次数 */
  maxRetries: number
  /** localStorage 键名（用于暂存失败日志） */
  storageKey: string
  /** 是否在 console 显示 */
  consoleOutput: boolean
}

export const DEFAULT_LOGGER_CONFIG: LoggerConfig = {
  enabled: import.meta.env.PROD,
  endpoint: '/v1/logs/batch',
  beaconEndpoint: '/v1/logs/beacon',
  bufferSize: 20,
  flushInterval: 5000,
  maxRetries: 3,
  storageKey: 'crm_frontend_logs',
  consoleOutput: import.meta.env.DEV
}
```

- [ ] **Step 3: Modify logger.ts to import config**

Edit `CRM-Client/src/utils/logger.ts:29-50`, replace hardcoded config with import:

```typescript
// Add import at top
import { DEFAULT_LOGGER_CONFIG, type LoggerConfig } from './logger.config'

// Replace DEFAULT_CONFIG constant (around line 50)
const DEFAULT_CONFIG: LoggerConfig = DEFAULT_LOGGER_CONFIG
```

- [ ] **Step 4: Add userId/teamId getter function in logger.ts**

Add after imports (around line 30):

```typescript
import { useUserStore } from '@/stores/user'
import { teamApi } from '@/api/team'

/**
 * 获取当前用户信息（userId + teamId）
 * 
 * @returns userId 和 teamId（可能为 undefined）
 */
async function getCurrentUserInfo(): Promise<{ userId?: number; teamId?: number }> {
  try {
    const userStore = useUserStore()
    const userId = userStore.userInfo?.id
    
    // 获取当前团队 ID
    let teamId: number | undefined
    try {
      const teamsResponse = await teamApi.getUserTeams()
      teamId = teamsResponse.current_team_id
    } catch {
      // 获取团队失败时静默忽略
      console.warn('[Logger] Failed to get team info')
    }
    
    return { userId, teamId }
  } catch {
    return {}
  }
}

// 缓存用户信息（避免频繁请求）
let cachedUserInfo: { userId?: number; teamId?: number } | null = null
let userInfoCacheTime = 0
const USER_INFO_CACHE_DURATION = 60000 // 1 分钟缓存

async function getCachedUserInfo(): Promise<{ userId?: number; teamId?: number }> {
  const now = Date.now()
  if (cachedUserInfo && now - userInfoCacheTime < USER_INFO_CACHE_DURATION) {
    return cachedUserInfo
  }
  
  cachedUserInfo = await getCurrentUserInfo()
  userInfoCacheTime = now
  return cachedUserInfo
}
```

- [ ] **Step 5: Modify LogEntry interface to include userId/teamId**

Edit interface around line 35-42:

```typescript
interface LogEntry {
  level: LogLevel
  context: string
  action: string
  data: unknown
  timestamp: number
  traceId?: string
  // 新增：用户关联
  userId?: number
  teamId?: number
}
```

- [ ] **Step 6: Modify log() method to include userId/teamId**

Find the `private log()` method (around line 200) and modify:

```typescript
private async log(level: LogLevel, context: string, action: string, data: unknown): void {
  // 获取用户信息（异步但不阻塞）
  const userInfo = await getCachedUserInfo()
  
  const entry: LogEntry = {
    level,
    context,
    action,
    data,
    timestamp: Date.now(),
    traceId: this.sessionId,
    userId: userInfo.userId,
    teamId: userInfo.teamId
  }

  // Console 输出（开发环境）
  if (this.config.consoleOutput) {
    this.outputToConsole(entry)
  }

  // 加入缓冲
  this.buffer.push(entry)

  // 达到缓冲大小立即发送
  if (this.buffer.length >= this.config.bufferSize) {
    this.flush()
  }
}
```

- [ ] **Step 7: Update sendLogs to include url and userAgent**

Modify `sendLogs()` method (around line 250):

```typescript
private async sendLogs(): Promise<void> {
  if (!this.config.enabled || this.buffer.length === 0) return

  this.isSending = true
  const logsToSend = [...this.buffer]
  this.buffer = []

  try {
    await request.post(this.config.endpoint, {
      logs: logsToSend,
      sessionId: this.sessionId,
      userAgent: navigator.userAgent,
      url: window.location.href
    })

    // 发送成功，重置重试计数
    this.retryCount = 0

    // 清理 localStorage 暂存
    this.clearStorage()

  } catch (error) {
    // ... existing retry logic
  }

  this.isSending = false
}
```

- [ ] **Step 8: Run TypeScript check to verify no errors**

Run: `cd CRM-Client && npm run type-check 2>&1 | grep logger.ts`

Expected: No errors related to logger.ts (other pre-existing errors may show)

- [ ] **Step 9: Commit frontend logger changes**

```bash
git add CRM-Client/src/utils/logger.ts CRM-Client/src/utils/logger.config.ts
git commit -m "feat(logger): add userId/teamId auto-inclusion + config file"
```

---

### Task 2: Create Backend API frontend_logs.py

**Files:**
- Create: `CRM-Server/app/api/frontend_logs.py`
- Create: `CRM-Server/app/schemas/frontend_log.py`

**Interfaces:**
- Consumes: FastAPI router pattern from `app/api/*.py`
- Consumes: Pydantic schema pattern from `app/schemas/*.py`
- Produces: POST `/v1/logs/batch` endpoint
- Produces: POST `/v1/logs/beacon` endpoint (sendBeacon专用)

- [ ] **Step 1: Check existing API pattern for reference**

Run: `head -50 CRM-Server/app/api/ai_conversation_history.py`

Expected: See router pattern, Pydantic request, async endpoint

- [ ] **Step 2: Create Pydantic schema for frontend logs**

Create file `CRM-Server/app/schemas/frontend_log.py`:

```python
"""
Frontend Log Schema

用于接收前端日志的 Pydantic schema
"""
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class FrontendLogEntry(BaseModel):
    """单条前端日志"""
    level: str  # debug, info, warn, error
    context: str  # 如 "[AIAssistant]"
    action: str  # 如 "restore"
    data: Optional[Any] = None
    timestamp: int  # Unix timestamp (ms)
    traceId: Optional[str] = None
    userId: Optional[int] = None
    teamId: Optional[int] = None


class FrontendLogBatchRequest(BaseModel):
    """批量日志请求"""
    logs: list[FrontendLogEntry]
    sessionId: str
    userAgent: Optional[str] = None
    url: Optional[str] = None


class FrontendLogBeaconRequest(BaseModel):
    """Beacon 日志请求（页面关闭时发送）"""
    logs: list[FrontendLogEntry]
    sessionId: str
```

- [ ] **Step 3: Create API file frontend_logs.py**

Create file `CRM-Server/app/api/frontend_logs.py`:

```python
"""
Frontend Logs API

接收前端日志的 API 端点
- POST /v1/logs/batch: 批量接收日志
- POST /v1/logs/beacon: sendBeacon 专用端点
"""
from fastapi import APIRouter, Request
from fastapi.responses import Response
from app.schemas.frontend_log import FrontendLogBatchRequest, FrontendLogBeaconRequest
from app.services.frontend_log_service import FrontendLogService
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/logs", tags=["frontend-logs"])

# 服务实例（单例）
log_service = FrontendLogService()


@router.post("/batch")
async def receive_log_batch(request: FrontendLogBatchRequest):
    """
    批量接收前端日志
    
    - 不阻塞响应（快速返回 200）
    - 写入文件存储
    """
    try:
        # 写入日志文件
        await log_service.write_logs(
            logs=request.logs,
            session_id=request.sessionId,
            user_agent=request.userAgent,
            url=request.url
        )
        
        logger.debug(f"Received {len(request.logs)} frontend logs from session {request.sessionId}")
        
        return {"received": len(request.logs)}
    
    except Exception as e:
        logger.error(f"Failed to write frontend logs: {e}")
        # 即使失败也返回 200，避免前端重试导致雪崩
        return {"received": 0, "error": str(e)}


@router.post("/beacon")
async def receive_beacon_logs(request: Request):
    """
    接收 sendBeacon 发送的日志（页面关闭时）
    
    - 使用 Request 直接接收 JSON（sendBeacon 无法发送标准 HTTP body）
    - 直接写入文件（不经过队列）
    """
    try:
        # 解析 JSON body
        body = await request.json()
        log_request = FrontendLogBeaconRequest(**body)
        
        # 直接写入文件
        await log_service.write_logs_direct(
            logs=log_request.logs,
            session_id=log_request.sessionId
        )
        
        logger.debug(f"Received beacon logs: {len(log_request.logs)} entries")
        
        # 返回 204 No Content（sendBeacon 不关心响应）
        return Response(status_code=204)
    
    except Exception as e:
        logger.error(f"Failed to write beacon logs: {e}")
        return Response(status_code=204)  # 始终返回 204
```

- [ ] **Step 4: Run Python syntax check**

Run: `python -m py_compile CRM-Server/app/api/frontend_logs.py CRM-Server/app/schemas/frontend_log.py`

Expected: No syntax errors

- [ ] **Step 5: Commit API files**

```bash
git add CRM-Server/app/api/frontend_logs.py CRM-Server/app/schemas/frontend_log.py
git commit -m "feat(api): add frontend logs endpoint (batch + beacon)"
```

---

### Task 3: Create FrontendLogService

**Files:**
- Create: `CRM-Server/app/services/frontend_log_service.py`

**Interfaces:**
- Consumes: `app/core/logging.py` (logger)
- Consumes: `pathlib.Path` for file operations
- Produces: `write_logs()` async method
- Produces: `write_logs_direct()` async method
- Produces: 日志文件轮转 + 30 天自动清理

- [ ] **Step 1: Check existing service pattern for reference**

Run: `head -50 CRM-Server/app/services/ai_service.py`

Expected: See async service pattern, logging usage

- [ ] **Step 2: Create frontend_log_service.py**

Create file `CRM-Server/app/services/frontend_log_service.py`:

```python
"""
Frontend Log Service

负责前端日志的文件存储、轮转、清理
"""
import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# 日志目录
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 日志保留天数
LOG_RETENTION_DAYS = 30


class FrontendLogService:
    """前端日志服务"""
    
    def __init__(self):
        self._lock = asyncio.Lock()
    
    async def write_logs(
        self,
        logs: list,
        session_id: str,
        user_agent: Optional[str] = None,
        url: Optional[str] = None
    ):
        """
        异步写入日志
        
        Args:
            logs: 日志条目列表
            session_id: 会话 ID
            user_agent: 用户代理
            url: 页面 URL
        """
        async with self._lock:
            try:
                # 获取当日日志文件
                log_file = self._get_log_file()
                
                # 写入日志
                with open(log_file, "a", encoding="utf-8") as f:
                    for log in logs:
                        # 构建完整日志结构
                        log_entry = {
                            "timestamp": log.timestamp,
                            "level": log.level,
                            "context": log.context,
                            "action": log.action,
                            "data": log.data,
                            "sessionId": session_id,
                            "userId": log.userId,
                            "teamId": log.teamId,
                            "traceId": log.traceId,
                            "userAgent": user_agent,
                            "url": url
                        }
                        
                        # 每行一个 JSON
                        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                
                logger.debug(f"Written {len(logs)} logs to {log_file}")
                
                # 清理过期日志
                await self._cleanup_old_logs()
                
            except Exception as e:
                logger.error(f"Failed to write logs: {e}")
                raise
    
    async def write_logs_direct(
        self,
        logs: list,
        session_id: str
    ):
        """
        直接写入日志（不经过队列，用于 beacon）
        
        Args:
            logs: 日志条目列表
            session_id: 会话 ID
        """
        try:
            log_file = self._get_log_file()
            
            with open(log_file, "a", encoding="utf-8") as f:
                for log in logs:
                    log_entry = {
                        "timestamp": log.timestamp,
                        "level": log.level,
                        "context": log.context,
                        "action": log.action,
                        "data": log.data,
                        "sessionId": session_id,
                        "userId": log.userId,
                        "teamId": log.teamId,
                        "traceId": log.traceId
                    }
                    
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
        except Exception as e:
            logger.error(f"Failed to write direct logs: {e}")
    
    def _get_log_file(self) -> Path:
        """获取当日日志文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        return LOG_DIR / f"frontend-{today}.log"
    
    async def _cleanup_old_logs(self):
        """清理超过保留天数的日志"""
        try:
            retention_date = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
            
            for log_file in LOG_DIR.glob("frontend-*.log"):
                # 解析日期
                date_str = log_file.stem.replace("frontend-", "")
                try:
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    if file_date < retention_date:
                        log_file.unlink()
                        logger.info(f"Deleted old log file: {log_file}")
                
                except ValueError:
                    # 无法解析日期的文件跳过
                    continue
        
        except Exception as e:
            logger.error(f"Failed to cleanup logs: {e}")
```

- [ ] **Step 3: Run Python syntax check**

Run: `python -m py_compile CRM-Server/app/services/frontend_log_service.py`

Expected: No syntax errors

- [ ] **Step 4: Create logs directory if not exists**

Run: `mkdir -p CRM-Server/logs`

Expected: Directory created (or already exists)

- [ ] **Step 5: Commit service file**

```bash
git add CRM-Server/app/services/frontend_log_service.py CRM-Server/logs/.gitkeep
git commit -m "feat(service): add frontend log service with rotation + cleanup"
```

---

### Task 4: Register API Router in main.py

**Files:**
- Modify: `CRM-Server/app/main.py:106-120`

**Interfaces:**
- Consumes: `frontend_logs.router`
- Produces: `/v1/logs/batch` and `/v1/logs/beacon` endpoints registered

- [ ] **Step 1: Check current main.py imports**

Run: `grep -n "include_router" CRM-Server/app/main.py | tail -10`

Expected: See router registration pattern

- [ ] **Step 2: Add import for frontend_logs router**

Edit `CRM-Server/app/main.py`, add after line 22 (imports section):

```python
# Frontend Logs 路由
from app.api.frontend_logs import router as frontend_logs_router
```

- [ ] **Step 3: Add router registration**

Edit `CRM-Server/app/main.py`, add after line 106 (after ai_conversation_history_router):

```python
# Frontend Logs 路由（前端日志系统）
app.include_router(frontend_logs_router)
```

- [ ] **Step 4: Run Python syntax check**

Run: `python -m py_compile CRM-Server/app/main.py`

Expected: No syntax errors

- [ ] **Step 5: Commit main.py changes**

```bash
git add CRM-Server/app/main.py
git commit -m "feat(main): register frontend logs router"
```

---

### Task 5: Create CLI Query Tool query_logs.py

**Files:**
- Create: `CRM-Server/scripts/query_logs.py`

**Interfaces:**
- Consumes: `CRM-Server/logs/frontend-*.log` files
- Produces: CLI output with filtered/formatted logs

- [ ] **Step 1: Create query_logs.py script**

Create file `CRM-Server/scripts/query_logs.py`:

```python
"""
Frontend Logs Query Tool

CLI 工具用于查询前端日志

Usage:
    python scripts/query_logs.py --date today
    python scripts/query_logs.py --context "[AIAssistant]"
    python scripts/query_logs.py --level error --date today
    python scripts/query_logs.py --user 16
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# 日志目录
LOG_DIR = Path(__file__).parent.parent / "logs"


def parse_date(date_str: str) -> str:
    """解析日期参数"""
    if date_str == "today":
        return datetime.now().strftime("%Y-%m-%d")
    elif date_str == "yesterday":
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        return date_str  # 直接使用


def get_log_file(date_str: str) -> Path:
    """获取日志文件路径"""
    date = parse_date(date_str)
    return LOG_DIR / f"frontend-{date}.log"


def filter_logs(
    logs: list[dict],
    context: Optional[str] = None,
    level: Optional[str] = None,
    user_id: Optional[int] = None,
    action: Optional[str] = None
) -> list[dict]:
    """过滤日志"""
    filtered = logs
    
    if context:
        filtered = [log for log in filtered if log.get("context") == context]
    
    if level:
        filtered = [log for log in filtered if log.get("level") == level]
    
    if user_id:
        filtered = [log for log in filtered if log.get("userId") == user_id]
    
    if action:
        filtered = [log for log in filtered if log.get("action") == action]
    
    return filtered


def format_log(log: dict, show_data: bool = True) -> str:
    """格式化单条日志"""
    timestamp = datetime.fromtimestamp(log["timestamp"] / 1000).strftime("%H:%M:%S")
    level = log.get("level", "unknown")
    context = log.get("context", "")
    action = log.get("action", "")
    user_id = log.get("userId", "")
    
    base = f"{timestamp} | {level.upper():6} | {context} | {action}"
    
    if user_id:
        base += f" | user:{user_id}"
    
    if show_data and log.get("data"):
        data_str = json.dumps(log["data"], ensure_ascii=False)
        if len(data_str) > 100:
            data_str = data_str[:100] + "..."
        base += f"\n  data: {data_str}"
    
    return base


def main():
    parser = argparse.ArgumentParser(description="Query frontend logs")
    
    parser.add_argument("--date", default="today", help="Date to query (today, yesterday, or YYYY-MM-DD)")
    parser.add_argument("--context", help="Filter by context (e.g., '[AIAssistant]')")
    parser.add_argument("--level", help="Filter by level (debug, info, warn, error)")
    parser.add_argument("--user", type=int, help="Filter by user ID")
    parser.add_argument("--action", help="Filter by action")
    parser.add_argument("--no-data", action="store_true", help="Hide data field")
    parser.add_argument("--count", action="store_true", help="Only show count")
    
    args = parser.parse_args()
    
    # 获取日志文件
    log_file = get_log_file(args.date)
    
    if not log_file.exists():
        print(f"No log file found: {log_file}")
        sys.exit(1)
    
    # 读取日志
    logs = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    
    # 过滤
    filtered = filter_logs(
        logs,
        context=args.context,
        level=args.level,
        user_id=args.user,
        action=args.action
    )
    
    # 输出
    if args.count:
        print(f"Total: {len(filtered)} logs")
    else:
        print(f"=== Frontend Logs: {log_file.name} ===")
        print(f"Total: {len(filtered)} logs")
        print("-" * 80)
        
        for log in filtered[:100]:  # 限制输出 100 条
            print(format_log(log, show_data=not args.no_data))
            print()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create scripts directory if not exists**

Run: `mkdir -p CRM-Server/scripts`

Expected: Directory created (or already exists)

- [ ] **Step 3: Test query script with --count flag**

Run: `cd CRM-Server && python scripts/query_logs.py --date today --count`

Expected: Shows count (may be 0 if no logs yet)

- [ ] **Step 4: Commit CLI tool**

```bash
git add CRM-Server/scripts/query_logs.py
git commit -m "feat(scripts): add frontend logs query CLI tool"
```

---

### Task 6: Integration Test

**Files:**
- Modify: `CRM-Client/src/views/AIAssistant.vue:228-244` (集成 logger 到 restore 流程)

**Interfaces:**
- Consumes: `logger` singleton from `@/utils/logger`
- Produces: 日志发送到后端，可通过 query_logs.py 查询

- [ ] **Step 1: Import logger in AIAssistant.vue**

Edit `CRM-Client/src/views/AIAssistant.vue`, add import after line 128:

```typescript
import { logger } from '@/utils/logger'
```

- [ ] **Step 2: Replace console.log with logger calls in restore flow**

Edit lines 228-244 (onMounted restore flow), replace console.log with logger:

```typescript
// ← Task 13: 恢复最后一条 AI 消息的 executionSteps
const executionSteps = store.getLastAIMessageExecutionSteps()

// 使用 logger 追踪（会发送到后端）
logger.info('[AIAssistant]', 'restore_start', {
  recentConversationId: recentConversation.id,
  storeCurrentId: currentId.value,
  executionStepsCount: executionSteps.length
})

if (executionSteps.length > 0) {
  // 直接设置步骤
  agentLog.setStepsDirectly(executionSteps)

  logger.info('[AIAssistant]', 'restore_success', {
    stepsCount: executionSteps.length,
    lastStep: executionSteps[executionSteps.length - 1]?.title
  })
} else {
  logger.warn('[AIAssistant]', 'restore_empty', {
    reason: 'No execution steps to restore'
  })
}
```

- [ ] **Step 3: Remove diagnostic console.log calls**

Search and remove excessive console.log in the restore flow that are now replaced by logger calls.

- [ ] **Step 4: Start dev server**

Run: `cd CRM-Client && npm run dev`

Expected: Dev server starts without errors

- [ ] **Step 5: Start backend server**

Run: `cd CRM-Server && ./run.sh`

Expected: Backend server starts, shows `/v1/logs/batch` endpoint registered

- [ ] **Step 6: Test in browser**

Open: `http://localhost:5173/ai-assistant`
Action: Send a message to AI, refresh page
Check: Console shows `[Logger]` logs

- [ ] **Step 7: Check backend log file**

Run: `cd CRM-Server && python scripts/query_logs.py --date today --context "[AIAssistant]" --count`

Expected: Shows logs received from frontend

- [ ] **Step 8: Commit integration changes**

```bash
git add CRM-Client/src/views/AIAssistant.vue
git commit -m "feat(ai-assistant): integrate logger into restore flow"
```

---

## Verification Checklist

After completing all tasks:

- [ ] **Frontend sends logs with userId/teamId**
  - Check: `query_logs.py --date today --user <your_user_id>`
  - Expected: Shows logs with userId field

- [ ] **Backend receives and stores logs**
  - Check: `ls CRM-Server/logs/frontend-*.log`
  - Expected: Log file exists with today's date

- [ ] **CLI query works**
  - Run: `python scripts/query_logs.py --date today --level error`
  - Expected: Shows error logs or "Total: 0 logs"

- [ ] **Logs survive page refresh**
  - Action: Send message, refresh page, check logs
  - Expected: restore_success log shows in query

---

## Notes

- Phase 2 (Performance Monitoring) and Phase 3 (Session Replay) will be implemented in separate plans after Phase 1 is verified working
- The logger.ts already has localStorage fallback and retry logic, so network failures are handled gracefully
- The backend API returns 200 even on failure to prevent frontend retry storms