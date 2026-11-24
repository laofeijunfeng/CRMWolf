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
        <p v-if="error.description">{{ error.description }}</p>
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
@use '@/styles/tokens.scss' as *;

.feedback-alert__body {
  display: flex;
  flex-direction: column;
  gap: $space-1;
}

.feedback-alert__body p {
  margin: 0;
}

.feedback-alert__outcome {
  color: hsl(var(--muted-foreground));
}

.feedback-alert__meta {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
}

.feedback-alert__actions {
  display: flex;
  flex-wrap: wrap;
  gap: $space-1;
}

.feedback-alert__action {
  min-height: var(--touch-target);
}

.feedback-alert--compact {
  padding-top: $space-2;
  padding-bottom: $space-2;

  .feedback-alert__body {
    gap: 2px;
    font-size: var(--font-size-caption);
  }
}
</style>
