# 系统架构规范 - CRMWolf

**适用范围**：CRMWolf 全项目（前端 + 后端）

---

## 一、前端目录结构

```
CRM-Client/src/
├── api/                    # API 调用层（禁止业务逻辑）
│   ├── auth.ts             # 认证接口
│   ├── customer.ts         # 客户接口
│   ├── lead.ts             # 线索接口
│   ├── opportunity.ts      # 商机接口
│   ├── contract.ts         # 合同接口
│   ├── payment.ts          # 回款接口
│   ├── invoice.ts          # 发票接口
│   └── user.ts             # 用户接口
│
├── schemas/                # Zod 校验 Schema（新增目录）
│   ├── common.ts           # 通用 Schema
│   ├── customer.ts         # 客户 Schema
│   ├── lead.ts             # 线索 Schema
│   └── index.ts            # Schema 导出
│
├── components/             # 共享组件
│   ├── [PascalCase].vue    # 组件文件
│   └── [PascalCase].stories.ts  # Storybook 文件（必配）
│
├── composables/            # Composition API Hooks
│   └── [camelCase].ts      # Hook 文件
│
├── directives/             # Vue 指令
│   └── permission.ts       # 权限指令
│
├── router/                 # 路由配置
│   └── index.ts            # 路由定义
│
├── stores/                 # Pinia 状态管理
│   ├── user.ts             # 用户状态
│   └── permissions.ts      # 权限状态
│
├── styles/                 # 样式文件
│   ├── variables.scss      # 设计变量
│   └── wolf-design.scss    # 主题样式
│
├── utils/                  # 工具函数（纯函数）
│   ├── request.ts          # HTTP 封装
│   └── permissions.ts      # 权限工具
│
├── views/                  # 页面视图
│   ├── [PascalCase].vue    # 页面文件
│   └── [PascalCase]Detail.vue  # 详情页
│
├── App.vue                 # 根组件
├── AppLayout.vue           # 布局组件
└── main.ts                 # 入口文件
```

---

## 二、后端目录结构

```
CRM-Server/app/
├── api/                    # 路由层（只处理请求响应）
│   ├── auth.py             # 认证路由
│   ├── customers.py        # 客户路由
│   ├── leads.py            # 线索路由
│   └── ...                 # 其他路由
│
├── core/                   # 核心配置
│   ├── config.py           # 配置管理
│   ├── database.py         # 数据库连接
│   ├── deps.py             # 依赖注入
│   ├── exceptions.py       # 异常定义
│   ├── redis.py            # Redis 连接
│   └── security.py         # 安全模块
│
├── crud/                   # 数据访问层
│   ├── customer.py         # 客户 CRUD
│   ├── lead.py             # 线索 CRUD
│   └── ...                 # 其他 CRUD
│
├── models/                 # 数据库模型
│   ├── customer.py         # 客户模型
│   ├── lead.py             # 线索模型
│   └── ...                 # 其他模型
│
├── schemas/                # Pydantic Schema
│   ├── customer.py         # 客户 Schema
│   ├── lead.py             # 线索 Schema
│   └── ...                 # 其他 Schema
│
├── services/               # 业务逻辑层
│   ├── permission_service.py
│   └── ...                 # 其他服务
│
├── constants/              # 常量定义
│   └── operation_log_events.py
│
└── main.py                 # 应用入口
```

---

## 三、模块职责边界

### 3.1 前端分层

| 层级 | 职责 | 禁止行为 |
|------|------|----------|
| **api/** | HTTP 调用 + 类型导出 | 业务逻辑、状态管理、组件渲染 |
| **schemas/** | Zod 校验定义 | HTTP 调用、业务逻辑 |
| **components/** | UI 渲染 + 交互 | 直接调用 API（通过 props/emit） |
| **stores/** | 全局状态管理 | 组件逻辑、DOM 操作 |
| **views/** | 页面编排 + 数据绑定 | 定义类型（从 api/ 导入） |
| **utils/** | 纯函数工具 | 带副作用的操作 |

### 3.2 后端分层

| 层级 | 职责 | 禁止行为 |
|------|------|----------|
| **api/** | 请求解析 + 响应封装 | 直接操作数据库（通过 crud） |
| **schemas/** | 数据校验 + 序列化 | 业务逻辑、数据库操作 |
| **crud/** | 数据库 CRUD | HTTP 处理、业务逻辑 |
| **services/** | 复杂业务逻辑 | HTTP 处理（可调用 crud） |
| **models/** | 表结构定义 | 业务逻辑 |

---

## 四、模块通信规则

### 4.1 前端通信

```
views/  ──调用──▶  api/  ──校验──▶  schemas/
  │                 │
  │                 │
  └─监听──▶  stores/  ──使用──▶  utils/
```

**允许调用**：
- views → api（获取数据）
- views → stores（读取/更新状态）
- views → components（渲染子组件）
- api → schemas（校验响应）
- stores → utils（使用工具）

**禁止调用**：
- components → api（禁止直接调用 API）
- stores → views（禁止反向依赖）
- api → stores（禁止访问状态）

### 4.2 后端通信

```
api/  ──调用──▶  services/  ──调用──▶  crud/  ──操作──▶  models/
  │                 │
  │                 │
  └──使用──▶  schemas/（请求/响应校验）
```

**允许调用**：
- api → services → crud → models（单向向下）
- api → schemas（校验请求/响应）

**禁止调用**：
- crud → api（禁止反向依赖）
- models → services（禁止反向依赖）
- api → models（禁止跨层，必须通过 crud）

---

## 五、文件命名规范

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| Vue 组件 | PascalCase | `CustomerCard.vue` |
| Vue 页面 | PascalCase | `Customers.vue` |
| TypeScript 文件 | camelCase | `customer.ts` |
| Zod Schema | camelCase | `customer.ts` |
| Python 文件 | snake_case | `customer.py` |
| 目录 | snake_case / camelCase | `api/` `components/` |

---

## 六、禁止的架构行为

| 禁止行为 | 原因 | 正确做法 |
|----------|------|----------|
| 组件内直接调用 API | 违反分层 | 通过 props/emit，由页面调用 |
| views 内定义类型 | 违反单一来源 | 从 api/ 或 schemas/ 导入 |
| stores 内使用 any | 违反类型安全 | 使用 TYPESCRIPT.md Approved Types |
| 跨模块导入（如 api 导入 stores） | 违反单向依赖 | 通过参数传递 |
| 修改核心配置文件 | 违反红线 | 需人工审批 |

---

## 七、校验规则

| 校验点 | 工具 | 时机 |
|--------|------|------|
| 目录结构 | Git hooks 文件检测 | pre-commit |
| 跨层调用 | ESLint import 规则 | pre-commit |
| 命名规范 | ESLint filename 规则 | pre-commit |

---

**版本：1.0 | 最后更新：2026-04-21 | 修改需人工审批**