"""
实体展示渲染服务

为多实体选择场景提供标准化、增强型的展示数据。

核心功能：
1. render_for_selection() - 渲染实体选择列表
2. 格式化金额、百分比、日期等字段
3. 按相关性或时间排序

展示字段配置：
- 商机：名称、金额、阶段、赢率、更新时间
- 客户：名称、行业、状态、更新时间
- 线索：名称、来源、状态、创建时间
- 合同：名称、金额、状态、签约日期
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session


class EntityRenderer:
    """实体展示渲染服务"""

    # 实体展示配置
    DISPLAY_CONFIGS = {
        "opportunity": {
            "name_field": "opportunity_name",
            "key_fields": [
                {"field": "total_amount", "label": "金额", "format": "currency", "unit": "万"},
                {"field": "current_stage_name", "label": "阶段", "format": "text"},
                {"field": "win_probability", "label": "赢率", "format": "percent"},
                {"field": "updated_at", "label": "更新时间", "format": "datetime"},
            ],
            "sort_by": "updated_at",
            "sort_order": "desc"
        },
        "customer": {
            "name_field": "account_name",
            "key_fields": [
                {"field": "industry", "label": "行业", "format": "text"},
                {"field": "status", "label": "状态", "format": "enum", "enum_type": "customer_status"},
                {"field": "updated_at", "label": "更新时间", "format": "datetime"},
            ],
            "sort_by": "updated_at",
            "sort_order": "desc"
        },
        "lead": {
            "name_field": "lead_name",
            "key_fields": [
                {"field": "source", "label": "来源", "format": "enum", "enum_type": "lead_source"},
                {"field": "status", "label": "状态", "format": "enum", "enum_type": "lead_status"},
                {"field": "created_at", "label": "创建时间", "format": "datetime"},
            ],
            "sort_by": "created_at",
            "sort_order": "desc"
        },
        "contract": {
            "name_field": "contract_name",
            "key_fields": [
                {"field": "contract_amount", "label": "金额", "format": "currency", "unit": "万"},
                {"field": "status", "label": "状态", "format": "enum", "enum_type": "contract_status"},
                {"field": "signed_date", "label": "签约日期", "format": "datetime"},
            ],
            "sort_by": "signed_date",
            "sort_order": "desc"
        }
    }

    # 枚举显示名称映射
    ENUM_DISPLAY_NAMES = {
        "customer_status": {
            0: "跟进中",
            1: "已成交",
            2: "已流失",
            3: "非激活",
        },
        "lead_status": {
            0: "新建",
            1: "跟进中",
            2: "已转化",
            3: "无效",
        },
        "lead_source": {
            "ADVERTISING": "广告",
            "EVENT": "活动",
            "REFERRAL": "推荐",
            "WEBSITE": "网站",
            "OTHER": "其他",
        },
        "contract_status": {
            0: "草稿",
            1: "待审核",
            2: "已签约",
            3: "生效中",
            4: "已终止",
        }
    }

    def render_for_selection(
        self,
        entity_type: str,
        entities: List[Any],
        context: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        渲染实体选择列表

        Args:
            entity_type: 实体类型（opportunity/customer/lead/contract）
            entities: 实体列表
            context: 上下文信息（可选，用于计算相关性）

        Returns:
            渲染后的选择列表，每个元素包含：
            - id: 实体ID
            - name: 实体名称
            - fields: 关键字段字典 {label: value}
            - display: 显示文本（一行摘要）
            - detail: 详情文本（多行详情）
        """
        config = self.DISPLAY_CONFIGS.get(entity_type)
        if not config:
            return self._render_default(entities)

        rendered = []
        for entity in entities:
            # 基本信息
            item = {
                "id": entity.id,
                "name": getattr(entity, config["name_field"], "未知"),
                "fields": {},
                "display": "",
                "detail": ""
            }

            # 渲染关键字段
            for field_config in config["key_fields"]:
                field_name = field_config["field"]
                value = getattr(entity, field_name, None)

                # 格式化值
                formatted_value = self._format_value(
                    value, field_config.get("format"), field_config
                )

                item["fields"][field_config["label"]] = formatted_value

            # 构建显示文本（一行摘要）
            item["display"] = self._build_display_text(item)

            # 构建详情文本（多行详情）
            item["detail"] = self._build_detail_text(item)

            # 计算相关性分数（如果提供了上下文）
            if context:
                item["relevance_score"] = self._calculate_relevance(entity, context)

            rendered.append(item)

        # 排序
        if config.get("sort_by"):
            rendered = self._sort_entities(rendered, entities, config)

        return rendered

    def _format_value(
        self,
        value: Any,
        format_type: str,
        config: Dict[str, Any]
    ) -> str:
        """
        格式化值

        Args:
            value: 原始值
            format_type: 格式类型（currency/percent/datetime/enum/text）
            config: 字段配置

        Returns:
            格式化后的字符串
        """
        if value is None:
            return "未知"

        if format_type == "currency":
            unit = config.get("unit", "万")
            if isinstance(value, (int, float)):
                return f"{value}{unit}"
            return str(value)

        elif format_type == "percent":
            if isinstance(value, (int, float)):
                return f"{value}%"
            return str(value)

        elif format_type == "datetime":
            if hasattr(value, 'strftime'):
                return value.strftime("%Y-%m-%d")
            elif isinstance(value, str):
                # 尝试解析日期字符串
                try:
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    return dt.strftime("%Y-%m-%d")
                except:
                    return value
            return str(value)

        elif format_type == "enum":
            enum_type = config.get("enum_type")
            if enum_type and enum_type in self.ENUM_DISPLAY_NAMES:
                enum_map = self.ENUM_DISPLAY_NAMES[enum_type]
                # 尝试按值查找
                if value in enum_map:
                    return enum_map[value]
                # 尝试按名称查找
                if hasattr(value, 'value'):
                    if value.value in enum_map:
                        return enum_map[value.value]
            return str(value) if hasattr(value, 'value') else str(value)

        else:  # text
            return str(value)

    def _build_display_text(self, item: Dict[str, Any]) -> str:
        """构建一行摘要文本"""
        name = item["name"]
        fields = item["fields"]

        # 选择最重要的2-3个字段
        important_fields = []
        priority_fields = ["金额", "阶段", "状态"]

        for label in priority_fields:
            if label in fields:
                important_fields.append(f"{label}:{fields[label]}")

        if important_fields:
            return f"{name} | {' | '.join(important_fields)}"
        else:
            # 如果没有优先字段，使用所有字段
            field_strs = [f"{label}:{value}" for label, value in fields.items()[:3]]
            return f"{name} | {' | '.join(field_strs)}"

    def _build_detail_text(self, item: Dict[str, Any]) -> str:
        """构建多行详情文本"""
        lines = [f"名称: {item['name']}"]

        for label, value in item["fields"].items():
            lines.append(f"{label}: {value}")

        return "\n".join(lines)

    def _calculate_relevance(self, entity: Any, context: Dict[str, Any]) -> float:
        """
        计算与上下文的相关性分数

        Args:
            entity: 实体对象
            context: 上下文信息

        Returns:
            相关性分数（0.0-1.0）
        """
        score = 0.5  # 默认分数

        # 1. 名称相似度（如果有目标名称）
        target_name = context.get("target_name")
        if target_name:
            entity_name = getattr(entity, "opportunity_name", "") or \
                          getattr(entity, "account_name", "") or \
                          getattr(entity, "lead_name", "")

            # 简单的包含关系检查
            if target_name.lower() in entity_name.lower():
                score += 0.3
            elif entity_name.lower() in target_name.lower():
                score += 0.2

        # 2. 时间接近度（最近更新的更相关）
        updated_at = getattr(entity, "updated_at", None) or getattr(entity, "created_at", None)
        if updated_at:
            days_ago = (datetime.now() - updated_at).days
            if days_ago < 7:
                score += 0.2
            elif days_ago < 30:
                score += 0.1

        # 3. 状态匹配度（跟进中的更相关）
        status = getattr(entity, "status", None)
        if status:
            # 商机：跟进中状态为 0
            if hasattr(status, 'value') and status.value == 0:
                score += 0.1
            elif status == 0:
                score += 0.1

        return min(score, 1.0)  # 上限 1.0

    def _sort_entities(
        self,
        rendered: List[Dict[str, Any]],
        entities: List[Any],
        config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        排序实体列表

        Args:
            rendered: 渲染后的列表
            entities: 原始实体列表
            config: 展示配置

        Returns:
            排序后的列表
        """
        sort_by = config.get("sort_by")
        sort_order = config.get("sort_order", "desc")

        # 创建 ID 到原始实体的映射
        entity_map = {e.id: e for e in entities}

        # 如果有相关性分数，优先按相关性排序
        if rendered and "relevance_score" in rendered[0]:
            rendered.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            return rendered

        # 否则按配置的字段排序
        def get_sort_value(item):
            entity = entity_map.get(item["id"])
            if not entity:
                return datetime.min

            value = getattr(entity, sort_by, None)
            return value or datetime.min

        rendered.sort(key=get_sort_value, reverse=(sort_order == "desc"))

        return rendered

    def _render_default(self, entities: List[Any]) -> List[Dict[str, Any]]:
        """默认渲染（未知实体类型）"""
        return [
            {
                "id": e.id,
                "name": getattr(e, "name", getattr(e, "id", "未知")),
                "fields": {},
                "display": f"ID: {e.id}",
                "detail": f"ID: {e.id}"
            }
            for e in entities
        ]


# 单例实例
entity_renderer = EntityRenderer()