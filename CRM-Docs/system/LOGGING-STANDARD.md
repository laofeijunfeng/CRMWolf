# 日志规范 - CRMWolf

**适用范围**：CRM-Server 后端服务

---

## 一、日志配置

### 1.1 日志文件位置

```
CRM-Server/
├── logs/                           # 日志目录（自动创建）
│   ├── app.log                     # 应用日志（INFO及以上）
│   ├── error.log                   # 错误日志（ERROR及以上）
│   └── debug.log                   # 调试日志（DEBUG，开发环境）
│   ├── app.log.2026-05-22          # 按日期轮转的历史日志
│   └── ...
```

### 1.2 日志级别使用

| 级别 | 场景 | 示例 |
|------|------|------|
| DEBUG | 开发调试、详细流程追踪 | `logger.debug("解析参数: %s", params)` |
| INFO | 正常业务流程、关键节点 | `logger.info("用户 %s 创建线索 %d", user_id, lead_id)` |
| WARNING | 异常但可恢复、需关注 | `logger.warning("AI 配置缺失，使用默认值")` |
| ERROR | 业务错误、异常捕获 | `logger.error("数据库错误: %s", exc)` |
| CRITICAL | 系统崩溃、致命错误 | `logger.critical("数据库连接失败，服务终止")` |

### 1.3 环境配置

| 环境 | 日志级别 | 输出位置 |
|------|----------|----------|
| 开发 | DEBUG | 控制台 + 文件 |
| 生产 | INFO | 文件（无控制台） |

---

## 二、日志格式

### 2.1 标准格式

```
2026-05-22 15:30:45.123 | INFO     | app.api.leads | 用户 2 创建线索 18 | lead_name=光大证券 team_id=4
```

格式结构：
```
时间戳 | 级别 | 模块 | 消息 | 关键字段（可选）
```

### 2.2 异常日志格式

```
2026-05-22 15:30:45.123 | ERROR    | app.core.exceptions | Database error | path=/api/v1/leads/ai/create
Traceback (most recent call last):
  File "...", line 128, in sqlalchemy_exception_handler
    ...
IntegrityError: Duplicate entry '18516212963'
```

---

## 三、日志使用规范

### 3.1 获取 Logger

```python
# 推荐：使用模块名
import logging
logger = logging.getLogger(__name__)

# 模块名示例：
# app.api.leads      → 日志中显示 app.api.leads
# app.crud.lead      → 日志中显示 app.crud.lead
# app.services.ai    → 日志中显示 app.services.ai
```

### 3.2 日志内容规范

**必须记录**：
- 关键业务操作：创建、更新、删除、状态变更
- 外部服务调用：AI API、邮件发送、飞书通知
- 异常和错误：完整堆栈、请求路径、关键参数

**禁止记录**：
- 密码、密钥、Token 等敏感信息
- 完整请求体（含用户隐私数据）
- 用户身份证号、银行卡号等

**敏感数据处理**：
```python
# 错误示例
logger.info("用户登录: password=%s", password)  # ❌ 禁止

# 正确示例
logger.info("用户 %s 登录成功", user_id)  # ✓
logger.debug("API 调用: key=%s", api_key[:8] + "...")  # ✓ 脱敏
```

### 3.3 结构化字段

重要日志应附带关键业务字段：

```python
# 业务操作日志
logger.info(
    "线索创建成功",
    extra={
        "lead_id": lead.id,
        "team_id": team_id,
        "user_id": user_id,
        "source": source
    }
)

# API 错误日志
logger.error(
    "请求处理失败",
    extra={
        "path": request.url.path,
        "method": request.method,
        "user_id": current_user.id if current_user else None
    }
)
```

---

## 四、异常处理日志

### 4.1 异常处理器（已实现）

```python
# app/core/exceptions.py

async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(
        "数据库错误",
        exc_info=True,  # 记录完整堆栈
        extra={
            "path": str(request.url),
            "error_type": type(exc).__name__
        }
    )
    return JSONResponse(...)
```

### 4.2 业务异常日志

```python
# 控制层：记录请求参数和结果
@router.post("/leads")
async def create_lead(...):
    logger.info("创建线索请求: team_id=%s", team_id)
    try:
        lead = lead_crud.create(...)
        logger.info("线索创建成功: lead_id=%d", lead.id)
        return lead
    except IntegrityError:
        logger.warning("重复数据: phone=%s", request.contact_phone)
        raise ConflictException("数据已存在")
```

---

## 五、日志轮转与清理

### 5.1 轮转策略

| 日志类型 | 轮转周期 | 保留天数 | 单文件上限 |
|----------|----------|----------|------------|
| app.log | 每天轮转 | 30 天 | 100MB |
| error.log | 每天轮转 | 90 天 | 50MB |
| debug.log | 每天轮转 | 7 天 | 200MB |

### 5.2 自动清理

```python
# 日志配置中已设置：
# - when='midnight'：每天午夜轮转
# - backupCount=30：保留30天
```

---

## 六、查看日志

### 6.1 常用命令

```bash
# 查看实时日志
tail -f logs/app.log

# 查看错误日志
tail -100 logs/error.log

# 搜索特定模块
grep "app.api.leads" logs/app.log

# 搜索特定用户操作
grep "user_id=2" logs/app.log

# 搜索今天的异常
grep "ERROR" logs/app.log | grep "2026-05-22"
```

### 6.2 日志分析

```bash
# 统计错误类型
grep "ERROR" logs/app.log | awk -F'|' '{print $4}' | sort | uniq -c

# 统计 API 调用
grep "INFO" logs/app.log | grep "请求" | awk -F'|' '{print $4}' | sort | uniq -c
```

---

## 七、实现位置

| 文件 | 作用 |
|------|------|
| `app/core/logging.py` | 日志配置模块 |
| `app/main.py` | 启动时初始化日志 |
| `app/core/exceptions.py` | 异常处理器日志 |
| `run.sh` | 启动脚本，设置日志环境 |

---

## 八、快速参考

```python
# 导入
import logging
logger = logging.getLogger(__name__)

# 基本使用
logger.debug("调试信息: %s", value)
logger.info("操作成功")
logger.warning("需要关注")
logger.error("错误发生", exc_info=True)

# 结构化
logger.info("创建成功", extra={"id": 123, "user": "test"})

# 异常捕获
try:
    ...
except Exception as e:
    logger.error("处理失败: %s", e, exc_info=True)
```