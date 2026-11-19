<script setup lang="ts">
import { computed } from 'vue'
import type { PropType, Component } from 'vue'
import { AlertCircle, Lock } from 'lucide-vue-next'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'

interface VariantConfig {
  icon: Component
  mediaClass: string
}

const VARIANT_MAP: Record<'error' | 'forbidden', VariantConfig> = {
  error: {
    icon: AlertCircle,
    mediaClass: 'bg-destructive/10 text-destructive'
  },
  forbidden: {
    icon: Lock,
    mediaClass: 'bg-destructive/10 text-destructive'
  }
}

const props = defineProps({
  variant: {
    type: String as PropType<'error' | 'forbidden'>,
    default: 'error'
  },
  title: {
    type: String,
    required: true
  },
  description: {
    type: String,
    default: ''
  }
})

const config = computed<VariantConfig>(() => VARIANT_MAP[props.variant])
</script>

<template>
  <Empty class="min-h-[200px] border-0" role="alert" :aria-label="title">
    <EmptyHeader>
      <EmptyMedia variant="icon" :class="config.mediaClass">
        <component :is="config.icon" class="size-5" aria-hidden="true" />
      </EmptyMedia>
      <EmptyTitle>{{ title }}</EmptyTitle>
      <EmptyDescription v-if="description">
        {{ description }}
      </EmptyDescription>
    </EmptyHeader>
    <div v-if="$slots['action']" class="flex items-center justify-center gap-2">
      <slot name="action" />
    </div>
  </Empty>
</template>
