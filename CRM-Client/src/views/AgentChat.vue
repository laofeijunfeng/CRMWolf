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
@use '@/styles/tokens.scss' as *;

.agent-page {
  display: flex;
  flex: 1;
  min-height: 0;
  padding: var(--page-padding) var(--page-padding) var(--page-padding);
  background: hsl(var(--card));
}

@media (max-width: $bp-sm - 1) {
  .agent-page {
    padding: var(--page-padding);
  }
}
</style>
