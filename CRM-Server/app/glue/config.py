"""胶水层配置

Redis Key 设计、TTL 配置、渠道配置等。

参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 0.2
"""

from typing import List


class GlueConfig:
    """胶水层全局配置"""

    # ==================== Redis Key 前缀 ====================

    # Session 存储
    SESSION_KEY_PREFIX = "ai:glue:session"
    # 格式: ai:glue:session:{tenant_id}:{crm_user_id}

    # Action 锁（幂等性）
    ACTION_LOCK_KEY_PREFIX = "ai:glue:action_lock"
    # 格式: ai:glue:action_lock:{action_id}

    # 消息去重
    MESSAGE_KEY_PREFIX = "ai:glue:message"
    # 格式: ai:glue:message:{message_id}

    # 主动推送去重
    PUSH_KEY_PREFIX = "ai:glue:push"
    # 格式: ai:glue:push:{user_id}:{opportunity_id}:{reason}

    # ==================== TTL 配置（秒） ====================

    # Session 过期时间（滑动续期）
    SESSION_TTL = 1800  # 30 分钟

    # Pending Action 过期时间
    PENDING_EXPIRE = 180  # 3 分钟

    # Action 锁过期时间
    ACTION_LOCK_TTL = 60  # 60 秒

    # 消息去重过期时间
    MESSAGE_TTL = 300  # 5 分钟

    # 推送去重过期时间
    PUSH_TTL = 86400  # 24 小时

    # ==================== 历史记录限制 ====================

    # Session history 最大条数
    HISTORY_MAX_LENGTH = 20

    # ==================== 渠道配置 ====================

    # 支持的渠道类型
    SUPPORTED_CHANNELS: List[str] = ["feishu", "wecom", "web", "test"]

    # 渠道特性配置
    CHANNEL_CONFIG = {
        "feishu": {
            "timeout": 3000,  # IM webhook 要求 ≤3s 响应
            "async_delivery": True,  # 异步推送队列
        },
        "wecom": {
            "timeout": 3000,
            "async_delivery": True,
        },
        "web": {
            "timeout": 10000,  # 网页可更长
            "async_delivery": False,  # 同步返回
        },
        "test": {
            "timeout": 10000,
            "async_delivery": False,
        },
    }

    # ==================== 推送配置 ====================

    # 商机停留提醒阈值（天）
    OPPORTUNITY_STAY_THRESHOLD = 14

    # 免打扰时段（小时）
    DND_HOURS_START = 22  # 22:00
    DND_HOURS_END = 8  # 08:00

    # 推送检查间隔（秒）
    PUSH_CHECK_INTERVAL = 3600  # 1 小时


class SessionMode:
    """对话状态枚举"""

    IDLE = "idle"  # 空闲，无 pending
    COLLECTING = "collecting"  # 槽位收集，等待用户补信息
    RESOLVING_ENTITY = "resolving_entity"  # 实体消解中，等待用户描述或选择
    RESOLVING_AMBIGUITY = "resolving_ambiguity"  # 消歧中，等待用户选择
    PREVIEW = "preview"  # 已 preview，等待确认
    EXECUTING = "executing"  # 正在执行
    ERROR = "error"  # 不可恢复错误


__all__ = ["GlueConfig", "SessionMode"]