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
@use '@/styles/variables-v2.scss' as *;

.sales-assistant-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  flex: 1;
  min-height: 0;
  padding: $wolf-list-page-padding-top-v2 $wolf-page-padding-v2 $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .sales-assistant-page {
    padding: $wolf-page-padding-mobile-v2;
  }
}
</style>
