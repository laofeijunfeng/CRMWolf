<script setup lang="ts">
import { onActivated, onDeactivated, onMounted, onUnmounted } from 'vue'
import { useHeaderStore } from '@/stores/header'
import { usePageTitleStore } from '@/stores/pageTitle'
import SalesAssistantChat from '@/components/sales-assistant/SalesAssistantChat.vue'

const pageTitleStore = usePageTitleStore()
const headerStore = useHeaderStore()

const setupHeader = (): void => {
  pageTitleStore.setTitle('销售助手')
  headerStore.clear()
}

const clearHeader = (): void => {
  pageTitleStore.reset()
  headerStore.clear()
}

defineOptions({ name: 'SalesAssistant' })

onMounted(setupHeader)
onActivated(setupHeader)
onDeactivated(clearHeader)
onUnmounted(clearHeader)
</script>

<template>
  <div class="sales-assistant-page">
    <SalesAssistantChat />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.sales-assistant-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  flex: 1;
  min-height: 0;
  padding: var(--page-padding) var(--page-padding) var(--page-padding);
  background: hsl(var(--card));
}

@media (max-width: $bp-sm - 1) {
  .sales-assistant-page {
    padding: var(--page-padding);
  }
}
</style>
