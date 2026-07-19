<script setup lang="ts">
/**
 * DetailSheetContent - 统一的详情页 Sheet 组件
 *
 * 基于 MASTER.md §6.6 布局架构和 LAYOUT.md z-index 管理：
 * - 宽度：w-3/4 max-w-[1080px]（右侧 3/4，最大宽度 1080px）
 * - 移动端：全屏承载，使用动态视口高度并避开安全区域
 * - z-index：使用 SheetContent 默认 z-[201]（高于 Overlay z-[200]）
 * - 样式：统一白色背景、无边距（p-0）
 *
 * 规范依据：
 * - docs/LAYOUT.md - z-index 层级管理
 * - MASTER.md §3.5 - 组件封装原则（仅封装样式，保留原生动态效果）
 *
 * 使用场景：
 * - LeadDetailSheet（线索详情）
 * - OpportunityDetailSheet（商机详情）
 * - CustomerDetailSheet（客户详情）
 * - SystemConfig Sheet（系统配置）
 */
import { SheetContent } from '@/components/ui/sheet'

defineOptions({
  name: 'DetailSheetContent'
})
</script>

<template>
  <SheetContent
    side="right"
    class="detail-sheet-content w-screen max-w-none sm:w-3/4 sm:max-w-[1080px] p-0 flex flex-col"
  >
    <slot />
  </SheetContent>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.detail-sheet-content {
  height: $wolf-viewport-height-mobile-v2;
  max-height: $wolf-viewport-height-mobile-v2;
  padding-left: $wolf-safe-area-left-v2;
  padding-right: $wolf-safe-area-right-v2;
}

@media (min-width: $wolf-breakpoint-sm-v2) {
  .detail-sheet-content {
    height: 100%;
    max-height: 100%;
    padding-left: 0;
    padding-right: 0;
  }
}
</style>
