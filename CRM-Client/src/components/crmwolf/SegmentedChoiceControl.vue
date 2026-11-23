<script setup lang="ts" generic="T extends string | string[] = string">
import { computed } from 'vue'
import { CheckboxGroupRoot, CheckboxRoot, RadioGroupRoot, RadioGroupItem } from 'reka-ui'

import { segmentedChoiceOptionId } from './segmentedChoiceControl'

type SegmentTone = 'primary' | 'success' | 'warning' | 'danger' | 'muted' | 'choice'

interface SegmentOption {
  value: string
  label: string
  tone?: SegmentTone
  /** 说明行；禁用项用它说明原因。带说明行的瓦片是双行、左对齐。 */
  description?: string | null | undefined
  /** 分组标题；与上一项不同时，在它上方渲染一行标题。 */
  group?: string | null | undefined
  disabled?: boolean | undefined
}

interface Props {
  modelValue: T
  options: SegmentOption[]
  disabled?: boolean
  /** 多选：语义换成 checkbox，外观不变；modelValue 为已选值数组。 */
  multiple?: boolean
  /** 标签与说明可换行，不再用省略号截断（选项文字较长时使用）。 */
  wrap?: boolean
  labelledBy?: string | undefined
  idPrefix?: string | undefined
  invalid?: boolean
  describedBy?: string | undefined
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  multiple: false,
  wrap: false,
  labelledBy: undefined,
  idPrefix: undefined,
  invalid: false,
  describedBy: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: T]
}>()

const controlIdPrefix = computed(() =>
  props.idPrefix ?? `segmented-choice-${Math.random().toString(36).slice(2, 9)}`
)
const isDisabled = computed(() => props.disabled === true)
const selectedValues = computed<string[]>(() => {
  if (Array.isArray(props.modelValue)) return props.modelValue
  return props.modelValue === '' ? [] : [props.modelValue]
})
const singleValue = computed(() => (Array.isArray(props.modelValue) ? '' : props.modelValue))
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
  return segmentedChoiceOptionId(controlIdPrefix.value, value)
}

function optionDisabled(option: SegmentOption): boolean {
  return isDisabled.value || option.disabled === true
}

function optionSelected(option: SegmentOption): boolean {
  return selectedValues.value.includes(option.value)
}

function showsGroupLabel(option: SegmentOption, index: number): boolean {
  const name = option.group ?? ''
  return name !== '' && name !== (props.options[index - 1]?.group ?? '')
}

function optionClasses(option: SegmentOption): string[] {
  return [
    `segmented-choice__option--${option.tone ?? 'muted'}`,
    ...(option.description !== undefined && option.description !== null && option.description !== '' ? ['segmented-choice__option--described'] : []),
    ...(props.wrap ? ['segmented-choice__option--wrap'] : []),
    ...(optionSelected(option) ? ['segmented-choice__option--active'] : []),
  ]
}

function selectOption(value: string): void {
  if (props.disabled || value === singleValue.value) return
  emit('update:modelValue', value as unknown as T)
}

function toggleOption(value: unknown): void {
  if (props.disabled) return
  const next = Array.isArray(value) ? value.map(String) : []
  emit('update:modelValue', next as unknown as T)
}
</script>

<template>
  <RadioGroupRoot
    v-if="!multiple"
    :model-value="singleValue"
    class="segmented-choice"
    v-bind="ariaBindings"
    :disabled="isDisabled"
    @update:model-value="selectOption(String($event))"
  >
    <template v-for="(option, index) in options" :key="option.value">
      <p v-if="showsGroupLabel(option, index)" class="segmented-choice__group">{{ option.group }}</p>
      <RadioGroupItem
        :id="optionId(option.value)"
        :value="option.value"
        :disabled="optionDisabled(option)"
        :title="wrap ? undefined : option.label"
        class="segmented-choice__option"
        :class="optionClasses(option)"
      >
        <span class="segmented-choice__label">{{ option.label }}</span>
        <span v-if="option.description" class="segmented-choice__hint">{{ option.description }}</span>
      </RadioGroupItem>
    </template>
  </RadioGroupRoot>
  <CheckboxGroupRoot
    v-else
    :model-value="selectedValues"
    class="segmented-choice"
    v-bind="ariaBindings"
    :disabled="isDisabled"
    @update:model-value="toggleOption"
  >
    <template v-for="(option, index) in options" :key="option.value">
      <p v-if="showsGroupLabel(option, index)" class="segmented-choice__group">{{ option.group }}</p>
      <CheckboxRoot
        :id="optionId(option.value)"
        :value="option.value"
        :disabled="optionDisabled(option)"
        :title="wrap ? undefined : option.label"
        class="segmented-choice__option"
        :class="optionClasses(option)"
      >
        <span class="segmented-choice__label">{{ option.label }}</span>
        <span v-if="option.description" class="segmented-choice__hint">{{ option.description }}</span>
      </CheckboxRoot>
    </template>
  </CheckboxGroupRoot>
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

.segmented-choice__group {
  grid-column: 1 / -1;
  margin: 0;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  font-weight: 500;
  line-height: var(--line-height-caption);
}

// reka 的 Radio / Checkbox 以 Fragment 渲染按钮，拿不到本组件的 scope id；按钮上的类必须经 :deep 命中
.segmented-choice :deep(.segmented-choice__option) {
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
  font-family: inherit;
  font-size: var(--font-size-body);
  font-weight: 500;
  line-height: var(--line-height-body);
  white-space: nowrap;
  overflow: hidden;
  text-align: center;
  cursor: pointer;
  appearance: none;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease,
    box-shadow 0.16s ease,
    color 0.16s ease,
    transform 0.16s ease;
}

.segmented-choice__label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: center;
}

.segmented-choice__hint {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  font-weight: 400;
  line-height: var(--line-height-caption);
  text-overflow: ellipsis;
  white-space: nowrap;
}

// 带说明行的瓦片：双行行高、左对齐
.segmented-choice :deep(.segmented-choice__option--described) {
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 0;
  min-height: 52px; // 列表双行行高
  padding: 6px $space-3;
  text-align: left;
}

.segmented-choice__option--described .segmented-choice__label {
  flex: none;
  max-width: 100%;
}

// 可换行：选项文字较长时不用省略号截断
.segmented-choice :deep(.segmented-choice__option--wrap) {
  white-space: normal;
  overflow: visible;
  overflow-wrap: anywhere;
}

.segmented-choice__option--wrap .segmented-choice__label,
.segmented-choice__option--wrap .segmented-choice__hint {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
}

.segmented-choice :deep(.segmented-choice__option:hover:not(:disabled)) {
  border-color: hsl(var(--brand));
}

.segmented-choice :deep(.segmented-choice__option:active:not(:disabled)) {
  transform: scale(var(--press-scale));
}

.segmented-choice :deep(.segmented-choice__option:disabled) {
  cursor: not-allowed;
  color: hsl(var(--muted-foreground));
  opacity: var(--disabled-opacity);
}

.segmented-choice :deep(.segmented-choice__option--primary:not(.segmented-choice__option--active):not(:disabled)) {
  color: hsl(var(--brand));
}

// choice：未选用前景色，选中与 primary 同一品牌蓝 recipe（选项瓦片的默认语气）
.segmented-choice :deep(.segmented-choice__option--choice:not(.segmented-choice__option--active):not(:disabled)) {
  color: hsl(var(--foreground));
}

.segmented-choice :deep(.segmented-choice__option--success:not(.segmented-choice__option--active):not(:disabled)) {
  color: hsl(var(--status-success));
}

.segmented-choice :deep(.segmented-choice__option--warning:not(.segmented-choice__option--active):not(:disabled)) {
  color: hsl(var(--status-warning));
}

.segmented-choice :deep(.segmented-choice__option--danger:not(.segmented-choice__option--active):not(:disabled)) {
  color: hsl(var(--status-danger));
}

.segmented-choice :deep(.segmented-choice__option--primary.segmented-choice__option--active) {
  border-color: hsl(var(--brand));
  background: var(--wash-hover);
  color: hsl(var(--brand));
  box-shadow: inset 0 0 0 1px hsl(var(--brand));
}

.segmented-choice :deep(.segmented-choice__option--choice.segmented-choice__option--active) {
  border-color: hsl(var(--brand));
  background: var(--wash-hover);
  color: hsl(var(--brand));
  box-shadow: inset 0 0 0 1px hsl(var(--brand));
}

.segmented-choice :deep(.segmented-choice__option--success.segmented-choice__option--active) {
  border-color: hsl(var(--status-success));
  background: color-mix(in srgb, hsl(var(--status-success)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-success));
  box-shadow: inset 0 0 0 1px hsl(var(--status-success));
}

.segmented-choice :deep(.segmented-choice__option--warning.segmented-choice__option--active) {
  border-color: hsl(var(--status-warning));
  background: color-mix(in srgb, hsl(var(--status-warning)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-warning));
  box-shadow: inset 0 0 0 1px hsl(var(--status-warning));
}

.segmented-choice :deep(.segmented-choice__option--danger.segmented-choice__option--active) {
  border-color: hsl(var(--status-danger));
  background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-danger));
  box-shadow: inset 0 0 0 1px hsl(var(--status-danger));
}

.segmented-choice :deep(.segmented-choice__option--muted.segmented-choice__option--active) {
  border-color: hsl(var(--border));
  background: hsl(var(--muted));
  color: hsl(var(--foreground));
  box-shadow: inset 0 0 0 1px hsl(var(--border));
}

// 窄视口：瓦片整体抬到 --touch-target，命中区与可见瓦片一致
@media (max-width: 767px) {
  .segmented-choice :deep(.segmented-choice__option) {
    min-height: var(--touch-target);
  }
}
</style>
