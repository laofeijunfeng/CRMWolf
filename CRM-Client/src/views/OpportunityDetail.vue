<template>
  <div class="opportunity-detail-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <el-button class="back-btn" @click="handleBack" aria-label="返回">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
      </div>
      <div class="header-right">
        <el-button v-if="opportunity?.status === 0 && canEditOpportunity" type="success" size="small" @click="handleShowWinModal">
          赢单
        </el-button>
        <el-button v-if="opportunity?.status === 0 && canEditOpportunity" type="danger" size="small" @click="handleShowLoseModal">
          输单
        </el-button>
        <el-button v-if="opportunity?.status === 0 && canEditOpportunity" type="primary" size="small" @click="handleEdit">
          编辑
        </el-button>
      </div>
    </div>

    <!-- 商机信息卡片 -->
    <div class="info-card">
      <div v-loading="loading">
        <el-empty v-if="!opportunity" description="商机信息加载失败" />

        <div v-else class="info-content">
          <!-- 上部分：标题和金额 -->
          <div class="info-top">
            <div class="info-left">
              <div class="title-section">
                <div class="title-avatar">{{ opportunity?.opportunity_name?.charAt(0) || '商' }}</div>
                <div class="title-content">
                  <h2 class="title-name">{{ opportunity?.opportunity_name }}</h2>
                  <div class="title-tags">
                    <span :class="['status-tag', getStatusClass(opportunity?.status)]">
                      {{ getStatusText(opportunity?.status) }}
                    </span>
                    <span :class="['status-tag', getPurchaseTypeClass(opportunity?.purchase_type)]">
                      {{ getPurchaseTypeText(opportunity?.purchase_type) }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div class="info-right">
              <div class="amount-section">
                <div class="amount-label">预计金额</div>
                <div class="amount-value">{{ formatAmount(opportunity?.total_amount) }}</div>
              </div>
            </div>
          </div>

          <div class="info-divider"></div>

          <!-- 下部分：属性网格 -->
          <div class="info-bottom">
            <div class="attributes-grid">
              <div class="attribute-item">
                <div class="attribute-label">客户名称</div>
                <span class="attribute-value">
                  <router-link v-if="opportunity?.customer_info" :to="`/customers/${opportunity.customer_id}`" class="link-text">
                    {{ opportunity.customer_info?.account_name || '-' }}
                  </router-link>
                  <span v-else>-</span>
                </span>
              </div>

              <div class="attribute-item">
                <div class="attribute-label">负责人</div>
                <span class="attribute-value" :class="{ 'not-filled': !opportunity?.owner_info?.name }">
                  {{ opportunity?.owner_info?.name || '待分配' }}
                </span>
              </div>

              <div class="attribute-item">
                <div class="attribute-label">采购用户数</div>
                <span class="attribute-value">{{ opportunity?.user_count }} 人</span>
              </div>

              <div class="attribute-item">
                <div class="attribute-label">标准单价</div>
                <span class="attribute-value">{{ formatAmount(opportunity?.unit_price) }}</span>
              </div>

              <div class="attribute-item">
                <div class="attribute-label">采购方式</div>
                <span class="attribute-value">
                  <span v-if="opportunity?.current_stage_snapshot?.procurement_method?.name" class="status-tag status-info">
                    {{ opportunity.current_stage_snapshot.procurement_method.name }}
                  </span>
                  <span v-else>-</span>
                </span>
              </div>

              <div class="attribute-item">
                <div class="attribute-label">预计成交日期</div>
                <span class="attribute-value">{{ formatDate(opportunity?.expected_closing_date || '') }}</span>
              </div>

              <div class="attribute-item">
                <div class="attribute-label">授权模式</div>
                <span class="attribute-value">{{ getLicenseTypeText(opportunity?.license_type) }}</span>
              </div>

              <div class="attribute-item">
                <div class="attribute-label">订阅年限</div>
                <span class="attribute-value" :class="{ 'not-filled': !opportunity?.subscription_years }">
                  {{ opportunity?.subscription_years ? `${opportunity.subscription_years} 年` : '-' }}
                </span>
              </div>

              <div class="attribute-item">
                <div class="attribute-label">实际成交日期</div>
                <span class="attribute-value" :class="{ 'not-filled': !opportunity?.actual_closing_date }">
                  {{ formatDate(opportunity?.actual_closing_date || '') }}
                </span>
              </div>

              <div class="attribute-item">
                <div class="attribute-label">创建时间</div>
                <span class="attribute-value">{{ formatDateTime(opportunity?.created_time) }}</span>
              </div>

              <div v-if="opportunity?.status === 2" class="attribute-item">
                <div class="attribute-label">输单原因</div>
                <span class="attribute-value" :class="{ 'not-filled': !opportunity?.loss_reason }">
                  {{ opportunity?.loss_reason || '-' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 采购阶段流程 -->
    <div class="stage-flow-wrapper">
      <ProcurementStageFlow v-if="opportunity" :opportunity-id="opportunity.id" />
    </div>

    <!-- 关联合同卡片 -->
    <div class="contract-card">
      <div class="card-header">
        <span class="card-title">关联合同</span>
      </div>
      <div v-loading="contractLoading" class="card-body">
        <el-empty v-if="!relatedContract" description="创建合同，锁定商机">
          <template v-if="opportunity?.status === 1">
            <p class="empty-tip">商机已赢单，请及时创建合同以锁定交易</p>
            <el-button type="primary" size="small" @click="handleCreateContract">
              创建合同
            </el-button>
          </template>
          <template v-else>
            <p class="empty-tip">当商机状态变为"赢单"后，可在此创建合同</p>
          </template>
        </el-empty>

        <div v-else class="contract-content">
          <div class="contract-header">
            <div class="title-section">
              <div class="title-avatar">{{ relatedContract.contract_name?.charAt(0) || '合' }}</div>
              <div class="title-content">
                <h3 class="title-name">{{ relatedContract.contract_name }}</h3>
                <div class="contract-meta">
                  <span :class="['status-tag', getContractStatusClass(relatedContract.status)]">
                    {{ getContractStatusText(relatedContract.status) }}
                  </span>
                  <span class="contract-number">{{ relatedContract.contract_number }}</span>
                </div>
              </div>
            </div>
            <span class="action-link" @click="handleViewContract">查看详情</span>
          </div>

          <div class="info-divider"></div>

          <div class="attributes-grid">
            <div class="attribute-item">
              <div class="attribute-label">采购用户数</div>
              <span class="attribute-value">{{ relatedContract.user_count }} 人</span>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">合同金额</div>
              <span class="attribute-value">{{ formatAmount(relatedContract.total_amount) }}</span>
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
      </div>
    </div>

    <!-- 赢单弹窗 -->
    <el-dialog
      v-model="winModalVisible"
      title="标记赢单"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form :model="winForm" :rules="winFormRules" label-position="top" ref="winFormRef">
        <el-form-item prop="actual_amount" label="实际成交金额" required>
          <el-input-number
            v-model="winForm.actual_amount"
            :min="0"
            :precision="2"
            :controls="false"
            style="width: 100%"
          >
            <template #prefix>¥</template>
          </el-input-number>
        </el-form-item>
        <el-form-item prop="actual_closing_date" label="实际成交日期" required>
          <el-date-picker
            v-model="winForm.actual_closing_date"
            style="width: 100%"
            placeholder="请选择实际成交日期"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="winModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleWinModalOk">确定</el-button>
      </template>
    </el-dialog>

    <!-- 输单弹窗 -->
    <el-dialog
      v-model="loseModalVisible"
      title="标记输单"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form :model="loseForm" :rules="loseFormRules" label-position="top" ref="loseFormRef">
        <el-form-item prop="loss_reason" label="输单原因" required>
          <el-input
            v-model="loseForm.loss_reason"
            type="textarea"
            placeholder="请输入输单原因说明"
            :rows="4"
            :maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="loseModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleLoseModalOk">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { showError, showSuccess } from '@/utils/errorMessages'
import { ArrowLeft } from '@element-plus/icons-vue'
import { opportunityApi, type Opportunity, type OpportunityWinRequest, type OpportunityLossRequest } from '@/api/opportunity'
import contractApi, { type ContractListResponse, type ContractStatus } from '@/api/contract'
import ProcurementStageFlow from '@/components/ProcurementStageFlow.vue'
import { usePermissionStore } from '@/stores/permissions'
import { usePageTitle } from '@/composables/usePageTitle'

const { setTitle } = usePageTitle()

const router = useRouter()
const route = useRoute()
const permissionStore = usePermissionStore()

const loading = ref(false)
const opportunity = ref<Opportunity | null>(null)
const relatedContract = ref<ContractListResponse | null>(null)
const contractLoading = ref(false)

// Win/Lose dialogs
const winModalVisible = ref(false)
const winFormRef = ref()
const winForm = reactive<OpportunityWinRequest>({
  actual_amount: 0,
  actual_closing_date: new Date().toISOString().split('T')[0] || ''
})
const winFormRules = {
  actual_amount: [{ required: true, message: '请输入实际金额', trigger: 'blur' }],
  actual_closing_date: [{ required: true, message: '请选择成交日期', trigger: 'change' }]
}

const loseModalVisible = ref(false)
const loseFormRef = ref()
const loseForm = reactive<OpportunityLossRequest>({ loss_reason: '' })
const loseFormRules = {
  loss_reason: [{ required: true, message: '请输入输单原因', trigger: 'blur' }]
}

const canEditOpportunity = computed(() =>
  permissionStore.hasAnyPermission(['opportunity:update', 'opportunity:edit_own', 'opportunity:edit_all'])
)

const fetchOpportunityDetail = async () => {
  loading.value = true
  try {
    const id = Number(route.params.id)
    const data = await opportunityApi.getOpportunity(id)
    opportunity.value = data
    // 设置动态标题
    setTitle(data.opportunity_name || '商机详情')
    await fetchRelatedContract()
  } catch (error: unknown) {
    console.error('获取商机详情失败', error)
    showError(error, '获取商机详情')
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
    if (error.response?.status !== 404) {
      console.error('获取关联合同失败', error)
    }
    relatedContract.value = null
  } finally {
    contractLoading.value = false
  }
}

const handleBack = () => {
  router.back()
}

const handleEdit = () => {
  if (!opportunity.value) return
  router.push(`/opportunities/${opportunity.value.id}/edit`)
}

const handleCreateContract = () => {
  if (!opportunity.value) return
  router.push({
    path: '/contracts/create',
    query: {
      opportunityId: opportunity.value.id
    }
  })
}

const handleViewContract = () => {
  if (relatedContract.value) {
    router.push(`/contracts/${relatedContract.value.id}`)
  }
}

const getLicenseTypeText = (type: string) => {
  const typeMap: Record<string, string> = {
    'SUBSCRIPTION': '订阅制',
    'PERPETUAL': '买断制'
  }
  return typeMap[type] || type
}

const getContractStatusClass = (status: ContractStatus) => {
  const map: Record<string, string> = {
    'DRAFT': 'status-info',
    'PENDING': 'status-warning',
    'ACTIVE': 'status-success',
    'EXPIRED': 'status-invalid',
    'TERMINATED': 'status-invalid'
  }
  return map[status] || 'status-default'
}

const getContractStatusText = (status: ContractStatus) => {
  const textMap: Record<string, string> = {
    'DRAFT': '草稿',
    'PENDING': '待签署',
    'ACTIVE': '生效中',
    'EXPIRED': '已过期',
    'TERMINATED': '已终止'
  }
  return textMap[status] || status
}

const formatAmount = (amount: number | string | undefined) => {
  if (!amount) return '0'
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString()
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const formatDateTime = (dateStr: string) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

const getStatusText = (status: number) => {
  const map: Record<number, string> = { 0: '跟进中', 1: '已赢单', 2: '已输单' }
  return map[status] || '未知'
}

const getStatusClass = (status: number) => {
  const map: Record<number, string> = {
    0: 'status-following',
    1: 'status-converted',
    2: 'status-invalid'
  }
  return map[status] || 'status-default'
}

const getPurchaseTypeText = (type: string) => {
  const map: Record<string, string> = { 'NEW': '新购', 'RENEWAL': '续购', 'EXPANSION': '增购' }
  return map[type] || '-'
}

const getPurchaseTypeClass = (type: string) => {
  const map: Record<string, string> = { 'NEW': 'status-info', 'RENEWAL': 'status-success', 'EXPANSION': 'status-warning' }
  return map[type] || 'status-default'
}

const handleShowWinModal = () => {
  if (!opportunity.value) return
  Object.assign(winForm, {
    actual_amount: opportunity.value.total_amount || 0,
    actual_closing_date: new Date().toISOString().split('T')[0]
  })
  winModalVisible.value = true
}

const handleShowLoseModal = () => {
  Object.assign(loseForm, { loss_reason: '' })
  loseModalVisible.value = true
}

const handleWinModalOk = async () => {
  if (!opportunity.value) return
  try {
    await winFormRef.value?.validate()
  } catch {
    return
  }
  try {
    await opportunityApi.markAsWon(opportunity.value.id, winForm)
    showSuccess('标记赢单', '商机')
    winModalVisible.value = false
    fetchOpportunityDetail()
  } catch (error: unknown) {
    showError(error, '标记赢单')
  }
}

const handleLoseModalOk = async () => {
  if (!opportunity.value) return
  try {
    await loseFormRef.value?.validate()
  } catch {
    return
  }
  try {
    await opportunityApi.markAsLost(opportunity.value.id, loseForm)
    showSuccess('标记输单', '商机')
    loseModalVisible.value = false
    fetchOpportunityDetail()
  } catch (error: unknown) {
    showError(error, '标记输单')
  }
}

onMounted(() => {
  fetchOpportunityDetail()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.opportunity-detail-page {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 页面标题（sticky）
.page-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: $wolf-bg-card;
  border-bottom: 1px solid $wolf-border-default;
  height: $wolf-header-height;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 $wolf-page-padding;
}

.header-left {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.header-right {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}


.back-btn {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: $wolf-radius-md !important;
  background: transparent !important;
  border: none !important;

  &:hover {
    background: $wolf-bg-hover !important;
  }
}

.page-title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
}

// 内容区域
.stage-flow-wrapper {
  margin: 0 $wolf-page-padding;
}

.info-card,
.contract-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  margin: $wolf-page-padding;
  box-shadow: $wolf-shadow-card;
}

.card-header {
  margin-bottom: $wolf-space-md;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.card-body {
  min-height: 100px;
}

// 信息内容
.info-content {
  width: 100%;
}

.info-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: $wolf-space-md;
  margin-bottom: $wolf-space-md;
}

.info-left {
  flex: 1;
  min-width: 0;
}

.info-right {
  flex-shrink: 0;
}

.title-section {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.title-avatar {
  width: 48px;
  height: 48px;
  border-radius: $wolf-radius-full;
  background: $wolf-primary-light;
  color: $wolf-primary;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold;
  flex-shrink: 0;
}

.title-content {
  flex: 1;
  min-width: 0;
}

.title-name {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0 0 $wolf-space-xs 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.title-tags {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs;
}

.amount-section {
  text-align: right;
  flex-shrink: 0;
}

.amount-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-bottom: $wolf-space-xs;
}

.amount-value {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  white-space: nowrap;
}

.info-divider {
  height: 1px;
  background: $wolf-border-default;
  margin: $wolf-space-md 0;
}

.info-bottom {
  margin-top: $wolf-space-md;
}

// 属性网格
.attributes-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $wolf-space-md $wolf-space-lg;
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
}

.attribute-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  font-weight: $wolf-font-weight-medium;
}

.attribute-value {
  font-size: $wolf-font-size-body;
  color: $wolf-text-secondary;
  font-weight: $wolf-font-weight-medium;
  word-break: break-all;
}

.attribute-value.not-filled {
  color: $wolf-text-placeholder;
}

// 状态标签（浅底色 + 同色系文字）
.status-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  border-radius: $wolf-radius-sm;
}

.status-new,
.status-info {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-following,
.status-warning {
  background: $wolf-warning-bg;
  color: $wolf-warning-text;
}

.status-converted,
.status-success {
  background: $wolf-success-bg;
  color: $wolf-success-text;
}

.status-invalid {
  background: $wolf-danger-bg;
  color: $wolf-danger-text;
}

.status-default {
  background: $wolf-bg-hover;
  color: $wolf-text-placeholder;
}

// 链接样式
.link-text {
  color: $wolf-text-link;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium;
  &:hover {
    color: $wolf-text-link-hover;
  }
}

.action-link {
  color: $wolf-text-link;
  font-size: $wolf-font-size-auxiliary;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: $wolf-radius-sm;
  transition: all 0.2s ease;

  &:hover {
    background: $wolf-bg-hover;
    color: $wolf-text-link-hover;
  }
}

// 合同内容
.contract-content {
  width: 100%;
}

.contract-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: $wolf-space-md;
  margin-bottom: $wolf-space-md;
}

.contract-meta {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  flex-wrap: wrap;
}

.contract-number {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.empty-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin: $wolf-space-sm 0;
}

// 响应式
@media (max-width: 1200px) {
  .attributes-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .info-card,
  .contract-card {
    margin: $wolf-space-md;
  }
  .stage-flow-wrapper {
    margin: 0 $wolf-space-md;
  }
  .attributes-grid { grid-template-columns: 1fr; }
  .contract-header { flex-direction: column; }
}
</style>