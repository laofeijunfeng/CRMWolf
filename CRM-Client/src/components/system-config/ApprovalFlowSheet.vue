<script setup lang="ts">
/**
 * ApprovalFlowSheet.vue - 审批流程管理 Sheet
 *
 * 功能：
 * - 展示审批流程列表（DataTable）
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
import { useRouter } from 'vue-router'
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
import { DataTable } from '@/components/crmwolf'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
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

// ==================== Props & Emits ====================
interface Props {
  open: boolean
}

type Emits = (e: 'update:open', value: boolean) => void

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const router = useRouter()

// ==================== State ====================
const loading = ref(false)
const approvalFlows = ref<ApprovalFlowDetail[]>([])
const searchText = ref('')
const filterStatus = ref<string | undefined>(undefined)
const filterLicenseType = ref<string | undefined>(undefined)
const filterBusinessType = ref<string | undefined>(undefined)
const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

// 详情 Dialog
const detailDialogOpen = ref(false)
const currentFlow = ref<ApprovalFlowDetail | null>(null)

// ==================== Types ====================
interface Column {
  key: string
  title: string
  width?: string
  align?: 'left' | 'center' | 'right'
  fixed?: 'left' | 'right'
}

// ==================== Table Columns ====================
const columns: Column[] = [
  {
    key: 'flow_name',
    title: '流程名称',
    width: '150px',
    fixed: 'left'
  },
  {
    key: 'flow_code',
    title: '流程编码',
    width: '120px'
  },
  {
    key: 'amount_range',
    title: '金额范围',
    width: '150px'
  },
  {
    key: 'license_type',
    title: '授权类型',
    width: '100px'
  },
  {
    key: 'business_type',
    title: '单据类型',
    width: '100px'
  },
  {
    key: 'nodes_count',
    title: '节点数',
    width: '80px',
    align: 'center'
  },
  {
    key: 'is_active',
    title: '状态',
    width: '80px',
    align: 'center'
  },
  {
    key: 'created_time',
    title: '创建时间',
    width: '160px'
  },
  {
    key: 'actions',
    title: '操作',
    width: '200px',
    fixed: 'right',
    align: 'center'
  }
]

// ==================== Computed ====================
const filteredFlows = computed(() => {
  let filtered = approvalFlows.value

  if (searchText.value) {
    const search = searchText.value.toLowerCase()
    filtered = filtered.filter(flow =>
      flow.flow_name.toLowerCase().includes(search) ||
      flow.flow_code.toLowerCase().includes(search)
    )
  }

  if (filterStatus.value !== undefined) {
    filtered = filtered.filter(flow =>
      filterStatus.value === 'true' ? flow.is_active : !flow.is_active
    )
  }

  if (filterLicenseType.value) {
    filtered = filtered.filter(flow => flow.license_type === filterLicenseType.value)
  }

  if (filterBusinessType.value) {
    filtered = filtered.filter(flow => flow.business_type === filterBusinessType.value)
  }

  return filtered
})

// ==================== Business Type Labels ====================
const businessTypeLabels: Record<string, string> = {
  CONTRACT: '合同',
  PAYMENT: '回款登记',
  INVOICE: '发票申请',
  LICENSE: 'License申请'
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
  if (!record.id) return
  try {
    const data = await approvalFlowApi.getApprovalFlowDetail(record.id)
    currentFlow.value = data
    detailDialogOpen.value = true
  } catch (error) {
    handleApiError(error, '获取流程详情')
  }
}

const handleEdit = (record: ApprovalFlowDetail): void => {
  if (!record.id) return
  router.push(`/approval-flows/${record.id}/edit`)
}

const handleToggleStatus = async (record: ApprovalFlowDetail): Promise<void> => {
  if (!record.id) return
  const action = record.is_active ? '禁用' : '启用'
  const confirmed = await confirmDialog(
    `确定要${action}流程"${record.flow_name}"吗？`,
    `确认${action}`
  )

  if (!confirmed) return

  try {
    await approvalFlowApi.updateApprovalFlow(record.id, {
      is_active: record.is_active ? 0 : 1
    })
    toast.success(`流程已${action}`)
    fetchApprovalFlows()
  } catch (error) {
    handleApiError(error, `${action}流程`)
  }
}

const handleManualCreate = (): void => {
  router.push('/approval-flows/create')
}

const handleAICreate = (): void => {
  // TODO: Open AI creation dialog
  toast.info('AI 创建流程功能开发中')
}

// ==================== Lifecycle ====================
watch(() => props.open, (open) => {
  if (open) {
    fetchApprovalFlows()
  }
})

// ==================== Helper Functions ====================
function formatAmount(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '0'
  return amount.toLocaleString()
}

function formatDate(dateStr: string | undefined): string {
  if (!dateStr) return '-'
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
    <SheetHeader>
      <SheetTitle>审批流程管理</SheetTitle>
      <SheetDescription>配置审批流程与节点</SheetDescription>
    </SheetHeader>
    <DetailSheetContent>
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
              </SelectContent>
            </Select>
          </div>
        </div>

        <!-- 表格区域 -->
        <div class="p-4">
          <DataTable
            :columns="columns"
            :data="filteredFlows"
            :loading="loading"
            :total="pagination.total"
            :page="pagination.page"
            :page-size="pagination.pageSize"
            height="calc(100vh - 400px)"
            empty-title="暂无审批流程"
          >
            <!-- 流程名称列 -->
            <template #cell-flow_name="{ row }">
              <span class="text-primary font-medium cursor-pointer hover:underline">
                {{ row.flow_name }}
              </span>
            </template>

            <!-- 金额范围列 -->
            <template #cell-amount_range="{ row }">
              <span v-if="row.min_amount || row.max_amount">
                ¥{{ formatAmount(row.min_amount) }} - ¥{{ formatAmount(row.max_amount) }}
              </span>
              <span v-else class="text-muted-foreground">不限</span>
            </template>

            <!-- 授权类型列 -->
            <template #cell-license_type="{ row }">
              <Badge v-if="row.license_type" variant="outline">
                {{ licenseTypeLabels[row.license_type] || row.license_type }}
              </Badge>
              <span v-else class="text-muted-foreground">不限</span>
            </template>

            <!-- 单据类型列 -->
            <template #cell-business_type="{ row }">
              <Badge variant="secondary">
                {{ businessTypeLabels[row.business_type] || row.business_type }}
              </Badge>
            </template>

            <!-- 节点数列 -->
            <template #cell-nodes_count="{ row }">
              <Badge variant="outline">{{ row.nodes?.length || 0 }}</Badge>
            </template>

            <!-- 状态列 -->
            <template #cell-is_active="{ row }">
              <Badge :variant="row.is_active ? 'default' : 'secondary'">
                {{ row.is_active ? '启用' : '禁用' }}
              </Badge>
            </template>

            <!-- 创建时间列 -->
            <template #cell-created_time="{ row }">
              {{ formatDate(row.created_time) }}
            </template>

            <!-- 操作列 -->
            <template #cell-actions="{ row }">
              <div class="flex items-center justify-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  class="h-8 px-2"
                  @click="handleView(row)"
                >
                  <Eye class="w-3.5 h-3.5 mr-1" />
                  查看
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  class="h-8 px-2"
                  @click="handleEdit(row)"
                >
                  <Pencil class="w-3.5 h-3.5 mr-1" />
                  编辑
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  class="h-8 px-2"
                  :class="row.is_active ? 'text-orange-500' : 'text-green-500'"
                  @click="handleToggleStatus(row)"
                >
                  <Power class="w-3.5 h-3.5 mr-1" />
                  {{ row.is_active ? '禁用' : '启用' }}
                </Button>
              </div>
            </template>
          </DataTable>
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
                ¥{{ formatAmount(currentFlow.min_amount) }} - ¥{{ formatAmount(currentFlow.max_amount) }}
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
          <div v-else class="text-sm text-muted-foreground text-center py-8">
            暂无审批节点
          </div>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>