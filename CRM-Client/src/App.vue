<template>
  <!-- UI/UX Pro Max §8: Toast notification container (global position) -->
  <Toast position="top-center" :duration="4000" />
  <!-- UI/UX Pro Max §8: Confirm dialog container (global) -->
  <ConfirmDialog />
  <TooltipProvider>
    <router-view />
  </TooltipProvider>
</template>

<script setup lang="ts">
/**
 * App Root Component
 * Global providers and containers
 *
 * UI/UX Pro Max compliance:
 * - Toast container at root level - §8 toast-accessibility
 * - z-index: 1000 (highest) - §5 z-index-management
 */
import { Toast, ConfirmDialog, TooltipProvider } from '@/components/crmwolf'
</script>

<style>
/* ==================== Global Base Styles ==================== */

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  /* 基础字体栈（功能性，不在关键位置覆盖） */
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f5f7fa;
  color: #1d2129;
}

#app {
  width: 100%;
  min-height: 100vh;
}
</style>
