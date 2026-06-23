<!-- CRM-Client/src/components/SmartBoundaryLine.vue -->
<template>
  <div
    class="smart-boundary-line"
    :class="{ 'is-active': active }"
    style="height: 2px"
  ></div>
</template>

<script setup lang="ts">
interface Props {
  active: boolean
}

const props = defineProps<Props>()
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.smart-boundary-line {
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    $wolf-primary 20%,
    $wolf-primary 80%,
    transparent 100%
  );

  &.is-active {
    animation: flow 2s ease-in-out infinite;
  }
}

@keyframes flow {
  0%, 100% {
    transform: scaleX(0.8);
    opacity: 0.6;
  }
  50% {
    transform: scaleX(1);
    opacity: 1;
  }
}

// ← Reduced Motion 支持（WCAG 要求）
@media (prefers-reduced-motion: reduce) {
  .smart-boundary-line.is-active {
    animation: none;
    opacity: 0.8;
  }
}
</style>