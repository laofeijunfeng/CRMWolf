---
name: ai-entity-parser-architecture
description: AI 实体解析通用架构设计（支持线索、客户、商机、合同等实体的 AI 创建功能）
created: 2026-06-30
status: approved
---

# AI 实体解析通用架构设计

## 背景

### 问题现状

CRMWolf 系统现有线索 AI 创建功能，但实现方式为独立服务，存在以下问题：

1. **代码重复**：每个实体（线索、客户、商机、合同）都需要独立实现 AI 解析逻辑
2. **扩展性差**：新增实体需要重复编写大量代码（SSE、AI 调用、枚举映射）
3. **维护成本高**：通用逻辑散落在各服务中，修改需多处同步

### 需求目标

参考现有的 `BaseHandler` + `HandlerFactory` 架构，设计一个可扩展的 AI 解析架构：

1. **客户 AI 创建**：实现客户创建的 AI 解析功能（含行业识别、档案生成）
2. **架构统一**：与现有 Handler 架构保持一致
3. **可扩展性**：未来支持商机、合同等实体，只需继承基类
4. **向后兼容**：保持现有 API 接口不变，前端无需修改

---

## 架构设计

### 整体架构

```
EntityAIParserBase (抽象基类)
├── 提供：
│   ├── 通用 SSE 流式响应逻辑
│   ├── 通用 AI 调用逻辑（获取配置、调用 API、解析 JSON）
│   ├── 通用枚举映射逻辑（从 constants 获取）
│   └── 通用时间解析逻辑（复用 follow_up_parser）
│
├── 抽象方法（子类必须实现）：
│   ├── get_system_prompt() - 各实体定义自己的提示词
│   ├── get_field_definitions() - 各实体定义需要解析的字段
│   ├── get_enum_maps() - 各实体定义枚举映射
│   ├── parse_ai_response() - 各实体定义解析逻辑
│   ├── create_entity() - 各实体定义创建逻辑
│   └── post_create_actions() - 各实体定义创建后的额外操作
│
└── 具体实现类：
    ├── LeadAIParser - 线索解析（现有代码迁移）
    ├── CustomerAIParser - 客户解析（新增，含行业识别、档案生成）
    ├── OpportunityAIParser - 商机解析（未来）
    └── ContractAIParser - 合同解析（未来）

EntityAIParserFactory (工厂类)
├── 根据 entity_type 返回对应的 Parser 实例
└── 提供统一的调用接口
```

---

### 目录结构

```
CRM-Server/app/
├── services/
│   ├── ai_parser/                      # 新建目录
│   │   ├── __init__.py
│   │   ├── base_parser.py              # EntityAIParserBase 基类
│   │   ├── lead_parser.py              # LeadAIParser（从 lead_ai_parser.py 迁移）
│   │   ├── customer_parser.py          # CustomerAIParser（新建）
│   │   ├── factory.py                  # EntityAIParserFactory 工厂类
│   │   └── constants.py                # 枚举映射配置（统一管理）
│   │
│   ├── lead_ai_parser.py               # ❌ 废弃，迁移后删除
│   ├── follow_up_parser.py             # ✅ 保留（通用服务，多处使用）
│   └── customer_profile_service.py     # ✅ 保留（档案生成服务）
│
├── schemas/
│   ├── lead_ai.py                      # ✅ 保留（API Schema）
│   ├── customer_ai_create.py           # 新建（客户创建 Schema）
│   └── customer_ai.py                  # ✅ 保留（客户跟进 Schema）
│
├── api/
│   ├── lead_ai.py                      # ✅ 保留（修改内部调用方式）
│   ├── customer_ai.py                  # ✅ 保留（新增创建客户接口）
│   └── __init__.py                     # 无需修改
│
└── main.py                             # 无需修改（路由已注册）
```

---

## 核心组件设计

### 1. EntityAIParserBase 基类

**职责**：提供通用的 AI 解析逻辑，子类继承后只需实现定制化部分。

**核心方法**：

```python
class EntityAIParserBase(ABC):
    """实体 AI 解析基类"""
    
    entity_type: str = ""  # 实体类型：lead, customer, opportunity, contract
    
    # ==================== 抽象方法（子类必须实现） ====================
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """获取系统提示词（各实体定义自己的提示词）"""
        pass
    
    @abstractmethod
    def get_enum_maps(self) -> Dict[str, Dict[str, Any]]:
        """获取枚举映射配置"""
        pass
    
    @abstractmethod
    def parse_ai_response(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """解析 AI 响应，转换为结构化数据"""
        pass
    
    @abstractmethod
    async def create_entity(
        self,
        db: Session,
        parsed_data: Dict[str, Any],
        user_id: str,
        team_id: int
    ) -> Any:
        """创建实体（各实体定义自己的创建逻辑）"""
        pass
    
    @abstractmethod
    async def post_create_actions(
        self,
        db: Session,
        entity: Any,
        parsed_data: Dict[str, Any],
        user_id: str,
        team_id: int
    ) -> None:
        """创建后的额外操作（可选）"""
        pass
    
    # ==================== 通用方法（基类提供） ====================
    
    async def parse_stream(
        self,
        db: Session,
        user_message: str,
        team_id: int
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式解析（通用 SSE 流式响应逻辑）"""
        # 1. 获取 AI 配置
        # 2. 构建请求（调用子类的 get_system_prompt）
        # 3. 流式调用 AI API
        # 4. 解析响应（调用子类的 parse_ai_response）
        # 5. 返回 SSE 事件
        pass
```

---

### 2. EntityAIParserFactory 工厂类

**职责**：根据实体类型返回对应的 Parser 实例，提供统一调用接口。

```python
class EntityAIParserFactory:
    """实体 AI 解析工厂"""
    
    PARSER_MAP = {
        "lead": LeadAIParser,
        "customer": CustomerAIParser,
        # 未来扩展：
        # "opportunity": OpportunityAIParser,
        # "contract": ContractAIParser,
    }
    
    @classmethod
    def get_parser(cls, entity_type: str) -> Optional[EntityAIParserBase]:
        """根据实体类型获取 Parser 实例"""
        parser_class = cls.PARSER_MAP.get(entity_type)
        if parser_class:
            return parser_class()
        return None
```

---

### 3. LeadAIParser（线索解析）

**职责**：解析线索信息，创建线索 + 跟进记录。

**特点**：
- 从 `lead_ai_parser.py` 迁移，保持原有解析逻辑
- 提示词保持不变（确保解析结果一致）
- 创建后自动创建跟进记录

**系统提示词**（保持原有）：
- 必填字段：lead_name, source, city, contact_name, contact_phone
- 可选字段：company_scale
- 枚举映射：线索来源（线上注册、市场活动等）、公司规模（1-50人等）
- 额外信息识别：跟进内容、下一步动作、下次跟进时间

---

### 4. CustomerAIParser（客户解析）

**职责**：解析客户信息，创建客户 + 主联系人 + 跟进记录，触发档案生成。

**特点**：
- **行业识别**：AI 提取行业关键词，匹配数据库一二级行业
- **档案生成**：创建后异步触发 `customer_profile_service.trigger_generation`
- **主联系人创建**：同时创建主联系人（联系人姓名、电话、职务、邮箱）

**系统提示词**（定制）：
- 必填字段：account_name, city, contact_name, contact_phone
- 可选字段：company_scale, source, contact_position, contact_email
- 行业识别：提取行业关键词（如"互联网公司"、"金融"）
- 枚举映射：客户来源、公司规模

**行业匹配逻辑**：
1. AI 提取行业关键词（如"互联网公司"）
2. 调用 `industry_crud.get_industry_hierarchy(db)` 获取行业层级结构
3. 从二级行业开始匹配，检查行业名称是否包含关键词
4. 如果未匹配，尝试一级行业
5. 返回行业编码（如"internet"）

---

### 5. constants.py（枚举映射统一管理）

**职责**：统一管理所有实体的枚举映射，避免硬编码散落各处。

```python
# 线索来源枚举映射
LEAD_SOURCE_ENUM_MAP = {
    "线上注册": "ONLINE_REGISTER",
    "市场活动": "MARKETING_ACTIVITY",
    ...
}

# 公司规模枚举映射（线索和客户共用）
COMPANY_SCALE_ENUM_MAP = {
    "1-50人": "SCALE_1_50",
    ...
}

# 客户来源枚举映射
CUSTOMER_SOURCE_ENUM_MAP = {
    "线上注册": "ONLINE_REGISTER",
    ...
}
```

---

## API 接口设计

### 线索 AI 创建（保持不变）

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 解析线索信息 | POST | `/v1/leads/ai/parse` | SSE 流式响应，解析线索信息 |
| 创建线索 | POST | `/v1/leads/ai/create` | 用户确认后创建线索 + 跟进记录 |

**变更点**：内部使用工厂调用 `EntityAIParserFactory.get_parser("lead")`，接口响应格式不变。

---

### 客户 AI 功能（新增 + 保留）

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 解析客户跟进信息（保留） | POST | `/v1/customers/ai/parse` | MagicWand 功能，解析跟进记录 |
| 创建客户跟进记录（保留） | POST | `/v1/customers/ai/create` | 创建跟进记录 |
| **解析客户创建信息（新增）** | POST | `/v1/customers/ai/create/parse` | SSE 流式响应，解析客户信息 |
| **创建客户（新增）** | POST | `/v1/customers/ai/create/submit` | 创建客户 + 主联系人 + 档案生成 + 跟进记录 |

**向后兼容**：原有跟进功能保持不变，新增客户创建接口。

---

## 前端设计

### 新增组件

1. **API**：`customerAICreate.ts`
   - `parseSSE()`：SSE 流式解析客户信息
   - `createFromAI()`：创建客户

2. **组件**：`AICustomerCreateDialog.vue`
   - 四阶段流程：输入 → 解析 → 预览 → 成功
   - 预览表单：客户信息 + 主联系人信息
   - 跟进信息显示（如果有）

3. **页面修改**：`Customers.vue`
   - 新增 "AI 创建客户" 按钮
   - 引入 `AICustomerCreateDialog` 组件

---

## 迁移计划

### Phase 1：后端架构搭建（不影响现有功能）

| 步骤 | 任务 | 验证 |
|------|------|------|
| 1.1 | 创建 `ai_parser` 目录 | 目录结构正确 |
| 1.2 | 实现 `constants.py` | 枚举映射正确 |
| 1.3 | 实现 `base_parser.py` | 基类方法完整 |
| 1.4 | 实现 `lead_parser.py` | 提示词复制正确 |
| 1.5 | 实现 `customer_parser.py` | 行业识别逻辑正确 |
| 1.6 | 实现 `factory.py` | 工厂映射正确 |
| 1.7 | 创建 Schema | Schema 定义正确 |

---

### Phase 2：API 接口修改（保持兼容）

| 步骤 | 任务 | 验证 |
|------|------|------|
| 2.1 | 修改 `lead_ai.py` | ✅ 线索解析功能正常 |
| 2.2 | 扩展 `customer_ai.py` | ✅ 原有跟进功能正常 |
| 2.3 | 注册路由（无需修改） | 路由已注册 |

**关键验证点**：
- `/v1/leads/ai/parse` 接口响应格式不变
- `/v1/leads/ai/create` 接口响应格式不变
- `/v1/customers/ai/parse` 接口响应格式不变（跟进记录解析）
- `/v1/customers/ai/create` 接口响应格式不变（跟进记录创建）

---

### Phase 3：前端实现

| 步骤 | 任务 | 验证 |
|------|------|------|
| 3.1 | 创建 API | API 定义正确 |
| 3.2 | 创建组件 | 组件逻辑正确 |
| 3.3 | 修改页面 | 按钮显示正确 |

---

### Phase 4：测试验证

| 测试场景 | 验证标准 |
|----------|----------|
| **线索创建（原有功能）** | ✅ 解析结果正确 |
| | ✅ 创建成功 |
| | ✅ 跟进记录自动创建 |
| **客户跟进（原有功能）** | ✅ 解析结果正确 |
| | ✅ 创建成功 |
| **客户创建（新功能）** | ✅ 解析结果正确 |
| | ✅ 创建客户 + 主联系人成功 |
| | ✅ 档案生成触发成功 |
| | ✅ 跟进记录自动创建 |

---

### Phase 5：清理废弃代码

| 清理内容 | 说明 |
|----------|------|
| ❌ 删除 `lead_ai_parser.py` | 已迁移到 `ai_parser/lead_parser.py` |
| ❌ 删除旧导入 | `api/lead_ai.py` 删除旧导入 |

---

## 测试用例

### 测试用例 1：线索创建（验证原有功能不被破坏）

**测试数据**：
```
张三，13800138000，来自杭州的阿里巴巴，大概500人，网上注册来的，想做电商系统，下一步推进POC部署试用，下周三再联系
```

**验证点**：
- 线索名称：阿里巴巴
- 来源：线上注册
- 城市：杭州
- 规模：501-1000人
- 联系人：张三
- 电话：13800138000
- 跟进内容：想做电商系统
- 下一步动作：推进POC部署试用
- 创建成功 + 跟进记录自动创建

---

### 测试用例 2：客户创建（验证新功能）

**测试数据**：
```
阿里巴巴，杭州，张三 13800138000 技术总监 zhangsan@alibaba.com，大概500人，网上注册来的，互联网公司，想做电商系统，下周三再联系
```

**验证点**：
- 客户名称：阿里巴巴
- 城市：杭州
- 规模：501-1000人
- 来源：线上注册
- 行业提示：互联网
- 联系人：张三
- 电话：13800138000
- 职务：技术总监
- 邮箱：zhangsan@alibaba.com
- 创建成功 + 主联系人创建 + 档案生成触发 + 跟进记录自动创建

---

### 测试用例 3：客户跟进（验证原有功能不被破坏）

**测试数据**：
```
下午和客户沟通了下，客户反馈已经经过领导审批，后续会有采购来联系；先提供了报价方案；等下周三看看，如果采购还没有联系，再和客户对齐下采购联系的时间
```

**验证点**：
- 跟进内容正确
- 跟进方式：电话
- 下一步动作正确
- 下次跟进时间正确
- 创建成功

---

## 回滚方案

如果迁移失败，立即回滚：

1. 删除新创建的 `ai_parser` 目录
2. 恢复 `lead_ai.py` 的原始导入：
   ```python
   from app.services.lead_ai_parser import lead_ai_parser_service
   ```
3. 删除新增的 API 路由
4. 验证原有功能正常

---

## 优势总结

| 维度 | 优势 |
|------|------|
| **代码复用** | 通用逻辑在基类实现，减少重复代码 |
| **扩展性** | 新增实体只需继承基类，不修改现有代码 |
| **维护成本** | 枚举映射统一管理，修改一处生效全局 |
| **架构一致性** | 与现有 Handler 架构保持一致 |
| **向后兼容** | API 接口保持不变，前端无需修改 |

---

## 未来扩展

支持其他实体（商机、合同等）只需：

1. 创建新 Parser 类（继承 `EntityAIParserBase`）
2. 实现抽象方法（提示词、解析逻辑、创建逻辑）
3. 在 `factory.py` 中注册
4. 创建对应 API 接口

---

## 版本信息

- **创建日期**：2026-06-30
- **状态**：approved
- **预计实现日期**：2026-07-01