<script setup lang="ts">
import { ref } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
import { AmountText, Badge, Button, DataViewStatePanel, HoverInfo, Progress, Skeleton } from '@/components/crmwolf'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { dealJourneyApi, type DealJourney } from '@/api/dealJourney'
import { dealJourneyProgressPercent, type DealJourneyBoardStage } from '@/utils/dealJourney'

const PREVIEW_LIMIT = 3
const HIDDEN_JOURNEY_STATUSES = new Set(['LOST', 'ARCHIVED'])

interface Props {
  customerId: string
  customerName: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'select-journey': [journeyPublicId: string]
  'view-all': []
}>()

const journeys = ref<DealJourney[]>([])
const total = ref(0)
const open = ref(false)
const loading = ref(false)
const loaded = ref(false)
const loadFailed = ref(false)

const isPreviewable = (journey: DealJourney): boolean =>
  !HIDDEN_JOURNEY_STATUSES.has(journey.status)

const getProductName = (journey: DealJourney): string =>
  journey.primary_opportunity?.product_name ?? ''

const boardStageBadgeClass = (stage: DealJourneyBoardStage): string => {
  if (stage === 'lost') return 'status-danger'
  if (stage === 'completed') return 'status-success'
  if (
    stage === 'closing_soon'
    || stage === 'contract_processing'
    || stage === 'payment_processing'
    || stage === 'invoice_processing'
  ) {
    return 'status-info'
  }
  return 'status-warning'
}

const loadJourneys = async (): Promise<void> => {
  if (loading.value || loaded.value) return

  loading.value = true
  loadFailed.value = false
  try {
    const items = await dealJourneyApi.listByCustomer(props.customerId)
    const previewable = items.filter(isPreviewable)
    total.value = previewable.length
    journeys.value = previewable.slice(0, PREVIEW_LIMIT)
    loaded.value = true
  } catch {
    loadFailed.value = true
  } finally {
    loading.value = false
  }
}

const handleOpenChange = (isOpen: boolean): void => {
  open.value = isOpen
  if (isOpen) {
    void loadJourneys()
  }
}

const retryLoad = (): void => {
  loaded.value = false
  void loadJourneys()
}

const handleSelectJourney = (journeyPublicId: string): void => {
  open.value = false
  emit('select-journey', journeyPublicId)
}

const handleViewAll = (): void => {
  open.value = false
  emit('view-all')
}
</script>

<template>
  <HoverInfo
    side="bottom"
    align="start"
    :open="open"
    :open-delay="250"
    :close-delay="180"
    content-class="customer-deal-journey-hover-card is-panel w-[460px] p-0"
    @update:open="handleOpenChange"
  >
    <template #trigger>
      <slot name="trigger" />
    </template>

    <section aria-label="客户业务旅程概览">
      <header class="flex items-start justify-between gap-wolf-md px-wolf-md pt-wolf-md pb-wolf-md">
        <h3 class="min-w-0 truncate text-wolf-body font-wolf-semibold text-wolf-text-primary-v2" :title="customerName">
          {{ customerName }}
        </h3>
        <Badge
          v-if="loaded"
          class="status-badge status-neutral shrink-0"
          data-testid="customer-deal-journey-total"
        >
          共 {{ total }} 个
        </Badge>
      </header>

      <DataViewStatePanel
        :state="loading ? 'loading' : loadFailed ? 'error' : loaded && journeys.length === 0 ? 'empty' : 'ready'"
        error-title="旅程加载失败"
        error-description="请稍后重试"
        empty-title="暂无业务旅程"
        empty-description="该客户暂未关联业务旅程"
        class="customer-deal-journey-state"
        @retry="retryLoad"
      >
        <template #loading>
          <div class="space-y-wolf-md px-wolf-md pb-wolf-md" aria-label="正在加载客户业务旅程">
            <div v-for="index in 2" :key="index" class="space-y-wolf-sm rounded-wolf bg-wolf-bg-muted-v2 p-wolf-md">
              <Skeleton class="h-4 w-2/5" />
              <Skeleton class="h-8 w-3/5" />
              <Skeleton class="h-1.5 w-full" />
              <Skeleton class="h-4 w-1/2" />
            </div>
          </div>
        </template>

        <template #error-action>
          <Button variant="outline" size="sm" class="mt-wolf-md" @click="retryLoad">
            重试
          </Button>
        </template>

        <template #default>
          <ScrollArea v-if="loaded" class="max-h-[420px]">
            <div class="space-y-wolf-md px-wolf-md pb-wolf-md">
              <Button
                v-for="journey in journeys"
                :key="journey.public_id"
                variant="ghost"
                class="group h-auto w-full items-stretch justify-start rounded-wolf bg-wolf-bg-muted-v2 p-wolf-md text-left hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-wolf-focus"
                :data-testid="`customer-deal-journey-${journey.public_id}`"
                @click="handleSelectJourney(journey.public_id)"
              >
                <span class="flex w-full min-w-0 flex-col">
                  <span class="flex min-w-0 items-start justify-between gap-wolf-md">
                    <span class="min-w-0">
                      <span class="block truncate text-wolf-body font-wolf-medium text-wolf-text-secondary-v2" :title="journey.name">
                        {{ journey.name }}
                      </span>
                      <span
                        v-if="getProductName(journey)"
                        class="mt-wolf-sm block truncate text-wolf-caption text-wolf-text-tertiary-v2"
                        :title="getProductName(journey)"
                      >
                        {{ getProductName(journey) }}
                      </span>
                    </span>
                    <AmountText
                      :value="journey.amount"
                      size="md"
                      tone="primary"
                      class="shrink-0 self-start text-wolf-text-primary-v2"
                    />
                  </span>
                  <Progress
                    :model-value="dealJourneyProgressPercent(journey.current_board_stage)"
                    class="mt-wolf-md h-1.5 bg-wolf-bg-card"
                    :aria-label="`${journey.name} 旅程进度 ${dealJourneyProgressPercent(journey.current_board_stage)}%`"
                  />
                  <span class="mt-wolf-sm flex items-center justify-between gap-wolf-md">
                    <Badge
                      :class="['status-badge', 'shrink-0', boardStageBadgeClass(journey.current_board_stage)]"
                      :data-testid="`customer-deal-journey-stage-${journey.public_id}`"
                      :title="`业务旅程当前状态：${journey.current_board_stage_label}`"
                    >
                      {{ journey.current_board_stage_label }}
                    </Badge>
                    <ChevronRight class="h-4 w-4 shrink-0 text-wolf-text-tertiary-v2 group-hover:text-sidebar-accent-foreground" aria-hidden="true" />
                  </span>
                </span>
              </Button>
            </div>
          </ScrollArea>

          <template v-if="loaded">
            <Separator />
            <div class="p-wolf-md">
              <Button
                variant="ghost"
                size="sm"
                class="w-full justify-between text-wolf-text-secondary-v2 hover:text-wolf-primary-v2"
                @click="handleViewAll"
              >
                查看全部业务旅程
                <ChevronRight class="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          </template>
        </template>
      </DataViewStatePanel>
    </section>
  </HoverInfo>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  font-size: 11px;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-full-v2;
  white-space: nowrap;
  border: none;
}

.status-neutral {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.status-warning {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-info {
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
}

.status-success {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.status-danger {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}
</style>
