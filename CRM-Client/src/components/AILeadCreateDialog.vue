<template>
  <el-dialog
    v-model="visible"
    title="AI 智能创建线索"
    width="600px"
    :close-on-click-modal="false"
    class="ai-lead-create-dialog"
    @close="handleClose"
  >
    <!-- 阶段 1：输入 -->
    <div v-if="stage === 'input'" class="input-stage">
      <div class="input-hint">
        <el-icon><InfoFilled /></el-icon>
        <span>请用自然语言描述线索信息，AI 会自动识别并提取关键信息</span>
      </div>
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="4"
        placeholder="例如：张三，13800138000，来自杭州的阿里巴巴，大概500人，网上注册来的，想做电商系统"
        :disabled="isParsing"
        @keydown.ctrl.enter="handleParse"
      />
      <div class="input-tip">按 Ctrl+Enter 快速识别</div>
      <div class="input-actions">
        <el-button @click="handleClose">取消</el-button>
        <el-button
          type="primary"
          :disabled="!inputText.trim() || isParsing"
          :loading="isParsing"
          @click="handleParse"
        >
          <el-icon><MagicStick /></el-icon>
          智能识别
        </el-button>
      </div>
    </div>

    <!-- 阶段 2：解析过程 -->
    <div v-if="stage === 'parsing'" class="parse-stage">
      <div class="status-message">
        <el-icon class="loading-icon"><Loading /></el-icon>
        <span>{{ statusMessage }}</span>
      </div>
      <div v-if="thinkingContent" class="thinking-section">
        <div class="thinking-header">
          <span>AI 思考过程</span>
        </div>
        <div class="thinking-content">{{ thinkingContent }}</div>
      </div>
    </div>

    <!-- 阶段 3：预览确认 -->
    <div v-if="stage === 'preview'" class="preview-stage">
      <div class="preview-header">
        <el-icon><SuccessFilled /></el-icon>
        <span>解析完成，请确认以下信息</span>
      </div>

      <!-- 缺失字段提示 -->
      <div v-if="parseResult?.lead_info?.missing_fields?.length" class="missing-fields-tip">
        <el-icon><WarningFilled /></el-icon>
        <span>以下必填信息未能识别，请手动补充：</span>
        <span class="missing-list">{{ formatMissingFields(parseResult.lead_info.missing_fields) }}</span>
      </div>

      <!-- 预览表单 -->
      <el-form
        ref="previewFormRef"
        :model="previewForm"
        :rules="previewRules"
        label-position="top"
        class="preview-form"
      >
        <div class="form-grid">
          <el-form-item label="线索名称" prop="lead_name" required>
            <el-input v-model="previewForm.lead_name" placeholder="请输入线索名称" />
          </el-form-item>

          <el-form-item label="线索来源" prop="source" required>
            <el-select v-model="previewForm.source" placeholder="请选择来源" style="width: 100%">
              <el-option value="线上注册" label="线上注册" />
              <el-option value="市场活动" label="市场活动" />
              <el-option value="客户推荐" label="客户推荐" />
              <el-option value="电话营销" label="电话营销" />
              <el-option value="网站咨询" label="网站咨询" />
              <el-option value="展会" label="展会" />
              <el-option value="其他" label="其他" />
            </el-select>
          </el-form-item>
        </div>

        <div class="form-grid">
          <el-form-item label="所在城市" prop="city" required>
            <el-input v-model="previewForm.city" placeholder="请输入城市" />
          </el-form-item>

          <el-form-item label="公司规模" prop="company_scale">
            <el-select
              v-model="previewForm.company_scale"
              placeholder="请选择规模"
              clearable
              style="width: 100%"
            >
              <el-option value="1-50人" label="1-50人" />
              <el-option value="51-200人" label="51-200人" />
              <el-option value="201-500人" label="201-500人" />
              <el-option value="501-1000人" label="501-1000人" />
              <el-option value="1000人以上" label="1000人以上" />
            </el-select>
          </el-form-item>
        </div>

        <div class="form-grid">
          <el-form-item label="联系人姓名" prop="contact_name" required>
            <el-input v-model="previewForm.contact_name" placeholder="请输入联系人姓名" />
          </el-form-item>

          <el-form-item label="联系电话" prop="contact_phone" required>
            <el-input v-model="previewForm.contact_phone" placeholder="请输入联系电话" />
          </el-form-item>
        </div>
      </el-form>

      <!-- 跟进信息 -->
      <div v-if="hasFollowUpInfo" class="follow-up-section">
        <div class="follow-up-header">
          <el-icon><Document /></el-icon>
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
        <el-button @click="handleBackToInput">返回修改</el-button>
        <el-button
          type="primary"
          :disabled="hasMissingRequiredFields"
          :loading="isCreating"
          @click="handleCreate"
        >
          创建线索
        </el-button>
      </div>
    </div>

    <!-- 阶段 4：创建成功 -->
    <div v-if="stage === 'success'" class="success-stage">
      <div class="success-icon">
        <el-icon><CircleCheckFilled /></el-icon>
      </div>
      <div class="success-message">线索创建成功！</div>
      <div v-if="hasFollowUpInfo" class="success-extra">
        <span>已自动创建跟进记录</span>
      </div>
      <div class="success-actions">
        <el-button @click="handleClose">关闭</el-button>
        <el-button type="primary" @click="handleViewLead">查看线索</el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  InfoFilled,
  MagicStick,
  Loading,
  SuccessFilled,
  WarningFilled,
  Document,
  CircleCheckFilled
} from '@element-plus/icons-vue'
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

// 预览表单
const previewFormRef = ref()
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

const previewRules = {
  lead_name: [{ required: true, message: '请输入线索名称', trigger: 'blur' }],
  source: [{ required: true, message: '请选择线索来源', trigger: 'change' }],
  city: [{ required: true, message: '请输入所在城市', trigger: 'blur' }],
  contact_name: [{ required: true, message: '请输入联系人姓名', trigger: 'blur' }],
  contact_phone: [
    { required: true, message: '请输入联系电话', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号码', trigger: 'blur' }
  ]
}

// 计算是否有缺失必填字段
const hasMissingRequiredFields = computed(() => {
  return !previewForm.lead_name ||
    !previewForm.source ||
    !previewForm.city ||
    !previewForm.contact_name ||
    !previewForm.contact_phone
})

// 计算是否有跟进信息
const hasFollowUpInfo = computed(() => {
  return parseResult.value?.follow_up_info &&
    (parseResult.value.follow_up_info.content ||
      parseResult.value.follow_up_info.next_action ||
      parseResult.value.follow_up_info.next_follow_time)
})

// 格式化缺失字段列表
const formatMissingFields = (fields: string[]) => {
  const fieldNames: Record<string, string> = {
    lead_name: '线索名称',
    source: '线索来源',
    city: '所在城市',
    contact_name: '联系人姓名',
    contact_phone: '联系电话'
  }
  return fields.map(f => fieldNames[f] || f).join('、')
}

// 重置状态
const resetState = () => {
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
const handleClose = () => {
  resetState()
  visible.value = false
}

// 处理解析
const handleParse = async () => {
  const content = inputText.value.trim()
  if (!content || isParsing.value) return

  stage.value = 'parsing'
  isParsing.value = true
  statusMessage.value = '正在解析...'
  thinkingContent.value = ''
  parseResult.value = null

  const token = userStore.token
  if (!token) {
    ElMessage.error('请先登录')
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
            statusMessage.value = event.message || '正在解析...'
            break
          case 'content':
            thinkingContent.value += event.content || ''
            break
          case 'parsed':
            if (event.lead_info) {
              parseResult.value = {
                lead_info: event.lead_info,
                follow_up_info: event.follow_up_info || null,
                thinking_process: event.thinking_process || null
              }

              // 填充预览表单
              Object.assign(previewForm, {
                lead_name: event.lead_info.lead_name || '',
                source: event.lead_info.source || '',
                city: event.lead_info.city || '',
                company_scale: event.lead_info.company_scale || '',
                contact_name: event.lead_info.contact_name || '',
                contact_phone: event.lead_info.contact_phone || '',
                follow_up_content: event.follow_up_info?.content || '',
                next_action: event.follow_up_info?.next_action || '',
                next_follow_time: event.follow_up_info?.next_follow_time || ''
              })

              stage.value = 'preview'
            }
            break
          case 'error':
            ElMessage.error(event.message || '解析失败')
            stage.value = 'input'
            break
        }
      },
      token
    )
  } catch (error) {
    ElMessage.error('解析请求失败')
    stage.value = 'input'
  } finally {
    isParsing.value = false
  }
}

// 返回输入阶段
const handleBackToInput = () => {
  stage.value = 'input'
}

// 处理创建
const handleCreate = async () => {
  if (!previewFormRef.value) return

  try {
    await previewFormRef.value.validate()
  } catch {
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
      ...(previewForm.company_scale ? { company_scale: previewForm.company_scale } : {}),
      ...(previewForm.follow_up_content ? { follow_up_content: previewForm.follow_up_content } : {}),
      ...(previewForm.next_action ? { next_action: previewForm.next_action } : {}),
      ...(previewForm.next_follow_time ? { next_follow_time: previewForm.next_follow_time } : {})
    }
    const response = await leadAiApi.createFromAI(createData)

    // 后端直接返回创建成功的线索数据
    if (response && response.id) {
      createdLeadId.value = response.id
      stage.value = 'success'
      emit('success')
    } else {
      ElMessage.error('创建失败')
    }
  } catch (error: any) {
    ElMessage.error(error.message || '创建失败')
  } finally {
    isCreating.value = false
  }
}

// 查看线索
const handleViewLead = () => {
  if (createdLeadId.value) {
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
@use '@/styles/variables.scss' as *;

.ai-lead-create-dialog {
  :deep(.el-dialog__body) {
    padding: $wolf-space-lg;
  }
}

.input-stage {
  .input-hint {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-md;
    background: $wolf-bg-hover;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;
    color: $wolf-text-secondary;
    font-size: $wolf-font-size-body;

    .el-icon {
      color: $wolf-primary;
    }
  }

  .el-textarea {
    margin-bottom: $wolf-space-sm;
  }

  .input-tip {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
    margin-bottom: $wolf-space-md;
  }

  .input-actions {
    display: flex;
    justify-content: flex-end;
    gap: $wolf-space-sm;
  }
}

.parse-stage {
  .status-message {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-md;
    background: $wolf-bg-hover;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;
    color: $wolf-text-secondary;

    .loading-icon {
      animation: spin 1s linear infinite;
      color: $wolf-primary;
    }
  }

  .thinking-section {
    .thinking-header {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      margin-bottom: $wolf-space-sm;
    }

    .thinking-content {
      padding: $wolf-space-md;
      background: $wolf-bg-page;
      border-radius: $wolf-radius-sm;
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      white-space: pre-wrap;
      max-height: 200px;
      overflow-y: auto;
    }
  }
}

.preview-stage {
  .preview-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-md;
    background: $wolf-success-bg;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;
    color: $wolf-success-text;

    .el-icon {
      font-size: 20px;
    }
  }

  .missing-fields-tip {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-md;
    background: $wolf-warning-bg;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;
    color: $wolf-warning-text;

    .el-icon {
      color: $wolf-warning;
    }

    .missing-list {
      font-weight: $wolf-font-weight-medium;
    }
  }

  .preview-form {
    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: $wolf-space-md;
      margin-bottom: $wolf-space-md;
    }
  }

  .follow-up-section {
    margin-top: $wolf-space-md;
    padding: $wolf-space-md;
    background: $wolf-bg-hover;
    border-radius: $wolf-radius-md;

    .follow-up-header {
      display: flex;
      align-items: center;
      gap: $wolf-space-sm;
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      margin-bottom: $wolf-space-sm;

      .el-icon {
        color: $wolf-primary;
      }
    }

    .follow-up-fields {
      .follow-up-item {
        display: flex;
        gap: $wolf-space-sm;
        margin-bottom: $wolf-space-xs;

        .label {
          color: $wolf-text-tertiary;
          font-size: $wolf-font-size-caption;
        }

        .value {
          color: $wolf-text-secondary;
          font-size: $wolf-font-size-body;
        }
      }
    }
  }

  .preview-actions {
    display: flex;
    justify-content: flex-end;
    gap: $wolf-space-sm;
    margin-top: $wolf-space-lg;
  }
}

.success-stage {
  text-align: center;
  padding: $wolf-space-lg 0;

  .success-icon {
    margin-bottom: $wolf-space-md;

    .el-icon {
      font-size: 48px;
      color: $wolf-success;
    }
  }

  .success-message {
    font-size: $wolf-font-size-title;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-primary;
    margin-bottom: $wolf-space-sm;
  }

  .success-extra {
    font-size: $wolf-font-size-body;
    color: $wolf-text-secondary;
    margin-bottom: $wolf-space-lg;
  }

  .success-actions {
    display: flex;
    justify-content: center;
    gap: $wolf-space-md;
  }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>