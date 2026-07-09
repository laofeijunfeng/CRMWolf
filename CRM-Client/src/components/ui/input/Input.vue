<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { useVModel } from '@vueuse/core'
import { cn } from '@/lib/utils'

interface Props extends /* @vue-ignore */ HTMLAttributes<HTMLInputElement> {
  defaultValue?: string | number
  modelValue?: string | number
}

const props = withDefaults(defineProps<Props>(), {
  defaultValue: '',
  modelValue: undefined,
})

const emits = defineEmits<{
  (e: 'update:modelValue', payload: string | number): void
}>()

const modelValue = useVModel(props, 'modelValue', emits, {
  passive: true,
  defaultValue: props.defaultValue,
})

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <input
    v-model="modelValue"
    v-bind="delegatedProps"
    :class="cn(
      'flex h-input-desktop w-full rounded-wolf border border-wolf-border-default bg-wolf-bg-card px-wolf-md text-wolf-body font-wolf ring-offset-wolf file:border-0 file:bg-transparent file:text-wolf-body file:font-wolf-medium placeholder:text-wolf-text-placeholder focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-38',
      'mobile:h-input-mobile mobile:px-wolf-xl',
      props.class,
    )"
  >
</template>