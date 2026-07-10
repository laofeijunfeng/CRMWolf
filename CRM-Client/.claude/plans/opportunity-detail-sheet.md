# 商机详情页抽屉化实施方案

**创建时间**：2026-07-10
**状态**：✅ 已实施

---

## 一、需求分析

### 1.1 用户需求
- 将商机详情页从"独立页面跳转"改为"右侧抽屉"
- 抽屉宽度：右侧页面的 **2/3**
- 使用 shadcn-vue 组件，只自定义样式
- 符合系统设计规范（CRM-Docs/design-system）

### 1.2 当前问题
- 点击商机名称跳转到独立页面，离开列表上下文
- 使用 Element Plus 组件（el-dialog、el-form）
- 页面跳转体验不够流畅

---

## 二、技术方案

### 2.1 组件选型（全部 shadcn-vue）

| 功能 | 组件 | 说明 |
|------|------|------|
| 抽屉容器 | `Sheet` | side="right", 宽度 66.67% |
| 滚动区域 | `ScrollArea` | 内容过长时滚动 |
| 信息卡片 | `Card` | 基本信息、关联合同 |
| 分隔线 | `Separator` | 区域分隔 |
| 状态标签 | `Badge` | 状态、采购类型 |
| 按钮 | `Button` | 赢单/输单/编辑 |
| 弹窗 | `Dialog` | 赢单/输单确认 |
| 图标 | `Lucide` | 统一图标来源 |

### 2.2 文件结构

```
src/views/
├── Opportunities.vue          # 修改：集成抽屉
├── OpportunityDetailSheet.vue # 新建：抽屉组件
└── OpportunityDetail.vue      # 保留：独立页面入口（可选）
```

---

## 三、详细设计

### 3.1 抽屉布局结构

```
Sheet (side="right", class="w-2/3 max-w-[880px]")
└── SheetContent
    ├── SheetHeader（商机名称 + 状态 Badge）
    ├── ScrollArea（内容区）
    │   ├── Card（基本信息）
    │   │   ├── 标题区：Avatar + 名称 + Badge
    │   │   ├── Separator
    │   │   └── 属性网格：4列 → 2列 → 1列（响应式）
    │   ├── Separator
    │   ├── ProcurementStageFlow（采购阶段流程）
    │   ├── Separator
    │   └── Card（关联合同）
    │       ├── 标题区：合同名称 + 状态 Badge
    │       ├── Separator
    │       └── 属性网格
    └── SheetFooter（操作按钮）
        ├── Button（赢单）- 仅"跟进中"状态
        ├── Button（输单）- 仅"跟进中"状态
        └── Button（编辑）
```

### 3.2 样式规范（V2 Design Tokens）

| 属性 | Token | 值 |
|------|-------|-----|
| 背景色 | `$wolf-bg-card-v2` | `#FFFFFF` |
| 页面背景 | `$wolf-bg-page-v2` | `#F8FAFC` |
| 主色 | `$wolf-primary-v2` | `#2563EB` |
| 圆角 | `$wolf-radius-v2` | `6px` |
| 过渡 | `$wolf-transition-v2` | `0.15s ease` |

### 3.3 属性网格设计

**4 列布局**（默认）：
```
客户名称    负责人    采购用户数    标准单价
采购方式    预计成交  授权模式      订阅年限
实际成交    创建时间  输单原因      -
```

**响应式**：
- xs/sm: 1 列
- md: 2 列
- lg+: 4 列

---

## 四、实施步骤

### Step 1：创建抽屉组件
**文件**：`src/views/OpportunityDetailSheet.vue`

**功能**：
- props: `opportunityId: number`, `visible: boolean`
- emits: `update:visible`, `refresh`
- 获取商机详情 API
- 获取关联合同 API
- 渲染基本信息、采购阶段流程、关联合同

**关键代码结构**：
```vue
<script setup lang="ts">
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter } from '@/components/ui/sheet'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent } from '@/components/ui/dialog'
// ...
</script>
```

### Step 2：修改列表页
**文件**：`src/views/Opportunities.vue`

**变更**：
1. 导入 OpportunityDetailSheet
2. 添加状态：`selectedOpportunityId: number | null`
3. 修改点击事件：`@click.stop="openDetailSheet(row.id)"`
4. 添加组件：`<OpportunityDetailSheet v-model:visible="sheetVisible" :opportunity-id="selectedId" />`

### Step 3：替换弹窗（赢单/输单）
**方案**：使用 shadcn-vue Dialog + Form

**赢单弹窗**：
- Dialog + DialogContent
- Form（金额、日期）
- Button（取消/确认）

**输单弹窗**：
- Dialog + DialogContent
- Form（输单原因 textarea）
- Button（取消/确认）

---

## 五、设计规范合规检查

| 规范章节 | 要求 | 实现 |
|----------|------|------|
| §9 Navigation | modal-escape | Sheet 有关闭按钮，支持 ESC |
| §7 Animation | 150-300ms | Sheet 动画自带符合 |
| §2 Touch | 44px 最小 | Button 尺寸符合 |
| §1 Accessibility | aria-labels | Sheet 有 aria 属性 |
| §3 shadcn-vue | 强制使用 | 全部使用 shadcn-vue |
| §2 Design Token | V2 变量 | 使用 `$wolf-xxx-v2` |

---

## 六、补充规范（基于 MASTER.md）

### 6.1 API 错误处理（§3.7）

**必须使用统一错误处理工具**：

```typescript
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { confirmDialog } from '@/utils/confirmDialog'

// 示例：标记赢单
const handleWin = async () => {
  try {
    await opportunityApi.markAsWon(opportunityId, winForm)
    toast.success('商机已标记为赢单')
    closeSheet()
    emit('refresh')
  } catch (error) {
    handleApiError(error, '标记赢单')
  }
}

// 禁止使用：ElMessage、ElMessageBox
```

### 6.2 移动端适配（§1.3, §10）

| 属性 | 桌面端 | 移动端 | Token |
|------|--------|--------|-------|
| **Sheet 方向** | side="right" | side="bottom" | - |
| **Sheet 宽度** | 66.67% | 100% | - |
| **Sheet 高度** | auto | 90vh | `$wolf-modal-height-mobile-v2` |
| **Button 高度** | 32px | 44px | `$wolf-button-height-mobile-v2` |
| **Input 高度** | 32px | 44px | `$wolf-input-height-mobile-v2` |
| **Input 字号** | 14px | 16px | `$wolf-font-size-body-mobile-v2` |

**响应式切换**：
```scss
.opportunity-sheet {
  width: 66.67%;
  
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    width: 100%;
    height: 90vh;
    border-radius: $wolf-radius-lg-v2 $wolf-radius-lg-v2 0 0;
  }
}
```

### 6.3 Focus 状态规范（§8.2）

**所有交互元素必须有可见 Focus 状态**：

```scss
// Button Focus
.button:focus-visible {
  outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
  outline-offset: $wolf-focus-ring-offset-v2;
}

// Input Focus
.input:focus-visible {
  border-width: 2px;
  border-color: $wolf-primary-v2;
  box-shadow: $wolf-focus-shadow-v2;
}
```

**Reduced Motion 支持**：
```scss
@media (prefers-reduced-motion: reduce) {
  .sheet,
  .button,
  .dialog {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
```

### 6.4 表格规范（§5.3）

**关联合同表格**：

| 属性 | Token | 值 |
|------|-------|-----|
| 行高 | - | 44px（自适应） |
| 表头背景 | - | `#F1F5FD` |
| 表头文字 | `$wolf-text-secondary-v2` | `#64748B` |
| Hover 背景 | `$wolf-bg-hover-v2` | `#EEF2FF` |

### 6.5 Form 组件使用（§3.4）

**shadcn-vue Form 基于 VeeValidate + Zod**：

```vue
<script setup lang="ts">
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'

// 定义验证规则
const winFormSchema = toTypedSchema(z.object({
  actual_amount: z.number().min(0, '金额必须大于等于0'),
  actual_closing_date: z.string().min(1, '请选择日期')
}))

// 使用 Form
const form = useForm({
  validationSchema: winFormSchema,
  initialValues: {
    actual_amount: 0,
    actual_closing_date: new Date().toISOString().split('T')[0]
  }
})
</script>

<template>
  <Form>
    <FormField name="actual_amount">
      <FormItem>
        <FormLabel>实际成交金额</FormLabel>
        <FormControl>
          <Input type="number" />
        </FormControl>
        <FormMessage />
      </FormItem>
    </FormField>
  </Form>
</template>
```

### 6.6 确认对话框设计

**赢单/输单使用 Dialog + Form 组合**：

```vue
<!-- 赢单确认对话框 -->
<Dialog v-model:open="winDialogOpen">
  <DialogContent class="sm:max-w-[425px]">
    <DialogHeader>
      <DialogTitle>标记赢单</DialogTitle>
      <DialogDescription>请输入实际成交金额和日期</DialogDescription>
    </DialogHeader>
    
    <Form>
      <!-- Form 内容 -->
    </Form>
    
    <DialogFooter>
      <Button variant="outline" @click="winDialogOpen = false">取消</Button>
      <Button type="submit" @click="handleWinConfirm">确认</Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

---

## 七、风险与备选方案

| 风险 | 备选方案 |
|------|---------|
| Sheet 宽度不够 | 增加到 80% 或使用 Drawer 组件 |
| 关联合同内容过多 | 使用 Tabs 分组展示 |
| 采购阶段流程依赖路由 | 改为传入 opportunity-id prop |
| Form 组件复杂 | 使用原生 Form + 手动验证 |

---

## 八、预期效果

| 效果 | 说明 |
|------|------|
| 上下文保留 | 用户不离开列表页，可快速切换查看多个商机 |
| 快速操作 | 抽屉内直接赢单/输单，无需跳转 |
| 性能优化 | 抽屉延迟加载，减少初始页面加载 |
| 一致性 | 与设计规范 V2 统一，使用 shadcn-vue |

---

## 九、验收标准

- [ ] 点击商机名称打开右侧抽屉（宽度 2/3）
- [ ] 抽屉内显示：基本信息 + 采购阶段流程 + 关联合同
- [ ] 赢单/输单按钮仅在"跟进中"状态显示
- [ ] 赢单/输单弹窗使用 shadcn-vue Dialog
- [ ] 所有样式使用 V2 Design Tokens
- [ ] 关闭抽屉后列表页数据刷新

---

**实施顺序**：
1. 创建 OpportunityDetailSheet.vue
2. 修改 Opportunities.vue
3. 替换赢单/输单弹窗
4. 测试验收