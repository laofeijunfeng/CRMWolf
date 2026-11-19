<script setup lang="ts">
import { ref } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
import { AmountText, Badge, Button, DataViewStatePanel, HoverInfo, Progress, Skeleton } from '@/components/crmwolf'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { dealJourneyApi, type DealJourney } from '@/api/dealJourney'
import { businessJourneyStageTone } from '@/components/business-journey/businessJourneyStagePresentation'

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
const getJourneyProgressPercent = (journey: DealJourney): number =>
  journey.cumulative_progress_percent

const getJourneyProgressLabel = (journey: DealJourney): string =>
  `${journey.name} 累计进度 ${getJourneyProgressPercent(journey)}%`

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
      <span class="customer-deal-journey-trigger">
        <slot name="trigger" />
      </span>
    </template>

    <section aria-label="客户业务旅程概览">
      <header class="flex items-start justify-between gap-3 px-3 pt-3 pb-3">
        <h3 class="min-w-0 truncate text-body font-semibold text-foreground" :title="customerName">
          {{ customerName }}
        </h3>
        <Badge
          v-if="loaded"
          variant="status"
          class="status-badge shrink-0"
          data-tone="neutral"
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
          <div class="space-y-3 px-3 pb-3" aria-label="正在加载客户业务旅程">
            <div v-for="index in 2" :key="index" class="space-y-2 rounded-md bg-muted p-3">
              <Skeleton class="h-4 w-2/5" />
              <Skeleton class="h-8 w-3/5" />
              <Skeleton class="h-1.5 w-full" />
              <Skeleton class="h-4 w-1/2" />
            </div>
          </div>
        </template>

        <template #error-action>
          <Button variant="outline" size="sm" class="mt-3" @click="retryLoad">
            重试
          </Button>
        </template>

        <template #default>
          <ScrollArea v-if="loaded" class="max-h-[420px]">
            <div class="space-y-3 px-3 pb-3">
              <Button
                v-for="journey in journeys"
                :key="journey.public_id"
                variant="ghost"
                class="group h-auto w-full items-stretch justify-start rounded-md bg-muted p-3 text-left hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-ring"
                :data-testid="`customer-deal-journey-${journey.public_id}`"
                @click="handleSelectJourney(journey.public_id)"
              >
                <span class="flex w-full min-w-0 flex-col">
                  <span class="flex min-w-0 items-start justify-between gap-3">
                    <span class="min-w-0">
                      <span class="block truncate text-body font-medium text-muted-foreground" :title="journey.name">
                        {{ journey.name }}
                      </span>
                      <span
                        v-if="getProductName(journey)"
                        class="mt-2 block truncate text-caption text-muted-foreground"
                        :title="getProductName(journey)"
                      >
                        {{ getProductName(journey) }}
                      </span>
                    </span>
                    <AmountText
                      :value="journey.amount"
                      size="md"
                      tone="primary"
                      class="shrink-0 self-start text-foreground"
                    />
                  </span>
                  <div class="mt-3 flex items-center gap-2">
                    <Progress
                      :model-value="getJourneyProgressPercent(journey)"
                      class="h-1.5 min-w-0 flex-1 bg-muted"
                      :aria-label="getJourneyProgressLabel(journey)"
                    />
                    <span class="shrink-0 tabular-nums text-caption text-muted-foreground">
                      {{ getJourneyProgressPercent(journey) }}%
                    </span>
                  </div>
                  <span class="mt-2 flex items-center justify-between gap-3">
                    <Badge
                      variant="status"
                      :data-tone="businessJourneyStageTone(journey.current_board_stage)"
                      class="status-badge shrink-0"
                      :data-testid="`customer-deal-journey-stage-${journey.public_id}`"
                      :title="`业务旅程当前状态：${journey.current_board_stage_label}`"
                    >
                      {{ journey.current_board_stage_label }}
                    </Badge>
                    <ChevronRight class="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-sidebar-accent-foreground" aria-hidden="true" />
                  </span>
                </span>
              </Button>
            </div>
          </ScrollArea>

          <template v-if="loaded">
            <Separator />
            <div class="p-3">
              <Button
                variant="ghost"
                size="sm"
                class="w-full justify-between text-muted-foreground hover:text-brand"
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

.customer-deal-journey-trigger {
  display: block;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  font-size: var(--font-size-caption);
  font-weight: 500;
  border-radius: 9999px;
  white-space: nowrap;
  border: none;
}
</style>
