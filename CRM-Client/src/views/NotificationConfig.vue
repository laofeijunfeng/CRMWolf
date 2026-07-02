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
              查看官方文档
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
      validator: (_rule, value: string, callback: (error?: Error) => void): void => {
        if (formData.feishu_webhook_enabled && value.length === 0) {
          callback(new Error('请输入 Webhook URL'))
        } else {
          callback()
        }
      },
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
const fetchConfig = async (): Promise<void> => {
  loading.value = true
  try {
    const response = await notificationConfigApi.getConfig()
    configInfo.value = response
    if (response !== null) {
      formData.feishu_webhook_enabled = response.feishu_webhook_enabled ?? false
      formData.feishu_webhook_url = response.feishu_webhook_url ?? ''
      formData.notification_group_name = response.notification_group_name ?? ''
    }
  } catch (error) {
    // 404 表示配置不存在，使用默认值
    const err = error as { response?: { status?: number } }
    if (err.response?.status !== 404) {
      showError(error, '获取通知配置')
    }
    // 使用默认值（表单初始值）
  } finally {
    loading.value = false
  }
}

// 保存配置
const handleSave = async (): Promise<void> => {
  if (formRef.value === undefined) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const response = await notificationConfigApi.updateConfig({
      notification_method: 'webhook',
      feishu_webhook_url: formData.feishu_webhook_url,
      feishu_webhook_enabled: formData.feishu_webhook_enabled,
      notification_group_name: formData.notification_group_name
    })

    configInfo.value = response
    showSuccess('保存', '通知配置')
    saving.value = false

    // 保存成功后询问是否测试
    if (formData.feishu_webhook_enabled && formData.feishu_webhook_url.length > 0) {
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
      }).catch(() => {
        // 用户取消
      })
    }
  } catch (error) {
    showError(error, '保存通知配置')
    saving.value = false
  }
}

// 测试通知
const handleTest = async (): Promise<void> => {
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
const copyWebhookExample = async (): Promise<void> => {
  try {
    await navigator.clipboard.writeText('https://open.feishu.cn/open-apis/bot/v2/hook/xxx')
    copySuccess.value = true
    setTimeout(() => {
      copySuccess.value = false
    }, 3000)
  } catch {
    // fallback - silently fail
  }
}

// 返回
const handleBack = (): void => {
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