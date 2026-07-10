<script setup lang="ts">
/**
 * EmptyState - Empty State Guidance Component
 * UI/UX Pro Max Compliant:
 * - §8 MEDIUM: Helpful message and action when no content
 * - §8 MEDIUM: Error-recovery (clear recovery path)
 * - §1 CRITICAL: Accessible content
 *
 * Based on shadcn-vue Button (§1.5 shadcn-vue 优先原则)
 */
import { computed } from 'vue'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import type { Component } from 'vue'

interface Props {
  /** Title text */
  title: string
  /** Description text */
  description?: string
  /** Icon component */
  icon?: Component | null
  /** Action button label */
  actionLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  description: undefined,
  icon: null,
  actionLabel: undefined,
})

const emit = defineEmits<{
  action: []
}>()

const containerClasses = computed((): string =>
  cn(
    'empty-state',
    'flex flex-col items-center justify-center',
    'min-h-[200px]',
    'px-wolf-lg py-wolf-xl',
    'text-center'
  )
)
</script>

<template>
  <div :class="containerClasses" role="status" aria-live="polite">
    <!-- Icon (optional) -->
    <div
      v-if="icon"
      class="empty-state-icon mb-wolf-md text-wolf-text-placeholder"
    >
      <component :is="icon" class="w-16 h-16" aria-hidden="true" />
    </div>

    <!-- Title -->
    <h3 class="empty-state-title text-wolf-body font-wolf-medium text-wolf-text-primary mb-wolf-sm">
      {{ title }}
    </h3>

    <!-- Description (optional) -->
    <p
      v-if="description"
      class="empty-state-description text-wolf-caption text-wolf-text-tertiary max-w-[300px] mb-wolf-md"
    >
      {{ description }}
    </p>

    <!-- Action Button (using shadcn-vue Button) -->
    <Button
      v-if="actionLabel"
      size="lg"
      @click="emit('action')"
    >
      {{ actionLabel }}
    </Button>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.empty-state-icon {
  opacity: 0.6;
}

.empty-state-title {
  line-height: 1.4;
}

.empty-state-description {
  line-height: 1.5;
}
</style>