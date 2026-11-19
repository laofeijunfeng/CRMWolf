<script setup lang="ts">
import { computed } from 'vue'
import { AlertCircle, CheckCircle2, RefreshCw, UserRound } from 'lucide-vue-next'
import { AmountText, TableToolbarButton } from '@/components/crmwolf'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type {
  BusinessJourneyBoardCard,
  BusinessJourneyBoardResponse
} from '@/schemas/dealJourney'
import {
  businessJourneyStageTone,
  isBusinessJourneyEndStage
} from './businessJourneyStagePresentation'
import { DEAL_JOURNEY_BOARD_STAGE_LABELS } from '@/utils/dealJourney'

interface Props {
  board: BusinessJourneyBoardResponse | null
  loading?: boolean
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  errorMessage: ''
})

const emit = defineEmits<{
  retry: []
  'row-click': [payload: { customerId: string; journeyPublicId: string }]
}>()
const columns = computed(() => props.board?.columns ?? [])
const hasBoardData = computed(() => props.board !== null)

const getStageAge = (value: string | null | undefined): string => {
  if (value === null || value === undefined || value === '') return '-'
  const start = new Date(value)
  if (Number.isNaN(start.getTime())) return '-'
  const days = Math.max(Math.floor((Date.now() - start.getTime()) / 86400000), 0)
  if (days === 0) return '今天'
  return `${days}天`
}

// 新鲜度：0–7 天无色，8–15 天警告，≥16 天危险；结束态不计
const getStageAgeTone = (card: BusinessJourneyBoardCard): 'warning' | 'danger' | undefined => {
  if (isBusinessJourneyEndStage(card.current_board_stage)) return undefined
  const value = card.last_event_at
  if (value === null || value === undefined || value === '') return undefined
  const start = new Date(value)
  if (Number.isNaN(start.getTime())) return undefined
  const days = Math.max(Math.floor((Date.now() - start.getTime()) / 86400000), 0)
  if (days <= 7) return undefined
  if (days <= 15) return 'warning'
  return 'danger'
}

const shouldShowStageAge = (card: BusinessJourneyBoardCard): boolean =>
  !isBusinessJourneyEndStage(card.current_board_stage)

const getEndStageLabel = (card: BusinessJourneyBoardCard): string =>
  card.current_board_stage === 'approval_rejected'
    ? '审批未通过 · 0%'
    : DEAL_JOURNEY_BOARD_STAGE_LABELS[card.current_board_stage]

type BoardCard = BusinessJourneyBoardCard

const shouldShowOpportunityStage = (card: BoardCard): boolean =>
  ['early_communication', 'active_progress', 'closing_soon'].includes(card.current_board_stage)

const getWinProbability = (card: BoardCard): string => {
  const value = card.primary_opportunity?.win_probability
  return value === null || value === undefined ? '-' : `${value}%`
}

const emitRowClick = (card: BoardCard): void => {
  emit('row-click', {
    customerId: card.customer_id,
    journeyPublicId: card.public_id
  })
}

const cardKey = (card: BoardCard): string => card.public_id

const cardAriaLabel = (card: BoardCard): string => `查看业务旅程：${card.journey_name}`
</script>

<template>
  <div class="business-board-view">
    <div
      v-if="errorMessage && hasBoardData"
      class="business-board-error"
      role="alert"
      aria-live="polite"
    >
      <AlertCircle class="error-icon" aria-hidden="true" />
      <span>{{ errorMessage }}</span>
      <TableToolbarButton
        class="business-board-inline-retry"
        :disabled="loading"
        @click="emit('retry')"
      >
        重试
      </TableToolbarButton>
    </div>

    <div
      v-if="loading && hasBoardData"
      class="business-board-refreshing"
      role="status"
      aria-live="polite"
    >
      <RefreshCw class="refreshing-icon spinning" aria-hidden="true" />
      <span>正在刷新，当前显示上次成功加载的数据</span>
    </div>

    <Card class="business-board-surface">
      <CardContent class="business-board-surface-content">
        <div class="business-board-scroll">
          <div v-if="loading && !hasBoardData" class="business-board-skeleton" aria-label="旅程看板加载中">
            <section v-for="index in 5" :key="index" class="business-board-column">
              <Skeleton class="h-8 w-24" />
              <Skeleton class="h-28 w-full" />
              <Skeleton class="h-28 w-full" />
              <Skeleton class="h-28 w-full" />
            </section>
          </div>

          <div v-else-if="!hasBoardData" class="business-board-blocking-error" role="alert">
            <AlertCircle class="blocking-error-icon" aria-hidden="true" />
            <strong>{{ errorMessage || '旅程看板暂时无法加载' }}</strong>
            <span>请检查网络连接后重试。</span>
            <TableToolbarButton :disabled="loading" @click="emit('retry')">
              {{ loading ? '加载中…' : '重新加载' }}
            </TableToolbarButton>
          </div>

          <div v-else class="business-board-columns">
            <section
              v-for="column in columns"
              :key="column.key"
              class="business-board-column"
            >
              <header class="column-header">
                <h2>{{ column.title }}</h2>
                <Badge variant="status" data-tone="neutral">
                  {{ column.count }}
                </Badge>
              </header>

              <div class="column-card-list">
                <Card
                  v-for="card in column.cards"
                  :key="cardKey(card)"
                  class="journey-card"
                  role="button"
                  tabindex="0"
                  :aria-label="cardAriaLabel(card)"
                  @click="emitRowClick(card)"
                  @keydown.enter.prevent="emitRowClick(card)"
                  @keydown.space.prevent="emitRowClick(card)"
                >
                  <CardContent class="journey-card-content">
                    <div class="journey-card-topline">
                      <span class="journey-customer">{{ card.customer_name ?? '-' }}</span>
                      <template v-if="shouldShowStageAge(card)">
                        <Badge
                          v-if="getStageAgeTone(card)"
                          variant="status"
                          class="journey-age"
                          :data-tone="getStageAgeTone(card)"
                        >
                          {{ getStageAge(card.last_event_at) }}
                        </Badge>
                        <span v-else class="journey-age journey-age--plain">
                          {{ getStageAge(card.last_event_at) }}
                        </span>
                      </template>
                    </div>

                    <div class="journey-title">{{ card.journey_name }}</div>

                    <div class="journey-main-metric">
                      <AmountText :value="card.amount" size="lg" tone="default" />
                    </div>

                    <div class="journey-tag-row">
                      <Badge
                        v-if="isBusinessJourneyEndStage(card.current_board_stage)"
                        variant="status"
                        class="journey-info-tag"
                        :data-tone="businessJourneyStageTone(card.current_board_stage)"
                      >
                        {{ getEndStageLabel(card) }}
                      </Badge>
                      <Badge
                        v-if="shouldShowOpportunityStage(card)"
                        variant="status"
                        class="journey-info-tag"
                        data-tone="neutral"
                      >
                        赢率 {{ getWinProbability(card) }}
                      </Badge>
                      <Badge
                        variant="status"
                        class="journey-info-tag"
                        data-tone="neutral"
                      >
                        <UserRound class="tag-icon" aria-hidden="true" />
                        {{ card.owner?.name ?? '-' }}
                      </Badge>
                    </div>

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
@use '@/styles/tokens.scss' as *;

.business-board-view {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  gap: $space-3;
  padding: $space-3; // 与图表视图 .journey-chart 同一内缩
}

.business-board-error,
.business-board-refreshing {
  display: flex;
  align-items: center;
  gap: $space-2;
  min-height: 40px;
  padding: 0 $space-3;
  border-radius: var(--radius-md);
  font-size: var(--font-size-caption);
}

.business-board-error {
  border: 1px solid color-mix(in srgb, hsl(var(--status-danger)) 18%, transparent);
  color: hsl(var(--status-danger));
  background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
}

.business-board-refreshing {
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
}

.business-board-inline-retry {
  flex-shrink: 0;
  margin-left: auto;
}

.refreshing-icon,
.error-icon {
  width: var(--icon-sm);
  height: var(--icon-sm);
  flex-shrink: 0;
}

.business-board-blocking-error {
  display: flex;
  flex: 1;
  min-width: 280px;
  min-height: 240px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $space-2;
  padding: $space-6;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.business-board-blocking-error strong {
  color: hsl(var(--foreground));
  font-size: var(--font-size-body);
}

.blocking-error-icon {
  width: $space-6;
  height: $space-6;
  color: hsl(var(--status-danger));
}

.business-board-surface {
  flex: 1;
  min-height: 0;
  border: 0;
  border-radius: var(--radius-md);
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
  padding-bottom: $space-2;
}

.business-board-columns,
.business-board-skeleton {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(280px, 320px);
  align-items: start;
  gap: $space-3;
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
  border-radius: var(--radius-lg);
  background: hsl(var(--muted));
}

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $space-2;
  padding: $space-3;
  border: 0;
  background: transparent;
  flex-shrink: 0;
}

.column-header h2 {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: var(--font-size-body-strong);
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
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius-lg);
  background: hsl(var(--card));
  box-shadow: none;
  cursor: pointer;
  transition: border-color 160ms ease, box-shadow 160ms ease;
}

.journey-card:hover,
.journey-card:focus-within {
  border-color: hsl(var(--ring-input));
  box-shadow: var(--shadow-1);
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
  font-size: var(--font-size-caption);
  font-weight: 600;
  line-height: 1.25;
}

.journey-age--plain {
  color: hsl(var(--muted-foreground));
  font-weight: 400;
}

.journey-title {
  color: hsl(var(--foreground));
  text-align: left;
  font-size: var(--font-size-body);
  line-height: 1.4;
  font-weight: 700;
}

.journey-customer {
  min-width: 0;
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-control-sm);
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
  font-size: var(--font-size-caption);
}

.journey-tag-row {
  flex-wrap: wrap;
  gap: 8px;
}

.journey-info-tag {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  max-width: 100%;
  gap: 5px;
  border: 0;
  font-size: var(--font-size-caption);
  font-weight: 500;
  line-height: 1.35;
}

.tag-icon,
.empty-icon {
  width: var(--icon-xs);
  height: var(--icon-xs);
  flex-shrink: 0;
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
  font-size: var(--font-size-control-sm);
}

.spinning {
  animation: business-board-spin 0.8s linear infinite;
}

@keyframes business-board-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .business-board-columns,
  .business-board-skeleton {
    grid-auto-columns: minmax(272px, 88vw);
  }
}
</style>
