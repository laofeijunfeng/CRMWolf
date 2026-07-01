# 飞书通知配置前端页面实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建飞书通知配置前端页面，支持 Webhook URL 配置、启用/禁用开关、一键测试功能。

**Architecture:** 三卡片布局（配置卡片 + 测试卡片 + 说明卡片），参照 AIConfig.vue 模式。启用开关联动下游字段禁用状态，测试按钮前置条件检查。

**Tech Stack:** Vue 3 Composition API, TypeScript, Element Plus, SCSS, Vite

## Global Constraints

- Design Token 唯一来源：`CRM-Client/src/styles/variables.scss`
- 禁止硬编码颜色、魔数间距
- 所有图标使用 Element Plus 图标组件，禁止 emoji
- TypeScript 四禁令：禁用 `any` `as any` `@ts-ignore` `!`
- 权限控制：使用 `canManageApprovalFlows` 变量
- API 响应格式遵循后端规范

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `CRM-Client/src/api/notificationConfig.ts` | 创建 | API 接口层：获取配置、更新配置、测试通知 |
| `CRM-Client/src/views/NotificationConfig.vue` | 创建 | 配置页面：三卡片布局、表单交互、测试功能 |
| `CRM-Client/src/router/index.ts` | 修改 | 添加 `/notification-config` 路由 |
| `CRM-Client/src/views/Settings.vue` | 修改 | 添加通知配置入口项 |

---

### Task 1: API 接口层

**Files:**
- Create: `CRM-Client/src/api/notificationConfig.ts`

**Interfaces:**
- Produces: `notificationConfigApi` 对象，包含 `getConfig`、`updateConfig`、`testNotification` 方法
- Produces: `NotificationConfigResponse`、`NotificationConfigUpdate`、`NotificationTestResponse` 类型

- [ ] **Step 1: 创建 API 文件**

```typescript
/**
 * 通知配置 API
 */
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
    return request.get<unknown, { data: NotificationConfigResponse | null }>('/v1/system/configs/notification')
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
    return request.post<unknown, NotificationTestResponse>('/v1/system/configs/notification/test')
  }
}
```

- [ ] **Step 2: 验证 TypeScript 类型检查**

Run: `cd CRM-Client && npm run type-check`
Expected: 无类型错误

- [ ] **Step 3: 提交 API 文件**

```bash
git add CRM-Client/src/api/notificationConfig.ts
git commit -m "feat(api): add notification config API layer"
```

---

### Task 2: 路由配置

**Files:**
- Modify: `CRM-Client/src/router/index.ts` (在 children 数组中添加路由)

**Interfaces:**
- Consumes: 无
- Produces: `/notification-config` 路由，指向 `NotificationConfig.vue`

- [ ] **Step 1: 添加路由配置**

在 `CRM-Client/src/router/index.ts` 的 children 数组中，在 `ai-config` 路由之后添加：

```typescript
{
  path: 'notification-config',
  name: 'NotificationConfig',
  component: () => import('@/views/NotificationConfig.vue'),
  meta: { requiresAuth: true }
}
```

- [ ] **Step 2: 验证路由配置**

Run: `cd CRM-Client && npm run type-check`
Expected: 无类型错误

- [ ] **Step 3: 提交路由配置**

```bash
git add CRM-Client/src/router/index.ts
git commit -m "feat(router): add notification-config route"
```

---

### Task 3: Settings 入口项

**Files:**
- Modify: `CRM-Client/src/views/Settings.vue`

**Interfaces:**
- Consumes: `canManageApprovalFlows` 计算属性（已存在）
- Produces: 通知配置入口项，点击跳转到 `/notification-config`

- [ ] **Step 1: 导入 Bell 图标**

在 `<script setup>` 部分的图标导入行中添加 `Bell`：

```typescript
// 修改此行（约第 177 行）
import { SwitchButton, User, UserFilled, Document, ShoppingCart, Cpu, ArrowRight, Key, Bell } from '@element-plus/icons-vue'
```

- [ ] **Step 2: 添加跳转方法**

在 `goToAIConfig` 方法之后添加：

```typescript
const goToNotificationConfig = () => router.push('/notification-config')
```

- [ ] **Step 3: 添加入口项**

在模板的 `settings-list` 中，在"AI 配置"入口项之后添加：

```vue
<!-- 在 <div v-if="canManageAIConfig" class="settings-item" @click="goToAIConfig"> 之后添加 -->
<div v-if="canManageApprovalFlows" class="settings-item" @click="goToNotificationConfig">
  <el-icon class="item-icon"><Bell /></el-icon>
  <span class="item-text">通知配置</span>
  <span class="item-desc">配置飞书群聊通知</span>
  <el-icon class="item-arrow"><ArrowRight /></el-icon>
</div>
```

- [ ] **Step 4: 验证修改**

Run: `cd CRM-Client && npm run type-check`
Expected: 无类型错误

- [ ] **Step 5: 提交 Settings 修改**

```bash
git add CRM-Client/src/views/Settings.vue
git commit -m "feat(settings): add notification config entry"
```

---

### Task 4: NotificationConfig.vue 页面组件

**Files:**
- Create: `CRM-Client/src/views/NotificationConfig.vue`

**Interfaces:**
- Consumes: `notificationConfigApi` from Task 1
- Consumes: `showError`, `showSuccess` from `@/utils/errorMessages`
- Consumes: Design Token from `@/styles/variables.scss`

- [ ] **Step 1: 创建 NotificationConfig.vue - Template 部分**

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
              示例 URL 已复制到剪贴板
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
```

- [ ] **Step 2: 创建 NotificationConfig.vue - Script 部分**

```vue
<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
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
    ElMessage.success('示例 URL 已复制')
    setTimeout(() => {
      copySuccess.value = false
    }, 3000)
  } catch {
    ElMessage.warning('复制失败，请手动复制')
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
```

- [ ] **Step 3: 创建 NotificationConfig.vue - Style 部分**

```vue
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

- [ ] **Step 4: 验证 TypeScript 类型检查**

Run: `cd CRM-Client && npm run type-check`
Expected: 无类型错误

- [ ] **Step 5: 验证 ESLint**

Run: `cd CRM-Client && npm run lint`
Expected: 无 lint 错误（或修复可忽略的 warning）

- [ ] **Step 6: 提交 NotificationConfig.vue**

```bash
git add CRM-Client/src/views/NotificationConfig.vue
git commit -m "feat: add notification config page with webhook setup"
```

---

### Task 5: 集成测试与最终提交

**Files:**
- 无新增文件

**Interfaces:**
- Consumes: 所有 Task 1-4 的产出

- [ ] **Step 1: 启动开发服务器验证页面**

Run: `cd CRM-Client && npm run dev`
Expected: 开发服务器启动成功

- [ ] **Step 2: 手动验证页面功能**

验证清单：
1. 访问 `/settings`，确认"通知配置"入口显示
2. 点击入口，跳转到 `/notification-config`
3. 页面加载，获取现有配置
4. 启用开关关闭时，URL 和群名称字段禁用
5. 启用开关开启时，字段可编辑
6. 测试按钮禁用时显示禁用原因
7. 填写 URL 后，测试按钮可点击
8. 点击测试，显示 loading 状态
9. 测试成功，显示成功提示
10. 点击保存，弹出测试确认框

- [ ] **Step 3: 最终提交（如有遗漏修复）**

```bash
git status
# 如有未提交文件，逐一提交
git add -A
git commit -m "feat: complete notification config feature"
```

---

## Self-Review

**1. Spec coverage check:**

| 规范要求 | 实现任务 |
|----------|----------|
| API 接口层 | Task 1 |
| 路由配置 | Task 2 |
| Settings 入口 | Task 3 |
| 配置页面 | Task 4 |
| 启用开关联动 | Task 4 (template + computed) |
| 测试前置条件 | Task 4 (canTest + testDisabledReason) |
| 测试结果展示 | Task 4 (testResult + el-alert) |
| 保存后询问 | Task 4 (ElMessageBox.confirm) |
| 步骤式引导 | Task 4 (guide-steps) |
| URL 复制功能 | Task 4 (copyWebhookExample) |

✅ 所有规范要求已覆盖

**2. Placeholder scan:**
- 无 "TBD"、"TODO"、"implement later" 等占位符
- 所有代码步骤包含完整实现

**3. Type consistency check:**
- `NotificationConfigResponse` 在 Task 1 定义，Task 4 使用
- `notificationConfigApi` 在 Task 1 导出，Task 4 导入
- 类型定义一致，无命名冲突

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-01-notification-config-implementation.md`.**