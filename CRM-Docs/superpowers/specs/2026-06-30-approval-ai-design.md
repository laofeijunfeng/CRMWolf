# AI 审批流程解析设计文档

**创建日期**：2026-06-30
**状态**：待审核

---

## 1. 概述

### 1.1 背景

参照系统中「新建采购方式」的 AI 解析流程，为审批流程创建提供同样的自然语言解析能力。

### 1.2 目标

- 用户可通过自然语言描述创建审批流程模板
- AI 解析流程名称、节点配置、金额范围、授权类型等完整信息
- 提供 SSE 流式响应，用户确认后再创建

### 1.3 参考实现

- `app/services/procurement_ai_parser.py` - 采购方式 AI 解析服务
- `app/api/procurement_ai.py` - 采购方式 AI API 端点
- `app/schemas/procurement_ai.py` - 采购方式 AI Schema

---

## 2. 方案选择

### 2.1 架构方案

采用**独立新建**模式（方案 A），与采购方式保持一致：

```
新增文件：
├── app/services/approval_ai_parser.py   # AI 解析服务
├── app/schemas/approval_ai.py           # AI 解析 Schema
├── app/api/approval_ai.py               # API 端点
├── app/constants/approval_roles.py      # 预定义角色常量

修改文件：
├── app/main.py                          # 注册新路由（1行代码）
```

### 2.2 路由设计

采用**独立路由**模式，与采购方式一致：

```
POST /v1/approval-ai/parse    → SSE 流式解析
POST /v1/approval-ai/create   → 创建审批流程（用户确认后）
```

现有审批管理路由保持不变：`/v1/approvals/flows`

---

## 3. Schema 设计

### 3.1 AI 解析 Schema

```python
# app/schemas/approval_ai.py

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from decimal import Decimal


class ApprovalAIParsedNode(BaseModel):
    """AI 解析的审批节点"""
    node_name: str = Field(..., description="节点名称，如：部门经理审批")
    node_code: str = Field(..., description="节点编码，如：DEPT_MANAGER")
    node_order: int = Field(..., gt=0, description="审批顺序，从1开始")
    approve_role: str = Field(..., description="审批角色编码，如：SALES_DIRECTOR")
    description: Optional[str] = Field(None, description="节点描述")
    is_required: int = Field(1, ge=0, le=1, description="是否必须审批，默认1")


class ApprovalAIParsedFlow(BaseModel):
    """AI 解析的审批流程"""
    flow_name: str = Field(..., description="流程名称")
    flow_code: str = Field(..., description="流程编码")
    description: Optional[str] = Field(None, description="流程描述")
    min_amount: Optional[Decimal] = Field(None, ge=0, description="最小金额（元）")
    max_amount: Optional[Decimal] = Field(None, ge=0, description="最大金额（元）")
    license_type: Optional[str] = Field(None, description="授权类型，如：STANDARD")
    nodes: List[ApprovalAIParsedNode] = Field(..., min_length=1, description="审批节点列表")


class ApprovalAIParseRequest(BaseModel):
    """AI 解析请求"""
    content: str = Field(..., description="用户自然语言描述")


class ApprovalAIParseResponse(BaseModel):
    """AI 解析响应"""
    flow: ApprovalAIParsedFlow
    thinking_process: str = Field(..., description="AI 思考过程")


class ApprovalAICreateRequest(BaseModel):
    """创建审批流程请求（用户确认后）"""
    flow_name: str
    flow_code: str
    description: Optional[str] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    license_type: Optional[str] = None
    nodes: List[ApprovalNodeCreate]  # 复用现有 Schema
```

### 3.2 Schema 兼容性

| 字段 | AI 解析 Schema | 现有 Schema | 数据库模型 | 兼容性 |
|------|----------------|-------------|-----------|--------|
| min_amount/max_amount | Decimal | Decimal | Numeric(12,2) | ✅ 兼容 |
| approve_role | str（预定义） | str | String(50) | ✅ 兼容 |
| nodes 子结构 | ApprovalAIParsedNode | ApprovalNodeCreate | ApprovalNode | ✅ 可转换 |
| is_required | 默认1 | 默认1 | 默认1 | ✅ 兼容 |

---

## 4. 角色编码设计

### 4.1 预定义角色

系统预定义角色来自 `app/constants/permissions.py`：

| 编码 | 角色名称 | 适用场景 |
|------|----------|----------|
| TEAM_ADMIN | 团队所有者 | 最高权限审批（总经理、老板） |
| SALES_DIRECTOR | 销售总监 | 销售相关审批（部门经理） |
| FINANCE | 财务人员 | 财务审核 |
| SALES_MEMBER | 销售成员 | 一般审批 |

### 4.2 角色映射规则

用户描述 → 角色编码映射：

| 用户描述 | 推荐编码 |
|----------|----------|
| "总经理审批" / "老板审批" / "最高审批" | TEAM_ADMIN |
| "部门经理审批" / "销售审批" / "总监审批" | SALES_DIRECTOR |
| "财务审批" / "财务审核" / "财务确认" | FINANCE |
| "普通审批" / "基础审批" | SALES_MEMBER |

### 4.3 角色常量文件

```python
# app/constants/approval_roles.py

ALLOWED_APPROVAL_ROLES = [
    "TEAM_ADMIN",       # 团队所有者
    "SALES_DIRECTOR",   # 销售总监
    "FINANCE",          # 财务人员
    "SALES_MEMBER",     # 销售成员
]

ROLE_DISPLAY_NAMES = {
    "TEAM_ADMIN": "团队所有者",
    "SALES_DIRECTOR": "销售总监",
    "FINANCE": "财务人员",
    "SALES_MEMBER": "销售成员",
}
```

---

## 5. System Prompt 设计

### 5.1 Prompt 结构

```
1. 任务说明 + 当前日期（动态注入）
2. 需要生成的字段说明
3. 审批角色编码参考表（预定义角色）
4. 金额匹配规则说明
5. 授权类型枚举
6. 编码命名规范
7. 常见审批流程模板
8. 输出格式 + JSON 示例
```

### 5.2 关键规则

- **approve_role 只能使用预定义角色编码**
- 如果用户描述的角色不在列表中，选择语义最接近的角色
- **动态注入当前日期**（参照 intent.py 模式，避免硬编码年份问题）

### 5.3 动态日期注入

```python
def get_system_prompt() -> str:
    current_date = datetime.now().strftime("%Y-%m-%d")
    return PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE.format(
        current_date=current_date
    )
```

---

## 6. API 端点设计

### 6.1 路由定义

```python
# app/api/approval_ai.py

router = APIRouter(prefix="/v1/approval-ai", tags=["AI 审批流程解析"])
```

### 6.2 解析端点

```
POST /v1/approval-ai/parse

SSE 事件类型：
- status: 状态更新（"正在分析审批流程配置..."）
- content: AI 思考过程内容片段
- parsed: 解析完成，返回结构化配置
- error: 错误信息
```

### 6.3 创建端点

```
POST /v1/approval-ai/create

创建审批流程 + 节点（事务保护）

权限要求：approval:flow:create
```

---

## 7. 创建校验规则

### 7.1 校验策略

| 类别 | 校验项 | 处理方式 |
|------|--------|----------|
| **必须校验** | flow_code 唯一性 | ❌ 拒绝创建 |
| **必须校验** | approve_role 在预定义列表 | ❌ 拒绝创建 |
| **必须校验** | nodes ≥ 1 | ❌ 拒绝创建 |
| **自动修正** | node_order 连续性 | 自动调整为连续 |
| **自动修正** | node_codes 重复 | 自动添加序号 |
| **可选校验** | flow_name 唯一性 | 提示警告（不阻止） |
| **可选校验** | min_amount < max_amount | 提示警告（不阻止） |

### 7.2 自动修正逻辑

```python
def auto_correct_nodes(nodes: List[ApprovalAIParsedNode]) -> List[ApprovalAIParsedNode]:
    """自动修正节点配置"""
    # 1. 修正 node_order 连续性
    for i, node in enumerate(nodes):
        node.node_order = i + 1
    
    # 2. 修正 node_codes 重复
    codes = {}
    for node in nodes:
        if node.node_code in codes:
            node.node_code = f"{node.node_code}_{node.node_order}"
        codes[node.node_code] = True
    
    return nodes
```

### 7.3 创建流程

```
1. 权限检查（approval:flow:create）
2. flow_code 唯一性检查 → 拒绝重复
3. approve_role 预定义检查 → 拒绝无效角色
4. nodes 数量检查 → 拒绝空列表
5. 自动修正 node_order / node_codes
6. 可选校验提示（警告但不阻止）
7. 创建 ApprovalFlow + ApprovalNode（事务）
8. 返回创建结果
```

---

## 8. 文件清单

### 8.1 新增文件

| 文件路径 | 说明 |
|----------|------|
| `app/services/approval_ai_parser.py` | AI 解析服务（SSE 流式响应） |
| `app/schemas/approval_ai.py` | AI 解析 Schema |
| `app/api/approval_ai.py` | API 端点（parse + create） |
| `app/constants/approval_roles.py` | 预定义角色常量 |

### 8.2 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `app/main.py` | 注册 `approval_ai.router`（1行代码） |
| `app/crud/approval.py` | 新增 `get_by_name()` 方法（可选） |

---

## 9. 与采购方式的对比

| 维度 | 采购方式 | 审批流程 |
|------|----------|----------|
| 主实体 | ProcurementMethod | ApprovalFlow |
| 子实体 | ProcurementStageTemplate | ApprovalNode |
| 顺序字段 | sort_order | node_order |
| 业务规则 | 最后阶段赢率=100 | approve_role 预定义 |
| 动态日期 | ❌ 无（需补充） | ✅ 有（设计已包含） |
| SSE 流式 | ✅ 有 | ✅ 有 |
| parse + create | ✅ 两步确认 | ✅ 两步确认 |

---

## 10. 注意事项

### 10.1 动态日期注入

System Prompt 必须动态注入当前日期，避免硬编码年份问题（参考 `intent.py` 模式）。

### 10.2 角色编码限制

只使用系统预定义的 4 个角色编码，确保审批流程可正常执行。

### 10.3 权限检查

创建端点需要 `approval:flow:create` 权限，与现有审批流程创建 API 保持一致。

---

## 11. 下一步

1. ✅ 用户审核设计文档
2. 编写实现计划（调用 writing-plans skill）
3. 实现代码