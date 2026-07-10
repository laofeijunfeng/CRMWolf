<script setup lang="ts">
/**
 * Customers.vue - 客户管理页面
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - AppLayout 提供 TopBar（56px）
 * - 页面 padding: 24px
 * - gap: 24px（组件间距）
 *
 * 改动清单：
 * - ✅ TopBar 集成（useHeaderStore）
 * - ✅ ContextTabs 组件（所有客户、我的客户、公海客户）
 * - ✅ FilterPanel 组件
 * - ✅ DataTable 组件
 * - ✅ V2 Design Tokens
 * - ✅ Flexbox 高度管理
 * - ✅ 移除活跃筛选汇总区
 * - ✅ 保留业务逻辑（退回公海、输单、赢单等）
 */
import { ref, reactive, computed, onMounted, onUnmounted, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, Sparkles, MoreHorizontal, ArrowRightLeft, TrendingUp, TrendingDown, XCircle, Trash2, Pencil } from 'lucide-vue-next'
import { FilterPanel, DataTable, TableRowActions, type ActionConfig } from '@/components/crmwolf'
import { Button } from '@/components/ui/button'
import { confirmDelete, confirmDialog } from '@/utils/confirmDialog'
import AICustomerCreateDialog from '@/components/AICustomerCreateDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import customerApi, {
  type CustomerResponse,
  type CustomerStatus,
  type CustomerReturnRequest,
  type ReturnReasonEnum,
  type CustomerLoseRequest
} from '@/api/customer'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const router = useRouter()
const userStore = useUserStore()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()

// ==================== State ====================
const loading = ref(false)
const tableData = ref<CustomerResponse[]>([])
const selectedCustomer = ref<CustomerResponse | null>(null)
const showAICustomerCreate = ref(false)

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// 退回公海弹窗
const returnModalVisible = ref(false)
const returnForm = reactive<CustomerReturnRequest>({
  return_reason: '' as ReturnReasonEnum,
  detailed_reason: ''
})

// 标记输单弹窗
const loseModalVisible = ref(false)
const loseForm = reactive<CustomerLoseRequest>({
  loss_reason: ''
})

// ==================== ContextTabs 配置 ====================
const tabs = [
  { key: 'all', label: '所有客户' },
  { key: 'my', label: '我的客户' },
  { key: 'public', label: '公海客户' }
]

const activeTab = ref('all')

// ==================== FilterPanel 配置 ====================
const filterFields = [
  { key: 'keyword', type: 'text' as const, label: '搜索', placeholder: '搜索客户名称' },
  {
    key: 'status',
    type: 'select' as const,
    label: '状态',
    placeholder: '全部状态',
    options: [
      { value: '0', label: '跟进中' },
      { value: '1', label: '已赢单' },
      { value: '2', label: '已输单' },
      { value: '3', label: '已失效' }
    ]
  }
]

const filterValues = reactive({
  keyword: '',
  status: ''
})

// ==================== DataTable 配置 ====================
const columns = [
  { key: 'account_name', title: '客户名称', width: '220px' },
  { key: 'industry', title: '行业', width: '120px' },
  { key: 'source', title: '来源', width: '120px' },
  { key: 'city', title: '城市', width: '100px' },
  { key: 'company_scale', title: '规模', width: '120px' },
  { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
  { key: 'score', title: '热力值', align: 'center' as const, width: '100px' },
  { key: 'default_procurement_method', title: '默认采购方式', width: '140px' },
  { key: 'owner', title: '负责人', width: '100px' },
  { key: 'creator', title: '创建人', width: '100px' },
  { key: 'created_time', title: '创建时间', width: '160px' },
  { key: 'actions', title: '操作', align: 'center' as const, width: '220px' }
]

// ==================== 权限 ====================
const canCreateCustomer = computed(() => permissionStore.hasPermission('customer:create'))
const canEditAllCustomer = computed(() => permissionStore.hasPermission('customer:edit:all'))
const canEditOwnCustomer = computed(() => permissionStore.hasPermission('customer:edit:own'))
const canDeleteAllCustomer = computed(() => permissionStore.hasPermission('customer:delete:all'))
const canDeleteOwnCustomer = computed(() => permissionStore.hasPermission('customer:delete:own'))
const canReturnCustomer = computed(() => permissionStore.hasPermission('customer:return'))
const canCreateOpportunity = computed(() => permissionStore.hasPermission('opportunity:create'))
const canAccessPublic = computed(() => permissionStore.hasAnyPermission(['customer:view:own', 'customer:view:all']))

// 行级权限检查函数
const canEditRow = (row: CustomerResponse): boolean => {
  if (canEditAllCustomer.value) return true
  if (canEditOwnCustomer.value && row['owner_id'] === String(userStore.userInfo?.id)) return true
  return false
}

const canDeleteRow = (row: CustomerResponse): boolean => {
  if (canDeleteAllCustomer.value) return true
  if (canDeleteOwnCustomer.value && row['owner_id'] === String(userStore.userInfo?.id)) return true
  return false
}

const canReturnRow = (row: CustomerResponse): boolean => {
  if (!canReturnCustomer.value) return false
  if (!row['owner_id']) return false
  if (canEditAllCustomer.value) return true
  if (canEditOwnCustomer.value && row['owner_id'] === String(userStore.userInfo?.id)) return true
  return false
}

// ==================== Methods ====================
const fetchCustomerList = async (): Promise<void> => {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      keyword: filterValues.keyword || null,
      status: filterValues.status ? parseInt(filterValues.status, 10) : null
    }

    if (activeTab.value === 'public') {
      const response = await customerApi.getPublicCustomers(params)
      tableData.value = Array.isArray(response) ? response : []
      pagination.total = Array.isArray(response) ? response.length : 0
    } else {
      if (activeTab.value === 'my') {
        params['owner_id'] = 'me'
      }

      const response = await customerApi.getCustomers(params)
      tableData.value = (response as any).data?.items || response || []
      pagination.total = (response as any).data?.total || (response as any).length || 0
    }
  } catch (error) {
    handleApiError(error, '获取客户列表')
  } finally {
    loading.value = false
  }
}

const handleSearch = (values: Record<string, any>): void => {
  Object.assign(filterValues, values)
  pagination.current = 1
  fetchCustomerList()
}

const handleReset = (): void => {
  filterValues.keyword = ''
  filterValues.status = ''
  pagination.current = 1
  fetchCustomerList()
}

const handlePageChange = (page: number): void => {
  pagination.current = page
  fetchCustomerList()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchCustomerList()
}

const handleViewDetail = (record: CustomerResponse): void => {
  router.push(`/customers/${record.id}`)
}

const handleEdit = (record: CustomerResponse): void => {
  router.push(`/customers/${record.id}/edit`)
}

const handleCreateOpportunity = (record: CustomerResponse): void => {
  router.push(`/customers/${record.id}/opportunities/create`)
}

const handleClaim = async (record: CustomerResponse): Promise<void> => {
  const confirmed = await confirmDialog(`确认要领取客户 "${record.account_name}" 吗？`, '确认领取')
  if (!confirmed) return

  try {
    await customerApi.claimCustomer(record.id, { owner_id: String(userStore.userInfo?.id ?? '') })
    toast.success('客户领取成功')
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '领取客户')
  }
}

const handleReturn = (record: CustomerResponse): void => {
  selectedCustomer.value = record
  returnForm.return_reason = '' as ReturnReasonEnum
  returnForm.detailed_reason = ''
  returnModalVisible.value = true
}

const handleReturnModalOk = async (): Promise<void> => {
  if (!selectedCustomer.value) return
  if (!returnForm.return_reason || !returnForm.detailed_reason) {
    toast.error('请填写退回原因和详细说明')
    return
  }

  try {
    await customerApi.returnToPool(selectedCustomer.value.id, returnForm)
    toast.success('客户已退回公海')
    returnModalVisible.value = false
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '退回公海')
  }
}

const handleWin = async (record: CustomerResponse): Promise<void> => {
  const confirmed = await confirmDialog(`确认要将客户 "${record.account_name}" 标记为赢单吗？`, '确认赢单')
  if (!confirmed) return

  try {
    await customerApi.updateCustomerStatus(record.id, { status: 1 as CustomerStatus })
    toast.success('客户已标记为赢单')
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '标记赢单')
  }
}

const handleLose = (record: CustomerResponse): void => {
  selectedCustomer.value = record
  loseForm.loss_reason = ''
  loseModalVisible.value = true
}

const handleLoseModalOk = async (): Promise<void> => {
  if (!selectedCustomer.value) return
  if (!loseForm.loss_reason) {
    toast.error('请输入输单原因')
    return
  }

  try {
    await customerApi.markAsLost(selectedCustomer.value.id, loseForm)
    toast.success('客户已标记为输单')
    loseModalVisible.value = false
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '标记输单')
  }
}

const handleInvalid = async (record: CustomerResponse): Promise<void> => {
  const confirmed = await confirmDialog(`确认要将客户 "${record.account_name}" 标记为失效吗？`, '确认失效')
  if (!confirmed) return

  try {
    await customerApi.updateCustomerStatus(record.id, { status: 3 as CustomerStatus })
    toast.success('客户已标记为失效')
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '标记失效')
  }
}

const handleDelete = async (record: CustomerResponse): Promise<void> => {
  const confirmed = await confirmDelete(`客户 "${record.account_name}"`)
  if (!confirmed) return

  try {
    await customerApi.deleteCustomer(record.id)
    toast.success('客户删除成功')
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '删除客户')
  }
}

// ==================== 格式化函数 ====================
const formatDateTime = (dateStr?: string): string => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  })
}

// 状态映射函数（数字状态 → 字符串状态）
const mapCustomerStatus = (status: number): 'following' | 'won' | 'lost' | 'expired' => {
  const map: Record<number, 'following' | 'won' | 'lost' | 'expired'> = {
    0: 'following',
    1: 'won',
    2: 'lost',
    3: 'expired'
  }
  return map[status] || 'following'
}

const getScoreIcon = (score: number | null): string => {
  if (score === null) return '❓'
  if (score >= 80) return '🔥'
  if (score >= 60) return '⚡'
  if (score >= 40) return '✅'
  return '❄️'
}

const getScoreColor = (score: number | null): string => {
  if (score === null) return '#d9d9d9'
  if (score >= 80) return '#ff4d4f'
  if (score >= 60) return '#faad14'
  if (score >= 40) return '#52c41a'
  return '#d9d9d9'
}

// ==================== Lifecycle ====================
onMounted(() => {
  fetchCustomerList()
})

// TopBar 配置（Tabs + Actions）
watchEffect(() => {
  // 注册 ContextTabs 到 TopBar
  headerStore.setTabs(tabs, activeTab.value)

  // 注册操作按钮
  headerStore.setActions([
    {
      id: 'ai-create-customer',
      label: 'AI 创建客户',
      icon: Sparkles,
      type: 'primary',
      handler: () => { showAICustomerCreate.value = true },
      visible: canCreateCustomer.value,
      ariaLabel: 'AI 创建客户'
    },
    {
      id: 'create-customer',
      label: '手动创建',
      icon: Plus,
      type: 'default',
      handler: () => router.push('/customers/create'),
      visible: canCreateCustomer.value,
      ariaLabel: '手动创建客户'
    }
  ])
})

// Watch activeTab changes from headerStore
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab
    pagination.current = 1
    fetchCustomerList()
  }
})

onUnmounted(() => {
  headerStore.clear()
})
</script>

<template>
  <div class="customers-page">
    <!-- FilterPanel -->
    <FilterPanel
      :fields="filterFields"
      @search="handleSearch"
      @reset="handleReset"
    />

    <!-- DataTable -->
    <DataTable
      :columns="columns"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      empty-title="暂无客户"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
    >
      <!-- 客户名称 -->
      <template #cell-account_name="{ row }">
        <span class="link-text" @click.stop="handleViewDetail(row)">
          {{ row.account_name }}
        </span>
      </template>

      <!-- 行业 -->
      <template #cell-industry="{ row }">
        <StatusBadge
          v-if="row.industry_info?.name"
          :status="row.industry_info.name"
          type="industry"
        />
        <span v-else class="text-muted-foreground">-</span>
      </template>

      <!-- 来源 -->
      <template #cell-source="{ row }">
        <StatusBadge
          v-if="row.source"
          :status="row.source"
          type="source"
        />
        <span v-else class="text-muted-foreground">-</span>
      </template>

      <!-- 城市 -->
      <template #cell-city="{ row }">
        {{ row.city || '-' }}
      </template>

      <!-- 规模 -->
      <template #cell-company_scale="{ row }">
        <StatusBadge
          v-if="row.company_scale"
          :status="row.company_scale"
          type="companyScale"
        />
        <span v-else class="text-muted-foreground">-</span>
      </template>

      <!-- 状态 -->
      <template #cell-status="{ row }">
        <StatusBadge :status="mapCustomerStatus(row.status)" type="customer" />
      </template>

      // 热力值
      <template #cell-score="{ row }">
        <div class="score-cell">
          <span class="score-icon" :style="{ color: getScoreColor((row as any).score) }">
            {{ getScoreIcon((row as any).score) }}
          </span>
          <span class="score-number">{{ (row as any).score ?? '--' }}</span>
        </div>
      </template>

      <!-- 默认采购方式 -->
      <template #cell-default_procurement_method="{ row }">
        {{ row.default_procurement_method_info?.name || '-' }}
      </template>

      <!-- 负责人 -->
      <template #cell-owner="{ row }">
        {{ row.owner_info?.name || '-' }}
      </template>

      <!-- 创建人 -->
      <template #cell-creator="{ row }">
        {{ row.creator_info?.name || '-' }}
      </template>

      <!-- 创建时间 -->
      <template #cell-created_time="{ row }">
        {{ formatDateTime(row.created_time) }}
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <!-- 公海客户：领取 -->
        <Button
          v-if="activeTab === 'public' && canAccessPublic"
          variant="ghost"
          size="sm"
          @click.stop="handleClaim(row)"
        >
          领取
        </Button>

        <!-- 非公海客户：使用 TableRowActions 组件 -->
        <TableRowActions
          v-else
          :row="row"
          :primary-actions="[
            {
              label: '新建商机',
              handler: handleCreateOpportunity,
              visible: canCreateOpportunity,
              icon: Sparkles
            },
            {
              label: '编辑',
              handler: handleEdit,
              visible: canEditRow(row),
              icon: Pencil
            }
          ]"
          :secondary-actions="[
            {
              label: '退回公海',
              handler: handleReturn,
              visible: canReturnRow(row),
              icon: ArrowRightLeft
            },
            {
              label: '赢单',
              handler: handleWin,
              visible: canEditRow(row),
              icon: TrendingUp
            },
            {
              label: '输单',
              handler: handleLose,
              visible: canEditRow(row),
              icon: TrendingDown,
              destructive: true,
              separator: true  // 在输单前添加分隔线，分隔普通操作和危险操作
            },
            {
              label: '失效',
              handler: handleInvalid,
              visible: canEditRow(row),
              icon: XCircle,
              destructive: true
            },
            {
              label: '删除',
              handler: handleDelete,
              visible: canDeleteRow(row),
              icon: Trash2,
              destructive: true
            }
          ]"
        />
      </template>
    </DataTable>

    <!-- 退回公海弹窗（临时样式，后续替换为 shadcn-vue Dialog）-->
    <div v-if="returnModalVisible" class="modal-overlay" @click="returnModalVisible = false">
      <div class="modal-content" @click.stop>
        <h3 class="modal-title">退回公海</h3>
        <div class="modal-body">
          <label class="form-label">退回原因 *</label>
          <select v-model="returnForm.return_reason" class="form-select">
            <option value="" disabled>请选择退回原因</option>
            <option value="丢单">丢单 - 客户已选择竞争对手</option>
            <option value="无意向">无意向 - 客户明确表示无合作意向</option>
            <option value="信息错误">信息错误 - 客户信息不准确或无效</option>
            <option value="长期未跟进">长期未跟进 - 超过规定时间未跟进</option>
            <option value="预算不足">预算不足 - 客户预算无法匹配产品价格</option>
            <option value="其他">其他</option>
          </select>
          <label class="form-label">详细原因 *</label>
          <textarea
            v-model="returnForm.detailed_reason"
            class="form-textarea"
            placeholder="请输入详细原因说明"
            rows="4"
            maxlength="500"
          />
        </div>
        <div class="modal-footer">
          <Button variant="outline" @click="returnModalVisible = false">取消</Button>
          <Button type="button" @click="handleReturnModalOk">确定</Button>
        </div>
      </div>
    </div>

    <!-- 标记输单弹窗 -->
    <div v-if="loseModalVisible" class="modal-overlay" @click="loseModalVisible = false">
      <div class="modal-content" @click.stop>
        <h3 class="modal-title">标记输单</h3>
        <div class="modal-body">
          <label class="form-label">输单原因 *</label>
          <textarea
            v-model="loseForm.loss_reason"
            class="form-textarea"
            placeholder="请输入输单原因说明"
            rows="4"
            maxlength="500"
          />
        </div>
        <div class="modal-footer">
          <Button variant="outline" @click="loseModalVisible = false">取消</Button>
          <Button type="button" @click="handleLoseModalOk">确定</Button>
        </div>
      </div>
    </div>

    <!-- AI 创建客户弹窗 -->
    <AICustomerCreateDialog
      v-model="showAICustomerCreate"
      @success="fetchCustomerList"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.customers-page {
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}

// 链接样式
.link-text {
  color: $wolf-text-link-v2;
  font-weight: $wolf-font-weight-medium-v2;
  cursor: pointer;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }
}

// 热力值单元格
.score-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.score-icon {
  font-size: 16px;
}

.score-number {
  font-weight: $wolf-font-weight-medium-v2;
  font-size: $wolf-font-size-auxiliary-v2;
}

// 简易弹窗样式（临时使用，后续替换为 shadcn-vue Dialog）
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-lg-v2;
  padding: $wolf-space-lg-v2;
  min-width: 400px;
  max-width: 500px;
}

.modal-title {
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  margin-bottom: $wolf-space-md-v2;
}

.modal-body {
  margin-bottom: $wolf-space-lg-v2;
}

.form-label {
  display: block;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-secondary-v2;
  margin-bottom: $wolf-space-xs-v2;
}

.form-select,
.form-textarea {
  width: 100%;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-primary-v2;
  margin-bottom: $wolf-space-md-v2;

  &:focus {
    outline: $wolf-focus-ring-width-v2 solid $wolf-primary-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.form-textarea {
  resize: vertical;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
}
</style>