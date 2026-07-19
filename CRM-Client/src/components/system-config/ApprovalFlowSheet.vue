<script setup lang="ts">
/**
 * ApprovalFlowSheet.vue - 审批流程管理 Sheet
 *
 * 功能：
 * - 展示审批流程列表（ListCard）
 * - 搜索流程
 * - 查看流程详情（Dialog）
 * - 启用/禁用流程
 * - AI 创建流程（Dialog）
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - 使用 shadcn-vue Sheet 组件
 * - V2 Design Tokens
 * - z-index: Sheet z-[200], Dialog z-[1000]
 */
import { ref, computed, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Search, Plus, Eye, Pencil, Power, Wand2 } from 'lucide-vue-next'
import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { AmountText, ListCard } from '@/components/crmwolf'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDialog } from '@/utils/confirmDialog'
import approvalFlowApi, {
  type ApprovalFlowDetail,
  type ApprovalNode
} from '@/api/approvalFlow'
import ApprovalFlowFormDialog from './ApprovalFlowFormDialog.vue'
import ApprovalFlowAIDialog from '@/components/ApprovalFlowAIDialog.vue'

// ==================== Props & Emits ====================
interface Props {
  open: boolean
}

type Emits = (e: 'update:open', value: boolean) => void

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// ==================== State ====================
const loading = ref(false)
const approvalFlows = ref<ApprovalFlowDetail[]>([])
const searchText = ref('')
const filterStatus = ref('')
const filterLicenseType = ref('')
const filterBusinessType = ref('')
const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

type ApprovalFlowListItem = ApprovalFlowDetail & { id: number }

// 详情 Dialog
const detailDialogOpen = ref(false)
const currentFlow = ref<ApprovalFlowDetail | null>(null)

// 新建/编辑 Dialog
const formDialogOpen = ref(false)
const formDialogMode = ref<'create' | 'edit'>('create')
const editingFlowId = ref<number | null>(null)
const aiDialogOpen = ref(false)

// ==================== Computed ====================
const filteredFlows = computed(() => {
  let filtered = approvalFlows.value.filter((flow): flow is ApprovalFlowListItem => typeof flow.id === 'number')

  if (searchText.value !== '') {
    const search = searchText.value.toLowerCase()
    filtered = filtered.filter(flow =>
      flow.flow_name.toLowerCase().includes(search) ||
      flow.flow_code.toLowerCase().includes(search)
    )
  }

  if (filterStatus.value !== '') {
    filtered = filtered.filter(flow =>
      filterStatus.value === 'true' ? flow.is_active === 1 : flow.is_active !== 1
    )
  }

  if (filterLicenseType.value !== '') {
    filtered = filtered.filter(flow => flow.license_type === filterLicenseType.value)
  }

  if (filterBusinessType.value !== '') {
    filtered = filtered.filter(flow => flow.business_type === filterBusinessType.value)
  }

  return filtered
})

const listTitle = computed(() => `审批流程列表（${filteredFlows.value.length}）`)

// ==================== Business Type Labels ====================
const businessTypeLabels: Record<string, string> = {
  CONTRACT: '合同',
  PAYMENT: '回款登记',
  INVOICE: '发票申请',
  LICENSE: 'License申请',
  OPPORTUNITY: '商机'
}

const licenseTypeLabels: Record<string, string> = {
  SUBSCRIPTION: '订阅',
  PERPETUAL: '买断'
}

// ==================== API Methods ====================
const fetchApprovalFlows = async (): Promise<void> => {
  loading.value = true
  try {
    const params = {
      skip: (pagination.value.page - 1) * pagination.value.pageSize,
      limit: pagination.value.pageSize
    }
    const data = await approvalFlowApi.getApprovalFlows(params)
    approvalFlows.value = Array.isArray(data) ? data : []
    pagination.value.total = approvalFlows.value.length
  } catch (error) {
    handleApiError(error, '获取审批流程')
  } finally {
    loading.value = false
  }
}

// ==================== Actions ====================
const handleView = async (record: ApprovalFlowDetail): Promise<void> => {
  if (typeof record.id !== 'number') return
  try {
    const data = await approvalFlowApi.getApprovalFlowDetail(record.id)
    currentFlow.value = data
    detailDialogOpen.value = true
  } catch (error) {
    handleApiError(error, '获取流程详情')
  }
}

const handleEdit = (record: ApprovalFlowDetail): void => {
  if (typeof record.id !== 'number') return
  formDialogMode.value = 'edit'
  editingFlowId.value = record.id
  formDialogOpen.value = true
}

const handleToggleStatus = async (record: ApprovalFlowDetail): Promise<void> => {
  if (typeof record.id !== 'number') return
  const isActive = record.is_active === 1
  const action = isActive ? '禁用' : '启用'
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
    fetchApprovalFlows()
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
  fetchApprovalFlows()
}

const handleAICreated = (): void => {
  fetchApprovalFlows()
}

// ==================== Lifecycle ====================
watch(() => props.open, (open) => {
  if (open) {
    fetchApprovalFlows()
  }
})

// ==================== Helper Functions ====================
function formatDate(dateStr: string | undefined): string {
  if (dateStr === undefined || dateStr === '') return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function getSortedNodes(nodes: ApprovalNode[] | undefined): ApprovalNode[] {
  if (!nodes) return []
  return [...nodes].sort((a, b) => a.node_order - b.node_order)
}
</script>

<template>
  <Sheet :open="open" @update:open="emit('update:open', $event)">
    <DetailSheetContent>
      <SheetHeader class="system-config-sheet-header">
        <SheetTitle class="text-base font-semibold text-wolf-text-primary">审批流程管理</SheetTitle>
        <SheetDescription class="text-sm text-wolf-text-secondary">配置审批流程与节点</SheetDescription>
      </SheetHeader>
      <ScrollArea class="h-full">
        <!-- 搜索/操作栏 -->
        <div class="p-4 border-b space-y-4">
          <div class="flex items-center gap-4">
            <div class="relative flex-1">
              <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                v-model="searchText"
                placeholder="搜索流程名称、编码"
                class="pl-10"
              />
            </div>
            <Button @click="handleAICreate">
              <Wand2 class="w-4 h-4 mr-2" />
              AI 创建
            </Button>
            <Button @click="handleManualCreate">
              <Plus class="w-4 h-4 mr-2" />
              手动创建
            </Button>
          </div>

          <!-- 筛选栏 -->
          <div class="flex items-center gap-4">
            <Select v-model="filterStatus">
              <SelectTrigger class="w-[120px]">
                <SelectValue placeholder="筛选状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="true">启用</SelectItem>
                <SelectItem value="false">禁用</SelectItem>
              </SelectContent>
            </Select>

            <Select v-model="filterLicenseType">
              <SelectTrigger class="w-[120px]">
                <SelectValue placeholder="授权类型" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="SUBSCRIPTION">订阅</SelectItem>
                <SelectItem value="PERPETUAL">买断</SelectItem>
              </SelectContent>
            </Select>

            <Select v-model="filterBusinessType">
              <SelectTrigger class="w-[120px]">
                <SelectValue placeholder="单据类型" />
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
        </div>

        <!-- 列表区域 -->
        <div class="p-4">
          <ListCard
            :title="listTitle"
            :items="filteredFlows"
            :loading="loading"
            empty-text="暂无审批流程"
          >
            <template #itemMain="{ item }">
              <div class="font-medium text-wolf-text-primary">{{ item.flow_name }}</div>
              <div class="mt-1 text-xs text-muted-foreground">
                {{ item.flow_code }} ·
                <span v-if="item.min_amount || item.max_amount">
                  <AmountText :value="item.min_amount ?? 0" size="sm" tone="warning" />
                  <span> - </span>
                  <AmountText :value="item.max_amount ?? 0" size="sm" tone="warning" />
                </span>
                <span v-else>不限金额</span>
                · {{ formatDate(item.created_time) }}
              </div>
              <div v-if="item.description" class="mt-1 text-sm text-muted-foreground">
                {{ item.description }}
              </div>
            </template>

            <template #itemBadges="{ item }">
              <Badge variant="secondary">
                {{ businessTypeLabels[item.business_type] || item.business_type }}
              </Badge>
              <Badge v-if="item.license_type" variant="outline">
                {{ licenseTypeLabels[item.license_type] || item.license_type }}
              </Badge>
              <Badge variant="outline">节点 {{ item.nodes?.length || 0 }}</Badge>
              <Badge :variant="item.is_active ? 'default' : 'secondary'">
                {{ item.is_active ? '启用' : '禁用' }}
              </Badge>
            </template>

            <template #itemActions="{ item }">
              <Button variant="ghost" size="icon" title="查看" @click="handleView(item)">
                <Eye class="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" title="编辑" @click="handleEdit(item)">
                <Pencil class="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                :title="item.is_active ? '禁用' : '启用'"
                :class="item.is_active ? 'text-orange-500' : 'text-green-600'"
                @click="handleToggleStatus(item)"
              >
                <Power class="h-4 w-4" />
              </Button>
            </template>
          </ListCard>
        </div>
      </ScrollArea>
    </DetailSheetContent>
  </Sheet>

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
              <span v-if="currentFlow.min_amount || currentFlow.max_amount">
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

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.system-config-sheet-header {
  padding: $wolf-space-xl-v2;
  padding-bottom: $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-default-v2;
  background: $wolf-bg-card-v2;
}
</style>
