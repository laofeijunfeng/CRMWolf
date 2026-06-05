"""
AI Skill Generator Service

基于 AI 自动生成 Skill/Action 配置
"""
import json
from typing import AsyncGenerator, Dict, Any
from sqlalchemy.orm import Session

from app.crud.ai_skill import ai_skill_crud, ai_skill_action_crud
from app.crud.ai_crud_mapping import ai_crud_mapping_crud
from app.crud.ai_enum_mapping import ai_enum_mapping_crud
from app.crud.ai_config import ai_config_crud
from app.services.skills.handlers.handler_factory import HandlerFactory
from app.services.ai_service import ai_service


SKILL_ANALYSIS_SYSTEM_PROMPT = """你是 CRMWolf 系统的 Skill 配置专家。你的任务是分析用户需求，判断系统是否能支持，并生成结构化的配置 Prompt。

## 系统上下文

{context}

## 分析规则

1. **模块支持检查**：
   - 检查用户需求的 module_type 是否在 CRUD 映射中存在
   - 如果不存在，返回不支持提示，列出所有支持的模块

2. **Handler 类型匹配**：
   - 根据用户需求的操作类型，匹配对应的 Handler
   - QueryListHandler: 查询列表、列出记录
   - QueryDetailHandler: 查询详情、获取单条记录
   - CreateHandler: 创建、新增记录
   - FollowUpHandler: 添加跟进、跟进记录
   - StatusChangeHandler: 状态变更、审批、转换
   - AggregateHandler: 统计、汇总、合计

3. **现有 Skill/Action 检查**：
   - 检查 module_type 是否已有 Skill
   - 检查现有 Actions，识别缺失的操作
   - 如果 Skill 存在且缺少某些 Action → 返回 operation_type="add_action"
   - 如果 Skill 不存在 → 返回 operation_type="create_skill"

## 输出格式

返回 JSON 格式：
```json
{{"supported": true, "operation_type": "create_skill", "skill_name": "LeadSkill", "message": "提示信息", "config_prompt": "配置描述"}}
```

或补充 Action 时：
```json
{{"supported": true, "operation_type": "add_action", "skill_name": "LeadSkill", "existing_actions": ["list", "detail"], "missing_actions": ["follow_up"], "message": "提示信息", "config_prompt": "配置描述"}}
```

或不支持时：
```json
{{"supported": false, "message": "不支持提示，列出支持的模块"}}
```

## Config Prompt 格式（仅当 supported=true）

生成一个结构化的配置描述，包含：

新建 Skill 时：
Skill 配置需求分析

操作类型：create_skill
模块：lead
模块显示名：线索管理

Actions：
1. convert - 线索转化
   Handler类型：StatusChangeHandler
   说明：将线索转化为客户
   参数：lead_id

权限码建议：lead:convert

补充 Action 时：
Skill 配置需求分析

操作类型：add_action
Skill名称：LeadSkill
模块：lead

需补充的 Actions：
1. follow_up - 添加跟进
   Handler类型：FollowUpHandler
   说明：为线索添加跟进记录
   参数：lead_name, content, method

权限码建议：lead:follow_up
"""


SKILL_GENERATION_SYSTEM_PROMPT = """你是 CRMWolf 系统的 Skill 配置生成器。根据用户确认的配置 Prompt，生成完整的 Skill/Action 配置 JSON。

## 系统上下文

{context}

## 输出要求

根据配置 Prompt 中的 operation_type，生成对应格式：

### 新建 Skill（operation_type=create_skill）

```json
{{"operation_type": "create_skill", "skill": {{ "skill_name": "LeadSkill", "display_name": "线索管理", "description": "描述", "module_type": "lead", "is_active": 1, "sort_order": 10 }}, "actions": [{{ "action_name": "convert", "display_name": "线索转化", "description": "描述", "handler_type": "StatusChangeHandler", "handler_config": {{}}, "required_params": [], "optional_params": [], "permission_code": "lead:convert", "is_active": 1, "sort_order": 0 }}]}}
```

### 补充 Action（operation_type=add_action）

```json
{{"operation_type": "add_action", "skill_name": "LeadSkill", "actions": [{{ "action_name": "follow_up", "display_name": "添加跟进", "description": "描述", "handler_type": "FollowUpHandler", "handler_config": {{}}, "required_params": [], "optional_params": [], "permission_code": "lead:follow_up", "is_active": 1, "sort_order": 0 }}]}}
```

## Handler Config 示例

QueryListHandler:
```json
{{ "crud_mapping": "lead", "owner_filter": true, "display_fields": ["id", "lead_name"], "template": "共有 {{total}} 条记录" }}
```

QueryDetailHandler（支持名称查找）:
```json
{{ "crud_mapping": "lead", "name_lookup_field": "lead_name", "name_field": "lead_name", "exclude_status": ["CONVERTED", "INVALID"], "display_fields": ["id", "lead_name"], "template": "{{item}}" }}
```

CreateHandler:
```json
{{ "crud_mapping": "lead", "template": "创建成功" }}
```

FollowUpHandler（支持名称查找）:
```json
{{ "crud_mapping": "lead_follow_up", "parent_crud_mapping": "lead", "parent_lookup_field": "lead_name", "parent_name_field": "lead_name", "enum_mappings": {{ "method": "follow_up_method" }}, "result_template": "跟进记录添加成功" }}
```

StatusChangeHandler（支持名称查找）:
```json
{{ "crud_mapping": "lead", "status_field": "status", "target_status": "CONVERTED", "name_lookup_field": "lead_name", "name_field": "lead_name", "exclude_status": ["CONVERTED", "INVALID"], "result_template": "转化成功" }}
```

LeadConvertHandler（支持名称查找）:
```json
{{ "crud_mapping": "lead", "name_lookup_field": "lead_name", "name_field": "lead_name", "exclude_status": ["CONVERTED", "INVALID"], "result_template": "线索转化成功" }}
```

## 名称查找规范

**重要**：所有涉及特定实体操作的 Handler（QueryDetailHandler、FollowUpHandler、StatusChangeHandler、LeadConvertHandler）必须配置名称查找参数：

- `name_lookup_field`: 用户输入的名称参数名（通常与实体 name_field 相同）
- `name_field`: 实体的名称字段（从 CRUD Mapping 的 name_field 读取）
- `exclude_status`: 排除的状态（默认 ["CONVERTED", "INVALID"])

参数配置：
- `required_params`: 设置为空数组 []（不强制要求 ID）
- `optional_params`: 包含 name_lookup_field 和 ID 字段（如 ["lead_name", "lead_id"]）

## 注意事项

1. skill_name 应遵循 PascalCase + Skill 的命名规范
2. permission_code 格式为 module:action
3. handler_config 必须符合对应 Handler 的配置要求
4. 所有 is_active 默认为 1
5. 补充 Action 时，operation_type 必须为 "add_action"，且不包含 skill 字段
"""


class SkillGeneratorService:
    """Skill Generator 服务"""

    def _build_analysis_context(self, db: Session) -> str:
        """构建分析上下文"""
        # CRUD 映射
        crud_mappings = ai_crud_mapping_crud.get_all(db)
        crud_info = [
            {
                "mapping_name": m.mapping_name,
                "model_class": m.model_class,
                "owner_field": m.owner_field,
                "status_field": m.status_field,
                "name_field": m.name_field
            }
            for m in crud_mappings
        ]

        # Enum 映射
        enum_mappings = ai_enum_mapping_crud.get_all(db)
        enum_info = [
            {
                "enum_name": e.enum_name,
                "display_name": e.display_name,
                "values": e.values
            }
            for e in enum_mappings
        ]

        # Handler 类型
        handler_types = HandlerFactory.get_supported_handlers()

        # 现有 Skills（包含 Actions）
        skills, _ = ai_skill_crud.get_multi(db, limit=100)
        skill_info = []
        for s in skills:
            actions = ai_skill_action_crud.get_by_skill_id(db, s.id)
            skill_info.append({
                "skill_name": s.skill_name,
                "module_type": s.module_type,
                "display_name": s.display_name,
                "existing_actions": [a.action_name for a in actions]
            })

        context = {
            "crud_mappings": crud_info,
            "enum_mappings": enum_info,
            "handler_types": handler_types,
            "existing_skills": skill_info
        }

        return json.dumps(context, ensure_ascii=False, indent=2)

    async def analyze_requirement(
        self,
        db: Session,
        requirement: str,
        team_id: int = 1
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        分析用户需求，生成 SSE 事件

        Yields:
            SSE 事件字典
        """
        config, api_key = ai_service.get_config_and_key(db, team_id)
        if not config or not api_key:
            yield {"event": "error", "message": "AI 配置未设置或异常"}
            return

        context = self._build_analysis_context(db)
        system_prompt = SKILL_ANALYSIS_SYSTEM_PROMPT.format(context=context)

        full_content = ""

        try:
            async for event in ai_service._stream_chat_generator(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": requirement}
                ],
                temperature=0.3,
                max_tokens=1024,
                response_format={"type": "json_object"}
            ):
                if event["event"] == "content":
                    full_content += event["content"]
                    yield {"event": "progress", "message": "正在分析需求..."}
                elif event["event"] == "error":
                    yield event
                    return
                elif event["event"] == "done":
                    # 解析结果
                    try:
                        clean_content = full_content.strip()
                        if clean_content.startswith("```json"):
                            clean_content = clean_content[7:]
                        if clean_content.startswith("```"):
                            clean_content = clean_content[3:]
                        if clean_content.endswith("```"):
                            clean_content = clean_content[:-3]
                        clean_content = clean_content.strip()

                        result = json.loads(clean_content)
                        yield {
                            "event": "result",
                            "supported": result.get("supported", False),
                            "operation_type": result.get("operation_type", "create_skill"),
                            "skill_name": result.get("skill_name"),
                            "skill_display_name": result.get("skill_display_name"),
                            "existing_actions": result.get("existing_actions", []),
                            "missing_actions": result.get("missing_actions", []),
                            "message": result.get("message", ""),
                            "config_prompt": result.get("config_prompt")
                        }
                    except json.JSONDecodeError:
                        yield {"event": "error", "message": f"AI 返回格式异常: {full_content[:200]}"}

        except Exception as e:
            yield {"event": "error", "message": f"分析异常: {str(e)}"}

    async def generate_and_save(
        self,
        db: Session,
        config_prompt: str,
        user_id: int,
        team_id: int = 1
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        根据配置 Prompt 生成并保存 Skill/Action 配置

        Yields:
            SSE 事件字典
        """
        config, api_key = ai_service.get_config_and_key(db, team_id)
        if not config or not api_key:
            yield {"event": "error", "message": "AI 配置未设置或异常"}
            return

        context = self._build_analysis_context(db)
        system_prompt = SKILL_GENERATION_SYSTEM_PROMPT.format(context=context)

        full_content = ""

        try:
            async for event in ai_service._stream_chat_generator(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": config_prompt}
                ],
                temperature=0.2,
                max_tokens=2048,
                response_format={"type": "json_object"}
            ):
                if event["event"] == "content":
                    full_content += event["content"]
                    yield {"event": "progress", "message": "正在生成配置..."}
                elif event["event"] == "error":
                    yield event
                    return
                elif event["event"] == "done":
                    # 解析并保存配置
                    try:
                        clean_content = full_content.strip()
                        if clean_content.startswith("```json"):
                            clean_content = clean_content[7:]
                        if clean_content.startswith("```"):
                            clean_content = clean_content[3:]
                        if clean_content.endswith("```"):
                            clean_content = clean_content[:-3]
                        clean_content = clean_content.strip()

                        result = json.loads(clean_content)
                        operation_type = result.get("operation_type", "create_skill")

                        if operation_type == "create_skill":
                            # 创建 Skill
                            skill_data = result.get("skill", {})
                            skill_data.setdefault("is_active", 1)
                            skill_data.setdefault("sort_order", 10)

                            # 检查是否已存在同名 Skill
                            existing = ai_skill_crud.get_by_name(db, skill_data.get("skill_name"))
                            if existing:
                                yield {"event": "error", "message": f"Skill 已存在: {skill_data.get('skill_name')}"}
                                return

                            skill = ai_skill_crud.create(db, skill_data)
                            yield {
                                "event": "skill",
                                "skill_id": skill.id,
                                "skill_name": skill.skill_name,
                                "display_name": skill.display_name
                            }

                            # 创建 Actions
                            actions_data = result.get("actions", [])
                            action_count = 0
                            for action_data in actions_data:
                                action_data["skill_id"] = skill.id
                                action_data.setdefault("is_active", 1)
                                action_data.setdefault("sort_order", 0)
                                action_data.setdefault("handler_config", {})
                                action_data.setdefault("required_params", [])
                                action_data.setdefault("optional_params", [])

                                action = ai_skill_action_crud.create(db, action_data)
                                action_count += 1
                                yield {
                                    "event": "action",
                                    "action_id": action.id,
                                    "action_name": action.action_name,
                                    "handler_type": action.handler_type
                                }

                            yield {
                                "event": "complete",
                                "operation_type": "create_skill",
                                "skill_id": skill.id,
                                "skill_name": skill.skill_name,
                                "display_name": skill.display_name,
                                "action_count": action_count,
                                "message": f"Skill 创建成功，共 {action_count} 个 Action"
                            }

                        elif operation_type == "add_action":
                            # 补充 Action
                            skill_name = result.get("skill_name")
                            skill = ai_skill_crud.get_by_name(db, skill_name)
                            if not skill:
                                yield {"event": "error", "message": f"Skill 不存在: {skill_name}"}
                                return

                            yield {
                                "event": "skill",
                                "skill_id": skill.id,
                                "skill_name": skill.skill_name,
                                "display_name": skill.display_name
                            }

                            # 创建 Actions（跳过已存在的）
                            actions_data = result.get("actions", [])
                            action_count = 0
                            skip_count = 0
                            for action_data in actions_data:
                                # 检查是否已存在
                                existing_action = ai_skill_action_crud.get_by_skill_and_action(
                                    db, skill.id, action_data.get("action_name")
                                )
                                if existing_action:
                                    skip_count += 1
                                    yield {
                                        "event": "skip",
                                        "action_name": action_data.get("action_name"),
                                        "message": "Action 已存在，跳过"
                                    }
                                    continue

                                action_data["skill_id"] = skill.id
                                action_data.setdefault("is_active", 1)
                                action_data.setdefault("sort_order", 0)
                                action_data.setdefault("handler_config", {})
                                action_data.setdefault("required_params", [])
                                action_data.setdefault("optional_params", [])

                                action = ai_skill_action_crud.create(db, action_data)
                                action_count += 1
                                yield {
                                    "event": "action",
                                    "action_id": action.id,
                                    "action_name": action.action_name,
                                    "handler_type": action.handler_type
                                }

                            message = f"为 {skill.display_name} 补充了 {action_count} 个 Action"
                            if skip_count > 0:
                                message += f"，跳过 {skip_count} 个已存在的 Action"

                            yield {
                                "event": "complete",
                                "operation_type": "add_action",
                                "skill_id": skill.id,
                                "skill_name": skill.skill_name,
                                "display_name": skill.display_name,
                                "action_count": action_count,
                                "skip_count": skip_count,
                                "message": message
                            }

                        else:
                            yield {"event": "error", "message": f"未知的操作类型: {operation_type}"}

                    except json.JSONDecodeError as e:
                        yield {"event": "error", "message": f"配置格式异常: {str(e)}"}
                    except Exception as e:
                        yield {"event": "error", "message": f"保存异常: {str(e)}"}

        except Exception as e:
            yield {"event": "error", "message": f"生成异常: {str(e)}"}


skill_generator_service = SkillGeneratorService()