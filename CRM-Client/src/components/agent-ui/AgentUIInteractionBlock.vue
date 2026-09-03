<script setup lang="ts">
import { CheckCircle2, Circle, Loader2 } from 'lucide-vue-next'
import { computed, nextTick, ref, watch } from 'vue'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { AgentUIBlock, JsonObject, JsonValue } from '@/schemas/agent-contracts'

type InteractionBlock = Extract<AgentUIBlock, { type: 'interaction' }>
type InteractionField = InteractionBlock['fields'][number]

const props = defineProps<{
  block: InteractionBlock
  disabled?: boolean
  locked?: boolean
  grouped?: boolean
}>()

const emit = defineEmits<{
  submit: [actionId: string, values: JsonObject]
}>()

const interactionRef = ref<HTMLElement | null>(null)
const selectedValues = ref<string[]>([])
const fieldValues = ref<Record<string, JsonValue>>({})
const validationAttempted = ref(false)
const submitting = ref(false)

const resetValues = (): void => {
  selectedValues.value = []
  fieldValues.value = Object.fromEntries(
    props.block.fields.map(field => [field.key, field.default_value])
  )
  validationAttempted.value = false
  submitting.value = false
}

watch(
  () => [props.block.interaction_id, props.block.state, props.block.submit_action_id] as const,
  resetValues,
  { immediate: true }
)

const isActive = computed(() => props.block.state === 'ACTIVE' && props.block.submit_action_id !== null)
const isCompactTaskCompletion = computed(() => (
  props.block.presentation === 'COMPACT_TASK_COMPLETION'
))
const compactCompletionOption = computed(() => props.block.options[0])
const compactCompletionSucceeded = computed(() => props.block.state === 'SUBMITTED')

const compactStateLabel = computed(() => {
  if (submitting.value) return '处理中'
  return ({
    ACTIVE: '待完成',
    SUBMITTED: '已完成',
    EXPIRED: '已过期',
    CANCELLED: '已取消',
    READ_ONLY: '已处理'
  })[props.block.state]
})

const stateLabel = computed(() => {
  if (submitting.value) return '处理中'
  return ({
    ACTIVE: '待处理',
    SUBMITTED: '已提交',
    EXPIRED: '已过期',
    CANCELLED: '已取消',
    READ_ONLY: '历史记录'
  })[props.block.state]
})

const controlsDisabled = computed(() => (
  !isActive.value
  || props.disabled === true
  || props.locked === true
  || submitting.value
))

const submittedTextField = computed(() => {
  if (props.block.state !== 'SUBMITTED' || props.block.submitted_values === null || props.block.submitted_values === undefined) {
    return null
  }

  const candidateField = props.block.interaction_type === 'text_input'
    ? props.block.fields[0]
    : props.block.interaction_type === 'form' && props.block.fields.length === 1
      ? props.block.fields[0]
      : undefined
  if (candidateField === undefined || !['text', 'textarea'].includes(candidateField.field_type)) {
    return null
  }

  const submittedKey = props.block.interaction_type === 'text_input' ? 'text' : candidateField.key
  const value = props.block.submitted_values[submittedKey]
  return typeof value === 'string'
    ? { label: candidateField.label, value }
    : null
})

const optionSelected = (value: string): boolean => selectedValues.value.includes(value)

const toggleOption = (value: string): void => {
  if (controlsDisabled.value) return
  if (props.block.selection_mode === 'single') {
    selectedValues.value = [value]
    return
  }
  selectedValues.value = optionSelected(value)
    ? selectedValues.value.filter(item => item !== value)
    : [...selectedValues.value, value]
}

const submitsOnOptionClick = computed(() => (
  props.block.interaction_type === 'confirmation'
  || (
    props.block.interaction_type === 'choice'
    && props.block.selection_mode === 'single'
    && props.block.submit_on_select === true
  )
))

const handleOptionClick = (value: string): void => {
  if (controlsDisabled.value) return
  if (!submitsOnOptionClick.value) {
    toggleOption(value)
    return
  }
  const actionId = props.block.submit_action_id
  if (actionId === null) return
  selectedValues.value = [value]
  submitting.value = true
  emit('submit', actionId, { choice: value })
}

const completeCompactTask = (): void => {
  const option = compactCompletionOption.value
  if (option === undefined) return
  handleOptionClick(option.value)
}

const updateTextValue = (field: InteractionField, value: string | number | undefined): void => {
  fieldValues.value[field.key] = value === undefined ? '' : String(value)
}

const updateNumberValue = (field: InteractionField, value: string | number | undefined): void => {
  fieldValues.value[field.key] = value === undefined || value === '' ? null : Number(value)
}

const updateBooleanValue = (field: InteractionField, value: boolean): void => {
  fieldValues.value[field.key] = value
}

const updateSelectValue = (field: InteractionField, value: unknown): void => {
  fieldValues.value[field.key] = typeof value === 'string' ? value : null
}

const updateMultiSelectValue = (field: InteractionField, value: unknown): void => {
  fieldValues.value[field.key] = Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

const textValue = (field: InteractionField): string => {
  const value = fieldValues.value[field.key]
  return typeof value === 'string' ? value : ''
}

const numberValue = (field: InteractionField): number | undefined => {
  const value = fieldValues.value[field.key]
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

const booleanValue = (field: InteractionField): boolean => fieldValues.value[field.key] === true

const selectedFieldValues = (field: InteractionField): string[] => {
  const value = fieldValues.value[field.key]
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

const fieldError = (field: InteractionField): string | null => {
  const value = fieldValues.value[field.key]
  const blankText = typeof value === 'string' && value.trim().length === 0
  const empty = value === null || value === undefined || blankText || (Array.isArray(value) && value.length === 0)
  const textInputRequiresContent = props.block.interaction_type === 'text_input'
    && props.block.fields[0]?.key === field.key
    && props.block.allow_blank !== true

  if ((field.required || textInputRequiresContent) && empty) {
    return field.field_type === 'select' || field.field_type === 'multi_select'
      ? `请选择${field.label}`
      : `请填写${field.label}`
  }
  if (field.required && field.field_type === 'boolean' && value !== true) {
    return `请确认${field.label}`
  }
  if ((field.field_type === 'text' || field.field_type === 'textarea') && typeof value === 'string' && !empty) {
    if (field.min_length !== undefined && field.min_length !== null && value.length < field.min_length) {
      return `${field.label}至少需要 ${field.min_length} 个字符`
    }
    if (field.max_length !== undefined && field.max_length !== null && value.length > field.max_length) {
      return `${field.label}不能超过 ${field.max_length} 个字符`
    }
  }
  if (field.field_type === 'number' && value !== null && value !== undefined) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return `请填写有效的${field.label}`
    if (field.minimum !== undefined && field.minimum !== null && value < field.minimum) {
      return `${field.label}不能小于 ${field.minimum}`
    }
    if (field.maximum !== undefined && field.maximum !== null && value > field.maximum) {
      return `${field.label}不能大于 ${field.maximum}`
    }
  }
  return null
}

const visibleFieldError = (field: InteractionField): string | null => (
  validationAttempted.value ? fieldError(field) : null
)

const selectionError = computed(() => {
  if (!validationAttempted.value) return null
  const minimum = props.block.min_selections ?? 1
  const maximum = props.block.max_selections ?? 1
  const count = selectedValues.value.length
  if (count < minimum) return `请至少选择 ${minimum} 项`
  if (count > maximum) return `最多只能选择 ${maximum} 项`
  return null
})

const fieldErrorId = (field: InteractionField): string => `${props.block.id}-${field.key}-error`

const focusFirstError = async (): Promise<void> => {
  await nextTick()
  interactionRef.value?.querySelector<HTMLElement>('[data-agent-ui-error-focus="true"]')?.focus()
}

const submit = async (): Promise<void> => {
  const actionId = props.block.submit_action_id
  if (controlsDisabled.value || actionId === null) return

  validationAttempted.value = true
  if (props.block.interaction_type === 'choice' || props.block.interaction_type === 'confirmation') {
    if (selectionError.value !== null) {
      await focusFirstError()
      return
    }
    const values: JsonObject = props.block.selection_mode === 'multiple'
      ? { choices: selectedValues.value }
      : { choice: selectedValues.value[0] ?? '' }
    submitting.value = true
    emit('submit', actionId, values)
    return
  }

  const invalidField = props.block.fields.find(field => fieldError(field) !== null)
  if (invalidField !== undefined) {
    await focusFirstError()
    return
  }
  if (props.block.interaction_type === 'text_input') {
    const field = props.block.fields[0]
    submitting.value = true
    emit('submit', actionId, { text: field === undefined ? '' : textValue(field) })
    return
  }
  submitting.value = true
  emit('submit', actionId, fieldValues.value)
}
</script>

<template>
  <section
    v-if="isCompactTaskCompletion"
    ref="interactionRef"
    class="agent-ui-interaction flex min-h-11 items-center gap-2 px-3 py-2 text-sm transition-colors"
    :class="[
      grouped ? '' : 'rounded-xl border',
      compactCompletionSucceeded
        ? (grouped ? 'bg-emerald-50/70 dark:bg-emerald-950/25' : 'border-emerald-200 bg-emerald-50/70 dark:border-emerald-900/70 dark:bg-emerald-950/25')
        : (grouped ? 'bg-transparent' : 'border-border/70 bg-muted/25')
    ]"
    :aria-labelledby="`${block.id}-prompt`"
    :aria-busy="submitting"
  >
    <button
      v-if="isActive"
      type="button"
      class="-my-2 grid h-11 w-11 shrink-0 place-items-center rounded-full text-muted-foreground outline-none transition-colors hover:text-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-default disabled:opacity-70"
      aria-label="标记完成"
      :disabled="controlsDisabled"
      @click="completeCompactTask"
    >
      <Loader2
        v-if="submitting"
        class="h-5 w-5 animate-spin text-primary motion-reduce:animate-none"
        aria-hidden="true"
      />
      <Circle v-else class="h-5 w-5" aria-hidden="true" />
    </button>
    <span
      v-else
      class="-my-2 grid h-11 w-11 shrink-0 place-items-center rounded-full"
      :class="compactCompletionSucceeded ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'"
      :aria-label="compactStateLabel"
      role="img"
    >
      <CheckCircle2 v-if="compactCompletionSucceeded" class="h-5 w-5" aria-hidden="true" />
      <Circle v-else class="h-5 w-5" aria-hidden="true" />
    </span>
    <p :id="`${block.id}-prompt`" class="m-0 min-w-0 flex-1 text-foreground">
      {{ block.prompt }}
    </p>
    <span
      class="shrink-0 text-xs"
      :class="compactCompletionSucceeded
        ? 'text-emerald-700 dark:text-emerald-300'
        : 'text-muted-foreground'"
    >
      {{ compactStateLabel }}
    </span>
  </section>

  <section
    v-else
    ref="interactionRef"
    class="agent-ui-interaction grid gap-3 rounded-xl border border-primary/20 bg-primary/5 p-3"
    :aria-labelledby="`${block.id}-prompt`"
    :aria-busy="submitting"
  >
    <header class="flex items-start justify-between gap-3">
      <p :id="`${block.id}-prompt`" class="m-0 text-foreground">{{ block.prompt }}</p>
      <span class="shrink-0 text-xs text-muted-foreground">{{ stateLabel }}</span>
    </header>

    <template v-if="block.interaction_type === 'choice' || block.interaction_type === 'confirmation'">
      <div
        class="grid gap-2"
        role="group"
        :aria-invalid="selectionError !== null"
        :aria-describedby="selectionError === null ? undefined : `${block.id}-selection-error`"
      >
      <Button
        v-for="(option, index) in block.options"
        :key="option.value"
        type="button"
        :variant="index === 0 ? 'default' : 'outline'"
        class="grid min-h-11 h-auto w-full justify-start gap-1 px-3 py-2 text-left"
        :class="{ 'border-primary bg-accent text-accent-foreground': optionSelected(option.value) }"
        :aria-pressed="optionSelected(option.value)"
        :disabled="controlsDisabled || option.disabled"
        :data-agent-ui-error-focus="selectionError !== null && index === 0 ? 'true' : undefined"
        @click="handleOptionClick(option.value)"
      >
        <span>{{ submitting && optionSelected(option.value) ? `${option.label}处理中…` : option.label }}</span>
        <small v-if="option.description" class="text-xs text-muted-foreground">
          {{ option.description }}
        </small>
      </Button>
        <p
          v-if="selectionError !== null"
          :id="`${block.id}-selection-error`"
          class="m-0 text-sm text-destructive"
          role="alert"
        >
          {{ selectionError }}
        </p>
      </div>
    </template>

    <div
      v-else-if="submittedTextField !== null"
      class="rounded-lg border border-border/70 bg-background/70 px-3 py-2 text-sm text-foreground"
      data-agent-ui-submitted-text
    >
      <span class="font-medium">{{ submittedTextField.label }}：</span>{{ submittedTextField.value }}
    </div>

    <form v-else class="grid gap-3" novalidate @submit.prevent="submit">
      <div v-for="field in block.fields" :key="field.key" class="grid gap-1.5">
        <Label :for="`${block.id}-${field.key}`" class="text-sm font-medium text-foreground">
          {{ field.label }}<b v-if="field.required" aria-hidden="true"> *</b>
        </Label>

        <Textarea
          v-if="field.field_type === 'textarea'"
          :id="`${block.id}-${field.key}`"
          :model-value="textValue(field)"
          :placeholder="field.placeholder ?? undefined"
          :minlength="field.min_length ?? undefined"
          :maxlength="field.max_length ?? undefined"
          :required="field.required"
          :disabled="controlsDisabled"
          :aria-invalid="visibleFieldError(field) !== null"
          :aria-describedby="visibleFieldError(field) === null ? undefined : fieldErrorId(field)"
          :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
          rows="3"
          @update:model-value="updateTextValue(field, $event)"
        />

        <Input
          v-else-if="field.field_type === 'text' || field.field_type === 'date' || field.field_type === 'datetime'"
          :id="`${block.id}-${field.key}`"
          class="min-h-11"
          :type="field.field_type === 'datetime' ? 'datetime-local' : field.field_type"
          :model-value="textValue(field)"
          :placeholder="field.placeholder ?? undefined"
          :minlength="field.min_length ?? undefined"
          :maxlength="field.max_length ?? undefined"
          :required="field.required"
          :disabled="controlsDisabled"
          :aria-invalid="visibleFieldError(field) !== null"
          :aria-describedby="visibleFieldError(field) === null ? undefined : fieldErrorId(field)"
          :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
          @update:model-value="updateTextValue(field, $event)"
        />

        <Input
          v-else-if="field.field_type === 'number'"
          :id="`${block.id}-${field.key}`"
          class="min-h-11"
          type="number"
          :model-value="numberValue(field)"
          :min="field.minimum ?? undefined"
          :max="field.maximum ?? undefined"
          :required="field.required"
          :disabled="controlsDisabled"
          :aria-invalid="visibleFieldError(field) !== null"
          :aria-describedby="visibleFieldError(field) === null ? undefined : fieldErrorId(field)"
          :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
          @update:model-value="updateNumberValue(field, $event)"
        />

        <Select
          v-else-if="field.field_type === 'select'"
          :model-value="textValue(field)"
          :disabled="controlsDisabled"
          @update:model-value="updateSelectValue(field, $event)"
        >
          <SelectTrigger
            :id="`${block.id}-${field.key}`"
            class="min-h-11"
            :aria-required="field.required"
            :aria-invalid="visibleFieldError(field) !== null"
            :aria-describedby="visibleFieldError(field) === null ? undefined : fieldErrorId(field)"
            :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
          >
            <SelectValue :placeholder="field.placeholder ?? `请选择${field.label}`" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              v-for="option in field.options"
              :key="option.value"
              :value="option.value"
              :disabled="option.disabled"
            >
              {{ option.label }}
            </SelectItem>
          </SelectContent>
        </Select>

        <Select
          v-else-if="field.field_type === 'multi_select'"
          :model-value="selectedFieldValues(field)"
          :multiple="true"
          :disabled="controlsDisabled"
          @update:model-value="updateMultiSelectValue(field, $event)"
        >
          <SelectTrigger
            :id="`${block.id}-${field.key}`"
            class="min-h-11"
            :aria-required="field.required"
            :aria-invalid="visibleFieldError(field) !== null"
            :aria-describedby="visibleFieldError(field) === null ? undefined : fieldErrorId(field)"
            :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
          >
            <SelectValue :placeholder="field.placeholder ?? `请选择${field.label}`" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              v-for="option in field.options"
              :key="option.value"
              :value="option.value"
              :disabled="option.disabled"
            >
              {{ option.label }}
            </SelectItem>
          </SelectContent>
        </Select>

        <div v-else class="flex min-h-11 items-center gap-2">
          <Checkbox
            :id="`${block.id}-${field.key}`"
            :checked="booleanValue(field)"
            :required="field.required"
            :disabled="controlsDisabled"
            :aria-invalid="visibleFieldError(field) !== null"
            :aria-describedby="visibleFieldError(field) === null ? undefined : fieldErrorId(field)"
            :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
            @update:checked="updateBooleanValue(field, $event)"
          />
          <span class="text-sm text-muted-foreground">
            {{ booleanValue(field) ? '是' : '否' }}
          </span>
        </div>

        <p
          v-if="visibleFieldError(field) !== null"
          :id="fieldErrorId(field)"
          class="m-0 text-sm text-destructive"
          role="alert"
        >
          {{ visibleFieldError(field) }}
        </p>
      </div>
    </form>

    <Button
      v-if="isActive && !submitsOnOptionClick"
      type="button"
      size="sm"
      class="min-h-11"
      :disabled="controlsDisabled"
      @click="submit"
    >
      {{ submitting ? `${block.submit_label}处理中…` : block.submit_label }}
    </Button>
  </section>
</template>
