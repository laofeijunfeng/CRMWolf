<script setup lang="ts">
/**
 * Tabs - shadcn-vue Tabs component
 * Container for tabbed interface
 */
import { TabsRoot, type TabsRootProps } from 'reka-ui'
import { cn } from '@/lib/utils'
import { computed, type HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
  defaultValue?: string
  modelValue?: string
}

const props = withDefaults(defineProps<Props>(), {})
const rootProps = computed<TabsRootProps>(() => ({
  ...(props.defaultValue !== undefined ? { defaultValue: props.defaultValue } : {}),
  ...(props.modelValue !== undefined ? { modelValue: props.modelValue } : {}),
}))

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <TabsRoot
    v-bind="rootProps"
    :class="cn('w-full', props.class)"
    @update:model-value="emit('update:modelValue', $event as string)"
  >
    <slot />
  </TabsRoot>
</template>