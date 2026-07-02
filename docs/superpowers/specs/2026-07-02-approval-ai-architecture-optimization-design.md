# 审批流程 AI 解析服务稳定性修复设计

**版本**: v2.0 (简化方案)
**日期**: 2026-07-02
**状态**: 待审核
**作者**: Claude (Brainstorming + Tool Design Review)

---

## 设计决策说明

### v1.0 → v2.0 变更原因

根据 Tool Design for Agents skill 的 Architectural Reduction 原则分析：

| 原方案 (v1.0) | 新方案 (v2.0) |
|---------------|---------------|
| 创建 4 个新组件（LangGraph Node/Tool/State/Prompt） | 直接修复现有文件 |
| 架构重构 | 代码质量修复 |
| 变更范围：7 文件 | 变更范围：2 文件 |
| 部署风险：中 | 部署风险：低 |

**关键洞察**：
- 三个缺陷（Format KeyError、Decimal 序列化、SSE 中断）都是**代码质量问题**，不是架构问题
- `approval_ai_parser.py` 是后端服务，不是 Agent Tool，架构重构不适用
- 简化方案更稳定：最小变更、最低风险、最快验证

---

## 1. 问题诊断

### 1.1 当前缺陷

| 问题 | 根因 | 影响 | 修复方案 |
|------|------|------|----------|
| **Format String KeyError** | System Prompt 中 JSON 示例的 `{...}` 被 Python `.format()` 误解析为占位符 | SSE 流中断，无错误事件发送 | 双花括号转义 `{{` `}}` |
| **Decimal 序列化失败** | Pydantic Schema 使用 `Decimal` 类型，`json.dumps()` 无法直接序列化 | parsed 事件发送失败，异常中断流 | 使用 `SSEJsonEncoder` 或改为 `float` |
| **SSE 流异常中断** | 异步生成器内部异常未被正确捕获，导致 HTTP 连接提前关闭 | 前端收到不完整响应，无错误提示 | 三层错误捕获 + 显式 done 事件 |

### 1.2 问题定位

```python
# 问题 1：模板转义错误（第 280 行）
# 错误：使用 .format() 但模板中包含 JSON 示例的 {}
PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE.format(current_date=current_date)
# KeyError: '\n  "flow"'

# 问题 2：Decimal 序列化（第 468 行）
# 错误：flow.model_dump() 返回 Decimal，json.dumps 失败
yield {"event": "parsed", "flow": flow.model_dump()}
# TypeError: Object of type Decimal is not JSON serializable

# 问题 3：异步生成器异常处理
# 错误：异常在生成器内部抛出，外层无法捕获，导致连接中断
async for event in approval_ai_parser_service.parse_approval_flow_stream(...):
    yield f"data: {json.dumps(event)}\n\n"  # json.dumps 失败 → 连接中断
```

---

## 2. 修复方案

### 2.1 文件变更清单

| 文件 | 变更类型 | 变更内容 |
|------|----------|----------|
| `approval_ai_parser.py` | **修改** | 模板转义 + 错误处理增强 |
| `schemas/approval_ai.py` | **修改** | Decimal → float 类型变更 |
| `api/approval_ai.py` | **修改** | 使用 SSEJsonEncoder |

**总变更**：3 文件，约 50 行代码

---

## 3. 具体修复实现

### 3.1 模板转义修复（approval_ai_parser.py）

**方案**：将 System Prompt 中所有 JSON 示例的 `{` → `{{`，`}` → `}}`

```python
# services/approval_ai_parser.py

# 修改前（有缺陷）
PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE = """...
## 输出格式
```json
{
  "flow": {
    "flow_name": "...",
    "nodes": [
      {
        "node_name": "..."
      }
    ]
  }
}
```
"""

# 修改后（正确转义）
PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE = """...
## 输出格式
```json
{{                              # 双花括号转义
  "flow": {{
    "flow_name": "...",
    "nodes": [
      {{
        "node_name": "..."
      }}
    ]
  }},
  "thinking_process": "..."
}}                              # 双花括号转义结束
```
"""

# 保持 .format() 调用（现在是正确的）
def _build_system_prompt(self) -> str:
    current_date = datetime.now().strftime("%Y-%m-%d")
    return PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE.format(current_date=current_date)
```

**验证方法**：
```python
# 单元测试
def test_prompt_format():
    prompt = PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE.format(current_date="2026-07-02")
    assert "今天是 2026-07-02" in prompt
    assert "{flow}" not in prompt  # 应该是 {{flow}}
    assert "{{" in prompt  # 双花括号存在
```

---

### 3.2 Decimal 序列化修复

**方案 A**：Schema 改为 float（推荐，彻底解决）

```python
# schemas/approval_ai.py

# 修改前
from decimal import Decimal

class ApprovalAIParsedFlow(BaseModel):
    min_amount: Optional[Decimal] = Field(None, ge=0)
    max_amount: Optional[Decimal] = Field(None, ge=0)

# 修改后
class ApprovalAIParsedFlow(BaseModel):
    min_amount: Optional[float] = Field(None, ge=0, description="最小金额（元）")
    max_amount: Optional[float] = Field(None, ge=0, description="最大金额（元）")
    
    def to_sse_dict(self) -> Dict[str, Any]:
        """转换为 SSE 可序列化的字典"""
        return self.model_dump(mode='json')

# 注意：ApprovalAICreateRequest 保持 Decimal（数据库层需要）
class ApprovalAICreateRequest(BaseModel):
    min_amount: Optional[Decimal] = Field(None, ge=0)  # 保持 Decimal
    max_amount: Optional[Decimal] = Field(None, ge=0)  # 保持 Decimal
```

**方案 B**：使用 SSEJsonEncoder（兼容方案）

```python
# api/approval_ai.py

from app.services.langgraph.sse_wrapper import SSEJsonEncoder

@router.post("/parse")
async def parse_approval_flow(...):
    async def generate_sse():
        async for event in approval_ai_parser_service.parse_approval_flow_stream(...):
            # 使用 SSEJsonEncoder 序列化（处理 Decimal）
            yield f"data: {json.dumps(event, cls=SSEJsonEncoder, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
```

**推荐**：方案 A + 方案 B 双重保障
- Schema 改为 float（前端接收）
- API 层使用 SSEJsonEncoder（兜底）

---

### 3.3 SSE 错误处理增强

**方案**：三层错误捕获 + 显式 done 事件

```python
# api/approval_ai.py

@router.post("/parse")
async def parse_approval_flow(
    request: ApprovalAIParseRequest,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team)
):
    """AI 解析审批流程配置（SSE 流式响应）
    
    错误处理层级：
    - Level 1: approval_ai_parser 内部捕获 → yield error 事件
    - Level 2: generate_sse 外层捕获 → yield error + done 事件
    - Level 3: StreamingResponse 确保连接正确关闭
    
    稳定性保证：
    - 所有异常都会 yield error 事件
    - 所有流都会 yield done 事件（成功或失败）
    - 使用 SSEJsonEncoder 确保 JSON 序列化成功
    """
    from app.services.langgraph.sse_wrapper import SSEJsonEncoder
    
    async def generate_sse():
        success = False
        try:
            # Level 1-2: 调用解析服务
            async for event in approval_ai_parser_service.parse_approval_flow_stream(
                db=SessionLocal(),
                user_message=request.content,
                team_id=team_id
            ):
                try:
                    # Level 2: 确保序列化成功
                    yield f"data: {json.dumps(event, cls=SSEJsonEncoder, ensure_ascii=False)}\n\n"
                    
                    # 检查是否成功完成
                    if event.get("event") == "parsed":
                        success = True
                except Exception as serialize_error:
                    # 序列化失败，发送错误事件
                    logger.error(f"SSE 序列化失败: {serialize_error}")
                    error_event = {"event": "error", "message": "响应序列化失败"}
                    yield f"data: {json.dumps(error_event)}\n\n"
                    break
            
        except Exception as outer_error:
            # Level 3: 外层兜底捕获
            logger.error(f"SSE 流异常: {outer_error}")
            error_event = {"event": "error", "message": f"服务异常: {str(outer_error)}"}
            yield f"data: {json.dumps(error_event)}\n\n"
        
        finally:
            # 确保发送 done 事件（成功或失败）
            done_event = {"event": "done", "success": success}
            yield f"data: {json.dumps(done_event)}\n\n"
    
    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
```

**SSE 事件序列保证**：

```
成功流程：
├── {"event": "status", "message": "正在分析..."}
├── {"event": "content", "content": "..."} (多次)
├── {"event": "parsed", "flow": {...}}
└── {"event": "done", "success": true}

错误流程：
├── {"event": "status", "message": "正在分析..."}
├── {"event": "content", "content": "..."} (可能部分)
├── {"event": "error", "message": "具体错误原因"}
└── {"event": "done", "success": false}
```

---

## 4. approval_ai_parser.py 内部增强

### 4.1 parse_approval_flow_stream 错误处理

```python
# services/approval_ai_parser.py

async def parse_approval_flow_stream(
    self,
    db: Session,
    user_message: str,
    team_id: int = 1
) -> AsyncGenerator[Dict[str, Any], None]:
    """流式解析审批流程配置
    
    稳定性保证：
    - 所有异常都会 yield error 事件
    - 不在生成器内部抛出异常
    - 使用 logger 记录详细错误信息
    """
    # 发送开始状态
    yield {"event": "status", "message": "正在分析审批流程配置..."}
    
    # 获取 AI 配置
    config = ai_config_crud.get_config(db, team_id)
    if not config:
        yield {"event": "error", "message": "AI 配置未设置，请联系管理员先配置 AI 服务"}
        return
    
    api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
    if not api_key:
        yield {"event": "error", "message": "AI 配置异常，无法获取 API Key"}
        return
    
    # 构建 System Prompt（已修复模板转义）
    system_prompt = self._build_system_prompt()
    
    request_body = {
        "model": config.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
        "stream": True
        # 不使用 response_format，兼容更多模型
    }
    
    full_content = ""
    
    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            async with client.stream(...) as response:
                response.raise_for_status()
                
                # 流式接收内容
                buffer = ""
                async for text_chunk in response.aiter_text():
                    # ... 处理流式响应
                    yield {"event": "content", "content": content_piece}
                
                # 解析完整 JSON
                clean_content = self._clean_json_response(full_content)
                parsed = json.loads(clean_content)
                
                # 构建结构化结果
                flow = ApprovalAIParsedFlow(...)
                
                # 使用 to_sse_dict 确保 Decimal 转换
                yield {
                    "event": "parsed",
                    "flow": flow.to_sse_dict(),  # 转换为可序列化字典
                    "thinking_process": parsed.get("thinking_process")
                }
    
    except httpx.HTTPStatusError as e:
        # 详细错误信息 + 恢复建议
        error_detail = e.response.text[:200]
        logger.error(f"AI 服务 HTTP 错误: {e.response.status_code}, 详情: {error_detail}")
        yield {
            "event": "error",
            "message": f"AI 服务请求失败（{e.response.status_code}）",
            "detail": error_detail,
            "recovery": "请稍后重试，或简化描述"
        }
    
    except json.JSONDecodeError as e:
        logger.error(f"AI 返回 JSON 解析失败: {e}, 内容: {clean_content[:200]}")
        yield {
            "event": "error",
            "message": "AI 返回格式异常",
            "detail": f"解析失败位置: {e.pos}",
            "recovery": "请尝试更明确的描述"
        }
    
    except Exception as e:
        logger.error(f"AI 服务异常: {type(e).__name__}: {str(e)}")
        yield {
            "event": "error",
            "message": f"AI 服务异常: {type(e).__name__}",
            "detail": str(e),
            "recovery": "请联系管理员检查日志"
        }
```

---

## 5. 完整 System Prompt 模板（双花括号转义）

```python
# services/approval_ai_parser.py

PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE = """你是 CRMWolf 系统的审批流程配置专家。

【当前日期】
今天是 {current_date}

你的任务是根据用户描述生成审批流程及其节点配置。

## 需要生成的内容

**审批流程信息**：
- flow_name: 流程名称
- flow_code: 流程编码（英文大写+下划线）
- description: 流程描述
- min_amount: 最小金额（元，可选）
- max_amount: 最大金额（元，可选）
- license_type: 授权类型（可选）

**审批节点列表**：
- node_name: 节点名称
- node_code: 节点编码
- node_order: 节点顺序（从1开始）
- approve_role: 审批角色编码（必须是预定义角色）
- description: 节点描述（可选）
- is_required: 是否必须审批（默认1）

## 审批角色编码（必须使用以下编码）

| 编码 | 角色名称 |
|------|----------|
| TEAM_ADMIN | 团队所有者 |
| SALES_DIRECTOR | 销售总监 |
| FINANCE | 财务人员 |
| SALES_MEMBER | 销售成员 |

## 输出格式

你必须输出严格的 JSON 格式：
```json
{{                                  # 双花括号转义
  "flow": {{
    "flow_name": "审批流程名称",
    "flow_code": "流程编码",
    "description": "流程描述",
    "min_amount": 最小金额或null,
    "max_amount": 最大金额或null,
    "license_type": "授权类型或null",
    "nodes": [
      {{
        "node_name": "节点名称",
        "node_code": "节点编码",
        "node_order": 顺序号,
        "approve_role": "审批角色编码",
        "description": "节点描述",
        "is_required": 1
      }}
    ]
  }},
  "thinking_process": "你的思考过程"
}}                                  # 双花括号转义结束
```

## 示例

用户输入："创建一个标准合同审批流程，销售总监审批然后财务审批"

正确输出：
```json
{{                                  # 双花括号转义
  "flow": {{
    "flow_name": "标准合同审批",
    "flow_code": "STANDARD",
    "nodes": [
      {{
        "node_name": "销售总监审批",
        "approve_role": "SALES_DIRECTOR",
        "node_order": 1
      }},
      {{
        "node_name": "财务审批",
        "approve_role": "FINANCE",
        "node_order": 2
      }}
    ]
  }},
  "thinking_process": "识别为标准审批流程..."
}}                                  # 双花括号转义结束
```
"""
```

---

## 6. 测试策略

### 6.1 单元测试

```python
# tests/unit/services/test_approval_ai_parser.py

def test_prompt_format_no_keyerror():
    """测试模板格式化不会抛出 KeyError"""
    prompt = PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE.format(current_date="2026-07-02")
    assert "今天是 2026-07-02" in prompt
    assert "{{" in prompt  # 双花括号存在

def test_schema_float_serialization():
    """测试 float 类型可以正确序列化"""
    flow = ApprovalAIParsedFlow(
        flow_name="测试",
        flow_code="TEST",
        min_amount=100000.0,  # float
        max_amount=500000.0,  # float
        nodes=[ApprovalAIParsedNode(...)]
    )
    sse_dict = flow.to_sse_dict()
    json_str = json.dumps(sse_dict)  # 应该成功
    assert json_str is not None

def test_sse_json_encoder_decimal():
    """测试 SSEJsonEncoder 可以处理 Decimal"""
    data = {"amount": Decimal("100000.00")}
    json_str = json.dumps(data, cls=SSEJsonEncoder)
    assert "100000" in json_str
```

### 6.2 集成测试

```python
# tests/integration/test_approval_ai_sse.py

async def test_sse_stream_complete():
    """测试 SSE 流完整发送（包含 done 事件）"""
    events = []
    async for event in parse_approval_flow_stream(...):
        events.append(event)
    
    # 验证事件序列
    assert events[0]["event"] == "status"
    assert events[-1]["event"] == "done"
    
    # 如果成功，倒数第二是 parsed
    if events[-1]["success"]:
        assert events[-2]["event"] == "parsed"

async def test_sse_stream_error_recovery():
    """测试错误情况下 SSE 流仍然完整"""
    # 模拟错误输入
    events = []
    async for event in parse_approval_flow_stream(db, "无效输入", team_id):
        events.append(event)
    
    # 即使错误，也应该有 done 事件
    assert events[-1]["event"] == "done"
    assert events[-1]["success"] == False
    
    # 应该有 error 事件
    error_events = [e for e in events if e["event"] == "error"]
    assert len(error_events) > 0
```

### 6.3 手动验证

```bash
# 验证命令
curl 'http://8.134.219.103/api/v1/approval-ai/parse' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  --data-raw '{"content":"创建一个 0-10 万的审批流程，需要销售总监审批"}'

# 预期输出（完整 SSE 流）
data: {"event": "status", "message": "正在分析审批流程配置..."}
data: {"event": "content", "content": "..."}
data: {"event": "parsed", "flow": {...}}
data: {"event": "done", "success": true}
```

---

## 7. 部署策略

### 7.1 分步部署

| Phase | 内容 | 验证 | 时间 |
|-------|------|------|------|
| **Phase 1** | 模板转义修复 | 单元测试 | 30 min |
| **Phase 2** | Decimal → float + SSEJsonEncoder | 单元 + 集成测试 | 30 min |
| **Phase 3** | 三层错误处理 + done 事件 | 手动验证 | 30 min |
| **Phase 4** | 部署 + 观察 | 生产环境验证 | 1 day |

### 7.2 回滚策略

```bash
# 如果出现问题，快速回滚
git revert <commit-hash>
./scripts/deploy.sh
```

---

## 8. 稳定性保障总结

| 保障项 | 实现方式 | 效果 |
|--------|----------|------|
| **模板转义** | 双花括号 `{{` `}}` | 消除 KeyError |
| **序列化兼容** | float + SSEJsonEncoder | 消除 Decimal 序列化失败 |
| **错误恢复** | 三层捕获 + recovery 提示 | 确保流完整 + 用户可恢复 |
| **流完整性** | 显式 done 事件 | 前端知道流结束状态 |
| **日志记录** | logger.error 详细记录 | 快速定位问题 |

---

## 9. 与原方案对比

| 维度 | 原方案 (v1.0) | 简化方案 (v2.0) |
|------|---------------|-----------------|
| **变更文件数** | 7 文件 | 3 文件 |
| **新增组件** | 4 个（State/Node/Tool/Prompt） | 0 个 |
| **部署风险** | 中（架构变更） | 低（局部修复） |
| **回滚难度** | 复杂 | 简单 |
| **修复时间** | 8-12 小时 | 1-2 小时 |
| **稳定性提升** | 通过架构重构 | 直接修复根因 |

**选择简化方案的理由**：
1. 问题根因是代码缺陷，不是架构问题
2. 简化方案最小变更，最低风险
3. 直接修复比架构重构更稳定
4. 符合 Architectural Reduction 原则

---

**文档版本**: v2.0 (简化方案)
**状态**: 待用户审核
**下一步**: 用户审核后调用 writing-plans skill