<script setup lang="ts">
import DetailContextHeader from '@/components/crmwolf/DetailContextHeader.vue'
import type { DetailContextNode } from '@/types/detailContext'

interface Props {
  nodes: readonly DetailContextNode[]
  canGoBack: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  back: []
  close: []
  navigate: [index: number]
}>()
</script>

<template>
  <div class="detail-context-host" data-testid="detail-context-host">
    <DetailContextHeader
      :nodes="props.nodes"
      :can-go-back="props.canGoBack"
      @back="emit('back')"
      @close="emit('close')"
      @navigate="emit('navigate', $event)"
    />
    <div class="detail-context-host__body">
      <slot />
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.detail-context-host {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: $wolf-bg-card-v2;
}

.detail-context-host__body {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
}
</style>
