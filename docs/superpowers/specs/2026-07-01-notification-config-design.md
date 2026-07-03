# 飞书通知配置前端页面设计规范

**日期**：2026-07-01
**状态**：待实现
**范围**：前端通知配置页面开发

---

## 一、背景

### 现状
- 后端已完整实现飞书通知功能（`CRM-Server/app/services/feishu.py`）
- 系统配置 API 已就绪（`GET/PUT/POST /v1/system/configs/notification`）
- 审批流程已集成通知调用

### 问题
- 前端缺少通知配置入口，用户无法配置飞书 Webhook URL
- Settings.vue 系统管理入口中没有通知配置项

### 目标
- 提供飞书群聊通知配置页面
- 支持 Webhook URL 配置、启用/禁用开关、通知群名称
- 提供一键测试功能验证配置正确性

---

## 二、设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 通知方式 | 仅 Webhook | API 方式后端标记为预留，先实现核心功能 |
| 页面入口 | 独立页面 `/notification-config` | 遵循现有模式（AIConfig、审批流程） |
| 权限控制 | 与审批流程一致 | 复用 `canManageApprovalFlows`，无需后端改动 |
| 测试交互 | 一键测试 | 预设测试消息，验证 Webhook URL 正确性 |

---

## 三、页面结构

```
NotificationConfig.vue
├── 页面头部（sticky header）
│   ├── 返回按钮
│   └── 页面标题 "通知配置"
│
├── 配置卡片
│   ├── 卡片标题 "飞书群聊通知"
│   ├── 保存按钮（右上角）
│   └── 表单
│       ├── 启用开关
│       ├── Webhook URL 输入框
│       └── 通知群名称输入框
│
├── 测试卡片
│   ├── 卡片标题 "通知测试"
│   ├── 测试按钮（右上角 + tooltip 提示）
│   └── 测试结果显示区域
│
└── 说明卡片
    ├── 卡片标题 "配置说明"
    └── 步骤式引导（可复制示例 URL）
    └── Webhook 获取方式说明
    └── 官方文档链接
```

**布局风格**：完全参照 `AIConfig.vue` 的三卡片布局模式。

---

## 四、表单字段与交互设计

### 4.1 字段定义

| 字段 | 类型 | 标签 | 校验规则 | 说明 |
|------|------|------|----------|------|
| `feishu_webhook_enabled` | Switch | 启用通知 | 无 | 开启/关闭飞书通知 |
| `feishu_webhook_url` | Input | Webhook URL | URL 格式校验 | 飞书群聊机器人 Webhook 地址 |
| `notification_group_name` | Input | 通知群名称 | 无（可选） | 用于标识通知目标群 |

### 4.2 启用开关联动设计（核心交互）

**设计原则**：启用开关关闭时，下游字段应显示禁用状态，避免用户困惑"关闭了为什么还要填"。

**详细交互规则**：

| 启用状态 | Webhook URL 字段 | 群名称字段 | 提示信息 |
|----------|------------------|------------|----------|
| **关闭** | 禁用（灰色背景）+ 可见 | 禁用（灰色背景）+ 可见 | 字段下方显示黄色提示："请先开启「启用通知」开关" |
| **开启** | 可编辑 | 可编辑 | 无提示 |

**视觉表现**：

```scss
// 禁用状态下的输入框
.input-disabled {
  background: $wolf-bg-hover;           // #F0F0ED 灰色背景
  cursor: not-allowed;
  opacity: 0.6;
}

// 警告提示（黄色）
.form-tip--warning {
  color: $wolf-warning-text;            // #FF7D00
  font-size: $wolf-font-size-caption;   // 12px
  margin-top: $wolf-space-xs;           // 4px
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  
  // 使用图标而非 emoji
  .icon {
    width: 14px;
    height: 14px;
    fill: $wolf-warning-text;
  }
}
```

**Vue 实现示例**：

```vue
<el-form-item label="启用通知">
  <el-switch 
    v-model="formData.feishu_webhook_enabled"
    @change="handleEnableChange"
  />
</el-form-item>

<el-form-item label="Webhook URL" prop="feishu_webhook_url">
  <el-input
    v-model="formData.feishu_webhook_url"
    :disabled="!formData.feishu_webhook_enabled"
    placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
  />
  <div v-if="!formData.feishu_webhook_enabled" class="form-tip form-tip--warning">
    <el-icon><Warning /></el-icon>
    <span>请先开启「启用通知」开关</span>
  </div>
</el-form-item>

<el-form-item label="通知群名称">
  <el-input
    v-model="formData.notification_group_name"
    :disabled="!formData.feishu_webhook_enabled"
    placeholder="如：审批通知群"
  />
  <div v-if="!formData.feishu_webhook_enabled" class="form-tip form-tip--warning">
    <el-icon><Warning /></el-icon>
    <span>请先开启「启用通知」开关</span>
  </div>
</el-form-item>
```

**状态切换逻辑**：

```typescript
const handleEnableChange = (enabled: boolean) => {
  if (!enabled) {
    // 关闭时：不清空已填数据，但字段变为禁用状态
    // 数据保留，用户重新开启后可继续使用
  } else {
    // 开启时：字段变为可编辑
    // 如果之前有数据，自动恢复
  }
}
```

### 4.3 Webhook URL 输入校验

**校验规则**：

| 规则 | 触发时机 | 错误提示 |
|------|----------|----------|
| 必填（启用时） | blur + submit | "请输入 Webhook URL" |
| URL 格式 | blur | "请输入有效的 URL 地址" |
| 飞书格式匹配（软校验） | blur | "URL 格式应为 https://open.feishu.cn/open-apis/bot/v2/hook/xxx" |

**校验实现**：

```typescript
const formRules: FormRules = {
  feishu_webhook_url: [
    { 
      required: computed(() => formData.feishu_webhook_enabled), 
      message: '请输入 Webhook URL', 
      trigger: 'blur' 
    },
    { 
      type: 'url', 
      message: '请输入有效的 URL 地址', 
      trigger: 'blur' 
    },
    {
      // 软校验：不阻止提交，但给出建议
      validator: (rule, value, callback) => {
        if (value && !value.includes('open.feishu.cn/open-apis/bot/v2/hook')) {
          callback(new Error('URL 格式应为飞书群聊机器人 Webhook'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}
```

**Placeholder 提示**：

```vue
<el-input
  placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
/>
<div class="form-tip">
  从飞书群聊机器人设置中获取
</div>
```

---

## 五、测试功能交互设计

### 5.1 测试按钮前置条件检查（核心交互）

**设计原则**：按钮禁用时必须告知用户原因，用户应明确知道下一步该做什么。

**前置条件矩阵**：

| 条件 | 状态 | 按钮状态 | Tooltip 内容 |
|------|------|----------|--------------|
| 启用开关关闭 | ❌ | 禁用 | "请先开启「启用通知」开关" |
| Webhook URL 为空 | ❌ | 禁用 | "请先填写 Webhook URL" |
| Webhook URL 格式错误 | ❌ | 禁用 | "Webhook URL 格式不正确" |
| 启用开关开启 + URL 有效 | ✅ | 可点击 | 无 tooltip |

**视觉表现**：

```scss
.test-btn--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

// 禁用提示条（当条件不满足时显示在按钮上方）
.test-prerequisite-warning {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-sm $wolf-space-md;
  background: $wolf-warning-bg;        // #FFF7E8
  border-radius: $wolf-radius-md;
  font-size: $wolf-font-size-caption;
  color: $wolf-warning-text;
  margin-bottom: $wolf-space-sm;
}
```

**Vue 实现示例**：

```vue
<!-- 禁用提示条（条件不满足时显示） -->
<div v-if="!canTest" class="test-prerequisite-warning">
  <el-icon><Warning /></el-icon>
  <span>{{ testDisabledReason }}</span>
</div>

<!-- 测试按钮（带 tooltip） -->
<el-tooltip 
  :content="testButtonTooltip" 
  :disabled="canTest"
  placement="top"
>
  <span> <!-- wrapper for tooltip on disabled button -->
    <el-button 
      type="primary"
      :disabled="!canTest"
      :loading="testing"
      @click="handleTest"
    >
      <el-icon><Promotion /></el-icon>
      测试通知
    </el-button>
  </span>
</el-tooltip>
```

**计算属性实现**：

```typescript
// 计算是否可测试
const canTest = computed(() => {
  return formData.feishu_webhook_enabled && 
         formData.feishu_webhook_url && 
         isValidWebhookUrl(formData.feishu_webhook_url)
})

// 计算禁用原因（用于显示提示）
const testDisabledReason = computed(() => {
  if (!formData.feishu_webhook_enabled) {
    return '请先开启「启用通知」开关'
  }
  if (!formData.feishu_webhook_url) {
    return '请先填写 Webhook URL'
  }
  if (!isValidWebhookUrl(formData.feishu_webhook_url)) {
    return 'Webhook URL 格式不正确'
  }
  return ''
})

// Tooltip 内容（与禁用原因一致）
const testButtonTooltip = computed(() => testDisabledReason.value)

// URL 格式校验函数
const isValidWebhookUrl = (url: string): boolean => {
  if (!url) return false
  try {
    new URL(url)
    return url.includes('open.feishu.cn')
  } catch {
    return false
  }
}
```

### 5.2 测试交互流程

```
用户点击"测试通知"按钮
    ↓
按钮变为 loading 状态（禁用 + 转圈图标）
    ↓
前端调用 POST /v1/system/configs/notification/test
    ↓
后端向 Webhook URL 发送预设消息
    ↓
返回 { success: boolean, message: string }
    ↓
按钮恢复常态
    ↓
前端显示结果（el-alert）
```

### 5.3 测试结果展示设计

**成功状态展示**：

```vue
<el-alert 
  v-if="testResult?.success" 
  type="success"
  :closable="false"
  show-icon
>
  <template #title>
    <span class="success-title">测试消息发送成功</span>
  </template>
  <div class="success-content">
    飞书群已收到测试消息，请检查群聊确认。
    <br />
    <span class="success-next-step">
      配置生效后，审批流程提交时会自动通知此群。
    </span>
  </div>
</el-alert>
```

**失败状态展示**：

```vue
<el-alert 
  v-if="testResult && !testResult.success" 
  type="error"
  :closable="false"
  show-icon
>
  <template #title>
    <span class="error-title">测试消息发送失败</span>
  </template>
  <div class="error-content">
    <div class="error-reason">{{ testResult.message }}</div>
    <div class="error-suggestions">
      <p>可能原因：</p>
      <ul>
        <li>Webhook URL 不正确或已失效</li>
        <li>飞书群聊机器人被移除</li>
        <li>网络连接问题</li>
      </ul>
      <p>建议检查后重新测试。</p>
    </div>
  </div>
</el-alert>
```

**样式定义**：

```scss
.success-title,
.error-title {
  font-weight: $wolf-font-weight-semibold;
}

.success-content,
.error-content {
  font-size: $wolf-font-size-caption;
  line-height: 1.6;
}

.success-next-step {
  color: $wolf-success-text;
  margin-top: $wolf-space-sm;
}

.error-reason {
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-sm;
}

.error-suggestions {
  color: $wolf-text-secondary;
  
  p {
    margin-bottom: $wolf-space-xs;
  }
  
  ul {
    margin: $wolf-space-xs 0;
    padding-left: $wolf-space-md;
    
    li {
      margin-bottom: $wolf-space-xs;
    }
  }
}
```

### 5.4 测试按钮 Loading 状态

**视觉表现**：

| 状态 | 按钮外观 | 文案 | 可点击 |
|------|----------|------|--------|
| 正常（可测试） | 蓝色填充 + 白色文字 | "测试通知" | ✅ |
| 正常（禁用） | 灰色填充 + 白色文字 | "测试通知" | ❌ |
| Loading | 蓝色填充 + 转圈图标 | "发送中..." | ❌ |

**实现**：

```vue
<el-button 
  :loading="testing"
  :disabled="!canTest"
>
  <template #icon>
    <el-icon v-if="!testing"><Promotion /></el-icon>
  </template>
  {{ testing ? '发送中...' : '测试通知' }}
</el-button>
```

---

## 六、保存与测试联动设计

### 6.1 保存成功后询问测试

**设计原则**：保存成功后，如果配置满足测试条件，主动询问用户是否立即验证，减少操作步骤。

**交互流程**：

```
用户点击"保存配置"
    ↓
保存成功 → Toast 提示 "通知配置已保存"
    ↓
检查是否满足测试条件（启用 + URL 有效）
    ↓
满足 → 弹出确认框："配置已保存，是否立即发送测试消息验证？"
    ↓
用户选择"测试" → 执行测试
用户选择"稍后" → 关闭确认框
```

**实现代码**：

```typescript
const handleSave = async () => {
  saving.value = true
  try {
    await notificationConfigApi.updateConfig({
      notification_method: 'webhook',
      feishu_webhook_url: formData.feishu_webhook_url,
      feishu_webhook_enabled: formData.feishu_webhook_enabled,
      notification_group_name: formData.notification_group_name
    })
    
    showSuccess('保存', '通知配置')
    saving.value = false
    
    // 保存成功后询问是否测试
    if (formData.feishu_webhook_enabled && formData.feishu_webhook_url) {
      ElMessageBox.confirm(
        '配置已保存，是否立即发送测试消息验证配置是否正确？',
        '验证配置',
        {
          confirmButtonText: '发送测试',
          cancelButtonText: '稍后验证',
          type: 'info'
        }
      ).then(() => {
        handleTest()
      }).catch(() => {})
    }
  } catch (error) {
    showError(error, '保存通知配置')
    saving.value = false
  }
}
```

### 6.2 未保存提示

**场景**：用户修改配置后未保存，点击测试按钮。

**处理方式**：

| 方案 | 说明 | 推荐 |
|------|------|------|
| A. 直接测试 | 测试使用当前输入值（未保存到后端） | ✅ 推荐 |
| B. 提示保存 | 弹出提示"请先保存配置再测试" | ❌ 增加操作步骤 |

**推荐方案 A 理由**：
- 测试目的是验证 URL 正确性，无需先保存
- 用户可能想先测试确认 URL 有效后再保存
- 减少操作步骤，提升效率

---

## 七、首次配置引导设计

### 7.1 步骤式引导

**设计原则**：新用户首次配置时，应有清晰的步骤引导，降低学习成本。

**视觉设计**：

```
┌─────────────────────────────────────────────┐
│ 配置说明                                     │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────┐  1. 在飞书群聊中添加机器人          │
│  │  1  │     → 查看官方文档                  │
│  └─────┐                                    │
│        │  2. 复制 Webhook URL               │
│  ┌─────┐     [可点击复制的示例 URL]          │
│  │  2  │                                    │
│  └─────┐                                    │
│        │  3. 粘贴到上方输入框，点击测试       │
│  ┌─────┐                                    │
│  │  3  │                                    │
│  └─────┘                                    │
│                                             │
│  ─────────────────────────────────────────  │
│                                             │
│  官方文档：                                  │
│  • 飞书群聊机器人配置指南                    │
│  • 如何获取 Webhook URL                     │
│                                             │
└─────────────────────────────────────────────┘
```

**Vue 实现**：

```vue
<el-card class="info-card">
  <template #header>
    <span>配置说明</span>
  </template>
  
  <div class="guide-steps">
    <!-- 步骤 1 -->
    <div class="guide-step">
      <div class="step-number">1</div>
      <div class="step-content">
        <div class="step-title">在飞书群聊中添加机器人</div>
        <a 
          href="https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN" 
          target="_blank"
          class="step-link"
        >
          查看官方文档 →
        </a>
      </div>
    </div>
    
    <!-- 步骤 2 -->
    <div class="guide-step">
      <div class="step-number">2</div>
      <div class="step-content">
        <div class="step-title">复制 Webhook URL</div>
        <div class="copy-example" @click="copyWebhookExample">
          <span class="example-url">https://open.feishu.cn/open-apis/bot/v2/hook/xxx</span>
          <el-icon class="copy-icon"><CopyDocument /></el-icon>
        </div>
        <div v-if="copySuccess" class="copy-success-tip">
          ✓ 示例 URL 已复制到剪贴板
        </div>
      </div>
    </div>
    
    <!-- 步骤 3 -->
    <div class="guide-step">
      <div class="step-number">3</div>
      <div class="step-content">
        <div class="step-title">粘贴到上方输入框，点击测试</div>
        <div class="step-tip">测试成功后保存配置即可</div>
      </div>
    </div>
  </div>
  
  <!-- 官方文档链接 -->
  <div class="doc-links">
    <div class="doc-title">官方文档：</div>
    <ul class="doc-list">
      <li>
        <a href="https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN" target="_blank">
          飞书群聊机器人配置指南
        </a>
      </li>
      <li>
        <a href="https://open.feishu.cn/document/ukTMukTMukTM/uUjN14yIdjL14iTMykTN" target="_blank">
          如何获取 Webhook URL
        </a>
      </li>
    </ul>
  </div>
</el-card>
```

**样式定义**：

```scss
.guide-steps {
  margin-bottom: $wolf-space-lg;
}

.guide-step {
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-md;
  margin-bottom: $wolf-space-md;
}

.step-number {
  width: 24px;
  height: 24px;
  border-radius: $wolf-radius-full;
  background: $wolf-primary;
  color: $wolf-text-inverse;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-semibold;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-content {
  flex: 1;
}

.step-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-xs;
}

.step-link {
  font-size: $wolf-font-size-caption;
  color: $wolf-primary;
  text-decoration: none;
  
  &:hover {
    text-decoration: underline;
  }
}

.step-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

// 可复制示例
.copy-example {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs;
  padding: $wolf-space-xs $wolf-space-sm;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-sm;
  cursor: pointer;
  transition: background 0.2s;
  
  &:hover {
    background: $wolf-primary-light;
  }
}

.example-url {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-secondary;
  font-family: monospace;
}

.copy-icon {
  width: 14px;
  height: 14px;
  color: $wolf-text-tertiary;
}

.copy-success-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-success-text;
  margin-top: $wolf-space-xs;
}

// 文档链接区
.doc-links {
  padding-top: $wolf-space-md;
  border-top: 1px solid $wolf-border-light;
}

.doc-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-sm;
}

.doc-list {
  list-style: none;
  padding: 0;
  margin: 0;
  
  li {
    margin-bottom: $wolf-space-sm;
  }
  
  a {
    font-size: $wolf-font-size-caption;
    color: $wolf-primary;
    text-decoration: none;
    
    &:hover {
      text-decoration: underline;
    }
  }
}
```

### 7.2 复制功能实现

```typescript
const copySuccess = ref(false)

const copyWebhookExample = async () => {
  try {
    await navigator.clipboard.writeText('https://open.feishu.cn/open-apis/bot/v2/hook/xxx')
    copySuccess.value = true
    ElMessage.success('示例 URL 已复制')
    
    // 3秒后隐藏提示
    setTimeout(() => {
      copySuccess.value = false
    }, 3000)
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}
```

---

## 八、API 层设计

**文件**：`CRM-Client/src/api/notificationConfig.ts`

```typescript
import request from '@/utils/request'

export interface NotificationConfigResponse {
  id: number
  team_id: number
  notification_method: string
  feishu_webhook_url: string | null
  feishu_webhook_enabled: boolean | null
  notification_group_name: string | null
  created_time: string
  updated_time: string
}

export interface NotificationConfigUpdate {
  notification_method?: string
  feishu_webhook_url?: string
  feishu_webhook_enabled?: boolean
  notification_group_name?: string
}

export interface NotificationTestResponse {
  success: boolean
  message: string
}

export const notificationConfigApi = {
  /**
   * 获取通知配置
   */
  getConfig: () => {
    return request.get<any, { data: NotificationConfigResponse | null }>('/v1/system/configs/notification')
  },
  
  /**
   * 更新通知配置
   */
  updateConfig: (data: NotificationConfigUpdate) => {
    return request.put<NotificationConfigUpdate, { data: NotificationConfigResponse }>('/v1/system/configs/notification', data)
  },
  
  /**
   * 测试通知发送
   */
  testNotification: () => {
    return request.post<any, NotificationTestResponse>('/v1/system/configs/notification/test')
  }
}
```

---

## 九、路由和入口

### 9.1 路由添加

**文件**：`CRM-Client/src/router/index.ts`

```typescript
{
  path: 'notification-config',
  name: 'NotificationConfig',
  component: () => import('@/views/NotificationConfig.vue'),
  meta: { requiresAuth: true }
}
```

### 9.2 Settings.vue 入口

**位置**：在"审批流程"入口项之后添加

```vue
<div v-if="canManageApprovalFlows" class="settings-item" @click="goToNotificationConfig">
  <el-icon class="item-icon"><Bell /></el-icon>
  <span class="item-text">通知配置</span>
  <span class="item-desc">配置飞书群聊通知</span>
  <el-icon class="item-arrow"><ArrowRight /></el-icon>
</div>
```

**新增导入和方法**：

```typescript
import { Bell } from '@element-plus/icons-vue'

const goToNotificationConfig = () => router.push('/notification-config')
```

**权限**：使用现有 `canManageApprovalFlows` 变量。

---

## 十、完整 Vue 组件实现示例

```vue
<template>
  <div class="notification-config-container">
    <!-- 页面头部（sticky） -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="page-title">通知配置</h1>
      </div>
    </div>

    <!-- 配置卡片 -->
    <el-card class="config-card" v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>飞书群聊通知</span>
          <el-button 
            type="primary" 
            size="small" 
            class="wolf-btn wolf-btn--primary-sm"
            @click="handleSave" 
            :loading="saving"
          >
            <el-icon><Check /></el-icon>
            保存配置
          </el-button>
        </div>
      </template>

      <el-form ref="formRef" :model="formData" :rules="formRules" label-width="120px">
        <el-form-item label="启用通知">
          <el-switch 
            v-model="formData.feishu_webhook_enabled"
            active-text="开启"
            inactive-text="关闭"
          />
          <div class="form-tip">
            开启后，审批流程提交时会自动发送通知到飞书群
          </div>
        </el-form-item>

        <el-form-item label="Webhook URL" prop="feishu_webhook_url">
          <el-input
            v-model="formData.feishu_webhook_url"
            :disabled="!formData.feishu_webhook_enabled"
            placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
          />
          <div v-if="!formData.feishu_webhook_enabled" class="form-tip form-tip--warning">
            <el-icon><Warning /></el-icon>
            <span>请先开启「启用通知」开关</span>
          </div>
          <div v-else class="form-tip">
            从飞书群聊机器人设置中获取
          </div>
        </el-form-item>

        <el-form-item label="通知群名称">
          <el-input
            v-model="formData.notification_group_name"
            :disabled="!formData.feishu_webhook_enabled"
            placeholder="如：审批通知群"
          />
          <div v-if="!formData.feishu_webhook_enabled" class="form-tip form-tip--warning">
            <el-icon><Warning /></el-icon>
            <span>请先开启「启用通知」开关</span>
          </div>
          <div v-else class="form-tip">
            用于标识通知目标群（可选）
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 测试卡片 -->
    <el-card class="test-card">
      <template #header>
        <div class="card-header">
          <span>通知测试</span>
          <el-tooltip 
            :content="testButtonTooltip" 
            :disabled="canTest"
            placement="top"
          >
            <span>
              <el-button 
                type="primary"
                size="small"
                class="wolf-btn wolf-btn--primary-sm"
                :disabled="!canTest"
                :loading="testing"
                @click="handleTest"
              >
                <el-icon><Promotion /></el-icon>
                {{ testing ? '发送中...' : '测试通知' }}
              </el-button>
            </span>
          </el-tooltip>
        </div>
      </template>

      <!-- 前置条件提示 -->
      <div v-if="!canTest" class="test-prerequisite-warning">
        <el-icon><Warning /></el-icon>
        <span>{{ testDisabledReason }}</span>
      </div>

      <!-- 测试结果 -->
      <div v-if="testResult" class="test-result">
        <el-alert 
          :type="testResult.success ? 'success' : 'error'"
          :closable="false"
          show-icon
        >
          <template #title>
            {{ testResult.success ? '测试消息发送成功' : '测试消息发送失败' }}
          </template>
          <div v-if="testResult.success" class="success-content">
            飞书群已收到测试消息，请检查群聊确认。
            <br />
            <span class="success-next-step">
              配置生效后，审批流程提交时会自动通知此群。
            </span>
          </div>
          <div v-else class="error-content">
            <div class="error-reason">{{ testResult.message }}</div>
            <div class="error-suggestions">
              <p>可能原因：</p>
              <ul>
                <li>Webhook URL 不正确或已失效</li>
                <li>飞书群聊机器人被移除</li>
                <li>网络连接问题</li>
              </ul>
            </div>
          </div>
        </el-alert>
      </div>
    </el-card>

    <!-- 说明卡片 -->
    <el-card class="info-card">
      <template #header>
        <span>配置说明</span>
      </template>

      <div class="guide-steps">
        <div class="guide-step">
          <div class="step-number">1</div>
          <div class="step-content">
            <div class="step-title">在飞书群聊中添加机器人</div>
            <a 
              href="https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN" 
              target="_blank"
              class="step-link"
            >
              查看官方文档 →
            </a>
          </div>
        </div>

        <div class="guide-step">
          <div class="step-number">2</div>
          <div class="step-content">
            <div class="step-title">复制 Webhook URL</div>
            <div class="copy-example" @click="copyWebhookExample">
              <span class="example-url">https://open.feishu.cn/open-apis/bot/v2/hook/xxx</span>
              <el-icon class="copy-icon"><CopyDocument /></el-icon>
            </div>
            <div v-if="copySuccess" class="copy-success-tip">
              ✓ 示例 URL 已复制到剪贴板
            </div>
          </div>
        </div>

        <div class="guide-step">
          <div class="step-number">3</div>
          <div class="step-content">
            <div class="step-title">粘贴到上方输入框，点击测试</div>
            <div class="step-tip">测试成功后保存配置即可</div>
          </div>
        </div>
      </div>

      <div class="doc-links">
        <div class="doc-title">官方文档：</div>
        <ul class="doc-list">
          <li>
            <a href="https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN" target="_blank">
              飞书群聊机器人配置指南
            </a>
          </li>
          <li>
            <a href="https://open.feishu.cn/document/ukTMukTMukTM/uUjN14yIdjL14iTMykTN" target="_blank">
              如何获取 Webhook URL
            </a>
          </li>
        </ul>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import type { FormInstance, FormRules } from 'element-plus'
import { 
  ArrowLeft, Check, Promotion, Warning, CopyDocument 
} from '@element-plus/icons-vue'
import { notificationConfigApi, type NotificationConfigResponse } from '@/api/notificationConfig'

const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const formRef = ref<FormInstance>()
const configInfo = ref<NotificationConfigResponse | null>(null)
const testResult = ref<{ success: boolean; message: string } | null>(null)
const copySuccess = ref(false)

const formData = reactive({
  feishu_webhook_enabled: false,
  feishu_webhook_url: '',
  notification_group_name: ''
})

// 校验规则
const formRules: FormRules = {
  feishu_webhook_url: [
    { 
      required: computed(() => formData.feishu_webhook_enabled), 
      message: '请输入 Webhook URL', 
      trigger: 'blur' 
    },
    { 
      type: 'url', 
      message: '请输入有效的 URL 地址', 
      trigger: 'blur' 
    }
  ]
}

// 计算是否可测试
const canTest = computed(() => {
  return formData.feishu_webhook_enabled && 
         formData.feishu_webhook_url && 
         isValidWebhookUrl(formData.feishu_webhook_url)
})

// 计算禁用原因
const testDisabledReason = computed(() => {
  if (!formData.feishu_webhook_enabled) {
    return '请先开启「启用通知」开关'
  }
  if (!formData.feishu_webhook_url) {
    return '请先填写 Webhook URL'
  }
  if (!isValidWebhookUrl(formData.feishu_webhook_url)) {
    return 'Webhook URL 格式不正确'
  }
  return ''
})

// Tooltip 内容
const testButtonTooltip = computed(() => testDisabledReason.value)

// URL 校验函数
const isValidWebhookUrl = (url: string): boolean => {
  if (!url) return false
  try {
    new URL(url)
    return url.includes('open.feishu.cn')
  } catch {
    return false
  }
}

// 获取配置
const fetchConfig = async () => {
  loading.value = true
  try {
    const response = await notificationConfigApi.getConfig()
    configInfo.value = response.data
    if (response.data) {
      formData.feishu_webhook_enabled = response.data.feishu_webhook_enabled ?? false
      formData.feishu_webhook_url = response.data.feishu_webhook_url ?? ''
      formData.notification_group_name = response.data.notification_group_name ?? ''
    }
  } catch (error) {
    showError(error, '获取通知配置')
  } finally {
    loading.value = false
  }
}

// 保存配置
const handleSave = async () => {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    await notificationConfigApi.updateConfig({
      notification_method: 'webhook',
      feishu_webhook_url: formData.feishu_webhook_url,
      feishu_webhook_enabled: formData.feishu_webhook_enabled,
      notification_group_name: formData.notification_group_name
    })
    
    showSuccess('保存', '通知配置')
    saving.value = false
    
    // 保存成功后询问是否测试
    if (formData.feishu_webhook_enabled && formData.feishu_webhook_url) {
      ElMessageBox.confirm(
        '配置已保存，是否立即发送测试消息验证配置是否正确？',
        '验证配置',
        {
          confirmButtonText: '发送测试',
          cancelButtonText: '稍后验证',
          type: 'info'
        }
      ).then(() => {
        handleTest()
      }).catch(() => {})
    }
  } catch (error) {
    showError(error, '保存通知配置')
    saving.value = false
  }
}

// 测试通知
const handleTest = async () => {
  testing.value = true
  testResult.value = null

  try {
    const response = await notificationConfigApi.testNotification()
    testResult.value = response
    
    if (response.success) {
      showSuccess('测试', '通知发送')
    }
  } catch (error) {
    testResult.value = {
      success: false,
      message: '请求失败，请稍后重试'
    }
    showError(error, '测试通知')
  } finally {
    testing.value = false
  }
}

// 复制示例 URL
const copyWebhookExample = async () => {
  try {
    await navigator.clipboard.writeText('https://open.feishu.cn/open-apis/bot/v2/hook/xxx')
    copySuccess.value = true
    setTimeout(() => {
      copySuccess.value = false
    }, 3000)
  } catch {
    // fallback
  }
}

// 返回
const handleBack = () => {
  router.back()
}

onMounted(() => {
  fetchConfig()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.notification-config-container {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 页面头部
.page-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: $wolf-bg-card;
  border-bottom: 1px solid $wolf-border-default;
  height: $wolf-header-height;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 $wolf-page-padding;
}

.page-header-left {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.back-btn {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: $wolf-radius-md !important;
  background: transparent !important;
  border: none !important;

  &:hover {
    background: $wolf-bg-hover !important;
  }
}

.page-title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
}

// 卡片样式
.config-card,
.test-card,
.info-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  margin: $wolf-page-padding $wolf-page-padding $wolf-space-md;
  border: none;
}

.config-card :deep(.el-card__header),
.test-card :deep(.el-card__header),
.info-card :deep(.el-card__header) {
  padding: $wolf-card-padding;
  border-bottom: 1px solid $wolf-border-light;
}

.config-card :deep(.el-card__body),
.test-card :deep(.el-card__body),
.info-card :deep(.el-card__body) {
  padding: $wolf-card-padding;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

// 表单提示
.form-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-top: $wolf-space-xs;
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
}

.form-tip--warning {
  color: $wolf-warning-text;
  
  .el-icon {
    width: 14px;
    height: 14px;
  }
}

// 测试前置条件提示
.test-prerequisite-warning {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-sm $wolf-space-md;
  background: $wolf-warning-bg;
  border-radius: $wolf-radius-md;
  font-size: $wolf-font-size-caption;
  color: $wolf-warning-text;
  margin-bottom: $wolf-space-md;
  
  .el-icon {
    width: 16px;
    height: 16px;
  }
}

// 测试结果
.test-result {
  margin-top: $wolf-space-md;
}

.success-content,
.error-content {
  font-size: $wolf-font-size-caption;
  line-height: 1.6;
}

.success-next-step {
  color: $wolf-success-text;
  margin-top: $wolf-space-sm;
}

.error-reason {
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-sm;
}

.error-suggestions {
  color: $wolf-text-secondary;
  
  p {
    margin-bottom: $wolf-space-xs;
  }
  
  ul {
    margin: $wolf-space-xs 0;
    padding-left: $wolf-space-md;
  }
}

// 步骤引导
.guide-steps {
  margin-bottom: $wolf-space-lg;
}

.guide-step {
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-md;
  margin-bottom: $wolf-space-md;
}

.step-number {
  width: 24px;
  height: 24px;
  border-radius: $wolf-radius-full;
  background: $wolf-primary;
  color: $wolf-text-inverse;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-semibold;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-content {
  flex: 1;
}

.step-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-xs;
}

.step-link {
  font-size: $wolf-font-size-caption;
  color: $wolf-primary;
  text-decoration: none;
  
  &:hover {
    text-decoration: underline;
  }
}

.step-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

// 可复制示例
.copy-example {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs;
  padding: $wolf-space-xs $wolf-space-sm;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-sm;
  cursor: pointer;
  transition: background 0.2s;
  
  &:hover {
    background: rgba($wolf-primary, 0.1);
  }
}

.example-url {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-secondary;
  font-family: monospace;
}

.copy-icon {
  width: 14px;
  height: 14px;
  color: $wolf-text-tertiary;
}

.copy-success-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-success-text;
  margin-top: $wolf-space-xs;
}

// 文档链接
.doc-links {
  padding-top: $wolf-space-md;
  border-top: 1px solid $wolf-border-light;
}

.doc-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-sm;
}

.doc-list {
  list-style: none;
  padding: 0;
  margin: 0;
  
  li {
    margin-bottom: $wolf-space-sm;
  }
  
  a {
    font-size: $wolf-font-size-caption;
    color: $wolf-primary;
    text-decoration: none;
    
    &:hover {
      text-decoration: underline;
    }
  }
}

// 按钮样式
.wolf-btn--primary-sm {
  background: $wolf-primary !important;
  border-color: $wolf-primary !important;
  color: $wolf-text-inverse !important;
  font-weight: $wolf-font-weight-medium !important;
}

// 响应式
@media (max-width: 768px) {
  .config-card,
  .test-card,
  .info-card {
    margin-left: $wolf-space-md;
    margin-right: $wolf-space-md;
    margin-top: $wolf-space-md;
  }
}
</style>
```

---

## 十一、文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `CRM-Client/src/api/notificationConfig.ts` | 新建 | API 接口层 |
| `CRM-Client/src/views/NotificationConfig.vue` | 新建 | 配置页面 |
| `CRM-Client/src/router/index.ts` | 修改 | 添加路由 |
| `CRM-Client/src/views/Settings.vue` | 修改 | 添加入口项 |

---

## 十二、验收标准

### 功能验收

| 项目 | 验收要求 |
|------|----------|
| 配置获取 | 页面加载时正确获取并显示现有配置 |
| 配置保存 | 能修改并保存 Webhook URL、启用状态、群名称 |
| 启用联动 | 启用开关关闭时，其他字段禁用并显示警告提示 |
| 测试前置 | 测试按钮禁用时显示禁用原因 |
| 测试执行 | 能一键测试通知发送，正确显示成功/失败结果 |
| 保存后询问 | 保存成功后弹出测试确认框 |

### 交互验收

| 项目 | 验收要求 |
|------|----------|
| 步骤引导 | 首次配置有清晰的 3 步引导 |
| URL 复制 | 示例 URL 可一键复制到剪贴板 |
| 成功提示 | 测试成功后显示下一步操作提示 |
| 失败建议 | 测试失败后显示可能原因和解决方案 |

### UI 验收

| 项目 | 验收要求 |
|------|----------|
| 布局一致 | 页面布局与 AIConfig.vue 保持一致 |
| Design Token | 使用 variables.scss 变量，无硬编码颜色 |
| 禁用样式 | 禁用字段有灰色背景和警告提示 |
| 无 emoji | 所有图标使用 Element Plus 图标组件 |

### 权限验收

| 项目 | 验收要求 |
|------|----------|
| 入口显示 | 有 `approval:flow:create` 或 `approval:flow:edit` 权限的用户能看到入口 |
| 入口隐藏 | 无权限用户看不到入口项 |

---

## 十三、后续扩展（暂不实现）

- API 方式通知配置（需要飞书应用集成）
- 通知历史记录查看
- 通知频率限制配置
- 多群通知支持