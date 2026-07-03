<!-- CRM-Client/src/components/ApprovalFlowAIDialog.vue -->

<template>
  <el-dialog
    v-model="visible"
    title="AI 快速创建审批流程"
    width="850px"
    :close-on-click-modal="false"
    class="approval-ai-dialog"
    @close="handleClose"
  >
    <!-- 阶段 1：输入 -->
    <div v-if="stage === 'input'" class="input-stage">
      <div class="input-hint">
        <el-icon><InfoFilled /></el-icon>
        <span>请用自然语言描述审批流程，AI 会自动生成节点配置</span>
      </div>
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="5"
        placeholder="例如：创建一个金额超过50万的合同审批流程，需要销售总监审批和财务审批"
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

    <!-- 阶段 2：解析过程（进度 + 思考 + 取消） -->
    <div v-if="stage === 'parsing'" class="parse-stage">
      <div class="progress-section">
        <el-progress
          :percentage="progressPercentage"
          :status="progressStatus"
          :stroke-width="8"
        />
        <div class="progress-stage">
          <span class="stage-label">{{ progressStageLabel }}</span>
          <span v-if="estimatedSeconds" class="estimated-time">
            预计 {{ estimatedSeconds }} 秒
          </span>
        </div>
      </div>

      <div class="status-message">
        <el-icon class="loading-icon"><Loading /></el-icon>
        <span>{{ statusMessage }}</span>
      </div>

      <div v-if="thinkingContent" class="thinking-section">
        <div class="thinking-header">
          <el-icon><ChatDotRound /></el-icon>
          <span>AI 思考过程</span>
        </div>
        <div class="thinking-content typewriter">{{ thinkingContent }}</div>
      </div>

      <div class="parse-actions">
        <el-button
          type="danger"
          plain
          :disabled="!canCancel"
          @click="handleCancel"
        >
          取消生成
        </el-button>
      </div>
    </div>

    <!-- 阶段：错误状态 -->
    <div v-if="stage === 'error'" class="error-stage">
      <div class="error-message">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ errorMessage }}</span>
      </div>

      <div v-if="errorRecovery" class="error-recovery">
        <span>建议：{{ errorRecovery }}</span>
      </div>

      <div v-if="errorActions.length" class="error-actions">
        <el-button
          v-for="action in errorActions"
          :key="action.type"
          :type="action.type === 'retry' ? 'primary' : 'default'"
          @click="handleErrorAction(action)"
        >
          {{ action.label }}
        </el-button>
      </div>

      <div class="error-back">
        <el-button @click="handleBackToInput">返回重新输入</el-button>
      </div>
    </div>

    <!-- 阶段 3：预览确认 -->
    <div v-if="stage === 'preview'" class="preview-stage">
      <div class="preview-header">
        <el-icon><SuccessFilled /></el-icon>
        <span>配置生成完成，可编辑调整后确认创建</span>
      </div>

      <!-- 流程基本信息 -->
      <el-form
        ref="flowFormRef"
        :model="flowForm"
        :rules="flowRules"
        label-position="top"
        class="flow-form"
      >
        <div class="form-grid">
          <el-form-item label="流程名称" prop="flow_name" required>
            <el-input v-model="flowForm.flow_name" placeholder="请输入名称" />
          </el-form-item>

          <el-form-item label="流程编码" prop="flow_code" required>
            <el-input v-model="flowForm.flow_code" placeholder="英文大写+下划线" />
          </el-form-item>
        </div>

        <el-form-item label="描述">
          <el-input v-model="flowForm.description" placeholder="一句话描述适用场景" />
        </el-form-item>

        <el-form-item label="适用单据" prop="business_type">
          <el-radio-group v-model="flowForm.business_type">
            <el-radio value="CONTRACT">合同</el-radio>
            <el-radio value="PAYMENT">回款登记</el-radio>
            <el-radio value="INVOICE">发票申请</el-radio>
          </el-radio-group>
          <div style="color: var(--el-text-color-secondary); font-size: 12px; margin-top: 4px;">
            AI 识别结果，可手动修改
          </div>
        </el-form-item>

        <div class="form-grid">
          <el-form-item label="最小金额（元）">
            <el-input-number
              v-model="flowForm.min_amount"
              :min="0"
              :precision="2"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>

          <el-form-item label="最大金额（元）">
            <el-input-number
              v-model="flowForm.max_amount"
              :min="0"
              :precision="2"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>
        </div>

        <el-form-item label="授权类型">
          <el-radio-group v-model="flowForm.license_type">
            <el-radio label="">不限</el-radio>
            <el-radio label="SUBSCRIPTION">订阅</el-radio>
            <el-radio label="PERPETUAL">买断</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <!-- 节点配置表格 -->
      <div class="nodes-section">
        <div class="nodes-header">
          <span>审批节点配置（可拖拽调整顺序）</span>
          <el-button
            size="small"
            type="primary"
            plain
            @click="handleAddNode"
          >
            <el-icon><Plus /></el-icon>
            添加节点
          </el-button>
        </div>

        <el-table
          :data="flowForm.nodes"
          border
          class="nodes-table"
        >
          <el-table-column prop="node_name" label="节点名称" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.node_name" size="small" />
            </template>
          </el-table-column>

          <el-table-column prop="node_code" label="编码" min-width="130">
            <template #default="{ row }">
              <el-input v-model="row.node_code" size="small" />
            </template>
          </el-table-column>

          <el-table-column prop="approve_role" label="审批角色" min-width="140">
            <template #default="{ row }">
              <el-select v-model="row.approve_role" size="small" style="width: 100%">
                <el-option
                  v-for="role in ALLOWED_APPROVAL_ROLES"
                  :key="role"
                  :label="ROLE_DISPLAY_NAMES[role]"
                  :value="role"
                />
              </el-select>
            </template>
          </el-table-column>

          <el-table-column prop="node_order" label="顺序" width="90">
            <template #default="{ $index }">
              <div class="order-buttons">
                <el-button
                  size="small"
                  :disabled="$index === 0"
                  @click="handleMoveNode($index, -1)"
                >
                  ↑
                </el-button>
                <el-button
                  size="small"
                  :disabled="$index === flowForm.nodes.length - 1"
                  @click="handleMoveNode($index, 1)"
                >
                  ↓
                </el-button>
              </div>
            </template>
          </el-table-column>

          <el-table-column prop="is_required" label="必须" width="70" align="center">
            <template #default="{ row }">
              <el-checkbox
                v-model="row.is_required"
                :true-value="1"
                :false-value="0"
              />
            </template>
          </el-table-column>

          <el-table-column prop="description" label="描述" min-width="150">
            <template #default="{ row }">
              <el-input v-model="row.description" size="small" placeholder="节点描述" />
            </template>
          </el-table-column>

          <el-table-column label="操作" width="60" align="center">
            <template #default="{ $index }">
              <el-button
                size="small"
                type="danger"
                link
                @click="handleRemoveNode($index)"
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
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  InfoFilled,
  MagicStick,
  Loading,
  SuccessFilled,
  Plus,
  WarningFilled,
  ChatDotRound
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import {
  approvalAiApi,
  ALLOWED_APPROVAL_ROLES,
  ROLE_DISPLAY_NAMES,
  type ApprovalAIParsedNode,
  type ErrorAction
} from '@/api/approvalAI'

// Props & Emits
const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'created', data: { id: number; flow_name: string }): void
}>()

// Store
const userStore = useUserStore()

// 状态
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const stage = ref<'input' | 'parsing' | 'preview' | 'error'>('input')
const inputText = ref('')
const isParsing = ref(false)
const isCreating = ref(false)
const statusMessage = ref('')
const thinkingContent = ref('')

// 进度状态
const progressPercentage = ref<number>(0)
const progressStage = ref<'analyzing' | 'generating' | 'validating' | 'complete'>('analyzing')
const progressStatus = ref<'' | 'success' | 'warning' | 'exception'>('')
const estimatedSeconds = ref<number | undefined>(undefined)
const canCancel = ref<boolean>(true)

// 错误状态
const errorMessage = ref('')
const errorRecovery = ref('')
const errorActions = ref<ErrorAction[]>([])

// 计算属性：进度阶段标签
const progressStageLabel = computed(() => {
  const labels = {
    analyzing: '正在理解您的需求',
    generating: '正在生成审批流程配置',
    validating: '正在验证角色编码',
    complete: '配置生成完成'
  }
  return labels[progressStage.value]
})

// 表单
const flowFormRef = ref<FormInstance>()
const flowForm = ref<{
  flow_name: string
  flow_code: string
  description: string
  min_amount: number | undefined
  max_amount: number | undefined
  license_type: string
  business_type: 'CONTRACT' | 'PAYMENT' | 'INVOICE'
  nodes: ApprovalAIParsedNode[]
}>({
  flow_name: '',
  flow_code: '',
  description: '',
  min_amount: undefined,
  max_amount: undefined,
  license_type: '',
  business_type: 'CONTRACT',
  nodes: []
})

const flowRules: FormRules = {
  flow_name: [{ required: true, message: '请输入流程名称', trigger: 'blur' }],
  flow_code: [
    { required: true, message: '请输入流程编码', trigger: 'blur' },
    { pattern: /^[A-Z][A-Z0-9_]*$/, message: '编码必须为大写字母、数字和下划线', trigger: 'blur' }
  ]
}

// 计算属性
const isFormValid = computed(() => {
  if (!flowForm.value.flow_name || !flowForm.value.flow_code) return false
  if (flowForm.value.nodes.length === 0) return false
  // 检查节点编码唯一性
  const codes = flowForm.value.nodes.map(n => n.node_code)
  if (codes.length !== new Set(codes).size) return false
  // 检查角色有效性
  for (const node of flowForm.value.nodes) {
    if (!ALLOWED_APPROVAL_ROLES.includes(node.approve_role as typeof ALLOWED_APPROVAL_ROLES[number])) {
      return false
    }
  }
  return true
})

// 方法
const handleParse = async (): Promise<void> => {
  if (inputText.value.trim() === '') return

  // 重置状态
  stage.value = 'parsing'
  isParsing.value = true
  statusMessage.value = '正在连接 AI 服务...'
  thinkingContent.value = ''
  progressPercentage.value = 0
  progressStage.value = 'analyzing'
  progressStatus.value = ''
  estimatedSeconds.value = undefined
  canCancel.value = true
  errorMessage.value = ''
  errorRecovery.value = ''
  errorActions.value = []

  try {
    const token = userStore.token ?? ''
    await approvalAiApi.parseSSE(
      { content: inputText.value },
      (event): void => {
        switch (event.event) {
          case 'status':
            statusMessage.value = event.message ?? ''
            if (event.estimated_seconds !== undefined) {
              estimatedSeconds.value = event.estimated_seconds
            }
            break
          case 'progress':
            progressPercentage.value = event.percentage ?? 0
            if (event.stage !== undefined) {
              progressStage.value = event.stage
            }
            statusMessage.value = event.message ?? ''
            break
          case 'content':
            thinkingContent.value += event.content ?? ''
            break
          case 'parsed':
            if (event.flow) {
              // 进度完成 + 填充表单
              progressPercentage.value = 100
              progressStage.value = 'complete'
              progressStatus.value = 'success'
              flowForm.value = {
                flow_name: event.flow.flow_name,
                flow_code: event.flow.flow_code,
                description: event.flow.description ?? '',
                min_amount: event.flow.min_amount,
                max_amount: event.flow.max_amount,
                license_type: event.flow.license_type ?? '',
                business_type: event.flow.business_type ?? 'CONTRACT',
                nodes: event.flow.nodes.map(n => ({ ...n }))
              }
              stage.value = 'preview'
            }
            break
          case 'error':
            errorMessage.value = event.message ?? '解析失败'
            errorRecovery.value = event.recovery ?? ''
            errorActions.value = event.actions ?? []
            stage.value = 'error'
            break
          case 'done':
            canCancel.value = false
            // done=false 且未收到 parsed/error → 连接中断
            if (event.success === false && stage.value === 'parsing') {
              errorMessage.value = 'AI 服务连接中断'
              errorRecovery.value = '请检查网络连接后重试'
              stage.value = 'error'
            }
            break
        }
      },
      token
    )
  } catch (error: unknown) {
    const err = error as Error
    errorMessage.value = err.message ?? 'AI 服务异常'
    errorRecovery.value = '请稍后重试'
    stage.value = 'error'
  } finally {
    isParsing.value = false
  }
}

const handleBackToInput = (): void => {
  stage.value = 'input'
}

const handleReset = (): void => {
  stage.value = 'input'
  inputText.value = ''
  thinkingContent.value = ''
}

const handleErrorAction = (action: ErrorAction): void => {
  switch (action.type) {
    case 'retry':
      if (action.suggestion !== undefined && action.suggestion !== '') {
        inputText.value = action.suggestion
      }
      void handleParse()
      break
    case 'simplify':
      if (action.suggestion !== undefined && action.suggestion !== '') {
        inputText.value = action.suggestion
        void handleParse()
      }
      break
    case 'help':
      if (action.url !== undefined && action.url !== '') {
        window.open(action.url, '_blank')
      }
      break
  }
}

const handleCancel = (): void => {
  canCancel.value = false
  stage.value = 'input'
  statusMessage.value = ''
  thinkingContent.value = ''
  ElMessage.info('已取消生成')
}

const handleAddNode = (): void => {
  const lastOrder = flowForm.value.nodes.length

  flowForm.value.nodes.push({
    node_name: '',
    node_code: '',
    node_order: lastOrder + 1,
    approve_role: 'SALES_DIRECTOR',
    description: '',
    is_required: 1
  })
}

const handleRemoveNode = (index: number): void => {
  flowForm.value.nodes.splice(index, 1)
  // 更新顺序
  flowForm.value.nodes.forEach((n, i) => {
    n.node_order = i + 1
  })
}

const handleMoveNode = (index: number, direction: number): void => {
  const newIndex = index + direction
  if (newIndex < 0 || newIndex >= flowForm.value.nodes.length) return

  const nodes = flowForm.value.nodes
  const temp = nodes[index]
  if (temp) {
    const targetNode = nodes[newIndex]
    if (targetNode) {
      nodes[index] = targetNode
      nodes[newIndex] = temp
    }
  }

  // 更新顺序
  nodes.forEach((n, i) => {
    n.node_order = i + 1
  })
}

const handleCreate = async (): Promise<void> => {
  if (!flowFormRef.value) return

  await flowFormRef.value.validate()

  isCreating.value = true

  try {
    // Build request object conditionally to handle exactOptionalPropertyTypes
    const requestData: import('@/api/approvalAI').ApprovalAICreateRequest = {
      flow_name: flowForm.value.flow_name,
      flow_code: flowForm.value.flow_code,
      nodes: flowForm.value.nodes
    }
    if (flowForm.value.description !== '') requestData.description = flowForm.value.description
    if (flowForm.value.min_amount !== undefined) requestData.min_amount = flowForm.value.min_amount
    if (flowForm.value.max_amount !== undefined) requestData.max_amount = flowForm.value.max_amount
    if (flowForm.value.license_type !== '') requestData.license_type = flowForm.value.license_type
    if (flowForm.value.business_type !== 'CONTRACT') requestData.business_type = flowForm.value.business_type

    const result = await approvalAiApi.createFromAI(requestData)

    ElMessage.success(result.message)
    emit('created', result.data.flow)
    handleClose()
  } catch (error: unknown) {
    const err = error as { response?: { data?: { detail?: string } }; message?: string }
    const errorMsg = err.response?.data?.detail ?? err.message ?? '创建失败'
    ElMessage.error(errorMsg)
  } finally {
    isCreating.value = false
  }
}

const handleClose = (): void => {
  visible.value = false
  // 重置状态
  stage.value = 'input'
  inputText.value = ''
  thinkingContent.value = ''
  flowForm.value = {
    flow_name: '',
    flow_code: '',
    description: '',
    min_amount: undefined,
    max_amount: undefined,
    license_type: '',
    business_type: 'CONTRACT',
    nodes: []
  }
}

// 监听关闭，确保重置
watch(visible, (val): void => {
  if (!val) {
    handleClose()
  }
})
</script>

<style scoped lang="scss">
.approval-ai-dialog {
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
    .progress-section {
      margin-bottom: 16px;

      .progress-stage {
        display: flex;
        justify-content: space-between;
        margin-top: 8px;
        font-size: 13px;

        .estimated-time {
          color: var(--el-text-color-secondary);
        }
      }
    }

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
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 4px;
        color: #fff;
        font-weight: 500;
        font-size: 13px;
      }

      .thinking-content {
        margin-top: 8px;
        padding: 16px;
        font-size: 13px;
        line-height: 1.6;
        white-space: pre-wrap;

        &.typewriter {
          animation: fadeIn 0.3s ease-out;
          border-left: 3px solid #667eea;
        }
      }
    }

    .parse-actions {
      margin-top: 16px;
      text-align: right;
    }
  }

  .error-stage {
    padding: 20px;

    .error-message {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px;
      background: var(--el-color-danger-light-9);
      border-radius: 4px;
      color: var(--el-color-danger);
      font-size: 14px;
    }

    .error-recovery {
      padding: 12px 16px;
      background: var(--el-fill-color-light);
      border-radius: 4px;
      margin-top: 12px;
      color: var(--el-text-color-secondary);
      font-size: 13px;
    }

    .error-actions {
      display: flex;
      gap: 12px;
      margin-top: 16px;
    }

    .error-back {
      margin-top: 16px;
      text-align: right;
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

    .flow-form {
      .form-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
      }
    }

    .nodes-section {
      margin-top: 20px;

      .nodes-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
        font-weight: 500;
      }

      .nodes-table {
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

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>