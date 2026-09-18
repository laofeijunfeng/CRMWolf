<script setup lang="ts">
interface Props {
  ariaLabel: string
  description?: string
}

withDefaults(defineProps<Props>(), {
  description: '',
})
</script>

<template>
  <main class="settings-content" :aria-label="ariaLabel">
    <p v-if="description.length > 0" class="settings-content__description">{{ description }}</p>
    <slot />
  </main>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.settings-content {
  min-height: 100%;
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.settings-content__description {
  margin: 0;
  font-size: $wolf-font-size-auxiliary-v2;
  color: $wolf-text-secondary-v2;
}

:deep(.settings-form-grid) {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-form-item-gap-v2;
}

:deep(.settings-form-grid-full) {
  grid-column: 1 / -1;
}

:deep(.settings-form-actions) {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-surface-v2;
  padding: $wolf-card-padding-v2;
  box-shadow: $wolf-shadow-card-v2;
}

:deep(.settings-dl) {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr) 120px minmax(0, 1fr);
  gap: $wolf-space-md-v2 $wolf-space-xl-v2;
  margin: 0;
  font-size: $wolf-font-size-body-v2;
}

:deep(.settings-dl dt) {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-auxiliary-v2;
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
  gap: $wolf-space-lg-v2;
  padding: $wolf-space-md-v2 0;
  border-top: 1px solid $wolf-border-light-v2;
}

:deep(.settings-setting-row:first-child) {
  border-top: 0;
  padding-top: 0;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .settings-content {
    padding: $wolf-page-padding-mobile-v2;
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
