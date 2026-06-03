"""Glue 层公共类型定义

避免循环导入的类型模块。
"""

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class EntityCandidate:
    """实体候选（R-ST-04 合规）"""

    id: int                              # 实体 ID
    name: str                            # 全名（展示）
    hint: str                            # 区分度 hint（如："最近跟进 5/20 · CRM项目升级")
    matched_by: str = "raw"              # "exact_norm" | "prefix_norm" | "wide" | "raw"
    entity_type: str = "Customer"        # 实体类型（用于歧义追问）


@dataclass
class EntityResolveResult:
    """实体消解结果"""

    entity_id: Optional[int] = None
    entity_type: Optional[str] = None
    confidence: float = 0.0
    candidates: List[EntityCandidate] = None  # 歧义时返回候选列表
    error: Optional[str] = None  # 错误信息（如 AI 服务不可用）

    def __post_init__(self):
        if self.candidates is None:
            self.candidates = []