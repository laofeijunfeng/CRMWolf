<script setup lang="ts">
interface Props {
  ariaLabel: string
  description?: string
}

const props = withDefaults(defineProps<Props>(), {
  description: '',
})
</script>

<template>
  <main class="settings-content" :aria-label="ariaLabel">
    <p v-if="props.description.length > 0" class="settings-content__description">{{ props.description }}</p>
    <slot />
  </main>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.settings-content {
  min-height: 100%;
  padding: var(--page-padding);
  background: hsl(var(--card));
  display: flex;
  flex-direction: column;
  gap: $space-4;
}

.settings-content__description {
  margin: 0;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

:deep(.settings-form-grid) {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $space-4;
}

:deep(.settings-form-grid-full) {
  grid-column: 1 / -1;
}

:deep(.settings-form-actions) {
  display: flex;
  justify-content: flex-end;
  gap: $space-2;
  background: hsl(var(--card));
  border-radius: var(--radius-lg);
  padding: $space-4;
  box-shadow: var(--shadow-1);
}

:deep(.settings-dl) {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr) 120px minmax(0, 1fr);
  gap: $space-3 $space-6;
  margin: 0;
  font-size: 14px;
}

:deep(.settings-dl dt) {
  color: hsl(var(--muted-foreground));
  font-size: 14px;
}

:deep(.settings-dl dd) {
  margin: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

:deep(.settings-setting-row) {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: $space-4;
  padding: $space-3 0;
  border-top: 1px solid hsl(var(--border));
}

:deep(.settings-setting-row:first-child) {
  border-top: 0;
  padding-top: 0;
}

@media (max-width: $bp-sm) {
  .settings-content {
    padding: var(--page-padding);
  }

  :deep(.settings-form-grid),
  :deep(.settings-dl) {
    grid-template-columns: 1fr;
  }

  :deep(.settings-setting-row) {
    flex-direction: column;
    align-items: stretch;
  }
}

</style>
