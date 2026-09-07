<script setup lang="ts">
import { computed } from 'vue'
import { AlertCircle, Lock } from 'lucide-vue-next'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type { FeedbackError } from '@/types/feedback'

interface Props {
  error: FeedbackError | null
  density?: 'default' | 'compact'
  retryLabel?: string
  refreshLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  density: 'default',
  retryLabel: '重试',
  refreshLabel: '刷新',
})

const emit = defineEmits<{
  retry: []
  refresh: []
}>()

const isForbidden = computed(() =>
  props.error?.variant === 'forbidden' || props.error?.kind === 'permission',
)
const alertVariant = computed(() => isForbidden.value ? 'warning' : 'destructive')
const hasRecoveryAction = computed(() =>
  props.error?.retryable === true || props.error?.canRefresh === true,
)
const feedbackAlertClass = computed(() => [
  'feedback-alert',
  ...(props.density === 'compact' ? ['feedback-alert--compact'] : []),
].join(' '))
</script>

<template>
  <Alert
    v-if="error !== null"
    :variant="alertVariant"
    :class="feedbackAlertClass"
    aria-live="assertive"
    aria-atomic="true"
  >
    <Lock v-if="isForbidden" aria-hidden="true" />
    <AlertCircle v-else aria-hidden="true" />

    <AlertTitle>{{ error.title }}</AlertTitle>
    <AlertDescription as-child>
      <div class="feedback-alert__body">
        <p>{{ error.description }}</p>
        <p v-if="error.outcomeUnknown" class="feedback-alert__outcome">
          请先确认记录状态，避免重复提交。
        </p>
        <p v-if="error.requestId" class="feedback-alert__meta">
          请求标识：{{ error.requestId }}
        </p>

        <div
          v-if="hasRecoveryAction || $slots['actions']"
          class="feedback-alert__actions"
        >
          <Button
            v-if="error.retryable"
            type="button"
            variant="outline"
            size="sm"
            class="feedback-alert__action"
            @click="emit('retry')"
          >
            {{ retryLabel }}
          </Button>
          <Button
            v-if="error.canRefresh"
            type="button"
            variant="outline"
            size="sm"
            class="feedback-alert__action"
            @click="emit('refresh')"
          >
            {{ refreshLabel }}
          </Button>
          <slot name="actions" />
        </div>
      </div>
    </AlertDescription>
  </Alert>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.feedback-alert__body {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.feedback-alert__body p {
  margin: 0;
}

.feedback-alert__outcome {
  color: $wolf-text-secondary-v2;
}

.feedback-alert__meta {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.feedback-alert__actions {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2;
}

.feedback-alert__action {
  min-height: $wolf-touch-target-min-v2;
}

.feedback-alert--compact {
  padding-top: $wolf-space-sm-v2;
  padding-bottom: $wolf-space-sm-v2;

  .feedback-alert__body {
    gap: 2px;
    font-size: $wolf-font-size-caption-v2;
  }
}
</style>
