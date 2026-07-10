# CRMWolf 设计系统文档索引

**全局设计规范文档中心**

---

## 一、文档结构

```
CRM-Docs/design-system/
├── MASTER.md                      # 全局设计规则唯一来源（含布局架构说明 §6.6）
├── pages/                         # 页面特定结构规范
│   ├── list-page.md               # 列表页结构规范
│   ├── detail-page.md             # 详情页结构规范
│   ├── form-page.md               # 表单页结构规范
│   └── approval-center.md         # 审批中心结构规范
└── README.md                      # 本文档（索引 + 架构说明 §三）
```

---

## 二、文档使用指南

### 2.1 如何查阅

**步骤**：

1. **确定页面类型**（列表页/详情页/表单页/审批中心）
2. **查阅页面特定文档**（`pages/[页面类型].md`）
3. **查阅 MASTER.md**（补充通用规则）

### 2.2 文档优先级

```
页面特定规则 > MASTER.md 规则
```

**示例**：
- 如果在 `pages/detail-page.md` 中有关于"ContextTabs 高度"的规则，优先使用
- 如果没有，使用 `MASTER.md` 中的通用规则（48px）

---

## 三、架构说明

### 3.1 布局架构实现

CRMWolf 采用 **"内部 Sticky TopBar"** 架构，与设计规范 HTML（navigation-redesign-v3.html）略有不同。

**关键差异：**

| 维度 | 设计规范 HTML | CRMWolf 实现 |
|------|--------------|--------------|
| TopBar 定位 | `fixed` 在外部 | `sticky` 在内部 |
| 间距处理 | `margin-top` 推开 | `padding-top` 创建间距 |
| ContextTabs | 有（48px） | 暂无 |

**实现原理：**

```scss
// AppLayout：TopBar 紧贴顶部
.main-content {
  // 无 padding-top
}

// 页面组件：自己的 padding 提供间距
.leads-page {
  padding: 24px;  // 顶部、左右、底部
  gap: 24px;  // 组件间距
  flex: 1;  // 继承高度
}
```

**总间距：24px**（由页面 padding-top 提供）

> 详见 `MASTER.md` 第 6.6 节"布局架构实现"

---

## 四、文档清单

### 3.1 MASTER.md（全局规则）

| 章节 | 内容 |
|------|------|
| **一、设计原则** | 四大核心原则、设计优先级、移动端设计原则 |
| **二、设计系统强制规范** | Design Token 强制规范（CRITICAL） |
| **三、组件开发规范** | shadcn-vue 优先原则（CRITICAL） |
| **四、视觉风格规范** | 色彩、圆角、间距、阴影、动画系统 |
| **五、组件设计规范** | Button、Input、Table、Card、Tab |
| **六、导航组件规范** | Sidebar、TopBar、ContextTabs、UserInfoDropdown |
| **七、交互规范** | Hover、Active、Disabled、Loading 状态 |
| **八、无障碍规范** | 对比度、Focus、Screen Reader |
| **九、性能规范** | 动画性能、响应时间 |
| **十、响应式规范** | 断点系统、间距适配、Safe Areas |
| **十一、禁止事项** | Anti-Patterns、Stylelint 强制规则 |
| **十二、向后兼容** | 变量别名、迁移时间表 |
| **十三、文档检索规则** | 层级检索、页面文档命名 |

---

### 3.2 pages/list-page.md（列表页）

| 章节 | 内容 |
|------|------|
| **一、页面组成** | 三层结构、组件清单 |
| **二、TopBar 布局** | 三段式、操作按钮规范 |
| **三、表格区域布局** | 搜索栏、表格规范、表头对齐 |
| **四、状态 Badge 规范** | 客户状态、审批状态 |
| **五、分页规范** | 分页位置、样式 |
| **六、空状态规范** | 空状态设计 |

**适用页面**：线索管理、客户管理、商机管理、合同管理、回款管理、发票管理

---

### 3.3 pages/detail-page.md（详情页）

| 章节 | 内容 |
|------|------|
| **一、页面组成** | 四层结构、组件清单 |
| **二、TopBar 布局** | 三段式、操作按钮规范 |
| **三、ContextTabs** | 二级导航、标签内容、样式 |
| **四、内容区域布局** | 信息头部、属性网格、业务流程卡片 |
| **五、表格区域规范** | 表格位置、样式、操作按钮 |

**适用页面**：客户详情、合同详情、回款详情、发票详情

---

### 3.4 pages/form-page.md（表单页）

| 章节 | 内容 |
|------|------|
| **一、页面组成** | 导航层级、组件清单 |
| **二、TopBar 布局** | 三段式、返回按钮 |
| **三、表单布局规范** | 表单宽度、卡片、分组 |
| **四、表单字段规范** | 字段布局、高度、间距 |
| **五、标签规范** | 标签样式、必填标识 |
| **六、错误提示规范** | 错误位置、样式、Input Error 状态 |
| **七、操作按钮规范** | 按钮位置、样式 |

**适用页面**：新建客户、新建合同、新建商机、编辑客户、编辑合同

---

### 3.5 pages/approval-center.md（审批中心）

| 章节 | 内容 |
|------|------|
| **一、页面组成** | 导航层级、组件清单 |
| **二、审批铃铛设计** | ApprovalIcon、Badge 样式 |
| **三、审批中心布局** | 审批类型标签、待审批表格 |
| **四、审批详情设计** | Modal、ApprovalProgressCompact |
| **五、审批时间线** | ApprovalTimeline 布局、样式 |
| **六、导航入口优化** | 审批入口唯一性、路由 |

**适用页面**：审批中心

---

## 四、核心设计原则速查

### 4.1 四大核心原则

| 原则 | 说明 | 关键检查 |
|------|------|---------|
| **极致克制** | 装饰性元素不超过5% | 所有设计元素必须有明确用途 |
| **柔和低噪** | 使用中性暖灰为主色调 | 避免高饱和色彩 |
| **统一有序** | 所有组件使用 Design Tokens | 禁止硬编码颜色、圆角、间距 |
| **服务内容** | UI 不抢夺用户注意力 | 内容为王，UI 为辅 |

### 4.2 关键数值速查表

| 属性 | Token | 值 |
|------|-------|-----|
| **主色** | `$wolf-primary-v2` | `#2563EB` |
| **统一圆角** | `$wolf-radius-v2` | `6px` |
| **过渡动画** | `$wolf-transition-v2` | `0.15s ease` |
| **表格行高** | - | `44px`（自适应） |
| **ContextTabs 高度** | - | `48px` |
| **Sidebar 宽度** | - | `220px` |
| **TopBar 高度** | - | `56px` |

---

## 五、强制规则速查

### 5.1 禁止事项

| 禁止项 | 原因 | 强制工具 |
|--------|------|---------|
| ❌ Emoji 作为图标 | 跨平台不一致 | Stylelint |
| ❌ 硬编码颜色 | 违反 Design Tokens | Stylelint |
| ❌ 硬编码圆角（4/8/12/16px） | 统一 6px | Stylelint |
| ❌ 超过 500ms 动画 | 用户感知慢 | 手动检查 |
| ❌ 无 Focus 状态 | 无障碍不合规 | axe-core |

### 5.2 Stylelint 配置（强制）

```javascript
{
  'declaration-property-value-disallowed-list': {
    'color': ['/#[0-9a-fA-F]{3,6}/'],
    'border-radius': ['/(4|8|12|16)px/']
  }
}
```

---

## 六、团队协作指南

### 6.1 设计评审流程

```
设计师提交设计稿 → 前端查阅 MASTER.md → 前端查阅页面文档 →
前端实现 → 设计师对照文档验收 → 团队评审
```

### 6.2 文档更新流程

```
发现设计规则缺失 → 提出 Issue → 团队讨论 →
更新 MASTER.md 或页面文档 → 团队通知
```

---

## 七、文档版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| **V2** | 2026-07-08 | 基于 navigation-redesign-v3.html 重新设计 |
| **V1** | 之前 | 极简中性风设计（variables.scss） |

---

## 八、shadcn-vue 强制使用规范（CRITICAL）

> ⚠️ **铁律：所有 UI 组件必须使用已安装的 shadcn-vue 组件，禁止自定义开发**

### 8.1 核心原则

| 规则 | 说明 |
|------|------|
| **唯一来源** | 所有 UI 组件必须来自 `src/components/ui/` |
| **用户确认** | shadcn-vue 没有的组件，必须向用户确认后才能自定义 |
| **零容忍** | 禁止任何"技术壁垒"、"特殊需求"、"临时方案"等借口 |

### 8.2 已安装组件清单（2026-07-10）

**总计**：41 个组件目录，136+ 个组件文件

| 类别 | 组件 |
|------|------|
| **核心组件** | Button, Input, Textarea, Label |
| **布局容器** | Card, Separator, ScrollArea, AspectRatio |
| **导航组件** | Tabs, Breadcrumb, NavigationMenu, DropdownMenu, Select |
| **数据录入** | Checkbox, Switch, RadioGroup, Select, Combobox, Slider |
| **反馈状态** | Badge, Progress, Skeleton, Avatar, Alert, Toast |
| **弹窗模态** | Dialog, AlertDialog, DropdownMenu, Popover, Sheet, Drawer, Tooltip, HoverCard |
| **命令菜单** | Command, ContextMenu, Menubar |
| **数据展示** | Table, Pagination |
| **折叠展开** | Accordion, Collapsible |
| **日历日期** | Calendar |
| **轮播** | Carousel |

### 8.3 使用方式

```typescript
// 统一从 crmwolf 导入
import {
  Button, Dialog, AlertDialog, DropdownMenu,
  Badge, Avatar, Progress
} from '@/components/crmwolf'

// 或直接从 ui 目录导入
import { Button } from '@/components/ui/button'
```

### 8.4 详细规范

> **完整规范**：详见 [MASTER.md §三、组件开发规范](MASTER.md#三组件开发规范critical)

### 8.5 组件封装原则（CRITICAL）

> ⚠️ **最高优先级原则**：如有冲突，以此原则为准

**核心规则**：

| 规则 | 说明 |
|------|------|
| **严格按规范封装** | 所有使用 shadcn-vue 的组件，必须严格按照设计规范进行封装 |
| **样式改造** | 封装过程中，仅根据设计规范调整样式（颜色、圆角、间距等） |
| **保留原生动态效果** | 所有动态效果（动画、过渡、交互反馈）使用组件本身的动态效果，不做任何调整 |
| **冲突处理** | 当其他规则与本原则冲突时，以本原则为准 |

**实施要点**：

```typescript
// ✅ 正确：仅封装样式
const CustomButton = defineComponent({
  setup(props, { slots }) {
    return () => h(Button, {
      class: 'bg-primary text-white rounded-md' // 仅样式改造
    }, slots)
  }
})

// ❌ 错误：修改动态效果
const CustomButton = defineComponent({
  setup(props, { slots }) {
    return () => h(Button, {
      class: 'bg-primary',
      // ❌ 禁止修改过渡时长
      style: { transition: 'all 0.3s ease' }
    }, slots)
  }
})
```

**为什么这样做**：

1. **一致性保证**：shadcn-vue 的动画经过精心设计和测试，保证跨浏览器一致性
2. **维护成本最低**：避免自定义动画带来的维护负担
3. **用户体验统一**：保持整个应用的交互体验一致性
4. **升级友好**：组件库升级时，不会因为自定义动画而产生冲突

**适用范围**：

- ✅ Button、Input、Table、Card 等所有 shadcn-vue 组件
- ✅ Dialog、DropdownMenu、Popover 等弹窗类组件
- ✅ Tabs、Breadcrumb 等导航类组件
- ✅ 所有未来新增的 shadcn-vue 组件

---

## 九、参考资料

| 文档 | 路径/链接 |
|------|----------|
| **UI/UX Pro Max** | `~/.claude/skills/ui-ux-pro-max/` |
| **shadcn-vue 文档** | https://www.shadcn-vue.com/ |
| **Lucide Icons** | https://lucide.dev/ |
| **VeeValidate** | https://vee-validate.logaretm.com/ |
| **vue-sonner (Toast)** | https://github.com/xiaoluoboding/vue-sonner |
| **Element Plus 文档** | https://element-plus.org/（迁移完成后删除） |
| **Material Design** | https://material.io/design |
| **Apple HIG** | https://developer.apple.com/design/human-interface-guidelines |

---

## 十、联系与反馈

**文档维护团队**：
- 设计负责人：[待定]
- 前端负责人：[待定]

**反馈渠道**：
- GitHub Issue：[项目仓库链接]
- Slack Channel：#design-system

---

**版本：V2.3 | 最后更新：2026-07-10**

> **本次更新**：新增 §8.5 组件封装原则（CRITICAL），明确 shadcn-vue 组件封装时仅改造样式、保留原生动态效果