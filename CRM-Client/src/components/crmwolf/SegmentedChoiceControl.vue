<script setup lang="ts">
import { computed } from 'vue'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Label } from '@/components/ui/label'

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
  labelledBy?: string | undefined
  idPrefix?: string | undefined
  invalid?: boolean
  describedBy?: string | undefined
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  labelledBy: undefined,
  idPrefix: undefined,
  invalid: false,
  describedBy: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

function selectOption(value: string): void {
  if (props.disabled || value === props.modelValue) return
  emit('update:modelValue', value)
}

const controlIdPrefix = computed(() =>
  props.idPrefix ?? `segmented-choice-${Math.random().toString(36).slice(2, 9)}`
)
const isDisabled = computed(() => props.disabled === true)
const ariaBindings = computed<Record<string, string>>(() => {
  const bindings: Record<string, string> = {}
  if (props.labelledBy !== undefined && props.labelledBy.trim().length > 0) {
    bindings['aria-labelledby'] = props.labelledBy
  }
  if (props.invalid) {
    bindings['aria-invalid'] = 'true'
  }
  if (props.describedBy !== undefined && props.describedBy.trim().length > 0) {
    bindings['aria-describedby'] = props.describedBy
  }
  return bindings
})

function optionId(value: string): string {
  return `${controlIdPrefix.value}-${value.replace(/[^a-zA-Z0-9_-]/g, '-')}`
}
</script>

<template>
  <RadioGroup
    :model-value="modelValue"
    class="segmented-choice"
    v-bind="ariaBindings"
    :disabled="isDisabled"
    @update:model-value="selectOption(String($event))"
  >
    <div
      v-for="option in options"
      :key="option.value"
      class="segmented-choice__item"
    >
      <RadioGroupItem
        :id="optionId(option.value)"
        class="segmented-choice__radio !absolute !h-full !w-full !border-0 !bg-transparent !p-0 !opacity-0 !shadow-none !ring-0"
        :value="option.value"
      />
      <Label
        :for="optionId(option.value)"
        class="segmented-choice__option"
        :class="[
          `segmented-choice__option--${option.tone ?? 'muted'}`,
          { 'segmented-choice__option--active': modelValue === option.value },
        ]"
        :title="option.label"
      >
        <span class="segmented-choice__label">{{ option.label }}</span>
      </Label>
    </div>
  </RadioGroup>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.segmented-choice {
  display: grid;
  grid-template-columns: repeat(var(--segmented-choice-columns, 2), minmax(0, 1fr));
  gap: $space-2;
  width: 100%;
  min-width: 0;
}

.segmented-choice__item {
  position: relative;
  min-width: 0;
  min-height: var(--control-h-md);
}

.segmented-choice__radio {
  inset: 0;
  margin: 0;
  cursor: pointer;
  z-index: 1;
  appearance: none;
}

.segmented-choice__option {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  width: 100%;
  height: auto;
  min-height: var(--control-h-md);
  padding: 0 $space-3;
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius-md);
  background: hsl(var(--card));
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-body);
  font-weight: 500;
  line-height: 20px;
  white-space: nowrap;
  overflow: hidden;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease,
    box-shadow 0.16s ease,
    color 0.16s ease;
  cursor: pointer;
  pointer-events: none;
}

.segmented-choice__label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: center;
}

.segmented-choice__item:hover .segmented-choice__option {
  border-color: hsl(var(--brand));
}

.segmented-choice__radio:focus-visible + .segmented-choice__option {
  outline: 2px solid hsl(var(--ring) / 0.5);
  outline-offset: 2px;
}

.segmented-choice__radio:disabled + .segmented-choice__option {
  cursor: not-allowed;
  color: hsl(var(--muted-foreground));
  opacity: 0.72;
}

.segmented-choice__option--primary:not(.segmented-choice__option--active) {
  color: hsl(var(--brand));
}

.segmented-choice__option--success:not(.segmented-choice__option--active) {
  color: hsl(var(--status-success));
}

.segmented-choice__option--warning:not(.segmented-choice__option--active) {
  color: hsl(var(--status-warning));
}

.segmented-choice__option--danger:not(.segmented-choice__option--active) {
  color: hsl(var(--status-danger));
}

.segmented-choice__option--primary.segmented-choice__option--active {
  border-color: hsl(var(--brand));
  background: var(--wash-hover);
  color: hsl(var(--brand));
  box-shadow: inset 0 0 0 1px hsl(var(--brand));
}

.segmented-choice__option--success.segmented-choice__option--active {
  border-color: hsl(var(--status-success));
  background: color-mix(in srgb, hsl(var(--status-success)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-success));
  box-shadow: inset 0 0 0 1px hsl(var(--status-success));
}

.segmented-choice__option--warning.segmented-choice__option--active {
  border-color: hsl(var(--status-warning));
  background: color-mix(in srgb, hsl(var(--status-warning)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-warning));
  box-shadow: inset 0 0 0 1px hsl(var(--status-warning));
}

.segmented-choice__option--danger.segmented-choice__option--active {
  border-color: hsl(var(--status-danger));
  background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-danger));
  box-shadow: inset 0 0 0 1px hsl(var(--status-danger));
}

.segmented-choice__option--muted.segmented-choice__option--active {
  border-color: hsl(var(--border));
  background: hsl(var(--muted));
  color: hsl(var(--foreground));
  box-shadow: inset 0 0 0 1px hsl(var(--border));
}
</style>
