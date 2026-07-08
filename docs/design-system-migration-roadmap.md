# CRMWolf 设计系统优化实施路线图

**目标**：基于 navigation-redesign-v3.html 方案，实现整体替换、统一标准、组件化

---

## 一、现状分析

### 1.1 现有设计系统（variables.scss）

| 维度 | 现有系统 | 新方案（v3） | 差异分析 |
|------|---------|------------|---------|
| **字体系统** | IBM Plex Sans（技术感） | Fira Sans（数据感） | 建议保留 IBM Plex Sans，符合现有品牌定位 |
| **主色调** | #4A6FA5（低饱和蓝） | #2563EB（标准蓝） | **建议升级为 #2563EB**，更现代、更清晰 |
| **圆角系统** | 4px / 8px / 12px / 16px | 6px（统一） | 建议采用新方案的 6px 标准，更简洁 |
| **间距系统** | 4px / 8px / 16px / 24px（8dp grid） | 8px / 12px / 16px | **建议保留现有 8dp grid**，更系统化 |
| **阴影系统** | 极淡极柔 | 中等强度 | 建议采用新方案的中等强度，更有层次感 |

### 1.2 现有组件库

- **审批组件**：ApprovalIcon、ApprovalStatusBadge、ApprovalProcess、ApprovalTimeline
- **导航组件**：AppLayout（左侧菜单）、CustomerDetailSidebar、PaymentSidebar
- **业务组件**：50+ 个组件文件

---

## 二、实施路线图（4个阶段）

### Phase 1: 设计系统基础升级（2-3 周）

**目标**：建立新设计系统基础，保持向后兼容

#### 任务清单

| 任务 | 优先级 | 工作量 | 依赖 |
|------|--------|--------|------|
| **1.1 更新 Design Tokens** | P0 | 2天 | 无 |
| 创建新文件 `variables-v2.scss`，包含新的颜色、圆角、阴影 tokens | | | |
| **1.2 创建过渡方案** | P0 | 1天 | 1.1 |
| 编写迁移指南，列出旧变量→新变量的映射关系 | | | |
| **1.3 创建 Design System 文档** | P0 | 2天 | 1.1 |
| 使用 UI/UX Pro Max 的 `--design-system --persist` 生成 MASTER.md | | | |
| **1.4 创建视觉对比文档** | P1 | 1天 | 1.1 |
| 使用 Storybook 创建新旧设计的对比展示 | | | |
| **1.5 更新 Element Plus 主题** | P0 | 1天 | 1.1 |
| 调整 `element-plus-theme.scss`，适配新的主色调 | | | |

#### 输出成果

- `src/styles/variables-v2.scss`（新设计系统）
- `docs/design-system/MASTER.md`（设计系统文档）
- `docs/design-system/MIGRATION.md`（迁移指南）
- Storybook 新旧对比展示

---

### Phase 2: 核心组件库建设（3-4 周）

**目标**：创建新的导航组件和通用组件，逐步替换旧组件

#### 2.1 导航组件重构

| 组件 | 优先级 | 工作量 | 说明 |
|------|--------|--------|------|
| **Sidebar（左侧菜单）** | P0 | 3天 | 基于 navigation-redesign-v3.html，包含左侧指示条设计 |
| **TopBar（顶部栏）** | P0 | 2天 | 包含面包屑、操作按钮、审批铃铛 |
| **ContextTabs（上下文标签栏）** | P0 | 2天 | 动态二级导航，根据页面类型切换 |
| **UserInfoDropdown（用户下拉菜单）** | P0 | 1天 | 包含团队切换、个人设置 |
| **ApprovalIcon（优化版）** | P1 | 1天 | 现有组件优化，适配新设计系统 |

#### 2.2 通用组件库

| 组件 | 优先级 | 工作量 | 说明 |
|------|--------|--------|------|
| **Button（新设计）** | P0 | 1天 | 基于 v3 方案，统一圆角、间距、阴影 |
| **Card（新设计）** | P0 | 1天 | 统一圆角、阴影、边框 |
| **Table（新设计）** | P1 | 2天 | 统一样式，无竖分割线、自适应行高 |
| **Dropdown（新设计）** | P1 | 1天 | 统一圆角、阴影、动画 |
| **StatusBadge（统一）** | P1 | 1天 | 统一审批状态、业务状态的颜色方案 |

#### 2.3 Storybook 建设

每个组件必须包含：
- `.stories.ts` 文件（展示组件的所有状态）
- 设计说明（引用 MASTER.md 的设计规则）
- 交互测试（hover/active/disabled 状态）

#### 输出成果

- 10+ 新组件（导航 + 通用）
- 完整的 Storybook 展示
- 组件使用文档

---

### Phase 3: 逐页面替换（4-6 周）

**目标**：逐页面替换，确保功能不受影响

#### 3.1 替换策略

**渐进式替换**（不建议一次性全替换）：
- 先替换高频页面（线索管理、客户管理、合同管理）
- 再替换低频页面（设置、配置）
- 最后替换详情页（客户详情、合同详情）

**每个页面替换流程**：
1. 创建新页面组件（使用新组件库）
2. 并行运行新旧页面（通过路由切换）
3. 团队测试新页面（功能、性能、样式）
4. 确认无问题后，替换旧页面
5. 删除旧页面代码

#### 3.2 页面替换顺序

| 页面 | 优先级 | 原因 |
|------|--------|------|
| **线索管理（Leads.vue）** | P0 | 高频使用，简单页面，适合作为试点 |
| **客户管理（Customers.vue）** | P0 | 高频使用，核心业务页面 |
| **合同管理（Contracts.vue）** | P0 | 高频使用，核心业务页面 |
| **回款管理（Payments.vue）** | P0 | 高频使用，涉及财务审批 |
| **发票管理（Invoices.vue）** | P1 | 中频使用 |
| **审批中心（ApprovalCenter.vue）** | P1 | 中频使用，涉及审批流程 |
| **客户详情（CustomerDetail.vue）** | P2 | 复杂页面，包含多个子组件 |
| **合同详情（ContractDetail.vue）** | P2 | 复杂页面 |
| **设置页面（Settings.vue）** | P3 | 低频使用 |

#### 3.3 替换标准

每个页面替换前必须满足：
- ✅ 所有新组件已测试通过（Storybook + 单元测试）
- ✅ 功能完整性测试通过（所有按钮、表单、表格功能正常）
- ✅ 性能测试通过（加载时间、交互响应）
- ✅ 无障碍测试通过（keyboard nav、screen reader）
- ✅ 团队评审通过（至少 2 人评审）

---

### Phase 4: 测试与验证（2 周）

**目标**：全面测试，确保无遗漏问题

#### 4.1 自动化测试

| 测试类型 | 工具 | 覆盖范围 |
|---------|------|---------|
| **单元测试** | Vitest + Vue Test Utils | 所有新组件 |
| **视觉回归测试** | Playwright + Storybook | 所有页面截图对比 |
| **性能测试** | Lighthouse | Core Web Vitals（CLS < 0.1） |
| **无障碍测试** | axe-core | WCAG AA 标准（4.5:1 contrast） |

#### 4.2 手动测试

- **功能测试**：团队全员测试所有功能流程
- **视觉测试**：对比新旧设计，确保视觉一致性
- **交互测试**：测试所有交互细节（hover、active、disabled、focus）
- **响应式测试**：测试不同屏幕尺寸（375px / 768px / 1024px / 1440px）

#### 4.3 验收标准

| 标准 | 目标值 | 说明 |
|------|--------|------|
| **视觉一致性** | 100% | 所有页面采用新设计系统 |
| **功能完整性** | 100% | 所有功能正常工作 |
| **性能** | CLS < 0.1 | Core Web Vitals 合规 |
| **无障碍** | WCAG AA | 4.5:1 contrast ratio |
| **单元测试覆盖率** | > 80% | 所有新组件有单元测试 |

---

## 三、关键实施细节

### 3.1 如何确保"整体替换"

**策略**：渐进式替换 + 强制规则

#### 强制规则（通过 CI/CD）

1. **禁止使用旧变量**：
   - ESLint 规则：禁止引用 `variables.scss` 中的旧变量（如 `$wolf-primary`）
   - 只允许使用 `variables-v2.scss` 中的新变量（如 `$wolf-primary-v2`）

2. **禁止直接写样式**：
   - ESLint 规则：禁止在组件中直接写 `color: #2563EB`、`border-radius: 6px`
   - 必须使用 Design Tokens（如 `color: $wolf-primary-v2`）

3. **强制 Storybook**：
   - CI 检查：每个新组件必须有对应的 `.stories.ts` 文件

#### 配置示例（.eslintrc.js）

```javascript
module.exports = {
  rules: {
    'no-restricted-syntax': [
      'error',
      {
        selector: 'Identifier[name="wolf-primary"]',
        message: '请使用 $wolf-primary-v2 替代旧变量'
      }
    ]
  }
}
```

---

### 3.2 如何确保"统一标准"

**策略**：Design System MASTER.md + 组件模板

#### Design System MASTER.md

使用 UI/UX Pro Max 生成：

```bash
python3 skills/ui-ux-pro-max/scripts/search.py \
  "CRM enterprise dashboard navigation minimal professional" \
  --design-system --persist \
  -p "CRMWolf" \
  -f markdown
```

输出：
- `design-system/MASTER.md`（所有设计规则的唯一来源）
- `design-system/pages/`（页面特定规则的覆盖）

#### 组件模板（CLAUDE.md）

为每个组件添加设计说明：

```markdown
# Button 组件设计说明

**引用规则**：design-system/MASTER.md §4.4（按钮尺寸）

**必须遵守**：
- 圆角：6px（$wolf-radius-v2）
- 间距：左右 24px，上下 8px（$wolf-button-padding-v2）
- 阴影：hover 时显示 $wolf-shadow-hover-v2
- 动画：150-300ms（$wolf-transition-v2）

**禁止**：
- 禁止使用 emoji 作为图标
- 禁止直接写 hex 颜色值
- 禁止超过 300ms 的动画
```

---

### 3.3 如何确保"组件化"

**策略**：组件库 + 组件测试 + 组件文档

#### 组件库结构

```
CRM-Client/src/components/
├── common/              # 通用组件（Button、Card、Table）
│   ├── Button.vue
│   ├── Button.stories.ts
│   ├── Button.spec.ts
│   └── Button.md        # 组件设计说明
├── navigation/          # 导航组件
│   ├── Sidebar.vue
│   ├── TopBar.vue
│   ├── ContextTabs.vue
│   ├── UserInfoDropdown.vue
├── approval/            # 审批组件
│   ├── ApprovalIcon.vue
│   ├── ApprovalStatusBadge.vue
└── business/            # 业务组件（客户、合同、回款）
```

#### 组件测试要求

每个组件必须包含：
1. **单元测试**（`.spec.ts`）：测试所有功能、状态、交互
2. **Storybook**（`.stories.ts`）：展示所有状态、变体
3. **设计说明**（`.md`）：引用 MASTER.md 的设计规则

#### Storybook 配置

```typescript
// Button.stories.ts
import type { Meta, StoryObj } from '@storybook/vue3'
import Button from './Button.vue'

const meta: Meta<typeof Button> = {
  title: 'Common/Button',
  component: Button,
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/file/xxx'  // 引用设计稿
    },
    docs: {
      description: {
        component: '引用规则：design-system/MASTER.md §4.4（按钮尺寸）'
      }
    }
  }
}
```

---

## 四、技术栈建议

### 4.1 必备工具

| 工具 | 用途 | 原因 |
|------|------|------|
| **Storybook** | 组件展示 + 文档 | 业界标准，支持 Vue 3，方便团队协作 |
| **Vitest** | 单元测试 | Vue 3 官方推荐，快速、支持 Vue Test Utils |
| **Playwright** | 视觉回归测试 | 跨浏览器，截图对比，自动化测试 |
| **ESLint + Stylelint** | 代码规范检查 | 强制使用 Design Tokens，禁止硬编码样式 |

### 4.2 配置文件

#### Storybook 配置（.storybook/main.ts）

```typescript
import type { StorybookConfig } from '@storybook/vue3-vite'

const config: StorybookConfig = {
  stories: ['../src/**/*.md', '../src/**/*.stories.@(js|jsx|ts|tsx)'],
  addons: [
    '@storybook/addon-links',
    '@storybook/addon-essentials',
    '@storybook/addon-interactions',
    '@storybook/addon-a11y'  // 无障碍检查
  ],
  framework: {
    name: '@storybook/vue3-vite',
    options: {}
  },
  docs: {
    autodocs: true
  }
}
```

#### Stylelint 配置（.stylelintrc.js）

```javascript
module.exports = {
  rules: {
    'declaration-property-value-disallowed-list': {
      'color': ['/#[0-9a-fA-F]{3,6}/'],  // 禁止直接写 hex 颜色
      'border-radius': ['/(4|8|12|16)px/']  // 禁止旧圆角值
    }
  }
}
```

---

## 五、团队协作流程

### 5.1 角色分工

| 角色 | 负责内容 | 产出 |
|------|---------|------|
| **设计负责人** | 设计系统制定、视觉评审 | MASTER.md、设计稿 |
| **前端负责人** | 组件库建设、页面替换 | 组件代码、Storybook |
| **测试负责人** | 自动化测试、验收测试 | 测试报告、覆盖率报告 |
| **全员** | 功能测试、评审 | 反馈、改进建议 |

### 5.2 协作流程

```
设计负责人制定设计规则 → 前端负责人实现组件 → 
Storybook 展示 → 全员评审 → 测试负责人测试 → 
合并到主分支 → 替换旧页面 → 删除旧代码
```

### 5.3 评审标准

每个组件合并前必须通过：
- ✅ 设计负责人视觉评审（符合 MASTER.md）
- ✅ 前端负责人代码评审（符合组件规范）
- ✅ 测试负责人测试评审（单元测试 + Storybook）

---

## 六、风险与应对

### 6.1 潜在风险

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| **视觉不一致** | 高 | 严格使用 Design Tokens，Stylelint 强制检查 |
| **功能遗漏** | 高 | 单元测试覆盖所有功能，手动测试验证 |
| **性能下降** | 中 | Lighthouse 监控，Core Web Vitals 合规 |
| **团队不熟悉新系统** | 中 | Storybook 文档、培训、迁移指南 |
| **向后兼容问题** | 高 | 保留旧变量别名，渐进式替换 |

### 6.2 向后兼容策略

```scss
// variables-v2.scss
$wolf-primary-v2: #2563EB;

// 向后兼容：保留旧变量名，指向新变量
$wolf-primary: $wolf-primary-v2;  // 兼容旧代码
```

---

## 七、验收标准总结

### 7.1 必须达到

| 标准 | 目标 | 验证方式 |
|------|------|---------|
| **整体替换** | 100% 页面使用新设计系统 | ESLint + Stylelint 检查 |
| **统一标准** | 所有组件引用 MASTER.md | Storybook docs |
| **组件化** | 所有页面使用组件库 | 代码审查 |
| **功能完整** | 所有功能正常工作 | 单元测试 + 手动测试 |
| **性能合规** | CLS < 0.1 | Lighthouse |
| **无障碍合规** | WCAG AA | axe-core |

### 7.2 成功标志

- ✅ 所有页面视觉统一（无旧样式残留）
- ✅ 所有组件有 Storybook 展示
- ✅ 所有样式使用 Design Tokens（无硬编码）
- ✅ 所有功能测试通过（单元测试 + E2E）
- ✅ 团队熟悉新系统（Storybook 文档 + 迁移指南）

---

## 八、参考资源

### 8.1 设计系统工具

- **UI/UX Pro Max**：`python3 skills/ui-ux-pro-max/scripts/search.py --design-system --persist`
- **Material Design**：https://material.io/design
- **Apple HIG**：https://developer.apple.com/design/human-interface-guidelines

### 8.2 技术工具

- **Storybook**：https://storybook.js.org
- **Vitest**：https://vitest.dev
- **Playwright**：https://playwright.dev
- **axe-core**：https://github.com/dequelabs/axe-core

### 8.3 书籍推荐

- **《Design Systems Handbook》**：InVision
- **《Refactoring UI》**：Adam Wathan & Steve Schoger

---

**总结**：这个实施路线图确保了整体替换、统一标准、组件化的三个核心目标，通过渐进式替换、强制规则、自动化测试、团队协作四个维度来保证实施质量。预计总工期：**8-15 周**（根据团队规模和页面复杂度调整）。