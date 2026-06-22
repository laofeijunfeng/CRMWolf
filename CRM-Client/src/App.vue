<template>
  <router-view />
</template>

<script setup lang="ts">
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
