<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { Primitive } from "reka-ui"
import { computed } from "vue"
import { useChart } from "."

defineProps<{
  id?: HTMLAttributes["id"]
}>()

const { config } = useChart()

const colorConfig = computed(() => {
  return Object.entries(config.value).filter(
    ([, item]) => item.color !== undefined && item.color !== "",
  )
})
</script>

<template>
  <Primitive
    v-if="colorConfig.length"
    as="style"
  >
    {{ `
[data-chart=${id}] {
${colorConfig.map(([key, itemConfig]) => `  --color-${key}: ${itemConfig.color};`).join("\n")}
}
` }}
  </Primitive>
</template>
