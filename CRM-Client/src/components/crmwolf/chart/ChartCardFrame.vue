<script setup lang="ts">
import type { VNode } from 'vue'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'

withDefaults(defineProps<{
  cardKey: string
  title?: string
  description?: string
  wide?: boolean
  testIdPrefix?: string
  headerClass?: string
  contentClass?: string
}>(), {
  title: '',
  description: '',
  wide: false,
  testIdPrefix: 'chart-card',
  headerClass: '',
  contentClass: '',
})

defineSlots<{
  header?: () => VNode[]
  content?: () => VNode[]
  default?: () => VNode[]
  legend?: () => VNode[]
  footer?: () => VNode[]
}>()
</script>

<template>
  <Card
    class="chart-card-frame"
    :class="wide ? 'chart-card-frame--wide' : ''"
    :data-testid="`${testIdPrefix}-${cardKey}`"
  >
    <CardHeader v-if="$slots['header'] || title || description" :class="headerClass ?? ''">
      <slot name="header">
        <CardTitle v-if="title">{{ title }}</CardTitle>
        <CardDescription v-if="description">{{ description }}</CardDescription>
      </slot>
    </CardHeader>
    <CardContent v-if="$slots['content']" :class="contentClass ?? ''">
      <slot name="content" />
    </CardContent>
    <slot v-else />
    <slot name="legend" />
    <CardFooter v-if="$slots['footer']"><slot name="footer" /></CardFooter>
  </Card>
</template>

<style scoped>
.chart-card-frame {
  min-width: 0;
}

.chart-card-frame--wide {
  grid-column: 1 / -1;
}
</style>
