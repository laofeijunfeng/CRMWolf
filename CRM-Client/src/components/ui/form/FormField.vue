<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { FieldRoot } from 'vee-validate'
import { cn } from '@/lib/utils'

interface Props extends HTMLAttributes {
  class?: HTMLAttributes['class']
  name?: string
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <FieldRoot v-bind="delegatedProps" :class="cn(props.class)">
    <slot />
  </FieldRoot>
</template>