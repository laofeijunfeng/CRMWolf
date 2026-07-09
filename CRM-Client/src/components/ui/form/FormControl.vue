<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { cn } from '@/lib/utils'

interface Props {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
</script>

<template>
  <slot
    v-bind="{
      id: formFieldId,
      name,
      error,
      modelValue,
      value,
      onBlur,
      onInput: setInputValue,
    }"
    :class="cn(props.class)"
  />
</template>