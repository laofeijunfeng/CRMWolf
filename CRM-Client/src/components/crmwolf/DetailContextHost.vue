<script setup lang="ts">
import { ref } from 'vue'
import DetailContextHeader from '@/components/crmwolf/DetailContextHeader.vue'
import type { DetailContextNode } from '@/types/detailContext'

interface Props {
  nodes: readonly DetailContextNode[]
  canGoBack: boolean
  showHeader?: boolean
}

const props = withDefaults(defineProps<Props>(), { showHeader: true })
const headerRef = ref<{ focusBackButton: () => void } | null>(null)

function focusBackButton(): void {
  headerRef.value?.focusBackButton()
}

defineExpose({ focusBackButton })

const emit = defineEmits<{
  back: []
  close: []
  navigate: [index: number]
}>()
</script>

<template>
  <div class="detail-context-host" data-testid="detail-context-host">
    <DetailContextHeader
      v-if="props.showHeader"
      ref="headerRef"
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

.detail-context-host {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: hsl(var(--card));
}

.detail-context-host__body {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
}
</style>
