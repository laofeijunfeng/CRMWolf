<template>
  <el-dialog
    v-model="visible"
    title="AI 快速创建采购方式"
    width="850px"
    :close-on-click-modal="false"
    class="procurement-ai-dialog"
    @close="handleClose"
  >
    <!-- 阶段 1：输入 -->
    <div v-if="stage === 'input'" class="input-stage">
      <div class="input-hint">
        <el-icon><InfoFilled /></el-icon>
        <span>请用自然语言描述采购方式及阶段流程，AI 会自动生成配置</span>
      </div>
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="5"
        placeholder="例如：创建一个公开招标采购方式，包含发布公告、报名、开标、评标、定标五个阶段"
        :disabled="isParsing"
        @keydown.ctrl.enter="handleParse"
      />
      <div class="input-tip">按 Ctrl+Enter 快速生成</div>
      <div class="input-actions">
        <el-button @click="handleClose">取消</el-button>
        <el-button
          type="primary"
          :disabled="!inputText.trim() || isParsing"
          :loading="isParsing"
          @click="handleParse"
        >
          <el-icon><MagicStick /></el-icon>
          AI 生成配置
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
        <span>配置生成完成，可编辑调整后确认创建</span>
      </div>

      <!-- 采购方式基本信息 -->
      <el-form
        ref="methodFormRef"
        :model="methodForm"
        :rules="methodRules"
        label-position="top"
        class="method-form"
      >
        <div class="form-grid">
          <el-form-item label="采购方式名称" prop="name" required>
            <el-input v-model="methodForm.name" placeholder="请输入名称" />
          </el-form-item>

          <el-form-item label="采购方式编码" prop="code" required>
            <el-input v-model="methodForm.code" placeholder="英文大写+下划线" />
          </el-form-item>
        </div>

        <el-form-item label="描述">
          <el-input v-model="methodForm.description" placeholder="一句话描述" />
        </el-form-item>
      </el-form>

      <!-- 阶段配置表格 -->
      <div class="stages-section">
        <div class="stages-header">
          <span>阶段配置（可拖拽调整顺序）</span>
          <el-button
            size="small"
            type="primary"
            plain
            @click="handleAddStage"
          >
            <el-icon><Plus /></el-icon>
            添加阶段
          </el-button>
        </div>

        <el-table
          :data="methodForm.stages"
          border
          class="stages-table"
        >
          <el-table-column prop="stage_name" label="阶段名称" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.stage_name" size="small" />
            </template>
          </el-table-column>

          <el-table-column prop="template_code" label="编码" min-width="130">
            <template #default="{ row }">
              <el-input v-model="row.template_code" size="small" />
            </template>
          </el-table-column>

          <el-table-column prop="win_probability" label="赢率" width="100">
            <template #default="{ row }">
              <el-input-number
                v-model="row.win_probability"
                :min="10"
                :max="100"
                size="small"
                controls-position="right"
                style="width: 80px"
              />
            </template>
          </el-table-column>

          <el-table-column prop="sort_order" label="顺序" width="90">
            <template #default="{ row, $index }">
              <div class="order-buttons">
                <el-button
                  size="small"
                  :disabled="$index === 0"
                  @click="handleMoveStage($index, -1)"
                >
                  ↑
                </el-button>
                <el-button
                  size="small"
                  :disabled="$index === methodForm.stages.length - 1"
                  @click="handleMoveStage($index, 1)"
                >
                  ↓
                </el-button>
              </div>
            </template>
          </el-table-column>

          <el-table-column prop="is_default_start" label="默认起始" width="80" align="center">
            <template #default="{ row, $index }">
              <el-checkbox
                v-model="row.is_default_start"
                @change="handleDefaultStartChange($index)"
              />
            </template>
          </el-table-column>

          <el-table-column prop="can_skip" label="可跳过" width="70" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.can_skip" />
            </template>
          </el-table-column>

          <el-table-column prop="description" label="描述" min-width="150">
            <template #default="{ row }">
              <el-input v-model="row.description" size="small" placeholder="阶段描述" />
            </template>
          </el-table-column>

          <el-table-column label="操作" width="60" align="center">
            <template #default="{ $index }">
              <el-button
                size="small"
                type="danger"
                link
                @click="handleRemoveStage($index)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="preview-actions">
        <el-button @click="handleBackToInput">返回重新生成</el-button>
        <el-button @click="handleReset">重新生成</el-button>
        <el-button
          type="primary"
          :disabled="!isFormValid"
          :loading="isCreating"
          @click="handleCreate"
        >
          确认创建
        </el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import {
  InfoFilled,
  MagicStick,
  Loading,
  SuccessFilled,
  Plus,
  WarningFilled
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import {
  procurementAiApi,
  type ProcurementAIParsedMethod,
  type ProcurementAIParsedStage
} from '@/api/procurementAI'

// Props & Emits
const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'created', data: { id: number; name: string }): void
}>()

// Store
const userStore = useUserStore()

// 状态
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const stage = ref<'input' | 'parsing' | 'preview'>('input')
const inputText = ref('')
const isParsing = ref(false)
const isCreating = ref(false)
const statusMessage = ref('')
const thinkingContent = ref('')
const parseResult = ref<ProcurementAIParsedMethod | null>(null)

// 表单
const methodFormRef = ref<FormInstance>()
const methodForm = ref<{
  name: string
  code: string
  description: string
  stages: ProcurementAIParsedStage[]
}>({
  name: '',
  code: '',
  description: '',
  stages: []
})

const methodRules: FormRules = {
  name: [{ required: true, message: '请输入采购方式名称', trigger: 'blur' }],
  code: [
    { required: true, message: '请输入采购方式编码', trigger: 'blur' },
    { pattern: /^[A-Z][A-Z0-9_]*$/, message: '编码必须为大写字母、数字和下划线', trigger: 'blur' }
  ]
}

// 计算属性
const isFormValid = computed(() => {
  if (!methodForm.value.name || !methodForm.value.code) return false
  if (methodForm.value.stages.length === 0) return false
  // 检查最后阶段赢率是否为100
  const lastStage = methodForm.value.stages[methodForm.value.stages.length - 1]
  if (lastStage.win_probability !== 100) return false
  // 检查编码唯一性
  const codes = methodForm.value.stages.map(s => s.template_code)
  if (codes.length !== new Set(codes).size) return false
  return true
})

// 方法
const handleParse = async () => {
  if (!inputText.value.trim()) return

  stage.value = 'parsing'
  isParsing.value = true
  statusMessage.value = '正在分析采购流程...'
  thinkingContent.value = ''

  try {
    const token = userStore.token || ''
    await procurementAiApi.parseSSE(
      { content: inputText.value },
      (event) => {
        switch (event.event) {
          case 'status':
            statusMessage.value = event.message || ''
            break
          case 'content':
            thinkingContent.value += event.content || ''
            break
          case 'parsed':
            parseResult.value = event.method || null
            if (parseResult.value) {
              // 填充表单
              methodForm.value = {
                name: parseResult.value.name,
                code: parseResult.value.code,
                description: parseResult.value.description || '',
                stages: parseResult.value.stages.map(s => ({ ...s }))
              }
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
  } catch (error: unknown) {
    ElMessage.error(error.message || 'AI 服务异常')
    stage.value = 'input'
  } finally {
    isParsing.value = false
  }
}

const handleBackToInput = () => {
  stage.value = 'input'
}

const handleReset = () => {
  stage.value = 'input'
  inputText.value = ''
  thinkingContent.value = ''
  parseResult.value = null
}

const handleAddStage = () => {
  const lastOrder = methodForm.value.stages.length
  const lastWinRate = lastOrder > 0 ? methodForm.value.stages[lastOrder - 1].win_probability : 80

  methodForm.value.stages.push({
    stage_name: '',
    template_code: '',
    win_probability: Math.min(lastWinRate + 20, 100),
    sort_order: lastOrder + 1,
    is_default_start: false,
    can_skip: false,
    description: ''
  })
}

const handleRemoveStage = (index: number) => {
  methodForm.value.stages.splice(index, 1)
  // 更新顺序
  methodForm.value.stages.forEach((s, i) => {
    s.sort_order = i + 1
  })
}

const handleMoveStage = (index: number, direction: number) => {
  const newIndex = index + direction
  if (newIndex < 0 || newIndex >= methodForm.value.stages.length) return

  const stages = methodForm.value.stages
  const temp = stages[index]
  stages[index] = stages[newIndex]
  stages[newIndex] = temp

  // 更新顺序
  stages.forEach((s, i) => {
    s.sort_order = i + 1
  })
}

const handleDefaultStartChange = (index: number) => {
  // 只允许一个默认起始阶段
  if (methodForm.value.stages[index].is_default_start) {
    methodForm.value.stages.forEach((s, i) => {
      if (i !== index) {
        s.is_default_start = false
      }
    })
  }
}

const handleCreate = async () => {
  if (!methodFormRef.value) return

  await methodFormRef.value.validate()

  isCreating.value = true

  try {
    const result = await procurementAiApi.createFromAI({
      name: methodForm.value.name,
      code: methodForm.value.code,
      description: methodForm.value.description,
      stages: methodForm.value.stages
    })

    ElMessage.success(result.message)
    emit('created', result.data)
    handleClose()
  } catch (error: unknown) {
    ElMessage.error(error.response?.data?.detail || error.message || '创建失败')
  } finally {
    isCreating.value = false
  }
}

const handleClose = () => {
  visible.value = false
  // 重置状态
  stage.value = 'input'
  inputText.value = ''
  thinkingContent.value = ''
  parseResult.value = null
  methodForm.value = {
    name: '',
    code: '',
    description: '',
    stages: []
  }
}

// 监听关闭，确保重置
watch(visible, (val) => {
  if (!val) {
    handleClose()
  }
})
</script>

<style scoped lang="scss">
.procurement-ai-dialog {
  .input-stage {
    .input-hint {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px;
      background: var(--el-fill-color-light);
      border-radius: 4px;
      margin-bottom: 16px;
      color: var(--el-text-color-secondary);
    }

    .input-tip {
      text-align: right;
      font-size: 12px;
      color: var(--el-text-color-placeholder);
      margin-top: 8px;
    }

    .input-actions {
      display: flex;
      justify-content: flex-end;
      gap: 12px;
      margin-top: 16px;
    }
  }

  .parse-stage {
    .status-message {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px;
      background: var(--el-fill-color-light);
      border-radius: 4px;

      .loading-icon {
        animation: spin 1s linear infinite;
      }
    }

    .thinking-section {
      margin-top: 16px;
      padding: 12px;
      background: #f5f7fa;
      border-radius: 4px;

      .thinking-header {
        font-size: 13px;
        font-weight: 500;
        color: var(--el-text-color-secondary);
        margin-bottom: 8px;
      }

      .thinking-content {
        font-size: 13px;
        line-height: 1.6;
        white-space: pre-wrap;
      }
    }
  }

  .preview-stage {
    .preview-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px;
      background: var(--el-color-success-light-9);
      border-radius: 4px;
      margin-bottom: 20px;
      color: var(--el-color-success);
    }

    .method-form {
      .form-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
      }
    }

    .stages-section {
      margin-top: 20px;

      .stages-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
        font-weight: 500;
      }

      .stages-table {
        .order-buttons {
          display: flex;
          gap: 4px;
        }
      }
    }

    .preview-actions {
      display: flex;
      justify-content: flex-end;
      gap: 12px;
      margin-top: 20px;
    }
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>