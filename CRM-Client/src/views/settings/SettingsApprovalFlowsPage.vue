<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { toast } from 'vue-sonner'
import { Plus } from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDialog } from '@/utils/confirmDialog'
import approvalFlowApi, {
  type ApprovalFlowDetail,
  type ApprovalFlowListItem,
  type ApprovalNode
} from '@/api/approvalFlow'
import ApprovalFlowFormDialog from '@/components/system-config/ApprovalFlowFormDialog.vue'
import ApprovalFlowAIDialog from '@/components/ApprovalFlowAIDialog.vue'
import { usePermissionStore } from '@/stores/permissions'
import { useTeamStore } from '@/stores/team'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { usePageTitle } from '@/composables/usePageTitle'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { AmountText, DataTable, TableRowActions } from '@/components/crmwolf'
import type { ActionConfig, TableRowActionSet } from '@/components/crmwolf'
import { defineListFields } from '@/components/crmwolf/listFieldCatalog'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import { settingsListColumn } from '@/views/settings/settingsListCatalog'
import { toFeedbackError } from '@/types/feedback'
import type { FeedbackError } from '@/types/feedback'
import SettingsContent from '@/views/settings/SettingsContent.vue'

usePageTitle()

const route = useRoute()
const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const { isOwner } = useSettingsAccess()

const submittedSearch = ref('')
const approvalFlows = ref<ApprovalFlowListItem[]>([])
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const listRequestId = ref(0)

const detailDialogOpen = ref(false)
const currentFlow = ref<ApprovalFlowDetail | null>(null)

const formDialogOpen = ref(false)
const formDialogMode = ref<'create' | 'edit'>('create')
const editingFlowId = ref<number | null>(null)
const aiDialogOpen = ref(false)

const canCreate = computed(() => isOwner.value || permissionStore.hasPermission('approval:flow:create'))
const canEdit = computed(() => isOwner.value || permissionStore.hasPermission('approval:flow:edit'))

const displayedFlows = computed(() => {
  const query = submittedSearch.value.trim().toLowerCase()
  const flows = approvalFlows.value.filter((flow): flow is ApprovalFlowListItem => typeof flow.id === 'number')
  if (query.length === 0) return flows
  return flows.filter((flow) => {
    const name = flow.flow_name.toLowerCase()
    const code = flow.flow_code.toLowerCase()
    return name.includes(query) || code.includes(query)
  })
})

const fields: ListFieldDefinition[] = defineListFields([
  settingsListColumn({ key: 'flow_name', label: '流程', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'business_type', label: '单据', column: true }),
  settingsListColumn({ key: 'amount_range', label: '金额范围', column: true }),
  settingsListColumn({ key: 'node_count', label: '节点', column: true }),
  settingsListColumn({ key: 'is_active', label: '状态', column: true }),
])

const businessTypeLabels: Record<string, string> = {
  CONTRACT: '合同',
  PAYMENT: '回款登记',
  INVOICE: '发票申请',
  INVOICE_REISSUE: '发票重开申请',
  LICENSE: 'License申请',
  OPPORTUNITY: '商机'
}

const licenseTypeLabels: Record<string, string> = {
  SUBSCRIPTION: '订阅',
  PERPETUAL: '买断'
}

const queryParam = (value: unknown): string => {
  if (typeof value === 'string') return value
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  return ''
}

const loadApprovalFlows = async (): Promise<void> => {
  const requestId = ++listRequestId.value
  loading.value = true
  loadError.value = null
  try {
    const data = await approvalFlowApi.getApprovalFlows()
    if (requestId !== listRequestId.value) return
    approvalFlows.value = Array.isArray(data) ? data : []
  } catch (error) {
    if (requestId !== listRequestId.value) return
    loadError.value = toFeedbackError(error, '审批流程')
  } finally {
    if (requestId === listRequestId.value) {
      loading.value = false
    }
  }
}

const handleView = async (record: ApprovalFlowListItem): Promise<void> => {
  if (typeof record.id !== 'number') return
  try {
    const data = await approvalFlowApi.getApprovalFlowDetail(record.id)
    currentFlow.value = data
    detailDialogOpen.value = true
  } catch (error) {
    handleApiError(error, '获取流程详情')
  }
}

const handleEdit = (record: ApprovalFlowListItem): void => {
  if (typeof record.id !== 'number') return
  formDialogMode.value = 'edit'
  editingFlowId.value = record.id
  formDialogOpen.value = true
}

const handleToggleStatus = async (record: ApprovalFlowListItem): Promise<void> => {
  if (typeof record.id !== 'number') return
  const isActive = record.is_active === 1
  const action = isActive ? '停用' : '启用'
  const confirmed = await confirmDialog(
    `确定要${action}流程"${record.flow_name}"吗？`,
    `确认${action}`
  )

  if (!confirmed) return

  try {
    await approvalFlowApi.updateApprovalFlow(record.id, {
      is_active: isActive ? 0 : 1
    })
    toast.success(`流程已${action}`)
    void loadApprovalFlows()
  } catch (error) {
    handleApiError(error, `${action}流程`)
  }
}

const handleManualCreate = (): void => {
  formDialogMode.value = 'create'
  editingFlowId.value = null
  formDialogOpen.value = true
}

const handleAICreate = (): void => {
  aiDialogOpen.value = true
}

const handleFormSuccess = (): void => {
  void loadApprovalFlows()
}

const handleAICreated = (): void => {
  void loadApprovalFlows()
}

const asFlowHandler = (handler: (row: ApprovalFlowListItem) => void): ActionConfig['handler'] => {
  return (row) => { handler(row as ApprovalFlowListItem) }
}

const getRowActions = (row: ApprovalFlowListItem): TableRowActionSet => {
  const isActive = row.is_active === 1
  return {
    primaryActions: [{
      id: 'edit',
      label: '编辑',
      desktopPrimary: true,
      visible: canEdit.value,
      handler: asFlowHandler(handleEdit),
    }],
    secondaryActions: [
      { label: '查看', kind: 'standard', visible: true, handler: asFlowHandler((flow) => { void handleView(flow) }) },
      { label: isActive ? '停用' : '启用', visible: canEdit.value, handler: asFlowHandler((flow) => { void handleToggleStatus(flow) }) },
    ],
  }
}

useTopBarRegistration({
  actionDeps: [canCreate],
  actions: () => [
    { id: 'create-flow', label: '手动创建', type: 'primary', icon: Plus, visible: canCreate.value, handler: handleManualCreate },
    { id: 'ai-create-flow', label: 'AI 创建', type: 'default', visible: canCreate.value, handler: handleAICreate },
  ],
})

const handleSearchApply = (value: string): void => {
  submittedSearch.value = value.trim()
}

const handleSearchClear = (): void => {
  submittedSearch.value = ''
}

function getSortedNodes(nodes: ApprovalNode[] | undefined): ApprovalNode[] {
  if (!nodes) return []
  return [...nodes].sort((a, b) => a.node_order - b.node_order)
}

function hasAmountRange(minAmount: number | null | undefined, maxAmount: number | null | undefined): boolean {
  return (minAmount !== null && minAmount !== undefined) || (maxAmount !== null && maxAmount !== undefined)
}

watch(() => [route.query['action'], canCreate.value] as const, ([action]) => {
  if (queryParam(action) === 'create' && canCreate.value) {
    handleManualCreate()
  }
}, { immediate: true })

watch(() => [route.query['action'], route.query['id'], approvalFlows.value.length, canEdit.value] as const, ([action, id]) => {
  const actionValue = queryParam(action)
  const idValue = queryParam(id)
  if (actionValue === 'edit' && idValue !== '' && canEdit.value) {
    const flow = approvalFlows.value.find(item => String(item.id) === idValue)
    if (flow !== undefined) handleEdit(flow)
  }
}, { immediate: true })

watch(() => teamStore.currentTeam?.id, () => {
  void loadApprovalFlows()
}, { immediate: true })
</script>

<template>
  <SettingsContent ariaLabel="审批流程管理" description="配置审批流程、节点和启停状态。短任务继续用对话框。">
    <DataTable
      :fields="fields"
      :data="displayedFlows"
      :loading="loading"
      :load-error="loadError"
      :page="1"
      :page-size="Math.max(displayedFlows.length, 1)"
      :total="displayedFlows.length"
      height-strategy="page"
      scroll-mode="page"
      compact-pagination
      empty-title="暂无审批流程"
      :empty-reason="submittedSearch.trim() !== '' ? 'filtered' : 'not-created'"
      :get-row-actions="getRowActions"
      mobile-title-key="flow_name"
      :mobile-meta-keys="['flow_code']"
      search-enabled
      :search="submittedSearch"
      search-placeholder="搜索流程名称、编码"
      :search-loading="loading"
      @search-apply="handleSearchApply"
      @search-clear="handleSearchClear"
      @retry="loadApprovalFlows"
    >
      <template #cell-flow_name="{ row }">
        <div class="font-medium text-wolf-text-primary">{{ row.flow_name }}</div>
        <div class="mt-1 text-xs text-muted-foreground">
          {{ row.flow_code }}
        </div>
        <div v-if="row.description" class="mt-1 text-sm text-muted-foreground">
          {{ row.description }}
        </div>
      </template>
      <template #cell-business_type="{ row }">
        <Badge variant="secondary">
          {{ businessTypeLabels[row.business_type] || row.business_type }}
        </Badge>
        <Badge v-if="row.license_type" variant="outline">
          {{ licenseTypeLabels[row.license_type] || row.license_type }}
        </Badge>
      </template>
      <template #cell-amount_range="{ row }">
        <span v-if="hasAmountRange(row.min_amount, row.max_amount)">
          <AmountText :value="row.min_amount ?? 0" size="sm" tone="warning" />
          <span> - </span>
          <AmountText :value="row.max_amount ?? 0" size="sm" tone="warning" />
        </span>
        <span v-else>不限金额</span>
      </template>
      <template #cell-node_count="{ row }">
        {{ row.nodes?.length || 0 }}
      </template>
      <template #cell-is_active="{ row }">
        <Badge :variant="row.is_active ? 'default' : 'secondary'">
          {{ row.is_active ? '启用' : '禁用' }}
        </Badge>
      </template>
      <template #mobile-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>
    </DataTable>
  </SettingsContent>

  <!-- 流程详情 Dialog (z-[1000]) -->
  <Dialog v-model:open="detailDialogOpen">
    <DialogContent class="max-w-2xl max-h-[90vh] overflow-y-auto z-[1000]">
      <DialogHeader>
        <DialogTitle>流程详情 - {{ currentFlow?.flow_name }}</DialogTitle>
        <DialogDescription>
          查看审批流程详细信息
        </DialogDescription>
      </DialogHeader>

      <div v-if="currentFlow" class="space-y-6">
        <!-- 基本信息 -->
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1">
            <div class="text-sm text-muted-foreground">流程名称</div>
            <div class="font-medium">{{ currentFlow.flow_name }}</div>
          </div>
          <div class="space-y-1">
            <div class="text-sm text-muted-foreground">流程编码</div>
            <div class="font-medium">{{ currentFlow.flow_code }}</div>
          </div>
          <div class="space-y-1">
            <div class="text-sm text-muted-foreground">金额范围</div>
            <div class="font-medium">
              <span v-if="hasAmountRange(currentFlow.min_amount, currentFlow.max_amount)">
                <AmountText :value="currentFlow.min_amount ?? 0" tone="warning" />
                <span> - </span>
                <AmountText :value="currentFlow.max_amount ?? 0" tone="warning" />
              </span>
              <span v-else class="text-muted-foreground">不限</span>
            </div>
          </div>
          <div class="space-y-1">
            <div class="text-sm text-muted-foreground">授权类型</div>
            <div class="font-medium">
              <Badge v-if="currentFlow.license_type" variant="outline">
                {{ licenseTypeLabels[currentFlow.license_type] || currentFlow.license_type }}
              </Badge>
              <span v-else class="text-muted-foreground">不限</span>
            </div>
          </div>
          <div class="space-y-1">
            <div class="text-sm text-muted-foreground">单据类型</div>
            <div class="font-medium">
              <Badge variant="secondary">
                {{ businessTypeLabels[currentFlow.business_type] || currentFlow.business_type }}
              </Badge>
            </div>
          </div>
          <div class="space-y-1">
            <div class="text-sm text-muted-foreground">状态</div>
            <div class="font-medium">
              <Badge :variant="currentFlow.is_active ? 'default' : 'secondary'">
                {{ currentFlow.is_active ? '启用' : '禁用' }}
              </Badge>
            </div>
          </div>
        </div>

        <!-- 描述 -->
        <div v-if="currentFlow.description" class="space-y-1">
          <div class="text-sm text-muted-foreground">描述</div>
          <div class="text-sm">{{ currentFlow.description }}</div>
        </div>

        <!-- 审批节点 -->
        <div class="space-y-3">
          <div class="text-sm font-semibold">审批节点</div>
          <div v-if="currentFlow.nodes && currentFlow.nodes.length > 0" class="space-y-3">
            <div
              v-for="node in getSortedNodes(currentFlow.nodes)"
              :key="node.id"
              class="p-4 rounded-lg border bg-card"
            >
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                  <Badge variant="outline">{{ node.node_order }}</Badge>
                  <span class="font-medium">{{ node.node_name }}</span>
                  <Badge v-if="node.is_required" variant="destructive" class="text-xs">必须</Badge>
                  <Badge v-else variant="secondary" class="text-xs">可选</Badge>
                </div>
              </div>
              <div class="text-sm text-muted-foreground space-y-1">
                <div>编码：{{ node.node_code }}</div>
                <div>审批角色：{{ node.approve_role }}</div>
                <div v-if="node.description">描述：{{ node.description }}</div>
              </div>
            </div>
          </div>
          <Empty v-else class="min-h-[160px] border-0 py-6">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <Plus class="h-5 w-5" aria-hidden="true" />
              </EmptyMedia>
              <EmptyTitle class="text-sm font-medium">暂无审批节点</EmptyTitle>
            </EmptyHeader>
          </Empty>
        </div>
      </div>
    </DialogContent>
  </Dialog>

  <ApprovalFlowFormDialog
    v-model:open="formDialogOpen"
    :mode="formDialogMode"
    :flow-id="editingFlowId"
    @success="handleFormSuccess"
  />

  <ApprovalFlowAIDialog
    v-model="aiDialogOpen"
    @created="handleAICreated"
  />
</template>
