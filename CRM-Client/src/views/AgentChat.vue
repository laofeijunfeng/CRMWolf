<template>
  <CRMAgentChat />
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
