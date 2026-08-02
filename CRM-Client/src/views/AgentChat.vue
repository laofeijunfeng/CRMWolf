<template>
  <div class="agent-page">
    <CRMAgentChat />
  </div>
</template>

<script setup lang="ts">
import { onActivated, onDeactivated, onMounted, onUnmounted } from "vue"
import { usePageTitleStore } from "@/stores/pageTitle"
import { useHeaderStore } from "@/stores/header"
import CRMAgentChat from "@/components/agent/CRMAgentChat.vue"

const pageTitleStore = usePageTitleStore()
const headerStore = useHeaderStore()

const setupAgentHeader = (): void => {
  pageTitleStore.setTitle("AI Agent")
  headerStore.clear()
}

const clearAgentHeader = (): void => {
  pageTitleStore.reset()
  headerStore.clear()
}

defineOptions({
  name: "AgentChat",
})

onMounted(setupAgentHeader)

onActivated(setupAgentHeader)

onDeactivated(clearAgentHeader)

onUnmounted(clearAgentHeader)
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
