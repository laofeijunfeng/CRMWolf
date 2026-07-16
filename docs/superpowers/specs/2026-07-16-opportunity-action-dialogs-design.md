# 商机操作弹窗重构设计文档

**日期**: 2026-07-16
**状态**: 设计完成，待实施
**影响范围**: 商机列表页、商机详情页

---

## 一、背景与目标

### 1.1 当前问题

商机列表页（`Opportunities.vue`）的"推进阶段"、"赢单"、"输单"按钮功能未完整实现：
- 点击后跳转到不存在的路由（`/opportunities/{id}/advance-stage`、`/opportunities/{id}/win`、`/opportunities/{id}/lose`）
- 用户无法从列表页快速完成这些操作

商机详情页（`OpportunityDetailContent.vue`）已实现弹窗方式，但代码内联在组件中，无法复用。

### 1.2 目标

1. 让用户能从列表页快速完成商机操作，无需跳转页面
2. 提取可复用的弹窗组件，避免代码重复
3. 保持详情页和列表页交互一致

---

## 二、设计方案

### 2.1 架构设计

#### 组件结构
```
src/components/dialogs/
├── OpportunityWinDialog.vue      # 新建：赢单表单弹窗
└── OpportunityLoseDialog.vue     # 新建：输单表单弹窗

src/components/panels/
└── OpportunityDetailContent.vue  # 重构：改用新弹窗组件

src/views/
└── Opportunities.vue              # 修改：集成新弹窗组件
```

#### 数据流
```
列表页（Opportunities.vue）
  ↓ 点击"赢单/输单"
打开弹窗组件（传入 opportunityId）
  ↓ 弹窗内部调用 API
opportunityApi.getOpportunity(opportunityId)  # 加载详情
opportunityApi.markAsWon/markAsLost()         # 提交操作
  ↓ 成功后
emit('success') → 父组件刷新列表
```

---

### 2.2 操作方式

| 操作 | 列表页实现方式 | 详情页实现方式 |
|------|----------------|----------------|
| **推进阶段** | `confirmDialog` 确认弹窗（键盘支持：Enter 确认、Esc 取消） | 已实现，保持不变 |
| **赢单** | `OpportunityWinDialog` 表单弹窗（焦点管理、焦点陷阱） | 改用 `OpportunityWinDialog` |
| **输单** | `OpportunityLoseDialog` 表单弹窗（焦点管理、焦点陷阱） | 改用 `OpportunityLoseDialog` |

### 2.3 推进阶段确认弹窗规范

**键盘交互**:
- `Enter`: 确认推进
- `Esc`: 取消操作
- `Tab`: 在"确认"和"取消"按钮间切换

**焦点管理**:
- 打开时焦点默认在"取消"按钮（安全优先，避免误操作）
- 不自动跳转到"确认"按钮

**视觉规范**:
- 标题: "推进阶段" 或 "设置起始阶段"
- 说明文字: 清晰说明当前阶段、目标阶段、赢率变化
- 按钮: 
  - 确认按钮使用主按钮样式
  - 取消按钮使用次要按钮样式
  - 非危险操作，无需使用危险色

**代码示例**:
```typescript
const confirmed = await confirmDialog(
  `确定将商机推进到「${nextStage.stage_name}」？赢率将从 ${currentStage.win_probability}% 变为 ${nextStage.win_probability}%`,
  '推进阶段',
  {
    confirmText: '确认推进',
    cancelText: '取消',
    defaultFocus: 'cancel' // 默认焦点在取消按钮
  }
)
```

---

## 三、组件接口设计

### 3.1 OpportunityWinDialog.vue

**用途**: 赢单表单弹窗，收集实际成交金额和日期

**Props**:
```typescript
interface Props {
  opportunityId: number | null    // 商机ID（null时不显示）
  open: boolean                   // 弹窗显示状态
}
```

**Emits**:
```typescript
interface Emits {
  (e: 'update:open', value: boolean): void  // 弹窗状态变化
  (e: 'success'): void                       // 操作成功
}
```

**内部状态**:
```typescript
const loading = ref(false)              // 加载商机详情
const submitting = ref(false)           // 提交中
const opportunity = ref<Opportunity | null>(null)
const form = reactive({
  actual_amount: 0,
  actual_closing_date: getTodayLocalDate()
})
```

**核心逻辑**:
1. 监听 `open` 变化，加载商机详情
2. 预填充预计金额
3. 表单校验（金额>0，日期必填）
4. 调用 `opportunityApi.markAsWon()` 提交
5. 成功后 emit('success')，刷新父组件列表

---

### 3.2 OpportunityLoseDialog.vue

**用途**: 输单表单弹窗，收集输单原因

**Props**:
```typescript
interface Props {
  opportunityId: number | null
  open: boolean
}
```

**Emits**:
```typescript
interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}
```

**内部状态**:
```typescript
const loading = ref(false)
const submitting = ref(false)
const opportunity = ref<Opportunity | null>(null)
const form = reactive({
  loss_reason: ''
})
```

**核心逻辑**:
1. 监听 `open` 变化，加载商机详情
2. 表单校验（输单原因 1-500 字符）
3. 调用 `opportunityApi.markAsLost()` 提交
4. 成功后 emit('success')，刷新父组件列表

---

## 四、列表页集成

### 4.1 Opportunities.vue 修改

**新增导入**:
```typescript
import OpportunityWinDialog from '@/components/dialogs/OpportunityWinDialog.vue'
import OpportunityLoseDialog from '@/components/dialogs/OpportunityLoseDialog.vue'
import { confirmDialog } from '@/utils/confirmDialog'
```

**新增状态**:
```typescript
// 赢单弹窗
const winDialogOpen = ref(false)
const selectedOpportunityIdForWin = ref<number | null>(null)

// 输单弹窗
const loseDialogOpen = ref(false)
const selectedOpportunityIdForLose = ref<number | null>(null)
```

**操作处理函数**:
```typescript
// 推进阶段（直接实现）
const handleAdvanceStage = async (record: Opportunity): void => {
  // 1. 获取可推进阶段
  // 2. 找到下一阶段或默认起始阶段
  // 3. confirmDialog 确认
  // 4. 调用 API 推进
  // 5. 刷新列表
}

// 赢单（打开弹窗）
const handleMarkAsWon = (record: Opportunity): void => {
  selectedOpportunityIdForWin.value = record.id
  winDialogOpen.value = true
}

// 输单（打开弹窗）
const handleMarkAsLost = (record: Opportunity): void => {
  selectedOpportunityIdForLose.value = record.id
  loseDialogOpen.value = true
}
```

---

## 五、详情页重构

### 5.1 OpportunityDetailContent.vue 修改

**移除内联弹窗逻辑**:
- 移除 `winForm`、`loseForm` 状态
- 移除内联 `<Dialog>` 模板代码（约 60 行）
- 保留 `winDialogOpen`、`loseDialogOpen` 状态

**改用新组件**:
```vue
<OpportunityWinDialog
  :opportunity-id="opportunity?.id ?? null"
  :open="winDialogOpen"
  @update:open="winDialogOpen = $event"
  @success="handleWinSuccess"
/>

<OpportunityLoseDialog
  :opportunity-id="opportunity?.id ?? null"
  :open="loseDialogOpen"
  @update:open="loseDialogOpen = $event"
  @success="handleLoseSuccess"
/>
```

---

## 六、无障碍与交互规范

### 6.1 焦点管理（遵循设计规范）

**弹窗打开**:
- 焦点自动进入弹窗，定位到第一个可交互元素（输入框）
- 使用 `autofocus` 或手动 `focus()` 实现

**弹窗关闭**:
- 焦点返回到启动弹窗的元素（列表页的操作按钮或详情页的操作按钮）
- 使用 `ref` 记录触发元素，关闭时调用 `focus()`

**代码示例**:
```typescript
// 弹窗打开时记录触发元素
const triggerElement = ref<HTMLElement | null>(null)

const handleMarkAsWon = (event: Event, record: Opportunity): void => {
  triggerElement.value = event.currentTarget as HTMLElement
  selectedOpportunityIdForWin.value = record.id
  winDialogOpen.value = true
}

// 弹窗关闭时恢复焦点
watch(winDialogOpen, (newOpen, oldOpen) => {
  if (!newOpen && oldOpen) {
    // 延迟确保 DOM 已更新
    setTimeout(() => {
      triggerElement.value?.focus()
    }, 100)
  }
})
```

---

### 6.2 键盘导航支持（遵循设计规范）

**基础导航**:
- `Tab` / `Shift+Tab`: 在弹窗内循环焦点
- `Esc`: 关闭弹窗（仅当未提交时）
- `Enter`: 在输入框时提交表单，在按钮时触发按钮

**焦点陷阱（Focus Trap）**:
```typescript
// 使用 @vueuse/integrations 的 useFocusTrap
import { useFocusTrap } from '@vueuse/integrations/useFocusTrap'

const dialogRef = ref<HTMLElement | null>(null)
const { activate, deactivate } = useFocusTrap(dialogRef)

watch(winDialogOpen, (newOpen) => {
  if (newOpen) {
    activate()
  } else {
    deactivate()
  }
})
```

---

### 6.3 表单标签与错误反馈（遵循表单页规范）

**标签位置**:
- 每个输入字段必须有可见标签（`<Label>`），位于输入框上方
- 标签简洁明确，必填字段使用红色星号 `*` 标记

**错误位置**:
- 错误信息显示在对应字段**正下方**，使用红色文字
- 不使用 toast 显示字段错误（toast 仅用于 API 错误）

**示例代码**:
```vue
<FormField name="actual_amount">
  <FormItem>
    <FormLabel>
      实际成交金额 <span class="text-destructive">*</span>
    </FormLabel>
    <FormControl>
      <Input type="number" placeholder="请输入金额" />
    </FormControl>
    <FormMessage /> <!-- 错误信息显示在这里 -->
  </FormItem>
</FormField>
```

---

### 6.4 禁用状态视觉（遵循无障碍规范）

**禁用状态**:
- 不透明度: `0.38`（`$wolf-disabled-opacity-v2`）
- 光标: `not-allowed`（`$wolf-cursor-disabled-v2`）
- 语义属性: `disabled` 或 `aria-disabled="true"`

**示例代码**:
```vue
<Button
  type="submit"
  :disabled="submitting || loading"
  class="disabled:opacity-38 disabled:cursor-not-allowed"
>
  {{ submitting ? '提交中...' : '确认' }}
</Button>
```

---

### 6.5 提交期间的交互边界（遵循模态框规范）

**禁止关闭**:
- 提交中（`submitting=true`）时，禁用所有关闭方式：
  - 禁用取消按钮
  - 禁用遮罩点击关闭
  - 禁用 Esc 键关闭
  - 禁用右上角关闭按钮

**未保存内容提示**:
- 用户填写后点击取消/关闭，显示确认对话框：
  ```
  "您有未保存的更改，确定要关闭吗？"
  [继续编辑] [放弃更改]
  ```

**代码实现**:
```typescript
const isDirty = ref(false) // 表单是否被修改

const handleCancel = (): void => {
  if (isDirty.value) {
    showConfirmDialog.value = true
  } else {
    winDialogOpen.value = false
  }
}
```

---

## 七、动效与响应式规范

### 7.1 动画时长（遵循动效规范）

**标准时长**: 150-300ms

| 动画类型 | 时长 | 缓动函数 |
|---------|------|---------|
| 弹窗进入 | 200ms | `ease-out` |
| 弹窗退出 | 150ms | `ease-in` |
| 字段错误显示 | 150ms | `ease-out` |
| 按钮状态变化 | 150ms | `ease-out` |

**减少动效支持**:
```scss
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

### 7.2 响应式适配（遵循响应式规范）

**窄视口（< 768px）**:
- 弹窗转为全屏或底部抽屉
- 表单字段改为堆叠布局（标签和输入框各占一行）
- 按钮改为全宽堆叠排列

**代码示例**:
```vue
<DialogContent class="sm:max-w-[425px] max-w-full">
  <div class="grid gap-4 py-4">
    <!-- 字段使用 flex-col 堆叠 -->
    <FormField name="actual_amount">
      <FormItem class="flex flex-col space-y-2">
        <FormLabel>实际成交金额 *</FormLabel>
        <FormControl>
          <Input type="number" class="w-full" />
        </FormControl>
        <FormMessage />
      </FormItem>
    </FormField>
  </div>
  
  <!-- 按钮全宽堆叠 -->
  <DialogFooter class="flex-col gap-2 sm:flex-row">
    <Button variant="outline" class="w-full sm:w-auto">取消</Button>
    <Button type="submit" class="w-full sm:w-auto">确认</Button>
  </DialogFooter>
</DialogContent>
```

---

## 八、错误处理与加载状态

### 8.1 API 调用错误
- 所有 API 调用使用 `handleApiError(error, '操作名称')` 统一处理
- 显示用户友好的错误信息

### 8.2 表单校验
- **赢单**: 金额>0，日期必填
- **输单**: 输单原因 1-500 字符
- 前端校验失败时显示字段下方错误信息

### 8.3 加载状态
- 弹窗打开时加载商机详情，显示骨架屏或加载指示器
- 加载失败时显示错误提示并自动关闭弹窗
- 提交时按钮显示"提交中..."文案并禁用

### 8.4 边界情况
- **新商机（无当前阶段）**: 自动选择默认起始阶段
- **已是最终阶段**: 提示用户无法继续推进
- **未配置默认起始阶段**: 提示配置错误

---

## 七、测试要点

### 7.1 OpportunityWinDialog
1. 弹窗打开时加载商机详情
2. 表单预填充预计金额
3. 表单校验正常工作
4. 提交成功后关闭弹窗并刷新列表
5. 提交失败时显示错误信息

### 7.2 OpportunityLoseDialog
1. 弹窗打开时加载商机详情
2. 表单校验正常工作
3. 提交成功后关闭弹窗并刷新列表
4. 提交失败时显示错误信息

### 7.3 列表页操作
1. 推进阶段确认弹窗显示正确
2. 新商机设置起始阶段正常
3. 已是最终阶段时提示
4. 赢单/输单弹窗正确打开
5. 操作成功后列表自动刷新

---

## 八、实施步骤

### 阶段 1: 创建弹窗组件
1. 创建 `OpportunityWinDialog.vue`
2. 创建 `OpportunityLoseDialog.vue`

### 阶段 2: 重构详情页
1. 修改 `OpportunityDetailContent.vue`
2. 移除内联弹窗逻辑
3. 集成新弹窗组件
4. 测试详情页功能

### 阶段 3: 集成列表页
1. 修改 `Opportunities.vue`
2. 实现推进阶段逻辑
3. 集成赢单/输单弹窗
4. 测试列表页功能

### 阶段 4: 验证和清理
1. 运行类型检查
2. 运行 lint 检查
3. 手动测试所有场景
4. 清理废弃代码

---

## 九、预期效果

### 用户体验提升
- ✅ 列表页可直接操作，无需跳转页面
- ✅ 操作流程简化，减少点击次数
- ✅ 详情页和列表页交互一致

### 代码质量提升
- ✅ 弹窗逻辑复用，避免重复代码
- ✅ 组件职责清晰，易于维护
- ✅ 符合 Vue 3 组件化最佳实践

### 维护成本降低
- ✅ 单一修改点（弹窗组件）
- ✅ 新增操作只需扩展组件
- ✅ 测试覆盖更集中

---

**设计完成日期**: 2026-07-16