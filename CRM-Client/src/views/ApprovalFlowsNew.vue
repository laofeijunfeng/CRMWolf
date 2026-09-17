<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import approvalFlowApi, { type ApprovalFlowListItem } from '@/api/approvalFlow'
import workflowApi, { type WorkflowDetail, type WorkflowSummary } from '@/api/workflow'
import ApprovalFlowFormDialog from '@/components/system-config/ApprovalFlowFormDialog.vue'
import WorkflowEditor from '@/components/workflow/WorkflowEditor.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { confirmDialog } from '@/utils/confirmDialog'
import { handleApiError } from '@/utils/errorHandler'
import { usePermissionStore } from '@/stores/permissions'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import SettingsContent from '@/views/settings/SettingsContent.vue'

const route = useRoute()

const permissionStore = usePermissionStore()

interface Props {
  active?: boolean
  embedded?: boolean
  action?: 'create' | 'edit' | ''
  recordId?: string
}

const props = defineProps<Props>()
const canReadApproval = computed(() => permissionStore.hasAnyPermission([
  'approval:flow:view',
  'approval:flow:create',
  'approval:flow:edit',
]))
const canCreate = computed(() => permissionStore.hasPermission('approval:flow:create'))
const canEdit = computed(() => permissionStore.hasPermission('approval:flow:edit'))
const canReadWorkflow = computed(() => permissionStore.hasPermission('automation:read'))
const canCreateWorkflow = computed(() => permissionStore.hasPermission('automation:create'))
const canEditWorkflow = computed(() => permissionStore.hasPermission('automation:edit'))
const canPublishWorkflow = computed(() => permissionStore.hasPermission('automation:publish'))

const flows = ref<ApprovalFlowListItem[]>([])
const workflows = ref<WorkflowSummary[]>([])
const loading = ref(false)
const workflowsLoading = ref(false)
const errorMessage = ref<string | null>(null)
const workflowErrorMessage = ref<string | null>(null)
const formOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingFlowId = ref<number | null>(null)
const workflowEditorOpen = ref(false)
const editingWorkflowId = ref<number | null>(null)
const togglingFlowId = ref<number | null>(null)
const workflowActionId = ref<number | null>(null)
const approvalLoaded = ref(false)
const workflowLoaded = ref(false)
const consumedAction = ref<string | null>(null)
const queryParam = (value: unknown): string => {
  if (typeof value === 'string') return value
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  return ''
}


const businessTypeLabels: Record<ApprovalFlowListItem['business_type'], string> = {
  CONTRACT: '合同', PAYMENT: '回款登记', INVOICE: '发票申请', INVOICE_REISSUE: '发票重开申请',
  LICENSE: 'License申请', OPPORTUNITY: '商机',
}
const actionableFlows = computed(() => flows.value.filter(flow => typeof flow.id === 'number'))
const workflowStatusLabels: Record<WorkflowSummary['status'], string> = {
  draft: '草稿', published: '已发布', paused: '已暂停',
}
const workflowStatusVariants: Record<WorkflowSummary['status'], 'secondary' | 'default' | 'outline'> = {
  draft: 'secondary', published: 'default', paused: 'outline',
}

async function loadFlows(): Promise<void> {
  if (!canReadApproval.value) return
  approvalLoaded.value = true
  loading.value = true
  errorMessage.value = null
  try {
    const data = await approvalFlowApi.getApprovalFlows()
    flows.value = Array.isArray(data) ? data : []
  } catch (error: unknown) {
    errorMessage.value = '加载审批流程失败，请稍后重试。'
    handleApiError(error, '获取审批流程')
  } finally { loading.value = false }
}

async function loadWorkflows(): Promise<void> {
  if (!canReadWorkflow.value) return
  workflowLoaded.value = true
  workflowsLoading.value = true
  workflowErrorMessage.value = null
  try {
    workflows.value = await workflowApi.list()
  } catch (error: unknown) {
    workflowErrorMessage.value = '加载工作流失败，请稍后重试。'
    handleApiError(error, '获取工作流')
  } finally { workflowsLoading.value = false }
}

function openCreate(): void { formMode.value = 'create'; editingFlowId.value = null; formOpen.value = true }
function openEdit(flowId: number): void { formMode.value = 'edit'; editingFlowId.value = flowId; formOpen.value = true }
function openWorkflowEditor(workflowId: number | null): void { editingWorkflowId.value = workflowId; workflowEditorOpen.value = true }
function closeWorkflowEditor(): void { workflowEditorOpen.value = false; editingWorkflowId.value = null }

function consumeAction(): void {
  const queryAction = queryParam(route.query['action'])
  const action = queryAction !== '' ? queryAction : (props.action ?? '')
  if (action !== 'create' && action !== 'edit') {
    consumedAction.value = null
    return
  }
  const queryId = queryParam(route.query['id'])
  const queryRecordId = queryParam(route.query['recordId'])
  const recordId = queryId !== '' ? queryId : (queryRecordId !== '' ? queryRecordId : (props.recordId ?? ''))
  const signature = `${action}:${recordId}`

  if (consumedAction.value === signature || formOpen.value) return
  if (action === 'create') {
    if (!canCreate.value) return
    openCreate()
  } else {
    if (!canEdit.value || !/^\d+$/.test(recordId)) return
    const flowId = Number(recordId)
    if (!Number.isSafeInteger(flowId) || flowId <= 0) return
    openEdit(flowId)
  }
  consumedAction.value = signature
}


async function toggleFlow(flow: ApprovalFlowListItem): Promise<void> {
  if (togglingFlowId.value !== null) return
  const nextActive = flow.is_active === 1 ? 0 : 1
  const action = nextActive === 1 ? '启用' : '停用'
  if (!await confirmDialog(`确定${action}“${flow.flow_name}”吗？`, `确认${action}`)) return
  togglingFlowId.value = flow.id
  try { await approvalFlowApi.updateApprovalFlow(flow.id, { is_active: nextActive }); await loadFlows() }
  catch (error: unknown) { handleApiError(error, `${action}审批流程`) }
  finally { togglingFlowId.value = null }
}

async function updateWorkflowStatus(workflow: WorkflowSummary, status: 'published' | 'paused'): Promise<void> {
  if (workflowActionId.value !== null) return
  workflowActionId.value = workflow.id
  try { await workflowApi.updateStatus(workflow.id, { status }); await loadWorkflows() }
  catch (error: unknown) { handleApiError(error, status === 'published' ? '发布工作流' : '暂停工作流') }
  finally { workflowActionId.value = null }
}

async function removeWorkflow(workflow: WorkflowSummary): Promise<void> {
  if (!canEditWorkflow.value || workflow.status !== 'draft' || workflowActionId.value !== null) return
  if (!await confirmDialog(`确定删除草稿“${workflow.name}”吗？`, '确认删除')) return
  workflowActionId.value = workflow.id
  try { await workflowApi.remove(workflow.id); await loadWorkflows() }
  catch (error: unknown) { handleApiError(error, '删除工作流') }
  finally { workflowActionId.value = null }
}

function handleFormSuccess(): void { formOpen.value = false; void loadFlows() }
function handleWorkflowSaved(_workflow: WorkflowDetail): void { closeWorkflowEditor(); void loadWorkflows() }
onMounted(() => {
  if (!approvalLoaded.value) void loadFlows()
  if (!workflowLoaded.value) void loadWorkflows()
  consumeAction()
})
watch(
  () => [permissionStore.loadState, canReadApproval.value, canReadWorkflow.value] as const,
  ([loadState, approvalReadable, workflowReadable], previous) => {
    if (loadState !== 'ready') return
    if (approvalReadable && (!approvalLoaded.value || previous?.[1] !== true)) void loadFlows()
    if (workflowReadable && (!workflowLoaded.value || previous?.[2] !== true)) void loadWorkflows()
  },
)
watch(() => [route.query['action'], route.query['id'], route.query['recordId'], props.action, props.recordId, canCreate.value, canEdit.value] as const, consumeAction, { immediate: true })


useTopBarRegistration({
  actionDeps: [canCreateWorkflow, canCreate, workflowEditorOpen],
  actions: () => workflowEditorOpen.value ? [] : [
    { id: 'create-workflow', label: '新建工作流', type: 'primary', visible: canCreateWorkflow.value, handler: (): void => { openWorkflowEditor(null) } },
    { id: 'create-approval-flow', label: '手动创建', type: 'default', visible: canCreate.value, handler: openCreate },
  ],
})

</script>

<template>
  <SettingsContent v-if="!workflowEditorOpen" ariaLabel="审批流程管理" description="CRM 侧审批流程配置预览，创建与编辑继续使用现有审批 API。">

      <Card v-if="canReadWorkflow" aria-label="工作流列表">
        <CardHeader>
          <CardTitle>工作流</CardTitle>
          <CardDescription>配置可复用的自动化工作流。</CardDescription>
        </CardHeader>
        <CardContent>
          <div v-if="workflowsLoading && workflows.length === 0" class="py-8 text-center text-sm text-muted-foreground" role="status">加载工作流...</div>
          <div v-else-if="workflowErrorMessage && workflows.length === 0" class="flex flex-col items-center gap-3 py-8 text-center">
            <p class="text-sm text-destructive">{{ workflowErrorMessage }}</p>
            <Button data-testid="workflow-retry" variant="outline" @click="loadWorkflows">重试</Button>
          </div>
          <template v-else>
            <div v-if="workflowErrorMessage" class="mb-4 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
              {{ workflowErrorMessage }}
              <Button data-testid="workflow-retry" size="sm" variant="outline" @click="loadWorkflows">重试</Button>
            </div>
            <div v-if="workflows.length === 0" class="py-8 text-center text-sm text-muted-foreground">暂无工作流</div>
            <div v-else class="grid gap-4 lg:grid-cols-2">
              <Card v-for="workflow in workflows" :key="workflow.id" :data-testid="`workflow-card-${workflow.id}`">
                <CardHeader class="gap-3">
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                      <CardTitle class="truncate">{{ workflow.name }}</CardTitle>
                      <CardDescription>{{ workflow.description || '暂无描述' }}</CardDescription>
                    </div>
                    <Badge :variant="workflowStatusVariants[workflow.status]">{{ workflowStatusLabels[workflow.status] }}</Badge>
                  </div>
                </CardHeader>
                <CardContent class="space-y-4">
                  <dl class="grid grid-cols-2 gap-3 text-sm">
                    <div><dt class="text-muted-foreground">节点数</dt><dd class="font-medium">{{ workflow.node_count }}</dd></div>
                    <div><dt class="text-muted-foreground">最近运行</dt><dd class="font-medium">暂未接入</dd></div>
                  </dl>
                  <div class="flex flex-wrap justify-end gap-2 border-t pt-4">
                    <Button v-if="canEditWorkflow" :data-testid="`workflow-edit-${workflow.id}`" variant="outline" @click="openWorkflowEditor(workflow.id)">编辑</Button>
                    <Button v-if="canPublishWorkflow && workflow.status === 'draft'" :data-testid="`workflow-publish-${workflow.id}`" @click="updateWorkflowStatus(workflow, 'published')">发布</Button>
                    <Button v-if="canPublishWorkflow && workflow.status === 'published'" :data-testid="`workflow-pause-${workflow.id}`" variant="outline" @click="updateWorkflowStatus(workflow, 'paused')">暂停</Button>
                    <Button v-if="canPublishWorkflow && workflow.status === 'paused'" :data-testid="`workflow-resume-${workflow.id}`" @click="updateWorkflowStatus(workflow, 'published')">恢复发布</Button>
                    <Button v-if="canEditWorkflow && workflow.status === 'draft'" :data-testid="`workflow-delete-${workflow.id}`" variant="destructive" @click="removeWorkflow(workflow)">删除草稿</Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </template>
        </CardContent>
      </Card>

      <template v-if="canReadApproval">
      <div v-if="loading && actionableFlows.length === 0" class="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground" role="status">加载审批流程...</div>
      <Card v-else-if="errorMessage && actionableFlows.length === 0">
        <CardContent class="flex flex-col items-center gap-3 py-10 text-center">
          <p class="text-sm text-destructive">{{ errorMessage }}</p>
          <Button data-testid="approval-flows-retry" variant="outline" @click="loadFlows">重试</Button>
        </CardContent>
      </Card>
      <template v-else>
        <div v-if="errorMessage" class="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
          {{ errorMessage }}
          <Button data-testid="approval-flows-retry" size="sm" variant="outline" @click="loadFlows">重试</Button>
        </div>
        <Card v-if="actionableFlows.length === 0">
          <CardContent class="flex flex-col items-center gap-3 py-10 text-center">
            <p class="text-sm text-muted-foreground">暂无审批流程</p>
            <Button v-if="canCreate" data-testid="approval-flows-create" variant="outline" @click="openCreate">手动创建</Button>
          </CardContent>
        </Card>
        <div v-else class="grid gap-4 lg:grid-cols-2">
          <Card v-for="flow in actionableFlows" :key="flow.id">
            <CardHeader class="gap-3">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <CardTitle class="truncate">{{ flow.flow_name }}</CardTitle>
                  <CardDescription class="mt-1 font-mono">{{ flow.flow_code }}</CardDescription>
                </div>
                <Badge :variant="flow.is_active === 1 ? 'default' : 'secondary'">{{ flow.is_active === 1 ? '启用' : '停用' }}</Badge>
              </div>
              <div class="flex flex-wrap gap-2"><Badge variant="outline">{{ businessTypeLabels[flow.business_type] }}</Badge></div>
            </CardHeader>
            <CardContent class="space-y-4">
              <p class="min-h-5 text-sm text-muted-foreground">{{ flow.description || '暂无描述' }}</p>
              <dl class="grid grid-cols-2 gap-3 text-sm">
                <div><dt class="text-muted-foreground">节点数</dt><dd class="font-medium">暂未提供</dd></div>
                <div><dt class="text-muted-foreground">最近运行：</dt><dd class="font-medium">暂未接入</dd></div>
                <div class="col-span-2"><dt class="text-muted-foreground">Activepieces：</dt><dd class="font-medium">暂未接入</dd></div>
              </dl>
              <div v-if="canEdit" class="flex justify-end gap-2 border-t pt-4">
                <Button :data-testid="`approval-flow-edit-${flow.id}`" variant="outline" @click="openEdit(flow.id)">编辑</Button>
                <Button :data-testid="`approval-flow-toggle-${flow.id}`" :disabled="togglingFlowId !== null" @click="toggleFlow(flow)">{{ flow.is_active === 1 ? '停用' : '启用' }}</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </template>
      </template>
  </SettingsContent>

  <div v-else class="min-h-[calc(100vh-8rem)]">
    <WorkflowEditor :workflow-id="editingWorkflowId" @saved="handleWorkflowSaved" @cancelled="closeWorkflowEditor" />
  </div>
  <ApprovalFlowFormDialog v-model:open="formOpen" :mode="formMode" :flow-id="editingFlowId" @success="handleFormSuccess" />
</template>
