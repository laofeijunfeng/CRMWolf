<script setup lang="ts">
import { computed } from 'vue'
import { AlertCircle, RefreshCw } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { BoardCardActivation, BoardTone } from './boardTypes'

export interface JourneyBoardCard {
  id: string | number
  context: string
  title: string
  owner: string
}

export interface JourneyBoardColumn {
  key: string
  label: string
  tone: BoardTone
  countLabel: string
  cards: readonly JourneyBoardCard[]
}

interface Props {
  columns: readonly JourneyBoardColumn[] | null
  loading?: boolean
  refreshing?: boolean
  stale?: boolean
  error?: Error | null
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  refreshing: false,
  stale: false,
  error: null,
})

const emit = defineEmits<{
  'activate-card': [payload: BoardCardActivation]
  retry: []
}>()

const columns = computed(() => props.columns ?? [])
const showSkeleton = computed(() => props.loading && props.columns === null)
const showBlockingError = computed(() => props.error !== null && props.columns === null && !props.loading)

function displayLine(value: string): string {
  const trimmed = value.trim()
  return trimmed === '' ? '-' : trimmed
}

function activateCard(column: JourneyBoardColumn, card: JourneyBoardCard): void {
  emit('activate-card', { id: card.id, columnKey: column.key })
}
</script>

<template>
  <section class="journey-board" :aria-busy="loading || refreshing ? 'true' : undefined">
    <div v-if="error && columns.length > 0" class="journey-board__alert" role="alert">
      <AlertCircle class="journey-board__icon" aria-hidden="true" />
      <span>{{ stale ? '数据已过期' : '刷新失败' }}：{{ error.message }}</span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        data-testid="board-inline-retry"
        :disabled="loading || refreshing"
        @click="emit('retry')"
      >
        重试
      </Button>
    </div>

    <div v-if="refreshing && columns.length > 0" class="journey-board__status" role="status">
      <RefreshCw class="journey-board__icon" aria-hidden="true" />
      <span>正在刷新，当前显示上次成功加载的数据</span>
    </div>

    <div v-if="showSkeleton" class="journey-board__columns" data-testid="board-skeleton" aria-label="看板加载中">
      <section v-for="index in 4" :key="`column-${index}`" class="journey-board__column">
        <Skeleton class="h-8 w-24" />
        <Skeleton class="h-24 w-full" />
        <Skeleton class="h-24 w-full" />
      </section>
    </div>

    <div v-else-if="showBlockingError" class="journey-board__blocking" role="alert">
      <AlertCircle class="journey-board__icon" aria-hidden="true" />
      <strong>{{ error?.message || '看板暂时无法加载' }}</strong>
      <span>请检查网络连接后重试。</span>
      <Button type="button" data-testid="board-blocking-retry" @click="emit('retry')">
        重新加载
      </Button>
    </div>

    <div v-else class="journey-board__scroll">
      <div class="journey-board__columns">
        <section
          v-for="column in columns"
          :key="column.key"
          class="journey-board__column"
          :data-column-key="column.key"
          :data-tone="column.tone"
        >
          <header class="journey-board__header">
            <h2>{{ column.label }}</h2>
            <span class="journey-board__count">{{ column.countLabel }}</span>
          </header>
          <div class="journey-board__cards">
            <Card
              v-for="card in column.cards"
              :key="String(card.id)"
              class="journey-board__card"
              tabindex="0"
              role="button"
              :aria-label="`查看${column.label}：${displayLine(card.title)}`"
              @click="activateCard(column, card)"
              @keydown.enter.prevent="activateCard(column, card)"
              @keydown.space.prevent="activateCard(column, card)"
            >
              <CardContent class="journey-board__card-content">
                <span class="journey-board__context">{{ displayLine(card.context) }}</span>
                <strong>{{ displayLine(card.title) }}</strong>
                <Badge variant="outline" class="journey-board__owner">{{ displayLine(card.owner) }}</Badge>
              </CardContent>
            </Card>
            <p v-if="column.cards.length === 0" class="journey-board__empty">暂无记录</p>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

/* DataTable 有 replacement 时不套用列表高度，图表才能按内容增高。
   看板要沿用列表那张卡片的视口高度，列才能在里面自己滚动。
   选择器只命中本组件，业务旅程和图表不受影响。 */
:global(.data-table-card:has(.journey-board)) {
  height: calc(100vh - 121px);
  max-height: calc(100vh - 121px);
}

.journey-board {
  display: flex;
  box-sizing: border-box;
  min-width: 0;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  padding: $wolf-space-md-v2;
}

.journey-board__alert,
.journey-board__status,
.journey-board__blocking {
  display: flex;
  align-items: center;
  gap: 8px;
}

.journey-board__alert,
.journey-board__blocking {
  color: hsl(var(--destructive));
}

.journey-board__blocking {
  min-height: 240px;
  flex-direction: column;
  justify-content: center;
}

.journey-board__blocking strong {
  color: hsl(var(--foreground));
}

.journey-board__icon {
  width: 16px;
  height: 16px;
  flex: none;
}

.journey-board__scroll {
  min-width: 0;
  min-height: 0;
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
}

.journey-board__columns {
  display: grid;
  height: 100%;
  min-height: 0;
  grid-auto-flow: column;
  grid-auto-columns: minmax(280px, 320px);
  align-items: stretch;
  gap: 12px;
}

.journey-board__column {
  display: flex;
  min-width: 0;
  min-height: 0;
  max-height: 100%;
  flex-direction: column;
  overflow: hidden;
  border-radius: 8px;
  background: hsl(var(--muted));
}

.journey-board__column[data-tone='info'] {
  background: hsl(var(--info) / 0.12);
}

.journey-board__column[data-tone='success'] {
  background: hsl(var(--success) / 0.12);
}

.journey-board__column[data-tone='warning'] {
  background: hsl(var(--warning) / 0.14);
}

.journey-board__column[data-tone='danger'] {
  background: hsl(var(--destructive) / 0.1);
}

.journey-board__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px;
}

.journey-board__header h2,
.journey-board__card strong {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: 15px;
  line-height: 1.4;
}

.journey-board__count {
  color: hsl(var(--muted-foreground));
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
}

.journey-board__column[data-tone='info'] .journey-board__count {
  color: hsl(var(--info));
}

.journey-board__column[data-tone='success'] .journey-board__count {
  color: hsl(var(--success));
}

.journey-board__column[data-tone='warning'] .journey-board__count {
  color: hsl(var(--warning));
}

.journey-board__column[data-tone='danger'] .journey-board__count {
  color: hsl(var(--destructive));
}

.journey-board__cards {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0 8px 8px;
}

.journey-board__card {
  flex: none;
  border: 1px solid transparent;
  border-radius: 8px;
  background: hsl(var(--card));
  box-shadow: none;
  cursor: pointer;
}

.journey-board__card:hover,
.journey-board__card:focus-visible {
  border-color: hsl(var(--border));
  outline: none;
}

.journey-board__card-content {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
}

.journey-board__context {
  max-width: 100%;
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.journey-board__owner {
  border-color: transparent;
  background: hsl(var(--info) / 0.12);
  color: hsl(var(--info));
  font-weight: 500;
}

.journey-board__empty {
  display: flex;
  min-height: 96px;
  align-items: center;
  justify-content: center;
  border: 1px dashed hsl(var(--border));
  border-radius: 8px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--card) / 0.64);
}

@media (max-width: 900px) {
  .journey-board__columns {
    grid-auto-columns: minmax(272px, 88vw);
  }
}

/* 窄屏列表卡片被 DataTable 写成 height: auto !important，列会跟着内容变高。
   看板仍要占满工具栏下面的视口，才能左右滑列、在列里往下滚。 */
@media (max-width: 767px) {
  :global(.data-table-card.has-mobile-cards:has(.journey-board)) {
    height: calc(100dvh - 132px) !important;
    max-height: calc(100dvh - 132px) !important;
    overflow: hidden !important;
  }
}
</style>
