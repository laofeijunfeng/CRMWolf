<template>
  <div class="agent-page">
    <CRMAgentChat />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from "vue"
import { usePageTitleStore } from "@/stores/pageTitle"
import { useHeaderStore } from "@/stores/header"
import CRMAgentChat from "@/components/agent/CRMAgentChat.vue"

const pageTitleStore = usePageTitleStore()
const headerStore = useHeaderStore()

onMounted(() => {
  pageTitleStore.setTitle("AI Agent")
  headerStore.clear()
})

onUnmounted(() => {
  pageTitleStore.reset()
  headerStore.clear()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.agent-page {
  display: flex;
  flex: 1;
  min-height: 0;
  padding: $wolf-list-page-padding-top-v2 $wolf-page-padding-v2 $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .agent-page {
    padding: $wolf-page-padding-mobile-v2;
  }
}
</style>
