<script setup lang="ts">
/**
 * Tabs - shadcn-vue Tabs component
 * Container for tabbed interface
 */
import { TabsRoot } from 'radix-vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
  defaultValue?: string
  modelValue?: string
}

const props = withDefaults(defineProps<Props>(), {})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <TabsRoot
    :default-value="props.defaultValue"
    :model-value="props.modelValue"
    :class="cn('w-full', props.class)"
    @update:model-value="emit('update:modelValue', $event as string)"
  >
    <slot />
  </TabsRoot>
</template>