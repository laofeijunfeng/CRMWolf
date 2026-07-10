<script setup lang="ts">
/**
 * OpportunityDetailSheet.vue - 商机详情抽屉组件
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - 使用 shadcn-vue Sheet 组件
 * - 宽度：右侧 2/3（66.67%）
 * - V2 Design Tokens
 *
 * 包含：
 * - 基本信息卡片
 * - 采购阶段流程
 * - 关联合同卡片
 * - 赢单/输单/编辑操作
 */
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Pencil, Trophy, XCircle, ExternalLink } from 'lucide-vue-next'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter
} from '@/components/ui/sheet'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import ProcurementStageFlow from '@/components/ProcurementStageFlow.vue'
import { opportunityApi, type Opportunity, type OpportunityWinRequest, type OpportunityLossRequest } from '@/api/opportunity'
import contractApi, { type ContractListResponse, type ContractStatus } from '@/api/contract'
import { usePermissionStore } from '@/stores/permissions'
import { formatCurrency } from '@/utils/format'

// ==================== Props & Emits ====================
interface Props {
  opportunityId: number | null
  visible: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
}>()

const router = useRouter()
const permissionStore = usePermissionStore()

// ==================== State ====================
const loading = ref(false)
const opportunity = ref<Opportunity | null>(null)
const relatedContract = ref<ContractListResponse | null>(null)
const contractLoading = ref(false)

// 赢单弹窗
const winDialogOpen = ref(false)
const winForm = ref<OpportunityWinRequest>({
  actual_amount: 0,
  actual_closing_date: new Date().toISOString().split('T')[0]
})
const winSubmitting = ref(false)

// 输单弹窗
const loseDialogOpen = ref(false)
const loseForm = ref<OpportunityLossRequest>({
  loss_reason: ''
})
const loseSubmitting = ref(false)

// ==================== Computed ====================
const canEdit = computed(() =>
  permissionStore.hasAnyPermission(['opportunity:update', 'opportunity:edit_own', 'opportunity:edit_all'])
)

const isActive = computed(() => opportunity.value?.status === 0)

// ==================== Methods ====================
const fetchOpportunityDetail = async () => {
  if (!props.opportunityId) return

  loading.value = true
  try {
    const data = await opportunityApi.getOpportunity(props.opportunityId)
    opportunity.value = data
    await fetchRelatedContract()
  } catch (error) {
    handleApiError(error, '获取商机详情')
  } finally {
    loading.value = false
  }
}

const fetchRelatedContract = async () => {
  if (!opportunity.value) return

  contractLoading.value = true
  try {
    const data = await contractApi.getContractByOpportunity(opportunity.value.id) as unknown as ContractListResponse
    relatedContract.value = data
  } catch (error: unknown) {
    if ((error as any)?.response?.status !== 404) {
      console.error('获取关联合同失败', error)
    }
    relatedContract.value = null
  } finally {
    contractLoading.value = false
  }
}

// ==================== 操作方法 ====================
const handleEdit = () => {
  if (!opportunity.value) return
  closeSheet()
  router.push(`/opportunities/${opportunity.value.id}/edit`)
}

const handleShowWinDialog = () => {
  if (!opportunity.value) return
  winForm.value = {
    actual_amount: opportunity.value.total_amount || 0,
    actual_closing_date: new Date().toISOString().split('T')[0]
  }
  winDialogOpen.value = true
}

const handleWinConfirm = async () => {
  if (!opportunity.value) return

  winSubmitting.value = true
  try {
    await opportunityApi.markAsWon(opportunity.value.id, winForm.value)
    toast.success('商机已标记为赢单')
    winDialogOpen.value = false
    closeSheet()
    emit('refresh')
  } catch (error) {
    handleApiError(error, '标记赢单')
  } finally {
    winSubmitting.value = false
  }
}

const handleShowLoseDialog = () => {
  loseForm.value = { loss_reason: '' }
  loseDialogOpen.value = true
}

const handleLoseConfirm = async () => {
  if (!opportunity.value) return
  if (!loseForm.value.loss_reason?.trim()) {
    toast.error('请输入输单原因')
    return
  }

  loseSubmitting.value = true
  try {
    await opportunityApi.markAsLost(opportunity.value.id, loseForm.value)
    toast.success('商机已标记为输单')
    loseDialogOpen.value = false
    closeSheet()
    emit('refresh')
  } catch (error) {
    handleApiError(error, '标记输单')
  } finally {
    loseSubmitting.value = false
  }
}

const handleCreateContract = () => {
  if (!opportunity.value) return
  closeSheet()
  router.push({
    path: '/contracts/create',
    query: { opportunityId: String(opportunity.value.id) }
  })
}

const handleViewContract = () => {
  if (!relatedContract.value) return
  closeSheet()
  router.push(`/contracts/${relatedContract.value.id}`)
}

const closeSheet = () => {
  emit('update:visible', false)
}

// ==================== 格式化函数 ====================
const formatDate = (dateStr: string | undefined): string => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const formatDateTime = (dateStr: string | undefined): string => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

const getStatusText = (status: number | undefined): string => {
  if (status === undefined) return '-'
  const map: Record<number, string> = { 0: '跟进中', 1: '已赢单', 2: '已输单' }
  return map[status] || '未知'
}

const getStatusClass = (status: number | undefined): string => {
  if (status === undefined) return ''
  const map: Record<number, string> = {
    0: 'status-warning',
    1: 'status-success',
    2: 'status-danger'
  }
  return map[status] || ''
}

const getPurchaseTypeText = (type: string | undefined): string => {
  if (!type) return '-'
  const map: Record<string, string> = { 'NEW': '新购', 'RENEWAL': '续购', 'EXPANSION': '增购' }
  return map[type] || type
}

const getPurchaseTypeClass = (type: string | undefined): string => {
  if (!type) return ''
  const map: Record<string, string> = { 'NEW': 'status-info', 'RENEWAL': 'status-success', 'EXPANSION': 'status-warning' }
  return map[type] || ''
}

const getLicenseTypeText = (type: string | undefined): string => {
  if (!type) return '-'
  return type === 'SUBSCRIPTION' ? '订阅制' : '买断制'
}

const getContractStatusText = (status: ContractStatus | undefined): string => {
  if (!status) return '-'
  const map: Record<string, string> = {
    'DRAFT': '草稿',
    'PENDING': '待签署',
    'ACTIVE': '生效中',
    'EXPIRED': '已过期',
    'TERMINATED': '已终止'
  }
  return map[status] || status
}

const getContractStatusClass = (status: ContractStatus | undefined): string => {
  if (!status) return ''
  const map: Record<string, string> = {
    'DRAFT': 'status-default',
    'PENDING': 'status-warning',
    'ACTIVE': 'status-success',
    'EXPIRED': 'status-danger',
    'TERMINATED': 'status-danger'
  }
  return map[status] || ''
}

// ==================== Watch ====================
watch(() => props.visible, (visible) => {
  if (visible && props.opportunityId) {
    fetchOpportunityDetail()
  }
})
</script>

<template>
  <!-- 商机详情抽屉 -->
  <Sheet :open="visible" @update:open="$emit('update:visible', $event)">
    <SheetContent
      side="right"
      class="w-2/3 max-w-[880px] sm:max-w-[880px] p-0 flex flex-col bg-white dark:bg-slate-900"
      style="z-index: 100"
    >
      <!-- Header -->
      <SheetHeader class="p-6 pb-4 border-b border-wolf-border-default-v2">
        <div class="flex items-center gap-4">
          <div v-if="opportunity" class="title-avatar">
            {{ opportunity.opportunity_name?.charAt(0) || '商' }}
          </div>
          <div class="flex-1 min-w-0">
            <SheetTitle class="text-lg font-semibold truncate">
              {{ opportunity?.opportunity_name || '商机详情' }}
            </SheetTitle>
            <SheetDescription class="flex items-center gap-2 mt-1">
              <Badge v-if="opportunity" :class="['status-badge', getStatusClass(opportunity.status)]">
                {{ getStatusText(opportunity.status) }}
              </Badge>
              <Badge v-if="opportunity" :class="['status-badge', getPurchaseTypeClass(opportunity.purchase_type)]">
                {{ getPurchaseTypeText(opportunity.purchase_type) }}
              </Badge>
            </SheetDescription>
          </div>
          <div v-if="opportunity" class="text-right">
            <div class="text-xs text-wolf-text-tertiary-v2">预计金额</div>
            <div class="text-xl font-semibold text-wolf-text-primary-v2">
              {{ formatCurrency(opportunity.total_amount) }}
            </div>
          </div>
        </div>
      </SheetHeader>

      <!-- Content -->
      <ScrollArea class="flex-1">
        <div class="p-6 space-y-6">
          <!-- 基本信息卡片 -->
          <Card v-if="opportunity" class="info-card">
            <CardContent class="p-0">
              <div class="p-4 border-b border-wolf-border-light-v2">
                <h3 class="text-sm font-semibold text-wolf-text-primary-v2">基本信息</h3>
              </div>
              <div class="p-4">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <div class="attribute-label">客户名称</div>
                    <router-link
                      v-if="opportunity.customer_info"
                      :to="`/customers/${opportunity.customer_id}`"
                      class="attribute-value link-text"
                      @click="closeSheet"
                    >
                      {{ opportunity.customer_info?.account_name || '-' }}
                    </router-link>
                    <span v-else class="attribute-value">-</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">负责人</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.owner_info?.name }">
                      {{ opportunity.owner_info?.name || '待分配' }}
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">采购用户数</div>
                    <span class="attribute-value">{{ opportunity.user_count || '-' }} 人</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">标准单价</div>
                    <span class="attribute-value">{{ formatCurrency(opportunity.unit_price) }}</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">采购方式</div>
                    <span class="attribute-value">
                      <Badge
                        v-if="opportunity.current_stage_snapshot?.procurement_method?.name"
                        class="status-badge status-info"
                      >
                        {{ opportunity.current_stage_snapshot.procurement_method.name }}
                      </Badge>
                      <span v-else>-</span>
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">预计成交日期</div>
                    <span class="attribute-value">{{ formatDate(opportunity.expected_closing_date) }}</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">授权模式</div>
                    <span class="attribute-value">{{ getLicenseTypeText(opportunity.license_type) }}</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">订阅年限</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.subscription_years }">
                      {{ opportunity.subscription_years ? `${opportunity.subscription_years} 年` : '-' }}
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">实际成交日期</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.actual_closing_date }">
                      {{ formatDate(opportunity.actual_closing_date) }}
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">创建时间</div>
                    <span class="attribute-value">{{ formatDateTime(opportunity.created_time) }}</span>
                  </div>

                  <div v-if="opportunity.status === 2" class="attribute-item">
                    <div class="attribute-label">输单原因</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.loss_reason }">
                      {{ opportunity.loss_reason || '-' }}
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <!-- 采购阶段流程 -->
          <Separator v-if="opportunity" />
          <ProcurementStageFlow v-if="opportunity" :opportunity-id="opportunity.id" />

          <!-- 关联合同卡片 -->
          <Separator v-if="opportunity" />
          <Card v-if="opportunity" class="contract-card">
            <CardHeader class="p-4 border-b border-wolf-border-light-v2">
              <h3 class="text-sm font-semibold text-wolf-text-primary-v2">关联合同</h3>
            </CardHeader>
            <CardContent class="p-4">
              <div v-if="contractLoading" class="py-8 text-center text-wolf-text-tertiary-v2">
                加载中...
              </div>

              <div v-else-if="!relatedContract" class="py-8 text-center">
                <p class="text-wolf-text-tertiary-v2 text-sm mb-4">暂无关联合同</p>
                <p v-if="opportunity.status === 1" class="text-wolf-text-tertiary-v2 text-xs mb-4">
                  商机已赢单，请及时创建合同以锁定交易
                </p>
                <Button
                  v-if="opportunity.status === 1"
                  size="sm"
                  @click="handleCreateContract"
                >
                  创建合同
                </Button>
              </div>

              <div v-else class="contract-content">
                <div class="contract-header">
                  <div class="flex items-center gap-3">
                    <div class="contract-avatar">
                      {{ relatedContract.contract_name?.charAt(0) || '合' }}
                    </div>
                    <div>
                      <div class="font-medium text-wolf-text-primary-v2">{{ relatedContract.contract_name }}</div>
                      <div class="flex items-center gap-2 mt-1">
                        <Badge :class="['status-badge', getContractStatusClass(relatedContract.status)]">
                          {{ getContractStatusText(relatedContract.status) }}
                        </Badge>
                        <span class="text-xs text-wolf-text-tertiary-v2">{{ relatedContract.contract_number }}</span>
                      </div>
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" @click="handleViewContract">
                    <ExternalLink class="w-4 h-4 mr-1" />
                    查看详情
                  </Button>
                </div>

                <Separator class="my-4" />

                <div class="attributes-grid grid-cols-4">
                  <div class="attribute-item">
                    <div class="attribute-label">采购用户数</div>
                    <span class="attribute-value">{{ relatedContract.user_count || '-' }} 人</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-label">合同金额</div>
                    <span class="attribute-value">{{ formatCurrency(relatedContract.total_amount) }}</span>
                  </div>
                  <div v-if="relatedContract.license_type === 'SUBSCRIPTION'" class="attribute-item">
                    <div class="attribute-label">订阅年限</div>
                    <span class="attribute-value" :class="{ 'not-filled': !relatedContract.subscription_years }">
                      {{ relatedContract.subscription_years ? `${relatedContract.subscription_years} 年` : '-' }}
                    </span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-label">到期日期</div>
                    <span class="attribute-value" :class="{ 'not-filled': !relatedContract.expiry_date }">
                      {{ relatedContract.expiry_date || '-' }}
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </ScrollArea>

      <!-- Footer -->
      <SheetFooter class="p-4 border-t border-wolf-border-default-v2 flex flex-row gap-2">
        <Button
          v-if="isActive && canEdit"
          variant="default"
          class="bg-wolf-success-v2 hover:bg-wolf-success-v2/90"
          @click="handleShowWinDialog"
        >
          <Trophy class="w-4 h-4 mr-2" />
          赢单
        </Button>
        <Button
          v-if="isActive && canEdit"
          variant="outline"
          class="text-wolf-danger-v2 border-wolf-danger-v2 hover:bg-wolf-danger-bg-v2"
          @click="handleShowLoseDialog"
        >
          <XCircle class="w-4 h-4 mr-2" />
          输单
        </Button>
        <Button
          v-if="canEdit"
          variant="outline"
          @click="handleEdit"
        >
          <Pencil class="w-4 h-4 mr-2" />
          编辑
        </Button>
      </SheetFooter>
    </SheetContent>
  </Sheet>

  <!-- 赢单确认弹窗 -->
  <Dialog v-model:open="winDialogOpen">
    <DialogContent class="sm:max-w-[425px]">
      <DialogHeader>
        <DialogTitle>标记赢单</DialogTitle>
        <DialogDescription>请输入实际成交金额和日期</DialogDescription>
      </DialogHeader>

      <div class="grid gap-4 py-4">
        <div class="grid gap-2">
          <Label for="actual_amount">实际成交金额</Label>
          <Input
            id="actual_amount"
            type="number"
            v-model.number="winForm.actual_amount"
            placeholder="请输入金额"
          />
        </div>
        <div class="grid gap-2">
          <Label for="actual_closing_date">实际成交日期</Label>
          <Input
            id="actual_closing_date"
            type="date"
            v-model="winForm.actual_closing_date"
          />
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="winDialogOpen = false">取消</Button>
        <Button :disabled="winSubmitting" @click="handleWinConfirm">
          {{ winSubmitting ? '处理中...' : '确认' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 输单确认弹窗 -->
  <Dialog v-model:open="loseDialogOpen">
    <DialogContent class="sm:max-w-[425px]">
      <DialogHeader>
        <DialogTitle>标记输单</DialogTitle>
        <DialogDescription>请输入输单原因</DialogDescription>
      </DialogHeader>

      <div class="grid gap-4 py-4">
        <div class="grid gap-2">
          <Label for="loss_reason">输单原因</Label>
          <Textarea
            id="loss_reason"
            v-model="loseForm.loss_reason"
            placeholder="请输入输单原因说明"
            :rows="4"
            :maxlength="500"
          />
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="loseDialogOpen = false">取消</Button>
        <Button
          variant="destructive"
          :disabled="loseSubmitting"
          @click="handleLoseConfirm"
        >
          {{ loseSubmitting ? '处理中...' : '确认输单' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.title-avatar {
  width: 48px;
  height: 48px;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold-v2;
  flex-shrink: 0;
}

.contract-avatar {
  width: 40px;
  height: 40px;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: $wolf-font-weight-semibold-v2;
  flex-shrink: 0;
}

.attributes-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $wolf-space-md-v2 $wolf-space-lg-v2;

  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.attribute-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.attribute-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  font-weight: $wolf-font-weight-medium-v2;
  word-break: break-all;

  &.not-filled {
    color: $wolf-text-placeholder-v2;
  }
}

.link-text {
  color: $wolf-text-link-v2;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium-v2;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }
}

// 状态 Badge
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-full-v2;
  white-space: nowrap;
}

.status-default {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.status-info {
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
}

.status-warning {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-success {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.status-danger {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

// 合同内容
.contract-content {
  width: 100%;
}

.contract-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: $wolf-space-md-v2;
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>