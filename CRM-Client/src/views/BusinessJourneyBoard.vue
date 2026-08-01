<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  UserRound
} from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import {
  AmountText,
  Badge,
  Card,
  CardContent,
  ListFilterPopover,
  Skeleton,
  TableToolbarButton
} from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import businessJourneyBoardApi, {
  type BusinessJourneyBoardCard,
  type BusinessJourneyBoardColumn,
  type BusinessJourneyBoardResponse,
  type BusinessJourneyBoardStageKey
} from '@/api/businessJourneyBoard'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { getDateBounds, getDelimitedFilterValues } from '@/utils/listFilters'
import { logger } from '@/utils/logger'

usePageTitle()

const headerStore = useHeaderStore()
const loading = ref(false)
const errorMessage = ref('')
const board = ref<BusinessJourneyBoardResponse | null>(null)
const activeFilters = ref<ListFilterCondition[]>([])
const ownerFilterOptions = ref<{ value: string; label: string }[]>([])

const filterFields = computed<ListFilterField[]>(() => [
  {
    key: 'last_event_at',
    label: '最近动态时间',
    type: 'date'
  },
  {
    key: 'owner_id',
    label: '负责人',
    type: 'enum',
    options: ownerFilterOptions.value
  }
])

const columns = computed<BusinessJourneyBoardColumn[]>(() => board.value?.columns ?? [])

const stagePalette: Record<BusinessJourneyBoardStageKey, { column: string; countBadge: string; emphasisBadge: string }> = {
  early_communication: {
    column: 'business-board-stage--sky',
    countBadge: 'bg-sky-50 text-sky-700 border-sky-100',
    emphasisBadge: 'bg-sky-600 text-white border-transparent'
  },
  active_progress: {
    column: 'business-board-stage--blue',
    countBadge: 'bg-blue-50 text-blue-700 border-blue-100',
    emphasisBadge: 'bg-blue-600 text-white border-transparent'
  },
  closing_soon: {
    column: 'business-board-stage--emerald',
    countBadge: 'bg-emerald-50 text-emerald-700 border-emerald-100',
    emphasisBadge: 'bg-emerald-600 text-white border-transparent'
  },
  contract_processing: {
    column: 'business-board-stage--violet',
    countBadge: 'bg-violet-50 text-violet-700 border-violet-100',
    emphasisBadge: 'bg-violet-600 text-white border-transparent'
  },
  payment_processing: {
    column: 'business-board-stage--amber',
    countBadge: 'bg-amber-50 text-amber-700 border-amber-100',
    emphasisBadge: 'bg-amber-600 text-white border-transparent'
  },
  invoice_processing: {
    column: 'business-board-stage--cyan',
    countBadge: 'bg-cyan-50 text-cyan-700 border-cyan-100',
    emphasisBadge: 'bg-cyan-600 text-white border-transparent'
  },
  completed: {
    column: 'business-board-stage--slate',
    countBadge: 'bg-slate-50 text-slate-700 border-slate-100',
    emphasisBadge: 'bg-slate-600 text-white border-transparent'
  },
  lost: {
    column: 'business-board-stage--rose',
    countBadge: 'bg-rose-50 text-rose-700 border-rose-100',
    emphasisBadge: 'bg-rose-600 text-white border-transparent'
  }
}

const getStageAge = (value: string | null | undefined): string => {
  if (value === null || value === undefined || value === '') return '-'
  const start = new Date(value)
  if (Number.isNaN(start.getTime())) return '-'
  const diff = Date.now() - start.getTime()
  const days = Math.max(Math.floor(diff / 86400000), 0)
  if (days === 0) return '今天'
  return `${days}天`
}

const getStageAgeTone = (value: string | null | undefined): string => {
  if (value === null || value === undefined || value === '') {
    return 'bg-slate-50 text-slate-600 border-slate-100'
  }
  const start = new Date(value)
  if (Number.isNaN(start.getTime())) {
    return 'bg-slate-50 text-slate-600 border-slate-100'
  }
  const days = Math.max(Math.floor((Date.now() - start.getTime()) / 86400000), 0)
  if (days <= 7) return 'bg-emerald-50 text-emerald-700 border-emerald-100'
  if (days <= 15) return 'bg-yellow-50 text-yellow-700 border-yellow-100'
  return 'bg-rose-50 text-rose-700 border-rose-100'
}

const shouldShowOpportunityStage = (card: BusinessJourneyBoardCard): boolean => {
  return ['early_communication', 'active_progress', 'closing_soon'].includes(card.current_board_stage)
}

const getCardStageName = (card: BusinessJourneyBoardCard): string => {
  return card.primary_opportunity?.current_stage_name ?? '未记录阶段'
}

const getWinProbability = (card: BusinessJourneyBoardCard): string => {
  const value = card.primary_opportunity?.win_probability
  return value === null || value === undefined ? '-' : `${value}%`
}

const loadBoard = async (): Promise<void> => {
  loading.value = true
  errorMessage.value = ''
  try {
    const lastEventBounds = getDateBounds(activeFilters.value, 'last_event_at')
    const ownerId = getDelimitedFilterValues(activeFilters.value, 'owner_id')
    board.value = await businessJourneyBoardApi.getBoard({
      start_date: lastEventBounds.start ?? null,
      end_date: lastEventBounds.end ?? null,
      owner_id: ownerId,
      limit: 500
    })
  } catch (error) {
    logger.error('[BusinessJourneyBoard]', '加载业务看板失败', { error })
    errorMessage.value = '业务看板加载失败'
    toast.error('业务看板加载失败')
  } finally {
    loading.value = false
  }
}

const fetchOwnerFilterOptions = async (): Promise<void> => {
  try {
    const response = await businessJourneyBoardApi.getOwnerFilterOptions()
    ownerFilterOptions.value = response.data.map((owner) => ({
      value: owner.id,
      label: owner.name
    }))
  } catch (error) {
    logger.error('[BusinessJourneyBoard]', '获取负责人筛选项失败', { error })
    ownerFilterOptions.value = []
  }
}

const handleFilterApply = (filters: ListFilterCondition[]): void => {
  activeFilters.value = filters
  void loadBoard()
}

const handleFilterReset = (): void => {
  activeFilters.value = []
  void loadBoard()
}

onMounted(() => {
  headerStore.clear()
  void fetchOwnerFilterOptions()
  void loadBoard()
})
</script>

<template>
  <div class="business-board-page">
    <div class="business-board-toolbar" aria-label="业务看板工具栏">
      <ListFilterPopover
        v-model="activeFilters"
        :fields="filterFields"
        @apply="handleFilterApply"
        @reset="handleFilterReset"
      />
      <TableToolbarButton
        class="refresh-button"
        :disabled="loading"
        aria-label="刷新业务看板"
        @click="loadBoard"
      >
        <RefreshCw class="refresh-icon" :class="{ spinning: loading }" aria-hidden="true" />
        刷新
      </TableToolbarButton>
    </div>

    <div v-if="errorMessage" class="business-board-error" role="alert">
      <AlertCircle class="error-icon" aria-hidden="true" />
      <span>{{ errorMessage }}</span>
    </div>

    <Card class="business-board-surface">
      <CardContent class="business-board-surface-content">
        <div class="business-board-scroll">
          <div v-if="loading && columns.length === 0" class="business-board-skeleton" aria-label="业务看板加载中">
            <section v-for="index in 5" :key="index" class="business-board-column">
              <Skeleton class="h-8 w-24" />
              <Skeleton class="h-28 w-full" />
              <Skeleton class="h-28 w-full" />
              <Skeleton class="h-28 w-full" />
            </section>
          </div>

          <div v-else class="business-board-columns">
            <section
              v-for="column in columns"
              :key="column.key"
              class="business-board-column"
              :class="stagePalette[column.key].column"
            >
              <header class="column-header">
                <h2>{{ column.title }}</h2>
                <Badge variant="outline" :class="stagePalette[column.key].countBadge">
                  {{ column.count }}
                </Badge>
              </header>

              <div class="column-card-list">
                <Card
                  v-for="card in column.cards"
                  :key="card.journey_id"
                  class="journey-card"
                >
                  <CardContent class="journey-card-content">
                    <div class="journey-card-topline">
                      <span class="journey-customer">{{ card.customer_name ?? '-' }}</span>
                      <Badge
                        variant="outline"
                        class="journey-age"
                        :class="getStageAgeTone(card.last_event_at)"
                      >
                        {{ getStageAge(card.last_event_at) }}
                      </Badge>
                    </div>

                    <div class="journey-title">
                      {{ card.journey_name }}
                    </div>

                    <div class="journey-main-metric">
                      <AmountText :value="card.amount" size="lg" tone="default" />
                    </div>

                    <div class="journey-tag-row">
                      <Badge
                        v-if="shouldShowOpportunityStage(card)"
                        variant="outline"
                        class="journey-info-tag bg-emerald-50 text-emerald-700 border-emerald-100"
                      >
                        赢率 {{ getWinProbability(card) }}
                      </Badge>
                      <Badge
                        variant="outline"
                        class="journey-info-tag bg-blue-50 text-blue-700 border-blue-100"
                      >
                        <UserRound class="tag-icon" aria-hidden="true" />
                        {{ card.owner?.name ?? '-' }}
                      </Badge>
                    </div>

                    <Badge
                      v-if="shouldShowOpportunityStage(card)"
                      class="journey-stage-tag"
                      :class="stagePalette[column.key].emphasisBadge"
                    >
                      {{ getCardStageName(card) }}
                    </Badge>
                  </CardContent>
                </Card>

                <div v-if="column.cards.length === 0" class="column-empty">
                  <CheckCircle2 class="empty-icon" aria-hidden="true" />
                  <span>暂无旅程</span>
                </div>
              </div>
            </section>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.business-board-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: $wolf-page-padding-v2;
  gap: 16px;
  background: $wolf-bg-page-v2;
}

.business-board-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  min-height: 32px;
}

.refresh-icon {
  width: 14px;
  height: 14px;
}

.refresh-icon.spinning {
  animation: business-board-spin 0.8s linear infinite;
}

.business-board-error {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  min-height: 40px;
  padding: 0 $wolf-space-md-v2;
  border: 1px solid rgba($wolf-danger-v2, 0.18);
  border-radius: $wolf-radius-v2;
  color: $wolf-danger-text-v2;
  background: $wolf-danger-bg-v2;
  font-size: $wolf-font-size-caption-v2;
}

.error-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.business-board-surface {
  flex: 1;
  min-height: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  box-shadow: none;
}

.business-board-surface-content {
  display: flex;
  height: 100%;
  min-height: 0;
  padding: 0;
}

.business-board-scroll {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: $wolf-space-sm-v2;
}

.business-board-columns,
.business-board-skeleton {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(280px, 320px);
  align-items: start;
  gap: $wolf-space-md-v2;
  height: 100%;
  min-height: 100%;
}

.business-board-column {
  display: flex;
  flex-direction: column;
  height: auto;
  max-height: 100%;
  min-height: 0;
  overflow: hidden;
  border: 0;
  border-radius: 8px;
  background: var(--column-bg);
}

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px;
  border: 0;
  background: transparent;
  flex-shrink: 0;
}

.column-header h2 {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: 15px;
  line-height: 1.35;
  font-weight: 700;
}

.column-card-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 8px;
}

.journey-card {
  flex-shrink: 0;
  border: 1px solid transparent;
  border-radius: 8px;
  background: hsl(var(--card));
  box-shadow: none;
  transition:
    border-color 160ms ease,
    box-shadow 160ms ease;
}

.journey-card:hover,
.journey-card:focus-within {
  border-color: $wolf-border-hover-v2;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.08);
}

.journey-card-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
}

.journey-card-topline,
.journey-tag-row {
  display: flex;
  align-items: center;
}

.journey-card-topline {
  justify-content: space-between;
  gap: 8px;
}

.journey-age {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.25;
}

.journey-title {
  color: hsl(var(--foreground));
  text-align: left;
  font-size: 15px;
  line-height: 1.4;
  font-weight: 700;
}

.journey-customer {
  min-width: 0;
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.journey-main-metric {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.journey-main-metric span {
  color: hsl(var(--muted-foreground));
  font-size: 12px;
}

.journey-tag-row {
  flex-wrap: wrap;
  gap: 8px;
}

.journey-info-tag {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 5px;
  font-size: 12px;
  line-height: 1.35;
}

.journey-info-tag {
  max-width: 100%;
  border: 0;
  font-weight: 500;
}

.tag-icon,
.empty-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.journey-stage-tag {
  align-self: flex-start;
  max-width: 100%;
  border: 0;
  font-weight: 500;
}

.column-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 96px;
  border: 1px dashed hsl(var(--border));
  border-radius: 8px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--card) / 0.64);
  font-size: 13px;
}

.business-board-stage--sky {
  --column-bg: rgb(240 249 255);
}

.business-board-stage--blue {
  --column-bg: rgb(239 246 255);
}

.business-board-stage--violet {
  --column-bg: rgb(245 243 255);
}

.business-board-stage--amber {
  --column-bg: rgb(255 251 235);
}

.business-board-stage--cyan {
  --column-bg: rgb(236 254 255);
}

.business-board-stage--emerald {
  --column-bg: rgb(236 253 245);
}

.business-board-stage--slate {
  --column-bg: rgb(248 250 252);
}

.business-board-stage--rose {
  --column-bg: rgb(255 241 242);
}

@keyframes business-board-spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 900px) {
  .business-board-page {
    padding: $wolf-page-padding-mobile-v2;
    padding-bottom: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
  }

  .business-board-columns,
  .business-board-skeleton {
    grid-auto-columns: minmax(272px, 88vw);
  }
}
</style>
