<script setup lang="ts">
type SegmentTone = 'primary' | 'success' | 'warning' | 'danger' | 'muted'

interface SegmentOption {
  value: string
  label: string
  tone?: SegmentTone
}

interface Props {
  modelValue: string
  options: SegmentOption[]
  disabled?: boolean
  labelledBy?: string
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  labelledBy: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

function selectOption(value: string): void {
  if (props.disabled || value === props.modelValue) return
  emit('update:modelValue', value)
}
</script>

<template>
  <div
    class="segmented-choice"
    role="radiogroup"
    :aria-labelledby="labelledBy"
  >
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="segmented-choice__option"
      :class="[
        `segmented-choice__option--${option.tone ?? 'muted'}`,
        { 'segmented-choice__option--active': modelValue === option.value },
      ]"
      role="radio"
      :aria-checked="modelValue === option.value"
      :disabled="disabled"
      @click="selectOption(option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.segmented-choice {
  display: grid;
  grid-template-columns: repeat(var(--segmented-choice-columns, 2), minmax(0, 1fr));
  gap: $wolf-space-sm-v2;
  width: 100%;
  min-width: 0;
}

.segmented-choice__option {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 0 $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-card-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
  white-space: nowrap;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease,
    box-shadow 0.16s ease,
    color 0.16s ease;

  &:hover:not(:disabled) {
    border-color: $wolf-border-hover-v2;
  }

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }

  &:disabled {
    cursor: not-allowed;
    color: $wolf-text-tertiary-v2;
    opacity: 0.72;
  }
}

.segmented-choice__option--primary:not(.segmented-choice__option--active) {
  color: $wolf-primary-v2;
}

.segmented-choice__option--success:not(.segmented-choice__option--active) {
  color: $wolf-success-v2;
}

.segmented-choice__option--warning:not(.segmented-choice__option--active) {
  color: $wolf-warning-text-v2;
}

.segmented-choice__option--danger:not(.segmented-choice__option--active) {
  color: $wolf-danger-v2;
}

.segmented-choice__option--primary.segmented-choice__option--active {
  border-color: $wolf-primary-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  box-shadow: inset 0 0 0 1px $wolf-primary-v2;
}

.segmented-choice__option--success.segmented-choice__option--active {
  border-color: $wolf-success-v2;
  background: $wolf-success-bg-v2;
  color: $wolf-success-v2;
  box-shadow: inset 0 0 0 1px $wolf-success-v2;
}

.segmented-choice__option--warning.segmented-choice__option--active {
  border-color: $wolf-warning-text-v2;
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
  box-shadow: inset 0 0 0 1px $wolf-warning-text-v2;
}

.segmented-choice__option--danger.segmented-choice__option--active {
  border-color: $wolf-danger-v2;
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-v2;
  box-shadow: inset 0 0 0 1px $wolf-danger-v2;
}

.segmented-choice__option--muted.segmented-choice__option--active {
  border-color: $wolf-border-default-v2;
  background: $wolf-bg-muted-v2;
  color: $wolf-text-primary-v2;
  box-shadow: inset 0 0 0 1px $wolf-border-default-v2;
}
</style>
