<template>
  <Dialog
    v-model:open="visible"
    class="ai-lead-create-dialog"
    @close="handleClose"
  >
    <DialogContent class="dialog-content">
      <DialogHeader>
        <DialogTitle>AI 智能创建线索</DialogTitle>
      </DialogHeader>

      <!-- 阶段 1：输入 -->
      <div v-if="stage === 'input'" class="input-stage">
        <div class="input-hint" role="note">
          <Info class="hint-icon" aria-hidden="true" />
          <span>请用自然语言描述线索信息，AI 会自动识别并提取关键信息</span>
        </div>
        <TextareaField
          v-model="inputText"
          :rows="4"
          placeholder="例如：张三，13800138000，来自杭州的阿里巴巴，大概500人，网上注册来的，想做电商系统"
          :disabled="isParsing"
          aria-label="输入线索信息描述"
          control-class="input-textarea"
          @keydown.ctrl.enter="handleParse"
        />
        <div class="input-tip">按 Ctrl+Enter 快速识别</div>
        <div class="input-actions">
          <Button
            variant="outline"
            aria-label="取消创建"
            class="dialog-button"
            @click="handleClose"
          >
            取消
          </Button>
          <Button
            variant="default"
            :disabled="!inputText.trim() || isParsing"
            aria-label="智能识别线索信息"
            class="dialog-button"
            @click="handleParse"
          >
            <WandSparkles v-if="!isParsing" class="w-4 h-4 mr-2" aria-hidden="true" />
            <Loader2 v-else class="w-4 h-4 mr-2 animate-spin" aria-hidden="true" />
            智能识别
          </Button>
        </div>
      </div>

      <!-- 阶段 2：解析过程 -->
      <div v-if="stage === 'parsing'" class="parse-stage" role="status" aria-live="polite">
        <div class="status-message">
          <Loader2 class="w-5 h-5 animate-spin status-icon" aria-hidden="true" />
          <span>{{ statusMessage }}</span>
        </div>
        <div v-if="thinkingContent" class="thinking-section">
          <div class="thinking-header">AI 思考过程</div>
          <ScrollArea class="thinking-scroll">
            <div class="thinking-content">{{ thinkingContent }}</div>
          </ScrollArea>
        </div>
      </div>

      <!-- 阶段 3：预览确认 -->
      <div v-if="stage === 'preview'" class="preview-stage">
        <div class="preview-header" role="status">
          <CircleCheck class="preview-icon" aria-hidden="true" />
          <span>解析完成，请确认以下信息</span>
        </div>

        <!-- 缺失字段提示 -->
        <div
          v-if="parseResult?.lead_info?.missing_fields?.length"
          class="missing-fields-tip"
          role="alert"
          aria-describedby="missing-fields-description"
        >
          <AlertCircle class="warning-icon" aria-hidden="true" />
          <span id="missing-fields-description">
            以下必填信息未能识别，请手动补充：
            <strong class="missing-list">{{ formatMissingFields(parseResult.lead_info.missing_fields) }}</strong>
          </span>
        </div>

        <!-- 预览表单 -->
        <form class="preview-form" @submit.prevent="handleCreate">
          <div class="form-grid">
            <div class="form-item">
              <InputField
                id="preview-lead-name"
                v-model="previewForm.lead_name"
                label="线索名称"
                required
                placeholder="请输入线索名称"
                :error="!previewForm.lead_name ? '请输入线索名称' : ''"
              />
            </div>

            <div class="form-item">
              <SelectField
                id="preview-source"
                v-model="previewForm.source"
                label="线索来源"
                required
                :options="sourceOptions"
                placeholder="请选择来源"
                :error="!previewForm.source ? '请选择线索来源' : ''"
              />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-item">
              <InputField
                id="preview-city"
                v-model="previewForm.city"
                label="所在城市"
                required
                placeholder="请输入城市"
                :error="!previewForm.city ? '请输入所在城市' : ''"
              />
            </div>

            <div class="form-item">
              <SelectField
                id="preview-company-scale"
                v-model="previewForm.company_scale"
                label="公司规模"
                :options="companyScaleOptions"
                placeholder="请选择规模"
              />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-item">
              <InputField
                id="preview-contact-name"
                v-model="previewForm.contact_name"
                label="联系人姓名"
                required
                placeholder="请输入联系人姓名"
                :error="!previewForm.contact_name ? '请输入联系人姓名' : ''"
              />
            </div>

            <div class="form-item">
              <InputField
                id="preview-contact-phone"
                v-model="previewForm.contact_phone"
                label="联系电话"
                required
                type="tel"
                autocomplete="tel"
                placeholder="请输入联系电话"
                :error="!previewForm.contact_phone ? '请输入联系电话' : !isValidPhone(previewForm.contact_phone) ? '请输入正确的手机号码' : ''"
              />
            </div>
          </div>
        </form>

        <!-- 跟进信息 -->
        <div v-if="hasFollowUpInfo" class="follow-up-section">
          <div class="follow-up-header">
            <FileText class="follow-up-icon" aria-hidden="true" />
            <span>跟进信息（将自动创建跟进记录）</span>
          </div>
          <div class="follow-up-fields">
            <div v-if="parseResult?.follow_up_info?.content" class="follow-up-item">
              <span class="label">跟进内容：</span>
              <span class="value">{{ parseResult.follow_up_info.content }}</span>
            </div>
            <div v-if="parseResult?.follow_up_info?.next_action" class="follow-up-item">
              <span class="label">下一步动作：</span>
              <span class="value">{{ parseResult.follow_up_info.next_action }}</span>
            </div>
            <div v-if="parseResult?.follow_up_info?.next_follow_time" class="follow-up-item">
              <span class="label">下次跟进时间：</span>
              <span class="value">{{ parseResult.follow_up_info.next_follow_time }}</span>
            </div>
          </div>
        </div>

        <div class="preview-actions">
          <Button
            variant="outline"
            aria-label="返回修改输入内容"
            class="dialog-button"
            @click="handleBackToInput"
          >
            返回修改
          </Button>
          <Button
            variant="default"
            :disabled="hasMissingRequiredFields"
            :aria-disabled="hasMissingRequiredFields"
            aria-label="创建线索"
            class="dialog-button"
            @click="handleCreate"
          >
            <Loader2 v-if="isCreating" class="w-4 h-4 mr-2 animate-spin" aria-hidden="true" />
            创建线索
          </Button>
        </div>
      </div>

      <!-- 阶段 4：创建成功 -->
      <div v-if="stage === 'success'" class="success-stage" role="status" aria-live="polite">
        <div class="success-icon">
          <CircleCheck class="w-12 h-12 success-check-icon" aria-hidden="true" />
        </div>
        <div class="success-message">线索创建成功!</div>
        <div v-if="hasFollowUpInfo" class="success-extra">
          <span>已自动创建跟进记录</span>
        </div>
        <div class="success-actions">
          <Button
            variant="outline"
            aria-label="关闭对话框"
            class="dialog-button"
            @click="handleClose"
          >
            关闭
          </Button>
          <Button
            variant="default"
            aria-label="查看创建的线索详情"
            class="dialog-button"
            @click="handleViewLead"
          >
            查看线索
          </Button>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import {
  Info,
  WandSparkles,
  Loader2,
  CircleCheck,
  AlertCircle,
  FileText
} from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  Button,
  InputField,
  SelectField,
  TextareaField,
  ScrollArea
} from '@/components/crmwolf'
import { useUserStore } from '@/stores/user'
import { leadAiApi, type LeadAIParsedInfo, type LeadAIFollowUpInfo, type LeadAIParseSSEEvent } from '@/api/leadAI'

interface Props {
  modelValue: boolean
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const router = useRouter()
const userStore = useUserStore()

// 对话框可见性
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// 阶段状态
const stage = ref<'input' | 'parsing' | 'preview' | 'success'>('input')
const inputText = ref('')
const isParsing = ref(false)
const isCreating = ref(false)
const statusMessage = ref('')
const thinkingContent = ref('')
const parseResult = ref<{
  lead_info: LeadAIParsedInfo
  follow_up_info: LeadAIFollowUpInfo | null
  thinking_process: string | null
} | null>(null)
const createdLeadId = ref<number | null>(null)
const sourceOptions = [
  { value: '线上注册', label: '线上注册' },
  { value: '市场活动', label: '市场活动' },
  { value: '客户推荐', label: '客户推荐' },
  { value: '电话营销', label: '电话营销' },
  { value: '网站咨询', label: '网站咨询' },
  { value: '展会', label: '展会' },
  { value: '其他', label: '其他' },
]
const companyScaleOptions = [
  { value: '1-50人', label: '1-50人' },
  { value: '51-200人', label: '51-200人' },
  { value: '201-500人', label: '201-500人' },
  { value: '501-1000人', label: '501-1000人' },
  { value: '1000人以上', label: '1000人以上' },
]

// 预览表单
const previewForm = reactive({
  lead_name: '',
  source: '',
  city: '',
  company_scale: '',
  contact_name: '',
  contact_phone: '',
  follow_up_content: '',
  next_action: '',
  next_follow_time: ''
})

// 手机号验证
const isValidPhone = (phone: string): boolean => /^1[3-9]\d{9}$/.test(phone)

// 计算是否有缺失必填字段
const hasMissingRequiredFields = computed(() => {
  return previewForm.lead_name.trim().length === 0 ||
    previewForm.source.trim().length === 0 ||
    previewForm.city.trim().length === 0 ||
    previewForm.contact_name.trim().length === 0 ||
    previewForm.contact_phone.trim().length === 0 ||
    !isValidPhone(previewForm.contact_phone)
})

// 计算是否有跟进信息
const hasFollowUpInfo = computed(() => {
  const followUpInfo = parseResult.value?.follow_up_info
  if (followUpInfo === null || followUpInfo === undefined) return false

  return (followUpInfo.content ?? '').trim().length > 0 ||
    (followUpInfo.next_action ?? '').trim().length > 0 ||
    (followUpInfo.next_follow_time ?? '').trim().length > 0
})

// 格式化缺失字段列表
const formatMissingFields = (fields: string[]): string => {
  const fieldNames: Record<string, string> = {
    lead_name: '线索名称',
    source: '线索来源',
    city: '所在城市',
    contact_name: '联系人姓名',
    contact_phone: '联系电话'
  }
  return fields.map(f => fieldNames[f] ?? f).join('、')
}

// 重置状态
const resetState = (): void => {
  stage.value = 'input'
  inputText.value = ''
  isParsing.value = false
  isCreating.value = false
  statusMessage.value = ''
  thinkingContent.value = ''
  parseResult.value = null
  createdLeadId.value = null
  Object.assign(previewForm, {
    lead_name: '',
    source: '',
    city: '',
    company_scale: '',
    contact_name: '',
    contact_phone: '',
    follow_up_content: '',
    next_action: '',
    next_follow_time: ''
  })
}

// 处理关闭
const handleClose = (): void => {
  resetState()
  visible.value = false
}

// 处理解析
const handleParse = async (): Promise<void> => {
  const content = inputText.value.trim()
  if (!content || isParsing.value) return

  stage.value = 'parsing'
  isParsing.value = true
  statusMessage.value = '正在解析...'
  thinkingContent.value = ''
  parseResult.value = null

  const token = userStore.token
  if (!token) {
    toast.error('请先登录')
    stage.value = 'input'
    isParsing.value = false
    return
  }

  try {
    await leadAiApi.parseSSE(
      { content },
      (event: LeadAIParseSSEEvent) => {
        switch (event.event) {
          case 'status':
            statusMessage.value = event.message ?? '正在解析...'
            break
          case 'content':
            thinkingContent.value += event.content ?? ''
            break
          case 'parsed':
            if (event.lead_info) {
              parseResult.value = {
                lead_info: event.lead_info,
                follow_up_info: event.follow_up_info ?? null,
                thinking_process: event.thinking_process ?? null
              }

              // 填充预览表单
              Object.assign(previewForm, {
                lead_name: event.lead_info.lead_name ?? '',
                source: event.lead_info.source ?? '',
                city: event.lead_info.city ?? '',
                company_scale: event.lead_info.company_scale ?? '',
                contact_name: event.lead_info.contact_name ?? '',
                contact_phone: event.lead_info.contact_phone ?? '',
                follow_up_content: event.follow_up_info?.content ?? '',
                next_action: event.follow_up_info?.next_action ?? '',
                next_follow_time: event.follow_up_info?.next_follow_time ?? ''
              })

              stage.value = 'preview'
            }
            break
          case 'error':
            toast.error(event.message ?? '解析失败')
            stage.value = 'input'
            break
        }
      },
      token
    )
  } catch {
    toast.error('解析请求失败')
    stage.value = 'input'
  } finally {
    isParsing.value = false
  }
}

// 返回输入阶段
const handleBackToInput = (): void => {
  stage.value = 'input'
}

// 处理创建
const handleCreate = async (): Promise<void> => {
  if (hasMissingRequiredFields.value) {
    toast.error('请填写所有必填字段')
    return
  }

  isCreating.value = true

  try {
    const createData = {
      lead_name: previewForm.lead_name,
      source: previewForm.source,
      city: previewForm.city,
      contact_name: previewForm.contact_name,
      contact_phone: previewForm.contact_phone,
      ...(previewForm.company_scale.trim().length > 0 ? { company_scale: previewForm.company_scale } : {}),
      ...(previewForm.follow_up_content.trim().length > 0 ? { follow_up_content: previewForm.follow_up_content } : {}),
      ...(previewForm.next_action.trim().length > 0 ? { next_action: previewForm.next_action } : {}),
      ...(previewForm.next_follow_time.trim().length > 0 ? { next_follow_time: previewForm.next_follow_time } : {})
    }
    const response = await leadAiApi.createFromAI(createData)

    // 后端直接返回创建成功的线索数据
    if (response.id !== undefined && response.id !== null) {
      createdLeadId.value = response.id
      stage.value = 'success'
      toast.success('线索创建成功')
      emit('success')
    } else {
      toast.error('创建失败')
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : '创建失败'
    toast.error(errorMessage)
  } finally {
    isCreating.value = false
  }
}

// 查看线索
const handleViewLead = (): void => {
  if (createdLeadId.value !== null) {
    router.push(`/leads/${createdLeadId.value}`)
  }
  handleClose()
}

// 监听对话框关闭，重置状态
watch(visible, (val) => {
  if (!val) {
    resetState()
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// Dialog 内容样式
.dialog-content {
  max-width: 600px;
  border-radius: $wolf-radius-lg-v2;
  background: $wolf-bg-card-v2;  // 使用 V2 Design Token
  box-shadow: $wolf-shadow-modal-v2;
  padding: $wolf-space-lg-v2;

  // 移动端适配
  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    max-width: 100%;
    width: 100%;
    margin: 0;
    border-radius: $wolf-radius-lg-v2 $wolf-radius-lg-v2 0 0;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    max-height: $wolf-modal-height-mobile-v2;
  }
}

// 输入阶段样式
.input-stage {
  .input-hint {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm-v2;
    padding: $wolf-space-md-v2;
    background: $wolf-bg-hover-v2;
    border-radius: $wolf-radius-v2;
    margin-bottom: $wolf-space-md-v2;
    color: $wolf-text-secondary-v2;
    font-size: $wolf-font-size-body-v2;

    .hint-icon {
      color: $wolf-primary-v2;
      width: 20px;
      height: 20px;
    }
  }

  .input-textarea {
    margin-bottom: $wolf-space-sm-v2;
    border-radius: $wolf-radius-v2;
    border: 1px solid $wolf-border-default-v2;

    &:focus-visible {
      border-color: $wolf-primary-v2;
      outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
      outline-offset: $wolf-focus-ring-offset-v2;
    }

    // 移动端适配
    @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
      min-height: $wolf-input-height-mobile-v2;
      font-size: $wolf-font-size-body-mobile-v2;
    }
  }

  .input-tip {
    font-size: $wolf-font-size-caption-v2;
    color: $wolf-text-tertiary-v2;
    margin-bottom: $wolf-space-md-v2;
  }

  .input-actions {
    display: flex;
    justify-content: flex-end;
    gap: $wolf-space-sm-v2;

    // 移动端按钮全宽
    @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
      flex-direction: column;
      gap: $wolf-space-md-v2;
    }
  }
}

// 解析阶段样式
.parse-stage {
  .status-message {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm-v2;
    padding: $wolf-space-md-v2;
    background: $wolf-bg-hover-v2;
    border-radius: $wolf-radius-v2;
    margin-bottom: $wolf-space-md-v2;
    color: $wolf-text-secondary-v2;

    .status-icon {
      color: $wolf-primary-v2;
    }
  }

  .thinking-section {
    .thinking-header {
      font-size: $wolf-font-size-caption-v2;
      color: $wolf-text-tertiary-v2;
      margin-bottom: $wolf-space-sm-v2;
    }

    .thinking-scroll {
      max-height: 200px;
    }

    .thinking-content {
      padding: $wolf-space-md-v2;
      background: $wolf-bg-muted-v2;
      border-radius: $wolf-radius-sm-v2;
      font-size: $wolf-font-size-caption-v2;
      color: $wolf-text-tertiary-v2;
      white-space: pre-wrap;
    }
  }
}

// 预览阶段样式
.preview-stage {
  .preview-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm-v2;
    padding: $wolf-space-md-v2;
    background: $wolf-success-bg-v2;
    border-radius: $wolf-radius-v2;
    margin-bottom: $wolf-space-md-v2;
    color: $wolf-success-text-v2;

    .preview-icon {
      width: 20px;
      height: 20px;
    }
  }

  .missing-fields-tip {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm-v2;
    padding: $wolf-space-md-v2;
    background: $wolf-warning-bg-v2;
    border-radius: $wolf-radius-v2;
    margin-bottom: $wolf-space-md-v2;
    color: $wolf-warning-text-v2;

    .warning-icon {
      color: $wolf-warning-v2;
      width: 20px;
      height: 20px;
    }

    .missing-list {
      font-weight: $wolf-font-weight-medium-v2;
    }
  }

  .preview-form {
    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: $wolf-space-md-v2;
      margin-bottom: $wolf-space-md-v2;

      // 移动端单列布局
      @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
        grid-template-columns: 1fr;
      }
    }

    .form-item {
      display: flex;
      flex-direction: column;
      gap: $wolf-space-xs-v2;
    }

    .form-label {
      font-size: $wolf-font-size-body-v2;
      font-weight: $wolf-font-weight-medium-v2;
      color: $wolf-text-secondary-v2;

      .required {
        color: $wolf-danger-v2;
      }
    }

    .error-message {
      display: block;
      font-size: $wolf-font-size-caption-v2;
      color: $wolf-danger-text-v2;
      margin-top: $wolf-space-xs-v2;
    }
  }

  .follow-up-section {
    margin-top: $wolf-space-md-v2;
    padding: $wolf-space-md-v2;
    background: $wolf-bg-hover-v2;
    border-radius: $wolf-radius-v2;

    .follow-up-header {
      display: flex;
      align-items: center;
      gap: $wolf-space-sm-v2;
      font-size: $wolf-font-size-caption-v2;
      color: $wolf-text-tertiary-v2;
      margin-bottom: $wolf-space-sm-v2;

      .follow-up-icon {
        color: $wolf-primary-v2;
        width: 16px;
        height: 16px;
      }
    }

    .follow-up-fields {
      .follow-up-item {
        display: flex;
        gap: $wolf-space-sm-v2;
        margin-bottom: $wolf-space-xs-v2;

        .label {
          color: $wolf-text-tertiary-v2;
          font-size: $wolf-font-size-caption-v2;
        }

        .value {
          color: $wolf-text-secondary-v2;
          font-size: $wolf-font-size-body-v2;
        }
      }
    }
  }

  .preview-actions {
    display: flex;
    justify-content: flex-end;
    gap: $wolf-space-sm-v2;
    margin-top: $wolf-space-lg-v2;

    // 移动端按钮全宽
    @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
      flex-direction: column;
      gap: $wolf-space-md-v2;
    }
  }
}

// 成功阶段样式
.success-stage {
  text-align: center;
  padding: $wolf-space-lg-v2 0;

  .success-icon {
    margin-bottom: $wolf-space-md-v2;

    .success-check-icon {
      color: $wolf-success-v2;
    }
  }

  .success-message {
    font-size: $wolf-font-size-title-v2;
    font-weight: $wolf-font-weight-semibold-v2;
    color: $wolf-text-primary-v2;
    margin-bottom: $wolf-space-sm-v2;
  }

  .success-extra {
    font-size: $wolf-font-size-body-v2;
    color: $wolf-text-secondary-v2;
    margin-bottom: $wolf-space-lg-v2;
  }

  .success-actions {
    display: flex;
    justify-content: center;
    gap: $wolf-space-md-v2;

    // 移动端按钮全宽
    @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
      flex-direction: column;
      gap: $wolf-space-md-v2;
    }
  }
}

// 按钮样式（桌面端 + 移动端 Touch Target）
.dialog-button {
  height: $wolf-button-height-md-v2;
  border-radius: $wolf-radius-v2;
  padding: $wolf-button-padding-md-v2;
  cursor: $wolf-cursor-clickable-v2;

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }

  &:disabled {
    opacity: $wolf-disabled-opacity-light-v2;
    cursor: $wolf-cursor-disabled-v2;
  }

  // 移动端 Touch Target 合规
  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    min-height: $wolf-touch-target-min-v2;
    height: $wolf-button-height-mobile-v2;
    padding: $wolf-button-padding-mobile-v2;
    width: 100%;
  }

  // Reduced Motion 支持
  @media (prefers-reduced-motion: reduce) {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}

// 输入框样式（桌面端 + 移动端 Touch Target）
.dialog-input {
  height: $wolf-input-height-v2;
  border-radius: $wolf-radius-v2;
  border: 1px solid $wolf-border-default-v2;
  padding: $wolf-input-padding-v2;

  &:focus-visible {
    border-color: $wolf-primary-v2;
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }

  // 移动端 Touch Target 合规 + 16px 字号
  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    min-height: $wolf-input-height-mobile-v2;
    height: $wolf-input-height-mobile-v2;
    font-size: $wolf-font-size-body-mobile-v2;
    padding: $wolf-input-padding-mobile-v2;
  }

  // Reduced Motion 支持
  @media (prefers-reduced-motion: reduce) {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}

// Select 样式（桌面端 + 移动端 Touch Target）
.dialog-select {
  height: $wolf-input-height-v2;
  border-radius: $wolf-radius-v2;
  border: 1px solid $wolf-border-default-v2;

  &:focus-visible {
    border-color: $wolf-primary-v2;
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }

  // 移动端 Touch Target 合规
  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    min-height: $wolf-input-height-mobile-v2;
    height: $wolf-input-height-mobile-v2;
    font-size: $wolf-font-size-body-mobile-v2;
  }

  // Reduced Motion 支持
  @media (prefers-reduced-motion: reduce) {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
