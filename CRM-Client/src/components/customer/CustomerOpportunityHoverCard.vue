<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronRight, CircleAlert } from 'lucide-vue-next'
import { AmountText, Badge, Button, HoverInfo, Progress, Skeleton } from '@/components/crmwolf'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from '@/components/ui/empty'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { OpportunityStatus, opportunityApi, type OpportunityListResponse } from '@/api/opportunity'
import { normalizePaginatedResponse } from '@/types/pagination'

const PREVIEW_LIMIT = 3

interface Props {
  customerId: string
  customerName: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'select-opportunity': [opportunityId: string]
  'view-all': []
}>()

const opportunities = ref<OpportunityListResponse[]>([])
const total = ref(0)
const open = ref(false)
const loading = ref(false)
const loaded = ref(false)
const loadFailed = ref(false)

const hasMore = computed(() => total.value > opportunities.value.length)

const getStageName = (opportunity: OpportunityListResponse): string => (
  opportunity.current_stage_snapshot?.stage_name
  ?? opportunity.stage_name
  ?? opportunity.stage_info?.stage_name
  ?? opportunity.stage?.stage_name
  ?? '未设置阶段'
)

const getWinProbability = (opportunity: OpportunityListResponse): number => {
  const probability = opportunity.current_stage_snapshot?.win_probability
    ?? opportunity.win_probability
    ?? opportunity.stage_info?.win_probability
    ?? opportunity.stage?.win_probability
    ?? 0

  return Math.min(100, Math.max(0, probability))
}

const loadOpportunities = async (): Promise<void> => {
  if (loading.value || loaded.value) return

  loading.value = true
  loadFailed.value = false
  try {
    const response = await opportunityApi.getOpportunities({
      customer_id: props.customerId,
      limit: PREVIEW_LIMIT,
      status_exclude: OpportunityStatus.LOST,
      order_by: 'created_time',
      order_dir: 'desc',
    })
    const normalized = normalizePaginatedResponse(response)
    opportunities.value = normalized.items
      .filter((opportunity) => opportunity.status !== OpportunityStatus.LOST)
      .slice(0, PREVIEW_LIMIT)
    total.value = normalized.total
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
    void loadOpportunities()
  }
}

const retryLoad = (): void => {
  loaded.value = false
  void loadOpportunities()
}

const handleSelectOpportunity = (opportunityId: string): void => {
  open.value = false
  emit('select-opportunity', opportunityId)
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
    content-class="customer-opportunity-hover-card w-[460px] p-0"
    @update:open="handleOpenChange"
  >
    <template #trigger>
      <slot name="trigger" />
    </template>

    <section aria-label="客户商机概览">
      <header class="flex items-start justify-between gap-3 px-4 pt-4 pb-3">
        <h3 class="min-w-0 truncate text-xl font-semibold leading-7 text-wolf-text-primary-v2" :title="customerName">
          {{ customerName }}
        </h3>
        <Badge
          v-if="loaded"
          variant="outline"
          class="shrink-0 border-blue-100 bg-blue-50 text-blue-700 hover:bg-blue-50"
          data-testid="customer-opportunity-total"
        >
          共 {{ total }} 个
        </Badge>
      </header>

      <div v-if="loading" class="space-y-3 px-4 pb-4" aria-live="polite" aria-label="正在加载客户商机">
        <div v-for="index in 2" :key="index" class="space-y-2 rounded-wolf bg-wolf-bg-muted-v2 p-4">
          <Skeleton class="h-4 w-2/5" />
          <Skeleton class="h-8 w-3/5" />
          <Skeleton class="h-1.5 w-full" />
          <Skeleton class="h-4 w-1/2" />
        </div>
      </div>

      <Empty v-else-if="loadFailed" class="border-0 px-4 py-8">
        <EmptyHeader>
          <CircleAlert class="h-5 w-5 text-wolf-danger-text-v2" aria-hidden="true" />
          <EmptyTitle class="text-sm">商机加载失败</EmptyTitle>
          <EmptyDescription class="text-xs">请稍后重试</EmptyDescription>
        </EmptyHeader>
        <Button variant="outline" size="sm" class="mt-3" @click="retryLoad">
          重试
        </Button>
      </Empty>

      <Empty v-else-if="loaded && opportunities.length === 0" class="border-0 px-4 py-8">
        <EmptyHeader>
          <EmptyTitle class="text-sm">暂无商机</EmptyTitle>
          <EmptyDescription class="text-xs">该客户暂未关联商机</EmptyDescription>
        </EmptyHeader>
      </Empty>

      <ScrollArea v-else-if="loaded" class="max-h-[420px]">
        <div class="space-y-3 px-4 pb-4">
          <Button
            v-for="opportunity in opportunities"
            :key="opportunity.id"
            variant="ghost"
            class="group h-auto w-full items-stretch justify-start rounded-wolf bg-wolf-bg-muted-v2 p-4 text-left hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-wolf-focus"
            :data-testid="`customer-opportunity-${opportunity.id}`"
            @click="handleSelectOpportunity(opportunity.id)"
          >
            <span class="flex w-full min-w-0 flex-col">
              <span class="flex min-w-0 items-start justify-between gap-3">
                <span class="truncate text-sm font-medium uppercase tracking-[0.08em] text-wolf-text-secondary-v2" :title="opportunity.opportunity_name">
                  {{ opportunity.opportunity_name }}
                </span>
                <Badge
                  variant="outline"
                  class="shrink-0 border-blue-100 bg-blue-50 text-blue-700 hover:bg-blue-50"
                  :data-testid="`customer-opportunity-stage-${opportunity.id}`"
                  :title="`业务旅程当前状态：${getStageName(opportunity)}`"
                >
                  {{ getStageName(opportunity) }}
                </Badge>
              </span>
              <AmountText
                :value="opportunity.total_amount"
                size="lg"
                tone="primary"
                class="mt-3 self-start text-wolf-text-primary-v2"
              />
              <Progress
                :model-value="getWinProbability(opportunity)"
                class="mt-3 h-1.5 bg-wolf-bg-card"
                :aria-label="`${opportunity.opportunity_name} 赢率 ${getWinProbability(opportunity)}%`"
              />
              <span class="mt-2 flex items-center justify-between gap-3 text-sm">
                <span class="font-medium text-wolf-text-secondary-v2">
                  赢率 {{ getWinProbability(opportunity) }}%
                </span>
                <ChevronRight class="h-4 w-4 shrink-0 text-wolf-text-tertiary-v2 group-hover:text-sidebar-accent-foreground" aria-hidden="true" />
              </span>
            </span>
          </Button>
        </div>
      </ScrollArea>

      <template v-if="loaded && hasMore">
        <Separator />
        <div class="p-3">
          <Button
            variant="ghost"
            size="sm"
            class="w-full justify-between text-wolf-text-secondary-v2 hover:text-wolf-primary-v2"
            @click="handleViewAll"
          >
            查看全部商机
            <ChevronRight class="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </template>
    </section>
  </HoverInfo>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

:global(.customer-opportunity-hover-card) {
  border-radius: $wolf-radius-popover-v2;
  box-shadow: $wolf-shadow-hover-v2;
}
</style>
