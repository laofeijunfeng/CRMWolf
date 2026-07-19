<!-- CRM-Client/src/components/ApprovalFlowAIDialog.vue -->

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="dialog-content">
      <DialogHeader>
        <DialogTitle>AI 智能创建审批流程</DialogTitle>
        <DialogDescription>
          根据自然语言生成审批流程和节点配置，确认后保存为系统审批流程
        </DialogDescription>
      </DialogHeader>

      <div v-if="stage === 'input'" class="input-stage">
        <div class="input-hint" role="note">
          <Info class="hint-icon" aria-hidden="true" />
          <span>请用自然语言描述审批流程，AI 会自动生成节点配置</span>
        </div>

        <Textarea
          v-model="inputText"
          :rows="5"
          placeholder="例如：创建商机审批流程，销售总监审批"
          :disabled="isParsing"
          aria-label="输入审批流程描述"
          class="input-textarea"
          @keydown.ctrl.enter="handleParse"
        />

        <div class="input-tip">按 Ctrl+Enter 快速生成</div>

        <div class="input-actions">
          <Button
            variant="outline"
            class="dialog-button"
            aria-label="取消创建"
            @click="handleClose"
          >
            取消
          </Button>
          <Button
            variant="default"
            class="dialog-button"
            :disabled="!inputText.trim() || isParsing"
            aria-label="生成审批流程配置"
            @click="handleParse"
          >
            <WandSparkles v-if="!isParsing" class="w-4 h-4 mr-2" aria-hidden="true" />
            <Loader2 v-else class="w-4 h-4 mr-2 animate-spin" aria-hidden="true" />
            AI 生成配置
          </Button>
        </div>
      </div>

      <div v-if="stage === 'parsing'" class="parse-stage" role="status" aria-live="polite">
        <div class="progress-section">
          <Progress :model-value="progressPercentage" class="progress-bar" />
          <div class="progress-stage">
            <span>{{ progressStageLabel }}</span>
            <span v-if="estimatedSeconds">预计 {{ estimatedSeconds }} 秒</span>
          </div>
        </div>

        <div class="status-message">
          <Loader2 class="w-5 h-5 animate-spin status-icon" aria-hidden="true" />
          <span>{{ statusMessage }}</span>
        </div>

        <div v-if="thinkingContent" class="thinking-section">
          <div class="thinking-header">
            <MessagesSquare class="w-4 h-4" aria-hidden="true" />
            <span>AI 思考过程</span>
          </div>
          <ScrollArea class="thinking-scroll">
            <div class="thinking-content">{{ thinkingContent }}</div>
          </ScrollArea>
        </div>

        <div class="parse-actions">
          <Button
            variant="outline"
            class="dialog-button"
            :disabled="!canCancel"
            @click="handleCancel"
          >
            取消生成
          </Button>
        </div>
      </div>

      <div v-if="stage === 'error'" class="error-stage" role="alert">
        <div class="error-message">
          <AlertCircle class="warning-icon" aria-hidden="true" />
          <span>{{ errorMessage }}</span>
        </div>

        <div v-if="errorRecovery" class="error-recovery">
          {{ errorRecovery }}
        </div>

        <div v-if="errorActions.length" class="error-actions">
          <Button
            v-for="action in errorActions"
            :key="`${action.type}-${action.label}`"
            :variant="action.type === 'retry' ? 'default' : 'outline'"
            class="dialog-button"
            @click="handleErrorAction(action)"
          >
            {{ action.label }}
          </Button>
        </div>

        <div class="error-back">
          <Button variant="outline" class="dialog-button" @click="handleBackToInput">
            返回重新输入
          </Button>
        </div>
      </div>

      <ScrollArea v-if="stage === 'preview'" class="preview-scroll">
        <div class="preview-stage">
          <div class="preview-header" role="status">
            <CircleCheck class="preview-icon" aria-hidden="true" />
            <span>配置生成完成，可编辑调整后确认创建</span>
          </div>

          <form class="preview-form" @submit.prevent="handleCreate">
            <div class="form-grid">
              <div class="form-item">
                <Label for="flow-name" class="form-label">
                  流程名称 <span class="required">*</span>
                </Label>
                <Input
                  id="flow-name"
                  v-model="flowForm.flow_name"
                  placeholder="请输入流程名称"
                  aria-required="true"
                  :aria-invalid="!flowForm.flow_name"
                  class="dialog-input"
                />
                <span v-if="!flowForm.flow_name" class="error-message" role="alert">
                  请输入流程名称
                </span>
              </div>

              <div class="form-item">
                <Label for="flow-code" class="form-label">
                  流程编码 <span class="required">*</span>
                </Label>
                <Input
                  id="flow-code"
                  v-model="flowForm.flow_code"
                  placeholder="英文大写+下划线"
                  aria-required="true"
                  :aria-invalid="!isFlowCodeValid"
                  class="dialog-input"
                />
                <span v-if="flowForm.flow_code && !isFlowCodeValid" class="error-message" role="alert">
                  编码必须为大写字母、数字和下划线
                </span>
                <span v-else-if="!flowForm.flow_code" class="error-message" role="alert">
                  请输入流程编码
                </span>
              </div>
            </div>

            <div class="form-item">
              <Label for="flow-description" class="form-label">描述</Label>
              <Input
                id="flow-description"
                v-model="flowForm.description"
                placeholder="一句话描述适用场景"
                class="dialog-input"
              />
            </div>

            <div class="form-grid">
              <div class="form-item">
                <Label for="business-type" class="form-label">适用单据</Label>
                <Select v-model="flowForm.business_type">
                  <SelectTrigger id="business-type" class="dialog-select">
                    <SelectValue placeholder="请选择单据类型" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="CONTRACT">合同</SelectItem>
                    <SelectItem value="PAYMENT">回款登记</SelectItem>
                    <SelectItem value="INVOICE">发票申请</SelectItem>
                    <SelectItem value="LICENSE">License申请</SelectItem>
                    <SelectItem value="OPPORTUNITY">商机</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div class="form-item">
                <Label for="license-type" class="form-label">授权类型</Label>
                <Select v-model="flowForm.license_type">
                  <SelectTrigger id="license-type" class="dialog-select">
                    <SelectValue placeholder="不限" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__NONE__">不限</SelectItem>
                    <SelectItem value="SUBSCRIPTION">订阅</SelectItem>
                    <SelectItem value="PERPETUAL">买断</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div class="form-grid">
              <div class="form-item">
                <Label for="min-amount" class="form-label">最小金额（元）</Label>
                <Input
                  id="min-amount"
                  v-model="minAmountText"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="不限"
                  class="dialog-input"
                  @blur="syncAmount('min')"
                />
              </div>

              <div class="form-item">
                <Label for="max-amount" class="form-label">最大金额（元）</Label>
                <Input
                  id="max-amount"
                  v-model="maxAmountText"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="不限"
                  class="dialog-input"
                  @blur="syncAmount('max')"
                />
              </div>
            </div>
          </form>

          <div class="nodes-section">
            <div class="nodes-header">
              <div>
                <div class="section-title">审批节点配置</div>
                <div class="section-subtitle">按顺序执行，可调整节点、角色和必审状态</div>
              </div>
              <Button variant="outline" size="sm" class="compact-button" @click="handleAddNode">
                <Plus class="w-4 h-4 mr-2" aria-hidden="true" />
                添加节点
              </Button>
            </div>

            <div v-if="flowForm.nodes.length" class="node-list">
              <div
                v-for="(node, index) in flowForm.nodes"
                :key="`${node.node_code}-${index}`"
                class="node-item"
              >
                <div class="node-order">{{ index + 1 }}</div>

                <div class="node-fields">
                  <div class="node-grid">
                    <div class="form-item">
                      <Label :for="`node-name-${index}`" class="form-label">节点名称</Label>
                      <Input
                        :id="`node-name-${index}`"
                        v-model="node.node_name"
                        placeholder="例如：销售总监审批"
                        class="dialog-input"
                      />
                    </div>

                    <div class="form-item">
                      <Label :for="`node-code-${index}`" class="form-label">节点编码</Label>
                      <Input
                        :id="`node-code-${index}`"
                        v-model="node.node_code"
                        placeholder="例如：SALES_REVIEW"
                        class="dialog-input"
                      />
                    </div>

                    <div class="form-item">
                      <Label :for="`node-role-${index}`" class="form-label">审批角色</Label>
                      <Select v-model="node.approve_role">
                        <SelectTrigger :id="`node-role-${index}`" class="dialog-select">
                          <SelectValue placeholder="请选择角色" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem
                            v-for="role in ALLOWED_APPROVAL_ROLES"
                            :key="role"
                            :value="role"
                          >
                            {{ ROLE_DISPLAY_NAMES[role] }}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div class="node-bottom">
                    <div class="form-item node-description">
                      <Label :for="`node-description-${index}`" class="form-label">描述</Label>
                      <Input
                        :id="`node-description-${index}`"
                        :model-value="node.description ?? ''"
                        placeholder="节点描述"
                        class="dialog-input"
                        @update:model-value="(value) => {
                          node.description = String(value)
                        }"
                      />
                    </div>

                    <label class="required-toggle">
                      <Checkbox
                        :checked="node.is_required === 1"
                        @update:checked="(checked: boolean | 'indeterminate') => updateNodeRequired(node, checked)"
                      />
                      <span>必须审批</span>
                    </label>
                  </div>
                </div>

                <div class="node-actions">
                  <Button
                    variant="ghost"
                    size="icon"
                    title="上移"
                    :disabled="index === 0"
                    @click="handleMoveNode(index, -1)"
                  >
                    <ArrowUp class="w-4 h-4" aria-hidden="true" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="下移"
                    :disabled="index === flowForm.nodes.length - 1"
                    @click="handleMoveNode(index, 1)"
                  >
                    <ArrowDown class="w-4 h-4" aria-hidden="true" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="删除"
                    class="danger-button"
                    @click="handleRemoveNode(index)"
                  >
                    <Trash2 class="w-4 h-4" aria-hidden="true" />
                  </Button>
                </div>
              </div>
            </div>

            <div v-else class="empty-nodes">
              <span>暂无审批节点</span>
              <Button variant="outline" size="sm" class="compact-button" @click="handleAddNode">
                添加节点
              </Button>
            </div>
          </div>

          <div class="preview-actions">
            <Button variant="outline" class="dialog-button" @click="handleBackToInput">
              返回修改
            </Button>
            <Button variant="outline" class="dialog-button" @click="handleReset">
              重新生成
            </Button>
            <Button
              variant="default"
              class="dialog-button"
              :disabled="!isFormValid || isCreating"
              :aria-disabled="!isFormValid || isCreating"
              @click="handleCreate"
            >
              <Loader2 v-if="isCreating" class="w-4 h-4 mr-2 animate-spin" aria-hidden="true" />
              确认创建
            </Button>
          </div>
        </div>
      </ScrollArea>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  CircleCheck,
  Info,
  Loader2,
  MessagesSquare,
  Plus,
  Trash2,
  WandSparkles
} from 'lucide-vue-next'
import {
  Button,
  Checkbox,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Progress,
  ScrollArea,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea
} from '@/components/crmwolf'
import { useUserStore } from '@/stores/user'
import {
  approvalAiApi,
  ALLOWED_APPROVAL_ROLES,
  ROLE_DISPLAY_NAMES,
  type ApprovalAIParsedNode,
  type ErrorAction
} from '@/api/approvalAI'

type BusinessType = 'CONTRACT' | 'PAYMENT' | 'INVOICE' | 'LICENSE' | 'OPPORTUNITY'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'created', data: { id: number; flow_name: string }): void
}>()

const userStore = useUserStore()

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

const progressPercentage = ref<number>(0)
const progressStage = ref<'analyzing' | 'generating' | 'validating' | 'complete'>('analyzing')
const estimatedSeconds = ref<number | undefined>(undefined)
const canCancel = ref<boolean>(true)

const errorMessage = ref('')
const errorRecovery = ref('')
const errorActions = ref<ErrorAction[]>([])

const flowForm = ref<{
  flow_name: string
  flow_code: string
  description: string
  min_amount: number | undefined
  max_amount: number | undefined
  license_type: string
  business_type: BusinessType
  nodes: ApprovalAIParsedNode[]
}>({
  flow_name: '',
  flow_code: '',
  description: '',
  min_amount: undefined,
  max_amount: undefined,
  license_type: '__NONE__',
  business_type: 'CONTRACT',
  nodes: []
})
const minAmountText = ref('')
const maxAmountText = ref('')

const progressStageLabel = computed(() => {
  const labels = {
    analyzing: '正在理解您的需求',
    generating: '正在生成审批流程配置',
    validating: '正在验证角色编码',
    complete: '配置生成完成'
  }
  return labels[progressStage.value]
})

const isFlowCodeValid = computed(() => /^[A-Z][A-Z0-9_]*$/.test(flowForm.value.flow_code))

const isFormValid = computed(() => {
  if (!flowForm.value.flow_name || !isFlowCodeValid.value) return false
  if (flowForm.value.nodes.length === 0) return false

  const codes = flowForm.value.nodes.map(n => n.node_code).filter(Boolean)
  if (codes.length !== flowForm.value.nodes.length || codes.length !== new Set(codes).size) return false

  return flowForm.value.nodes.every(node =>
    node.node_name.trim() !== '' &&
    ALLOWED_APPROVAL_ROLES.includes(node.approve_role as typeof ALLOWED_APPROVAL_ROLES[number])
  )
})

const resetState = (): void => {
  stage.value = 'input'
  inputText.value = ''
  isParsing.value = false
  isCreating.value = false
  statusMessage.value = ''
  thinkingContent.value = ''
  progressPercentage.value = 0
  progressStage.value = 'analyzing'
  estimatedSeconds.value = undefined
  canCancel.value = true
  errorMessage.value = ''
  errorRecovery.value = ''
  errorActions.value = []
  flowForm.value = {
    flow_name: '',
    flow_code: '',
    description: '',
    min_amount: undefined,
    max_amount: undefined,
    license_type: '__NONE__',
    business_type: 'CONTRACT',
    nodes: []
  }
  minAmountText.value = ''
  maxAmountText.value = ''
}

const handleClose = (): void => {
  resetState()
  visible.value = false
}

const handleParse = async (): Promise<void> => {
  const content = inputText.value.trim()
  if (content === '' || isParsing.value) return

  stage.value = 'parsing'
  isParsing.value = true
  statusMessage.value = '正在连接 AI 服务...'
  thinkingContent.value = ''
  progressPercentage.value = 0
  progressStage.value = 'analyzing'
  estimatedSeconds.value = undefined
  canCancel.value = true
  errorMessage.value = ''
  errorRecovery.value = ''
  errorActions.value = []

  const token = userStore.token
  if (!token) {
    toast.error('请先登录')
    stage.value = 'input'
    isParsing.value = false
    return
  }

  try {
    await approvalAiApi.parseSSE(
      { content },
      (event): void => {
        switch (event.event) {
          case 'status':
            statusMessage.value = event.message ?? '正在解析...'
            if (event.estimated_seconds !== undefined) {
              estimatedSeconds.value = event.estimated_seconds
            }
            break
          case 'progress':
            progressPercentage.value = event.percentage ?? 0
            if (event.stage !== undefined) {
              progressStage.value = event.stage
            }
            statusMessage.value = event.message ?? '正在解析...'
            break
          case 'content':
            thinkingContent.value += event.content ?? ''
            break
          case 'parsed':
            if (event.flow) {
              progressPercentage.value = 100
              progressStage.value = 'complete'
              const minAmount = event.flow.min_amount
              const maxAmount = event.flow.max_amount
              flowForm.value = {
                flow_name: event.flow.flow_name,
                flow_code: event.flow.flow_code,
                description: event.flow.description ?? '',
                min_amount: minAmount,
                max_amount: maxAmount,
                license_type: event.flow.license_type ?? '__NONE__',
                business_type: event.flow.business_type ?? 'CONTRACT',
                nodes: event.flow.nodes.map(n => ({ ...n }))
              }
              minAmountText.value = minAmount !== undefined ? String(minAmount) : ''
              maxAmountText.value = maxAmount !== undefined ? String(maxAmount) : ''
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
  toast.info('已取消生成')
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
  normalizeNodeOrder()
}

const handleMoveNode = (index: number, direction: number): void => {
  const newIndex = index + direction
  if (newIndex < 0 || newIndex >= flowForm.value.nodes.length) return

  const nodes = flowForm.value.nodes
  const temp = nodes[index]
  const targetNode = nodes[newIndex]
  if (!temp || !targetNode) return

  nodes[index] = targetNode
  nodes[newIndex] = temp
  normalizeNodeOrder()
}

const updateNodeRequired = (node: ApprovalAIParsedNode, checked: boolean | 'indeterminate'): void => {
  node.is_required = checked === true ? 1 : 0
}

const normalizeNodeOrder = (): void => {
  flowForm.value.nodes.forEach((node, index) => {
    node.node_order = index + 1
  })
}

const syncAmount = (field: 'min' | 'max'): void => {
  const source = field === 'min' ? minAmountText : maxAmountText
  const value = source.value.trim()
  const amount = value === '' ? undefined : Number(value)
  const normalized = amount !== undefined && Number.isFinite(amount) && amount >= 0 ? amount : undefined

  if (field === 'min') {
    flowForm.value.min_amount = normalized
    minAmountText.value = normalized !== undefined ? String(normalized) : ''
  } else {
    flowForm.value.max_amount = normalized
    maxAmountText.value = normalized !== undefined ? String(normalized) : ''
  }
}

const handleCreate = async (): Promise<void> => {
  syncAmount('min')
  syncAmount('max')

  if (!isFormValid.value) {
    toast.error('请完善流程名称、编码和审批节点')
    return
  }

  isCreating.value = true

  try {
    const requestData: import('@/api/approvalAI').ApprovalAICreateRequest = {
      flow_name: flowForm.value.flow_name,
      flow_code: flowForm.value.flow_code,
      nodes: flowForm.value.nodes
    }
    if (flowForm.value.description !== '') requestData.description = flowForm.value.description
    if (flowForm.value.min_amount !== undefined) requestData.min_amount = flowForm.value.min_amount
    if (flowForm.value.max_amount !== undefined) requestData.max_amount = flowForm.value.max_amount
    if (flowForm.value.license_type !== '__NONE__') requestData.license_type = flowForm.value.license_type
    if (flowForm.value.business_type !== 'CONTRACT') requestData.business_type = flowForm.value.business_type

    const result = await approvalAiApi.createFromAI(requestData)

    toast.success(result.message)
    emit('created', result.data.flow)
    handleClose()
  } catch (error: unknown) {
    const err = error as { response?: { data?: { detail?: string } }; message?: string }
    toast.error(err.response?.data?.detail ?? err.message ?? '创建失败')
  } finally {
    isCreating.value = false
  }
}

watch(visible, (val): void => {
  if (!val) {
    resetState()
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.dialog-content {
  width: min(920px, calc(100vw - #{$wolf-space-xl-v2}));
  max-width: 920px;
  max-height: 88vh;
  border-radius: $wolf-radius-lg-v2;
  background: $wolf-bg-card-v2;
  box-shadow: $wolf-shadow-modal-v2;
  padding: $wolf-space-lg-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    width: 100%;
    max-width: 100%;
    max-height: $wolf-modal-height-mobile-v2;
    margin: 0;
    border-radius: $wolf-radius-lg-v2 $wolf-radius-lg-v2 0 0;
    position: fixed;
    right: 0;
    bottom: 0;
    left: 0;
  }
}

.input-hint,
.status-message,
.preview-header,
.error-message,
.error-recovery {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  padding: $wolf-space-md-v2;
  border-radius: $wolf-radius-v2;
  font-size: $wolf-font-size-body-v2;
}

.input-hint,
.status-message {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-secondary-v2;
}

.hint-icon,
.status-icon {
  width: 20px;
  height: 20px;
  color: $wolf-primary-v2;
  flex: 0 0 auto;
}

.input-stage {
  .input-hint {
    margin-bottom: $wolf-space-md-v2;
  }

  .input-tip {
    font-size: $wolf-font-size-caption-v2;
    color: $wolf-text-tertiary-v2;
    margin-top: $wolf-space-sm-v2;
  }

  .input-actions {
    display: flex;
    justify-content: flex-end;
    gap: $wolf-space-sm-v2;
    margin-top: $wolf-space-md-v2;
  }
}

.input-textarea {
  border-radius: $wolf-radius-v2;
  border: 1px solid $wolf-border-default-v2;

  &:focus-visible {
    border-color: $wolf-primary-v2;
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.parse-stage {
  .progress-section {
    margin-bottom: $wolf-space-md-v2;
  }

  .progress-bar {
    height: 8px;
  }

  .progress-stage {
    display: flex;
    justify-content: space-between;
    gap: $wolf-space-md-v2;
    margin-top: $wolf-space-sm-v2;
    color: $wolf-text-tertiary-v2;
    font-size: $wolf-font-size-caption-v2;
  }

  .thinking-section {
    margin-top: $wolf-space-md-v2;
  }

  .thinking-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs-v2;
    margin-bottom: $wolf-space-sm-v2;
    color: $wolf-text-tertiary-v2;
    font-size: $wolf-font-size-caption-v2;
  }

  .thinking-scroll {
    max-height: 220px;
  }

  .thinking-content {
    padding: $wolf-space-md-v2;
    border-radius: $wolf-radius-sm-v2;
    background: $wolf-bg-muted-v2;
    color: $wolf-text-secondary-v2;
    font-size: $wolf-font-size-caption-v2;
    line-height: 1.6;
    white-space: pre-wrap;
  }

  .parse-actions {
    display: flex;
    justify-content: flex-end;
    margin-top: $wolf-space-md-v2;
  }
}

.error-stage {
  .error-message {
    background: $wolf-danger-bg-v2;
    color: $wolf-danger-text-v2;
  }

  .warning-icon {
    width: 20px;
    height: 20px;
    color: $wolf-danger-v2;
    flex: 0 0 auto;
  }

  .error-recovery {
    margin-top: $wolf-space-md-v2;
    background: $wolf-bg-hover-v2;
    color: $wolf-text-secondary-v2;
  }

  .error-actions,
  .error-back {
    display: flex;
    justify-content: flex-end;
    gap: $wolf-space-sm-v2;
    margin-top: $wolf-space-md-v2;
  }
}

.preview-scroll {
  max-height: calc(88vh - 112px);
  padding-right: $wolf-space-xs-v2;
}

.preview-stage {
  .preview-header {
    margin-bottom: $wolf-space-md-v2;
    background: $wolf-success-bg-v2;
    color: $wolf-success-text-v2;
  }

  .preview-icon {
    width: 20px;
    height: 20px;
    flex: 0 0 auto;
  }
}

.preview-form {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

.form-grid,
.node-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.node-grid {
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr) minmax(180px, 0.8fr);

  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;
}

.form-label {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;

  .required {
    color: $wolf-danger-v2;
  }
}

.error-message {
  color: $wolf-danger-text-v2;
  font-size: $wolf-font-size-caption-v2;
}

.dialog-input,
.dialog-select {
  height: $wolf-input-height-v2;
  border-radius: $wolf-radius-v2;
  border: 1px solid $wolf-border-default-v2;

  &:focus-visible {
    border-color: $wolf-primary-v2;
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.nodes-section {
  margin-top: $wolf-space-lg-v2;
}

.nodes-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  margin-bottom: $wolf-space-md-v2;
}

.section-title {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.section-subtitle {
  margin-top: $wolf-space-xs-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.node-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

.node-item {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-card-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 28px minmax(0, 1fr);
  }
}

.node-order {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: $wolf-radius-sm-v2;
  background: $wolf-bg-muted-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.node-fields {
  min-width: 0;
}

.node-bottom {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: $wolf-space-md-v2;
  align-items: end;
  margin-top: $wolf-space-md-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.required-toggle {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  height: $wolf-input-height-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  white-space: nowrap;
}

.node-actions {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-column: 2;
    justify-content: flex-end;
  }
}

.danger-button {
  color: $wolf-danger-v2;
}

.empty-nodes {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-lg-v2;
  border: 1px dashed $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-body-v2;
}

.preview-actions {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-lg-v2;
}

.dialog-button,
.compact-button {
  border-radius: $wolf-radius-v2;
  cursor: $wolf-cursor-clickable-v2;

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }

  &:disabled {
    cursor: $wolf-cursor-disabled-v2;
    opacity: $wolf-disabled-opacity-light-v2;
  }
}

.dialog-button {
  height: $wolf-button-height-md-v2;
  padding: $wolf-button-padding-md-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .input-actions,
  .preview-actions,
  .error-actions,
  .error-back {
    flex-direction: column;
  }

  .dialog-button {
    width: 100%;
    min-height: $wolf-touch-target-min-v2;
    height: $wolf-button-height-mobile-v2;
    padding: $wolf-button-padding-mobile-v2;
  }

  .dialog-input,
  .dialog-select,
  .input-textarea {
    min-height: $wolf-input-height-mobile-v2;
    font-size: $wolf-font-size-body-mobile-v2;
  }
}

@media (prefers-reduced-motion: reduce) {
  .dialog-button,
  .dialog-input,
  .dialog-select,
  .input-textarea {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
