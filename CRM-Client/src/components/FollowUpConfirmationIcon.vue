<template>
  <RouterLink
    to="/follow-up-confirmations"
    :class="buttonVariants({ variant: 'ghost', size: 'icon-sm', class: 'relative shrink-0' })"
    :aria-label="ariaLabel"
    data-testid="follow-up-confirmation-link"
  >
    <ListChecks class="size-4 text-muted-foreground" aria-hidden="true" />
    <span
      v-if="pendingCount > 0"
      class="absolute right-0.5 top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-none text-destructive-foreground"
      data-testid="follow-up-confirmation-badge"
    >
      {{ displayCount }}
    </span>
  </RouterLink>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { RouterLink } from 'vue-router'
import { ListChecks } from 'lucide-vue-next'
import { buttonVariants } from '@/components/ui/button'
import { useFollowUpConfirmationStore } from '@/stores/followUpConfirmation'
import { logger } from '@/utils/logger'

const store = useFollowUpConfirmationStore()
const { pendingCount } = storeToRefs(store)
const { fetchPendingCount } = store

const ariaLabel = computed(() => pendingCount.value > 0
  ? `跟进确认中心，待确认 ${pendingCount.value} 条`
  : '跟进确认中心，无待确认事项')

const displayCount = computed(() => pendingCount.value > 99 ? '99+' : String(pendingCount.value))
const refreshIntervalMs = 45_000
let refreshTimer: number | undefined
let refreshInFlight = false

const refreshPendingCount = async (): Promise<void> => {
  if (refreshInFlight) return
  refreshInFlight = true
  try {
    await fetchPendingCount()
  } catch (error) {
    logger.warn('[FollowUpConfirmationIcon]', '待确认数量加载失败', { error })
  } finally {
    refreshInFlight = false
  }
}

const handleWindowFocus = (): void => {
  void refreshPendingCount()
}

const handleVisibilityChange = (): void => {
  if (document.visibilityState === 'visible') {
    void refreshPendingCount()
  }
}

onMounted(() => {
  void refreshPendingCount()
  refreshTimer = window.setInterval(() => {
    void refreshPendingCount()
  }, refreshIntervalMs)
  window.addEventListener('focus', handleWindowFocus)
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onBeforeUnmount(() => {
  if (refreshTimer !== undefined) {
    window.clearInterval(refreshTimer)
  }
  window.removeEventListener('focus', handleWindowFocus)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>
