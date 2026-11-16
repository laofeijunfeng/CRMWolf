/**
 * ApprovalStatusBadge — generic approval status badge.
 *
 * The public props and icon cues remain stable while the visual base and
 * semantic presentation are shared with other business-status badges.
 */
<script setup lang="ts">
import { computed, type Component } from 'vue'
import {
  Clock,
  CheckCircle2,
  XCircle,
  MinusCircle,
} from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { getStatusPresentation } from '@/utils/statusPresentation'
import type { StatusTone } from '@/utils/statusPresentation'

const props = withDefaults(defineProps<{
  status: string
  size?: 'default' | 'small'
}>(), {
  size: 'default',
})

const iconMap: Record<string, Component> = {
  PENDING: Clock,
  APPROVED: CheckCircle2,
  REJECTED: XCircle,
  CANCELLED: MinusCircle,
}

const presentation = computed(() => getStatusPresentation('approval', props.status))
const tone = computed<StatusTone>(() => presentation.value.tone)
const icon = computed(() => Object.prototype.hasOwnProperty.call(iconMap, props.status) ? iconMap[props.status] : MinusCircle)
const isUnknown = computed(() => presentation.value.traceValue !== undefined)
const title = computed(() => isUnknown.value ? `approval: ${presentation.value.traceValue}` : undefined)
</script>

<template>
  <Badge
    variant="status"
    class="approval-status-badge"
    :class="size === 'small' ? 'approval-status-badge--small' : ''"
    :data-status-tone="tone"
    data-status-domain="approval"
    :data-status-value="status"
    :title="title"
    role="status"
    :aria-label="presentation.label"
  >
    <component
      :is="icon"
      class="approval-status-badge__icon"
      :size="size === 'small' ? 12 : 14"
      aria-hidden="true"
    />
    <span class="approval-status-badge__label">{{ presentation.label }}</span>
  </Badge>
</template>

<style scoped lang="scss">
.approval-status-badge {
  height: 22px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.5;
  white-space: nowrap;
  vertical-align: middle;

  .approval-status-badge__icon {
    flex-shrink: 0;
  }

  .approval-status-badge__label {
    color: inherit;
  }
}

.approval-status-badge--small {
  height: 18px;
  padding: 2px 6px;
  font-size: 11px;
}
</style>
