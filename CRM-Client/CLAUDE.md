# CRM-Client 前端模块

**Claude Code 进入此目录时自动加载**

---

## 模块结构地图

```
CRM-Client/
├── src/
│   ├── api/           # API 请求层（复用 baseURL，禁止硬编码）
│   ├── components/    # 共享组件（必须配 .stories.ts）
│   ├── views/         # 页面组件
│   ├── stores/        # Pinia 状态管理（详见 stores/CLAUDE.md）
│   ├── schemas/       # TypeScript 类型 + Zod schema
│   ├── styles/        # Design Token 唯一来源（variables-v2.scss）
│   └── utils/         # 工具函数
├── docs/              # 详细规范文档（按需查阅）
└── tests/             # 测试文件
```

---

## 开发命令

```bash
npm run dev          # 启动开发服务器
npm run lint         # ESLint 校验
npm run type-check   # TypeScript 校验
npm run test:unit    # 单元测试
npm run coverage     # 覆盖率报告
```

---

## 防幻觉指令（禁止推断）

Claude **绝对禁止推断**以下业务常量，必须查阅代码定义：

| 禁止推断 | 定义位置 |
|----------|----------|
| 客户状态枚举 | `CRM-Server/app/constants/customer_status.py` |
| 商机阶段映射 | `CRM-Server/app/constants/opportunity_stages.py` |
| 权限码 | `CRM-Docs/system/GLOSSARY.md` |
| **设计 Token** | **`CRM-Client/src/styles/variables-v2.scss`** ⚠️ 必须使用 `-v2` 后缀 |
| API 响应格式 | `CRM-Docs/best-practices/backend/api-design.md` |

---

## 核心规则

- **TypeScript 四禁令**：禁用 `any` `as any` `@ts-ignore` `!`
- **组件 Props/Emits**：必须类型化
- **Pinia Store**：禁止 any 状态，必须 storeToRefs 解构
- **API 请求**：必须 Zod 校验
- **设计 Token（CRITICAL）**：
  - ✅ 导入 `variables-v2.scss`
  - ✅ 使用 `$wolf-xxx-v2` 变量名
  - ❌ 禁止使用 `variables.scss`
  - ❌ 禁止硬编码颜色/间距/圆角

**详细规则**：`.claude/rules/frontend.md`, `.claude/rules/design.md`

---

**详细规范（按需查阅）**：`docs/TYPESCRIPT.md`, `docs/COMPONENTS.md`, `docs/STATE-MANAGEMENT.md`