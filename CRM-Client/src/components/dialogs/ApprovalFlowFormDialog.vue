<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { DataViewStatePanel } from '@/components/crmwolf'
import ApprovalNodeApproverPicker from '@/components/ApprovalNodeApproverPicker.vue'
import approvalFlowApi, { type ApprovalFlow, type ApprovalFlowDetail, type ApprovalNode, type ApprovalNodeAssignees, type ApprovalNodeType } from '@/api/approvalFlow'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  open: boolean
  mode: 'create' | 'edit'
  flowId?: number | null
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'success'): void
}

interface FlowNodeForm {
  key: number
  id?: number
  nodeName: string
  nodeCode: string
  nodeType: ApprovalNodeType
  assignees: ApprovalNodeAssignees
  description: string
}

interface FlowForm {
  flowName: string
  flowCode: string
  description: string
  licenseType: string
  businessType: string
  minAmount: string
  maxAmount: string
  active: boolean
  nodes: FlowNodeForm[]
}

interface FlowFormErrors {
  flowName: string
  flowCode: string
  businessType: string
  amountRange: string
  nodes: string
}

const props = withDefaults(defineProps<Props>(), {
  flowId: null,
})
const emit = defineEmits<Emits>()

let nextNodeKey = 0
const loadingDetail = ref(false)
const submitting = ref(false)

const form = reactive<FlowForm>({
  flowName: '',
  flowCode: '',
  description: '',
  licenseType: 'ALL',
  businessType: 'CONTRACT',
  minAmount: '',
  maxAmount: '',
  active: true,
  nodes: [],
})

const errors = reactive<FlowFormErrors>({
  flowName: '',
  flowCode: '',
  businessType: '',
  amountRange: '',
  nodes: '',
})

const visible = computed({
  get: (): boolean => props.open,
  set: (value: boolean): void => emit('update:open', value),
})
const isEditMode = computed<boolean>(() => props.mode === 'edit')
const title = computed<string>(() => isEditMode.value ? '编辑审批流程' : '新建审批流程')
const description = computed<string>(() => {
  return isEditMode.value
    ? '调整流程适用条件、状态和审批节点。'
    : '填写流程基础信息，并按顺序配置审批节点。'
})

function resetForm(): void {
  form.flowName = ''
  form.flowCode = ''
  form.description = ''
  form.licenseType = 'ALL'
  form.businessType = 'CONTRACT'
  form.minAmount = ''
  form.maxAmount = ''
  form.active = true
  form.nodes = []
  clearErrors()
}

function clearErrors(): void {
  errors.flowName = ''
  errors.flowCode = ''
  errors.businessType = ''
  errors.amountRange = ''
  errors.nodes = ''
}

function hydrateForm(flow: ApprovalFlowDetail): void {
  form.flowName = flow.flow_name ?? ''
  form.flowCode = flow.flow_code ?? ''
  form.description = flow.description ?? ''
  form.licenseType = flow.license_type !== null && flow.license_type !== undefined && flow.license_type !== '' ? flow.license_type : 'ALL'
  form.businessType = flow.business_type ?? 'CONTRACT'
  form.minAmount = flow.min_amount !== null && flow.min_amount !== undefined ? String(flow.min_amount) : ''
  form.maxAmount = flow.max_amount !== null && flow.max_amount !== undefined ? String(flow.max_amount) : ''
  form.active = flow.is_active !== 0
  form.nodes = [...(flow.nodes ?? [])]
    .sort((a, b) => a.node_order - b.node_order)
    .map((node) => {
      const formNode: FlowNodeForm = {
        key: nextNodeKey++,
        nodeName: node.node_name,
        nodeCode: node.node_code,
        nodeType: node.node_type,
        assignees: { roles: [...node.approver_roles], users: [...node.approver_users] },
        description: node.description ?? '',
      }

      if (node.id !== undefined) {
        formNode.id = node.id
      }

      return formNode
    })
  clearErrors()
}


async function fetchFlowDetail(): Promise<void> {
  if (!isEditMode.value || props.flowId === null) return

  loadingDetail.value = true
  try {
    const flow = await approvalFlowApi.getApprovalFlowDetail(props.flowId) as ApprovalFlowDetail
    hydrateForm(flow)
  } catch (error: unknown) {
    handleApiError(error, '获取审批流程详情')
  } finally {
    loadingDetail.value = false
  }
}

function addNode(nodeType: ApprovalNodeType): void {
  form.nodes.push({
    key: nextNodeKey++,
    nodeName: '',
    nodeCode: '',
    nodeType,
    assignees: { roles: [], users: [] },
    description: '',
  })
  errors.nodes = ''
}

function removeNode(index: number): void {
  form.nodes.splice(index, 1)
}

function moveNode(index: number, direction: 'up' | 'down'): void {
  const targetIndex = direction === 'up' ? index - 1 : index + 1
  if (targetIndex < 0 || targetIndex >= form.nodes.length) return

  const current = form.nodes[index]
  const target = form.nodes[targetIndex]
  if (current === undefined || target === undefined) return

  form.nodes[index] = target
  form.nodes[targetIndex] = current
}

function validateForm(): boolean {
  clearErrors()

  if (form.flowName.trim() === '') {
    errors.flowName = '请输入流程名称'
  }

  if (form.flowCode.trim() === '') {
    errors.flowCode = '请输入流程编码'
  } else if (!/^[A-Z_][A-Z0-9_]*$/.test(form.flowCode.trim())) {
    errors.flowCode = '只能包含大写字母、数字和下划线，且必须以字母或下划线开头'
  }

  if (form.businessType.trim() === '') {
    errors.businessType = '请选择适用单据'
  }

  const minAmount = form.minAmount.trim() === '' ? null : Number(form.minAmount)
  const maxAmount = form.maxAmount.trim() === '' ? null : Number(form.maxAmount)
  if ((minAmount !== null && (!Number.isFinite(minAmount) || minAmount < 0))
    || (maxAmount !== null && (!Number.isFinite(maxAmount) || maxAmount < 0))) {
    errors.amountRange = '金额必须为大于等于 0 的数字'
  } else if (minAmount !== null && maxAmount !== null && maxAmount < minAmount) {
    errors.amountRange = '最大金额不能小于最小金额'
  }

  if (form.nodes.length === 0) {
    errors.nodes = '请至少添加一个审批节点'
  } else if (form.nodes[0]?.nodeType !== 'APPROVAL') {
    errors.nodes = '首个节点必须是审批节点'
  } else {
    const invalidIndex = form.nodes.findIndex((node) =>
      node.nodeName.trim() === ''
      || node.nodeCode.trim() === ''
      || (node.assignees.roles.length === 0 && node.assignees.users.length === 0)
    )
    if (invalidIndex !== -1) {
      errors.nodes = `请填写第 ${invalidIndex + 1} 个节点的名称、编码，并选择角色或人员`
    }
  }

  return errors.flowName === ''
    && errors.flowCode === ''
    && errors.businessType === ''
    && errors.amountRange === ''
    && errors.nodes === ''
}

function buildPayload(): ApprovalFlow {
  const payload: ApprovalFlow = {
    flow_name: form.flowName.trim(),
    flow_code: form.flowCode.trim(),
    business_type: form.businessType as ApprovalFlow['business_type'],
    is_active: form.active ? 1 : 0,
    nodes: form.nodes.map((node, index): ApprovalNode => {
      const nextNode: ApprovalNode = {
        node_name: node.nodeName.trim(),
        node_code: node.nodeCode.trim(),
        node_order: index + 1,
        node_type: node.nodeType,
        approver_roles: node.assignees.roles,
        approver_users: node.assignees.users,
      }

      if (node.id !== undefined) {
        nextNode.id = node.id
      }

      const nodeDescription = node.description.trim()
      if (nodeDescription !== '') {
        nextNode.description = nodeDescription
      }

      return nextNode
    }),
  }

  const flowDescription = form.description.trim()
  if (flowDescription !== '') {
    payload.description = flowDescription
  }

  if (form.licenseType !== 'ALL') {
    payload.license_type = form.licenseType
  }

  if (form.minAmount.trim() !== '') {
    payload.min_amount = Number(form.minAmount)
  }

  if (form.maxAmount.trim() !== '') {
    payload.max_amount = Number(form.maxAmount)
  }

  return payload
}

async function handleSubmit(): Promise<void> {
  if (submitting.value || !validateForm()) return

  submitting.value = true
  try {
    if (isEditMode.value && props.flowId !== null) {
      await approvalFlowApi.updateApprovalFlow(props.flowId, buildPayload())
      toast.success('审批流程更新成功')
    } else {
      await approvalFlowApi.createApprovalFlow(buildPayload())
      toast.success('审批流程创建成功')
    }

    visible.value = false
    emit('success')
  } catch (error: unknown) {
    handleApiError(error, isEditMode.value ? '更新审批流程' : '创建审批流程')
  } finally {
    submitting.value = false
  }
}

function handleCancel(): void {
  if (!submitting.value) {
    visible.value = false
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return

    resetForm()
    if (isEditMode.value) {
      void fetchFlowDetail()
    }
  }
)
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent size="xl" class="approval-flow-form-dialog z-[1000]">
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription>{{ description }}</DialogDescription>
      </DialogHeader>

      <div class="dialog-body">
        <DataViewStatePanel :state="loadingDetail ? 'loading' : 'ready'" loading-type="list">
          <section class="form-section">
            <h3 class="section-title">基本信息</h3>
            <div class="form-grid">
              <div class="form-field">
                <Label for="approval-flow-name">流程名称 <span class="required">*</span></Label>
                <Input
                  id="approval-flow-name"
                  v-model="form.flowName"
                  maxlength="100"
                  placeholder="例如：合同默认审批"
                  :aria-invalid="errors.flowName !== ''"
                />
                <p v-if="errors.flowName" class="field-error">{{ errors.flowName }}</p>
              </div>

              <div class="form-field">
                <Label for="approval-flow-code">流程编码 <span class="required">*</span></Label>
                <Input
                  id="approval-flow-code"
                  v-model="form.flowCode"
                  maxlength="50"
                  placeholder="例如：CONTRACT_DEFAULT"
                  :disabled="isEditMode"
                  :aria-invalid="errors.flowCode !== ''"
                />
                <p v-if="errors.flowCode" class="field-error">{{ errors.flowCode }}</p>
              </div>
            </div>

            <div class="form-field">
              <Label for="approval-flow-description">流程描述</Label>
              <Textarea
                id="approval-flow-description"
                v-model="form.description"
                maxlength="500"
                placeholder="补充说明该流程的适用场景"
              />
            </div>
          </section>

          <section class="form-section">
            <h3 class="section-title">适用条件</h3>
            <div class="form-grid">
              <div class="form-field">
                <Label>授权类型</Label>
                <Select v-model="form.licenseType">
                  <SelectTrigger>
                    <SelectValue placeholder="选择授权类型" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ALL">不限</SelectItem>
                    <SelectItem value="SUBSCRIPTION">订阅</SelectItem>
                    <SelectItem value="PERPETUAL">买断</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div class="form-field">
                <Label>适用单据 <span class="required">*</span></Label>
                <Select v-model="form.businessType">
                  <SelectTrigger :aria-invalid="errors.businessType !== ''">
                    <SelectValue placeholder="选择单据类型" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="CONTRACT">合同</SelectItem>
                    <SelectItem value="PAYMENT">回款登记</SelectItem>
                    <SelectItem value="INVOICE">发票申请</SelectItem>
                    <SelectItem value="INVOICE_REISSUE">发票重开申请</SelectItem>
                    <SelectItem value="LICENSE">License申请</SelectItem>
                    <SelectItem value="OPPORTUNITY">商机</SelectItem>
                  </SelectContent>
                </Select>
                <p v-if="errors.businessType" class="field-error">{{ errors.businessType }}</p>
              </div>
            </div>

            <div class="form-grid">
              <div class="form-field">
                <Label for="approval-flow-min-amount">最小金额</Label>
                <Input
                  id="approval-flow-min-amount"
                  v-model="form.minAmount"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="不限制"
                  :aria-invalid="errors.amountRange !== ''"
                />
              </div>
              <div class="form-field">
                <Label for="approval-flow-max-amount">最大金额</Label>
                <Input
                  id="approval-flow-max-amount"
                  v-model="form.maxAmount"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="不限制"
                  :aria-invalid="errors.amountRange !== ''"
                />
              </div>
            </div>
            <p v-if="errors.amountRange" class="field-error">{{ errors.amountRange }}</p>

            <div class="switch-row">
              <Switch
                id="approval-flow-active"
                :checked="form.active"
                @update:checked="form.active = $event"
              />
              <Label for="approval-flow-active" class="cursor-pointer">启用流程</Label>
            </div>
          </section>

          <section class="form-section">
            <div class="section-header">
              <h3 class="section-title">审批节点</h3>
            </div>

            <p v-if="errors.nodes" class="field-error">{{ errors.nodes }}</p>

            <DataViewStatePanel
              :state="form.nodes.length === 0 ? 'empty' : 'ready'"
              class="nodes-list"
              empty-title="暂无审批节点"
            >
              <div
                v-for="(node, index) in form.nodes"
                :key="node.key"
                class="node-item"
              >
                <div class="node-header">
                  <span class="node-order">节点 {{ index + 1 }}</span>
                  <Badge :variant="node.nodeType === 'CC' ? 'secondary' : 'outline'" class="mr-auto ml-2">{{ node.nodeType === 'CC' ? '抄送' : '审批' }}</Badge>
                  <div class="node-actions">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      :disabled="index === 0"
                      aria-label="上移节点"
                      @click="moveNode(index, 'up')"
                    >
                      <ArrowUp class="w-4 h-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      :disabled="index === form.nodes.length - 1"
                      aria-label="下移节点"
                      @click="moveNode(index, 'down')"
                    >
                      <ArrowDown class="w-4 h-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      class="text-destructive"
                      aria-label="删除节点"
                      @click="removeNode(index)"
                    >
                      <Trash2 class="w-4 h-4" />
                    </Button>
                  </div>
                </div>

                <div class="form-grid">
                  <div class="form-field">
                    <Label :for="`node-name-${index}`">节点名称 <span class="required">*</span></Label>
                    <Input
                      :id="`node-name-${index}`"
                      v-model="node.nodeName"
                      maxlength="100"
                      placeholder="例如：部门经理审批"
                    />
                  </div>

                  <div class="form-field">
                    <Label :for="`node-code-${index}`">节点编码 <span class="required">*</span></Label>
                    <Input
                      :id="`node-code-${index}`"
                      v-model="node.nodeCode"
                      maxlength="50"
                      placeholder="例如：DEPT_MANAGER"
                    />
                  </div>
                </div>

                <div class="form-field">
                  <Label :for="`node-assignees-${node.key}`">{{ node.nodeType === 'CC' ? '抄送对象' : '审批人员' }} <span class="required">*</span></Label>
                  <ApprovalNodeApproverPicker
                    :id="`node-assignees-${node.key}`"
                    v-model="node.assignees"
                    :disabled="submitting"
                  />
                  <p class="field-help">
                    {{ node.nodeType === 'CC'
                      ? '前面的审批通过，流程走到这里时发飞书消息，不需要处理，流程直接进入下一个节点。被抄送人可只读查看这一张单据。'
                      : '审批人员：只有选中的人能看到、能审批、收到通知，其中一人审了即通过。' }}
                  </p>
                </div>
              </div>
            </DataViewStatePanel>

            <div class="node-add-actions">
              <Button type="button" size="sm" variant="outline" @click="addNode('APPROVAL')">
                <Plus class="size-4" /> 添加审批节点
              </Button>
              <Button type="button" size="sm" variant="outline" :disabled="form.nodes.length === 0" @click="addNode('CC')">
                <Plus class="size-4" /> 添加抄送节点
              </Button>
            </div>
          </section>
        </DataViewStatePanel>
      </div>

      <DialogFooter>
        <Button type="button" variant="outline" :disabled="submitting" @click="handleCancel">
          取消
        </Button>
        <Button type="button" :disabled="submitting || loadingDetail" @click="handleSubmit">
          {{ submitting ? '保存中...' : (isEditMode ? '保存' : '创建') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.dialog-body {
  max-height: min(70vh, 720px);
  overflow-y: auto;
  padding-left: calc(2px + 2px);
  padding-right: $space-1;
}

.form-section {
  border-top: 1px solid hsl(var(--border));
  padding: $space-4 0;

  &:first-child {
    border-top: 0;
    padding-top: 0;
  }
}

.section-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-bottom: $space-3;
}

.section-title {
  color: hsl(var(--foreground));
  font-size: var(--font-size-body);
  font-weight: 600;
  line-height: 24px;
  margin: 0 0 $space-3;
}

.section-header .section-title {
  margin-bottom: 0;
}

.form-grid {
  display: grid;
  gap: $space-3;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: $space-3;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: $space-1;
}

.required,
.field-error {
  color: hsl(var(--status-danger));
}

.field-error {
  font-size: var(--font-size-caption);
  line-height: 20px;
  margin: 0;
}

.switch-row {
  align-items: center;
  display: flex;
  gap: $space-2;
  min-height: var(--touch-target);
}


.nodes-list {
  display: flex;
  flex-direction: column;
  gap: $space-3;
}

.node-item {
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius-md);
  padding: $space-4;
}

.node-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-bottom: $space-3;
}

.node-order {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-body);
  font-weight: 500;
}

.node-actions {
  display: flex;
  gap: $space-1;
}

.field-help {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  margin: 0;
}

.node-add-actions {
  display: flex;
  flex-wrap: wrap;
  gap: $space-2;
  margin-top: $space-3;
}


@media (max-width: $bp-sm) {
  .dialog-body {
    max-height: 72vh;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
