<script setup lang="ts">
/**
 * CustomerDetailSheet.vue - 客户详情抽屉组件
 *
 * 技术栈：shadcn-vue + variables-v2.scss
 * 宽度：80%（max-width: 1200px），移动端 95%/100%
 */
import { computed, ref, watch } from 'vue'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetFooter
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import CustomerDetailSidebar from '@/components/CustomerDetailSidebar.vue'
import { Plus, Pencil } from 'lucide-vue-next'
import { handleApiError } from '@/utils/errorHandler'
import customerApi, { type CustomerDetailResponse } from '@/api/customer'
import customerFollowUpApi, { type CustomerFollowUpResponse } from '@/api/customerFollowUp'
import { opportunityApi, type OpportunityListResponse } from '@/api/opportunity'
import contractApi, { type ContractListResponse } from '@/api/contract'
import invoiceApi, { type InvoiceTitleResponse } from '@/api/invoice'
import licenseApplicationApi, { type LicenseApplicationResponse } from '@/api/licenseApplication'
import deploymentApi, { type DeploymentInfoResponse } from '@/api/deployment'
import { getCustomerScore, type ScoreResponse } from '@/api/score'

// ==================== Props & Emits ====================
interface Props {
  customerId: number | null
  visible: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
}>()

// ==================== State ====================
const loading = ref(false)  // TODO: Task 3 - 加载客户详情数据时使用
const activePanel = ref('followup')  // Sidebar 导航切换

// ==================== Data Loading State ====================
const customer = ref<CustomerDetailResponse | null>(null)
const score = ref<ScoreResponse | null>(null)
const followUps = ref<CustomerFollowUpResponse[]>([])
const opportunities = ref<OpportunityListResponse[]>([])
const contracts = ref<ContractListResponse[]>([])
const invoiceTitles = ref<InvoiceTitleResponse[]>([])
const licenseApplications = ref<LicenseApplicationResponse[]>([])
const deployments = ref<DeploymentInfoResponse[]>([])

// ==================== Mobile Navigation ====================
interface MobileNavItem {
  key: string
  label: string
}

const mobileNavItems: MobileNavItem[] = [
  { key: 'followup', label: '跟进记录' },
  { key: 'contacts', label: '联系人' },
  { key: 'opportunities', label: '商机' },
  { key: 'contracts', label: '合同' },
  { key: 'payments', label: '回款' },
  { key: 'invoices', label: '发票' },
  { key: 'license-management', label: 'License' }
]

const getActivePanelLabel = computed((): string => {
  const item = mobileNavItems.find(item => item.key === activePanel.value)
  return item?.label ?? '选择面板'
})

// ==================== Methods ====================
const handleCreateOpportunity = (): void => {
  // TODO: 打开新建商机弹窗，成功后刷新
  emit('refresh')
}

const handleCreateContract = (): void => {
  // TODO: 打开新建合同弹窗
}

const handleEdit = (): void => {
  // TODO: 跳转编辑页面
}

// 占位方法：Sidebar 面板切换（Task 4 实现）
const setActivePanel = (panel: string): void => {
  activePanel.value = panel
}

// ==================== Data Loading ====================
const loadAllData = async (customerId: number): Promise<void> => {
  loading.value = true
  try {
    const [
      customerDetail,
      scoreData,
      followUpsData,
      opportunitiesData,
      contractsData,
      invoiceTitlesData,
      licenseApplicationsData,
      deploymentsData
    ] = await Promise.all([
      customerApi.getCustomerDetail(customerId),
      getCustomerScore(customerId).catch(() => null),
      customerFollowUpApi.getFollowUps(customerId).catch(() => []),
      opportunityApi.getAvailableForContract(customerId).catch(() => []),
      contractApi.getCustomerContracts(customerId).catch(() => []),
      invoiceApi.getInvoiceTitles(customerId).catch(() => ({ invoice_titles: [] })),
      licenseApplicationApi.list(customerId).catch(() => []),
      deploymentApi.list(customerId).catch(() => [])
    ])

    customer.value = customerDetail
    score.value = scoreData
    followUps.value = followUpsData
    opportunities.value = opportunitiesData
    contracts.value = contractsData
    invoiceTitles.value = invoiceTitlesData.invoice_titles ?? []
    licenseApplications.value = licenseApplicationsData
    deployments.value = deploymentsData
  } catch (error) {
    handleApiError(error, '加载客户详情')
  } finally {
    loading.value = false
  }
}

// ==================== Watch ====================
watch(() => props.visible, (visible): void => {
  if (visible && props.customerId !== null) {
    loadAllData(props.customerId)
    setActivePanel('followup')
  } else if (!visible) {
    // 清理状态
    customer.value = null
    score.value = null
    followUps.value = []
    opportunities.value = []
    contracts.value = []
    invoiceTitles.value = []
    licenseApplications.value = []
    deployments.value = []
  }
})
</script>

<template>
  <Sheet :open="visible" @update:open="$emit('update:visible', $event)">
    <SheetContent
      side="right"
      class="w-[80%] max-w-[1200px] p-0 flex flex-col bg-white dark:bg-slate-900 max-md:w-[95%] max-sm:w-full"
    >
      <!-- Header -->
      <SheetHeader class="p-6 border-b border-wolf-border-default-v2">
        <!-- 桌面端：客户信息 -->
        <div class="hidden md:flex items-center gap-4">
          <div class="title-avatar">客</div>
          <div class="flex-1">
            <SheetTitle class="text-base font-semibold">客户详情</SheetTitle>
            <div class="flex items-center gap-2 mt-1">
              <Badge>状态</Badge>
            </div>
          </div>
          <div class="text-right">
            <div class="text-xs text-wolf-text-tertiary-v2">联系人数</div>
            <div class="text-base font-semibold text-wolf-text-primary-v2">0 人</div>
          </div>
        </div>

        <!-- 移动端：客户信息 + Select 导航 -->
        <div class="md:hidden">
          <div class="flex items-center gap-4 mb-3">
            <div class="title-avatar">客</div>
            <SheetTitle class="text-base font-semibold">客户详情</SheetTitle>
          </div>
          <Select v-model="activePanel">
            <SelectTrigger class="w-full h-12">
              <SelectValue>{{ getActivePanelLabel }}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="item in mobileNavItems" :key="item.key" :value="item.key">
                {{ item.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </SheetHeader>

      <!-- Content -->
      <div class="sheet-content-wrapper flex-1 overflow-hidden">
        <!-- 左侧 Sidebar（桌面端） -->
        <div class="sidebar-wrapper hidden md:block">
          <CustomerDetailSidebar
            :active-panel="activePanel"
            @update:active-panel="activePanel = $event"
          />
        </div>

        <!-- 右侧内容区 -->
        <ScrollArea class="flex-1">
          <div class="p-6 space-y-6">
            <!-- 基本信息卡片 -->
            <Card class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">基本信息</h3>
                </div>
                <div class="p-4">
                  <div class="attributes-grid">
                    <div class="attribute-item">
                      <div class="attribute-label">客户来源</div>
                      <div class="attribute-value">-</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">所在城市</div>
                      <div class="attribute-value">-</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">公司地址</div>
                      <div class="attribute-value">-</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">负责销售</div>
                      <div class="attribute-value">-</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">采购方式</div>
                      <div class="attribute-value">-</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">创建人</div>
                      <div class="attribute-value">-</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">创建时间</div>
                      <div class="attribute-value">-</div>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-label">最后修改</div>
                      <div class="attribute-value">-</div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <!-- 内容面板（待后续实现） -->
            <div class="text-sm text-wolf-text-secondary-v2">面板内容: {{ activePanel }}</div>
          </div>
        </ScrollArea>
      </div>

      <!-- Footer -->
      <SheetFooter class="p-4 border-t border-wolf-border-default-v2 flex flex-row gap-2">
        <Button variant="default" @click="handleCreateOpportunity">
          <Plus class="w-4 h-4 mr-2" />
          新建商机
        </Button>
        <Button variant="outline" @click="handleCreateContract">
          <Plus class="w-4 h-4 mr-2" />
          新建合同
        </Button>
        <Button variant="outline" @click="handleEdit">
          <Pencil class="w-4 h-4 mr-2" />
          编辑
        </Button>
      </SheetFooter>
    </SheetContent>
  </Sheet>
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

.sheet-content-wrapper {
  display: flex;
  flex-direction: column;

  @media (min-width: 769px) {
    flex-direction: row;
  }
}

.attributes-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $wolf-space-md-v2 $wolf-space-lg-v2;

  @media (max-width: 768px) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: 480px) {
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
}
</style>