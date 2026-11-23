<script setup lang="ts">
import { AlertCircle, Check, ChevronRight, Circle, Info, LoaderCircle } from 'lucide-vue-next'
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import StatusBadge from '@/components/crmwolf/StatusBadge.vue'
import SegmentedChoiceControl from '@/components/crmwolf/SegmentedChoiceControl.vue'
import InputField from '@/components/crmwolf/InputField.vue'
import TextareaField from '@/components/crmwolf/TextareaField.vue'
import SelectField from '@/components/crmwolf/SelectField.vue'
import CheckboxField from '@/components/crmwolf/CheckboxField.vue'
import MultiSelectField from '@/components/crmwolf/MultiSelectField.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { AgentUIBlock, JsonObject, JsonValue } from '@/schemas/agent-contracts'

import AgentUIBanner from './AgentUIBanner.vue'
import type { InteractionNotice } from './interactionNotice'

type InteractionBlock = Extract<AgentUIBlock, { type: 'interaction' }>
type InteractionField = InteractionBlock['fields'][number]
type InteractionOption = InteractionBlock['options'][number]

interface TileOption {
  value: string
  label: string
  /** choice：未选前景色、选中品牌蓝，助手页选项瓦片的统一语气 */
  tone: 'choice'
  description?: string | null | undefined
  group?: string | null | undefined
  disabled?: boolean | undefined
}

const props = defineProps<{
  block: InteractionBlock
  disabled?: boolean
  locked?: boolean
  grouped?: boolean
  notice?: InteractionNotice | null
}>()

const emit = defineEmits<{
  submit: [actionId: string, values: JsonObject]
}>()

const interactionRef = ref<HTMLElement | null>(null)
const selectedValues = ref<string[]>([])
const manualDate = ref('')
const fieldValues = ref<Record<string, JsonValue>>({})
const validationAttempted = ref(false)
const submitting = ref(false)
const cancelReasonsOpen = ref(false)
const cancelReasonsRef = ref<HTMLElement | null>(null)
const editedFieldErrors = ref<Record<string, boolean>>({})

const availableFieldOptions = (field: InteractionField): InteractionField['options'] => {
  if (field.depends_on_key == null) return field.options
  const parentValue = fieldValues.value[field.depends_on_key]
  return field.options.filter(option => option.depends_on_value == null || (
    Array.isArray(parentValue) ? parentValue.includes(option.depends_on_value) : parentValue === option.depends_on_value
  ))
}

const submittedChoiceValue = computed<string | null>(() => {
  if (props.block.state !== 'SUBMITTED' ||
      (props.block.interaction_type !== 'choice' && props.block.interaction_type !== 'confirmation') ||
      props.block.submitted_values === null ||
      props.block.submitted_values === undefined) {
    return null
  }

  const value = props.block.submitted_values['choice']
  return typeof value === 'string' && value.length > 0 ? value : null
})

const submittedChoiceOption = computed(() => {
  const value = submittedChoiceValue.value
  return value === null
    ? null
    : props.block.options.find(option => option.value === value) ?? null
})

const resetValues = (): void => {
  const failedChoice = props.notice?.kind === 'failed' ? props.notice.choice : null
  const submitted = submittedChoiceValue.value
  selectedValues.value = failedChoice !== null ? [failedChoice] : submitted === null ? [] : [submitted]
  fieldValues.value = Object.fromEntries(
    props.block.fields.map(field => [field.key, field.default_value])
  )
  cancelReasonsOpen.value = false
  editedFieldErrors.value = {}
  validationAttempted.value = false
  submitting.value = false
  manualDate.value = ''
}

watch(
  () => [
    props.block.interaction_id,
    props.block.state,
    props.block.submit_action_id,
    submittedChoiceValue.value,
    props.notice?.kind ?? null,
  ] as const,
  resetValues,
  { immediate: true }
)

watch(() => props.block.fields, () => { editedFieldErrors.value = {} })

watch(() => props.locked, (locked, previous) => {
  if (previous !== true || locked === true || props.block.state !== 'ACTIVE') return
  const releaseForm = props.block.interaction_type === 'form' && props.block.allow_cancel
  if (props.block.interaction_type === 'text_input' || releaseForm || isOpenFollowUpDisposition.value) submitting.value = false
})

const isActive = computed(() => props.block.state === 'ACTIVE' && props.block.submit_action_id !== null)
const canCancel = computed(() => (
  isActive.value
  && props.block.allow_cancel === true
  && (props.block.interaction_type === 'form' || (
    props.block.interaction_type === 'text_input' && props.block.business_action === 'provide_follow_up_content'
  ))
))
const readonly = computed(() => props.block.state === 'READ_ONLY')
const isCompactTaskCompletion = computed(() => (
  props.block.presentation === 'COMPACT_TASK_COMPLETION'
))
const isOpenFollowUpDisposition = computed(() => (
  props.block.presentation === 'OPEN_FOLLOW_UP_DISPOSITION'
))
const dispositionGroups = computed(() => [
  props.block.disposition_items.slice(0, 10),
  props.block.disposition_items.slice(10),
].filter(items => items.length > 0))
const dispositionStateLabels = {
  current: '待处理', waiting: '待处理', complete: '已完成', hold: '保持未完成',
  skip: '已跳过', failed: '处理失败', unknown: '结果待核对',
}
const cancelReasons = computed(() => props.block.cancel_reasons ?? [])
const confirmationEdit = computed(() => props.block.secondary_action?.value === 'request_edit' ? props.block.secondary_action : null)
const weeklySuppression = computed(() => props.block.secondary_action?.value === 'suppress_week' ? props.block.secondary_action : null)
const evidenceOpenId = ref<string | null>(null)
const toggleEvidence = (itemId: string): void => {
  evidenceOpenId.value = evidenceOpenId.value === itemId ? null : itemId
}
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

const stateStatus = computed(() => {
  if (props.notice?.kind === 'expired') return 'expired'
  if (props.notice?.kind === 'failed') return 'failed'
  if (submitting.value) return 'processing'
  return ({
    ACTIVE: 'pending',
    SUBMITTED: 'done',
    EXPIRED: 'expired',
    CANCELLED: 'cancelled',
    READ_ONLY: 'history'
  })[props.block.state]
})

const compactStatus = computed(() => {
  if (submitting.value) return 'processing'
  return ({
    ACTIVE: 'pending',
    SUBMITTED: 'done',
    EXPIRED: 'expired',
    CANCELLED: 'cancelled',
    READ_ONLY: 'history'
  })[props.block.state]
})

const controlsDisabled = computed(() => (
  !isActive.value
  || props.disabled === true
  || props.locked === true
  || submitting.value
  || props.notice?.kind === 'expired'
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
  // Confirmation cards historically submitted on option click even when old
  // persisted payloads omitted submit_on_select. Keep that compatibility while
  // making the explicit flag authoritative for generic single choices.
  props.block.interaction_type === 'confirmation'
  || props.block.submit_on_select === true
))

const submitManualDate = (): void => {
  const actionId = props.block.submit_action_id
  const value = manualDate.value.trim()
  if (controlsDisabled.value || actionId === null || value === '') return
  submitting.value = true
  emit('submit', actionId, { text: value })
}

const kindEditorOpen = ref(false)
const activityHistoryHeadingRef = ref<HTMLElement | null>(null)
const isActivityConfirmation = computed(() => props.block.business_action === 'confirm_activity_write')
const activityFact = (key: string): InteractionBlock['facts'][number] | undefined => props.block.facts.find(fact => fact.key === key)
const activityKindFact = computed(() => activityFact('activity_kind'))
const activityScoreFact = computed(() => activityFact('score'))
const activityScoreReason = computed(() => activityFact('score_reason'))
const activityChangeSummary = computed(() => activityFact('change_summary'))
const activityComparisonCurrent = computed(() => activityFact('comparison_current'))
const activityComparisonPrevious = computed(() => activityFact('comparison_previous'))
const activityContextStatus = computed(() => activityFact('context_status'))
const activityLegacyContext = computed(() => activityFact('change_signal'))
const activityTimeFact = computed(() => activityFact('next_follow_time'))
const activityOpportunity = computed(() => activityFact('opportunity'))
const activityEvidence = computed(() => activityFact('context_evidence'))
const activityEvidenceLines = computed(() => (activityEvidence.value?.value ?? '').split('；').map(line => line.trim()).filter(line => line !== ''))
const activityNotices = computed(() => props.block.facts.filter(fact => fact.key.startsWith('context_notice_')))
const activityIgnoredNoise = computed(() => activityFact('ignored_noise'))
const activitySourceFolded = computed(() => {
  const fact = activityKindFact.value
  if (fact === undefined || fact.source === null || fact.source === undefined || fact.source === '') return ''
  if (fact.status_label === '未识别 · 需要确认') return ''
  return fact.source
})
const showActivityOrganizingBasis = computed(() => Boolean(
  activityScoreFact.value || activityScoreReason.value || activitySourceFolded.value
  || (activityTimeFact.value?.source ?? '') !== '' || activityIgnoredNoise.value
))
const showActivityHistory = computed(() => Boolean(
  activityChangeSummary.value || activityComparisonCurrent.value || activityComparisonPrevious.value
  || activityContextStatus.value || activityLegacyContext.value || activityEvidenceLines.value.length > 0
  || activityNotices.value.length > 0
))
const showActivityBasis = computed(() => showActivityHistory.value || activityOpportunity.value || showActivityOrganizingBasis.value)
// 「查看参考与依据」用 ui/collapsible；宿主点「查看对比依据」时展开并把焦点移到历史标题。
const basisOpen = ref(false)
const openActivityComparison = async (): Promise<void> => {
  basisOpen.value = true
  await nextTick()
  activityHistoryHeadingRef.value?.focus({ preventScroll: true })
  activityHistoryHeadingRef.value?.scrollIntoView?.({ block: 'nearest' })
}
const activityHistory = computed(() => props.block.state === 'READ_ONLY')
const activityWaitingLabel = computed(() => {
  if (activityHistory.value) return '历史'
  return activityKindFact.value?.status_label === '未识别 · 需要确认' ? '等待选择类型' : '待确认'
})
const activityActionOptions = computed(() => {
  const cancel = props.block.options.find(option => option.value === 'cancel')
  const confirm = props.block.options.find(option => option.value === 'confirm')
  return [cancel, confirm].filter((option): option is InteractionOption => option !== undefined)
})
const activityDisabledHint = computed(() => (
  props.block.options.find((option) => option.disabled === true && option.description !== undefined && option.description !== null && option.description !== '')?.description ?? ''
))

const KIND_HINT_PREFIX = '原文提到：'
const kindHintChannels = computed((): string[] => {
  const hint = props.block.hint ?? ''
  if (!hint.startsWith(KIND_HINT_PREFIX)) return []
  return hint.slice(KIND_HINT_PREFIX.length).split('、').map(part => part.trim()).filter(part => part !== '')
})

const choiceOptions = computed(() => (
  isActivityConfirmation.value ? activityActionOptions.value : props.block.options
))
const showsChoiceOptions = computed(() => (
  isActive.value
  && (props.block.interaction_type === 'choice' || props.block.interaction_type === 'confirmation')
  && props.notice?.kind !== 'expired'
))
const isGenericConfirmation = computed(() => (
  isActivityConfirmation.value === false
  && props.block.interaction_type === 'confirmation'
  && showsChoiceOptions.value
))
const confirmationOptions = computed(() => ({
  cancel: props.block.options.find(option => option.value === 'cancel'),
  confirm: props.block.options.find(option => option.value === 'confirm')
}))
const confirmationDisabledHint = computed(() => (
  props.block.options.find((option) => option.disabled === true && option.description !== undefined && option.description !== null && option.description !== '')?.description ?? ''
))
// 不再待处理的选择 / 确认折叠成一行摘要，不保留任何操作入口。
const isCollapsedChoice = computed(() => (
  isActivityConfirmation.value === false
  && submittedChoiceValue.value !== null
  && !isCompactTaskCompletion.value
  && !isOpenFollowUpDisposition.value
))
// 确认卡里选了「取消」也算已处理，但不该配成功色的对勾。
const isDeclinedConfirmation = computed(() => (
  props.block.interaction_type === 'confirmation' && submittedChoiceValue.value === 'cancel'
))
// 提交中：被点的那一块在瓦片里写明「处理中…」；瓦片是等宽网格，文字变长不改宽。
const tileOption = (option: InteractionOption): TileOption => ({
  value: option.value,
  tone: 'choice',
  label: submitting.value && optionSelected(option.value) ? `${option.label}处理中…` : option.label,
  description: option.description,
  group: option.group,
  disabled: option.disabled
})
const choiceTileOptions = computed<TileOption[]>(() => choiceOptions.value.map(tileOption))
// 活动类型的候选也走同一种瓦片语气。
const kindTileOptions = (options: InteractionOption[] | undefined): TileOption[] => (options ?? []).map((option) => tileOption(option))
const kindTileValue = (fact: InteractionBlock['facts'][number]): string => (
  (fact.options ?? []).find(option => option.value === fact.value || option.label === fact.value)?.value ?? ''
)

const retryNoticeChoice = (): void => {
  const notice = props.notice
  const actionId = props.block.submit_action_id
  if (notice === null || notice === undefined || notice.kind !== 'failed' || actionId === null) return
  if (props.disabled === true || props.locked === true || submitting.value) return
  selectedValues.value = [notice.choice]
  submitting.value = true
  emit('submit', actionId, { choice: notice.choice })
}

const kindOptionsVisible = (fact: InteractionBlock['facts'][number]): boolean => {
  if ((fact.options?.length ?? 0) === 0 || !isActive.value) return false
  if (fact.status_label === '未识别 · 需要确认') return true
  return kindEditorOpen.value
}

const reviseActivityKind = (value: string): void => {
  const actionId = props.block.submit_action_id
  if (controlsDisabled.value || actionId === null) return
  submitting.value = true
  emit('submit', actionId, { revise_activity_kind: value })
}

const submitConfirmationCancel = (reason?: string): void => {
  const actionId = props.block.submit_action_id
  const cancelOption = props.block.options.find(option => option.value === 'cancel')
  if (controlsDisabled.value || actionId === null || !cancelOption || cancelOption.disabled) return
  if (reason !== undefined && !cancelReasons.value.some(option => option.value === reason && !option.disabled)) return
  selectedValues.value = ['cancel']
  submitting.value = true
  emit('submit', actionId, reason === undefined ? { choice: 'cancel' } : { choice: 'cancel', reason })
}

const handleOptionClick = async (value: string): Promise<void> => {
  const actionId = props.block.submit_action_id
  if (controlsDisabled.value || actionId === null) return
  if (value === 'cancel' && props.block.interaction_type === 'confirmation' && cancelReasons.value.length > 0) {
    cancelReasonsOpen.value = !cancelReasonsOpen.value
    if (cancelReasonsOpen.value) {
      await nextTick()
      cancelReasonsRef.value?.querySelector<HTMLElement>('button:not(:disabled)')?.focus()
    }
    return
  }
  if (!submitsOnOptionClick.value) {
    toggleOption(value)
    return
  }
  selectedValues.value = [value]
  submitting.value = true
  emit('submit', actionId, { choice: value })
}

const submitConfirmationEdit = (): void => {
  const actionId = props.block.submit_action_id
  if (controlsDisabled.value || actionId === null || !confirmationEdit.value || confirmationEdit.value.disabled) return
  submitting.value = true
  emit('submit', actionId, { choice: 'request_edit' })
}

const submitDisposition = (suppressWeek: boolean): void => {
  const actionId = props.block.submit_action_id
  if (controlsDisabled.value || actionId === null || (suppressWeek && (!weeklySuppression.value || weeklySuppression.value.disabled))) return
  const choices = props.block.options.filter(option => !option.disabled && optionSelected(option.value)).map(option => option.value)
  submitting.value = true
  emit('submit', actionId, { choices, suppress_week: suppressWeek })
}

const completeCompactTask = (): void => {
  const option = compactCompletionOption.value
  if (option === undefined) return
  handleOptionClick(option.value)
}

const updateFieldValue = (field: InteractionField, value: JsonValue): void => {
  const previous = fieldValues.value[field.key]
  if (controlsDisabled.value || previous === value || (
    Array.isArray(previous) && Array.isArray(value) && previous.length === value.length &&
    previous.every((item, index) => item === value[index])
  )) return
  fieldValues.value[field.key] = value
  editedFieldErrors.value[field.key] = true

  // Clearing a selector also clears every selector depending on it.
  const changed = new Set([field.key])
  for (const key of changed) {
    for (const dependent of props.block.fields) {
      if (dependent.depends_on_key !== key || changed.has(dependent.key)) continue
      fieldValues.value[dependent.key] = dependent.field_type === 'multi_select' ? [] : null
      editedFieldErrors.value[dependent.key] = true
      changed.add(dependent.key)
    }
  }
}

const updateTextValue = (field: InteractionField, value: string | number | undefined): void => {
  updateFieldValue(field, value === undefined ? '' : String(value))
}

const updateNumberValue = (field: InteractionField, value: string | number | undefined): void => {
  updateFieldValue(field, value === undefined || value === '' ? null : Number(value))
}

const updateBooleanValue = (field: InteractionField, value: boolean): void => {
  updateFieldValue(field, value)
}

const updateSelectValue = (field: InteractionField, value: unknown): void => {
  updateFieldValue(field, typeof value === 'string' && value !== '' ? value : null)
}

const updateMultiSelectValue = (field: InteractionField, value: unknown): void => {
  updateFieldValue(field, Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [])
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
  if (field.depends_on_key != null && !empty) {
    const choices = Array.isArray(value) ? value : [value]
    if (choices.some(choice => !availableFieldOptions(field).some(option => option.value === choice && !option.disabled))) {
      return `请选择有效的${field.label}`
    }
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
  (isActive.value && editedFieldErrors.value[field.key] !== true ? field.error_message : null)
  ?? (validationAttempted.value ? fieldError(field) : null)
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

const focusFirstError = async (): Promise<void> => {
  await nextTick()
  const root = interactionRef.value
  root?.querySelector<HTMLElement>('[data-agent-ui-error-focus="true"]')?.focus()
  // 选项瓦片是分段选择控件，校验失败时把焦点移到第一个选项按钮。
  root?.querySelector<HTMLElement>('[data-agent-ui-choice] [role="radio"], [data-agent-ui-choice] [role="checkbox"]')?.focus()
}

const cancel = (): void => {
  const actionId = props.block.submit_action_id
  if (!canCancel.value || controlsDisabled.value || actionId === null) return
  submitting.value = true
  // The legacy signed follow-up prompt still uses its original resolver.
  emit('submit', actionId, props.block.business_action === 'provide_follow_up_content' ? { cancel: true } : { choice: 'cancel' })
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
  <!-- 待办任务：列表单行 -->
  <section
    v-if="isCompactTaskCompletion"
    ref="interactionRef"
    class="agent-ui-interaction flex min-h-[var(--control-h-lg)] max-[767px]:min-h-touch-target items-center gap-space-2 px-space-3 text-foreground"
    :class="grouped ? '' : 'rounded-lg border border-border bg-card'"
    :aria-labelledby="`${block.id}-prompt`"
    :aria-busy="submitting"
  >
    <button
      v-if="isActive"
      type="button"
      class="-ml-space-2 grid size-control shrink-0 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-wash-hover hover:text-brand disabled:cursor-default"
      aria-label="标记完成"
      :disabled="controlsDisabled"
      @click="completeCompactTask"
    >
      <LoaderCircle
        v-if="submitting"
        class="size-icon-sm animate-spin text-brand motion-reduce:animate-none"
        aria-hidden="true"
      />
      <Circle v-else class="size-icon-sm" aria-hidden="true" />
    </button>
    <span
      v-else
      class="grid h-space-4 w-space-4 shrink-0 place-items-center"
      :class="compactCompletionSucceeded ? 'text-tone-success' : 'text-muted-foreground'"
      role="img"
      :aria-label="compactStateLabel"
    >
      <Check v-if="compactCompletionSucceeded" class="size-icon-sm" aria-hidden="true" />
      <Circle v-else class="size-icon-sm" aria-hidden="true" />
    </span>
    <p :id="`${block.id}-prompt`" class="m-0 min-w-0 flex-1 text-body text-foreground">
      {{ block.prompt }}
    </p>
    <StatusBadge
      class="shrink-0"
      :status="compactStatus"
      type="agentInteraction"
      size="small"
      :label="compactStateLabel"
    />
  </section>

  <!-- 历史跟进任务 -->
  <section
    v-else-if="isOpenFollowUpDisposition"
    ref="interactionRef"
    class="agent-ui-interaction grid min-w-0 overflow-hidden rounded-lg border border-border bg-card text-foreground"
    :aria-labelledby="`${block.id}-prompt`"
    :aria-busy="submitting"
  >
    <header class="flex items-start justify-between gap-space-3 px-space-4 pt-space-4">
      <h4 :id="`${block.id}-prompt`" class="m-0 min-w-0 text-body font-semibold text-foreground [overflow-wrap:anywhere]">{{ block.prompt }}</h4>
      <Badge variant="secondary" class="shrink-0 font-semibold">共 {{ block.disposition_items.length }} 项</Badge>
    </header>
    <p v-if="block.hint" class="m-0 px-space-4 pt-space-2 text-body text-muted-foreground" data-agent-ui-disposition-summary>{{ block.hint }}</p>
    <component :is="groupIndex === 0 ? 'div' : 'details'" v-for="(items, groupIndex) in dispositionGroups" :key="groupIndex">
      <summary v-if="groupIndex > 0" class="min-h-touch-target cursor-pointer px-space-4 py-space-3 text-body text-foreground focus-visible:outline-ring">
        其余 {{ items.length }} 项
      </summary>
      <ol :start="groupIndex * 10 + 1" class="m-0 mt-space-3 grid list-none gap-0 border-t border-border p-0">
        <li
          v-for="(item, index) in items"
          :key="item.item_id"
          class="grid gap-space-1 border-b border-border px-space-4 py-space-2 last:border-b-0"
        >
          <div class="flex items-start justify-between gap-space-2">
            <label v-if="isActive" class="flex min-h-touch-target min-w-0 cursor-pointer items-center gap-space-2 text-body text-foreground">
              <input
                type="checkbox"
                class="size-4 shrink-0 rounded-sm border-input focus-visible:ring-ring"
                :value="item.item_id"
                :checked="optionSelected(item.item_id)"
                :disabled="controlsDisabled || block.options[groupIndex * 10 + index]?.disabled !== false"
                @change="toggleOption(item.item_id)"
              />
              <span><span class="sr-only">标记完成：</span>{{ item.title }}</span>
            </label>
            <p v-else class="m-0 min-w-0 text-body text-foreground">{{ item.title }}</p>
            <StatusBadge
              class="shrink-0"
              :status="item.state"
              type="agentDisposition"
              size="small"
              :label="item.result_title || dispositionStateLabels[item.state]"
            />
        </div>
        <p v-if="item.owner_line" class="m-0 text-caption text-muted-foreground">{{ item.owner_line }}</p>
        <div v-if="item.related && item.evidence_quote" class="grid gap-space-1">
          <Button
            type="button"
            variant="link"
            size="sm"
            class="justify-start px-0"
            :aria-expanded="evidenceOpenId === item.item_id"
            :aria-controls="`${block.id}-evidence-${item.item_id}`"
            data-agent-ui-related-toggle
            @click="toggleEvidence(item.item_id)"
          >
            查看关联信息
          </Button>
          <p
            v-if="evidenceOpenId === item.item_id"
            :id="`${block.id}-evidence-${item.item_id}`"
            class="m-0 rounded-md bg-muted px-space-3 py-space-2 text-body text-foreground"
            data-agent-ui-related-line
          >
            本次跟进：“{{ item.evidence_quote }}”
          </p>
        </div>
          <p v-if="item.result_message" class="m-0 text-caption text-muted-foreground">{{ item.result_message }}</p>
        </li>
      </ol>
    </component>
    <div v-if="isActive" class="flex flex-wrap gap-space-2 px-space-4 pb-space-4 pt-space-3">
      <Button type="button" :disabled="controlsDisabled" @click="submitDisposition(false)">
        {{ block.submit_label }}
      </Button>
      <Button
        v-if="weeklySuppression"
        type="button"
        variant="outline"
        :disabled="controlsDisabled || weeklySuppression.disabled"
        @click="submitDisposition(true)"
      >
        {{ weeklySuppression.label }}
      </Button>
    </div>
    <RouterLink
      v-if="block.disposition_link"
      :to="{ name: 'CustomerTracking' }"
      class="mx-space-4 mb-space-3 inline-flex min-h-touch-target w-fit items-center text-body text-brand underline underline-offset-2 focus-visible:outline-ring"
    >
      在客户追踪页处理
    </RouterLink>
  </section>

  <!-- 已处理的选择 / 确认：折叠成一行 -->
  <section
    v-else-if="isCollapsedChoice"
    ref="interactionRef"
    class="agent-ui-interaction flex min-h-[var(--control-h-lg)] max-[767px]:min-h-touch-target items-center gap-space-2 overflow-hidden px-space-4 py-space-2 text-foreground"
    :class="grouped ? '' : 'rounded-lg border border-border bg-card'"
    :aria-labelledby="`${block.id}-prompt`"
  >
    <component
      :is="block.state === 'CANCELLED' || isDeclinedConfirmation ? Circle : Check"
      class="size-icon-sm shrink-0"
      :class="block.state === 'CANCELLED' || isDeclinedConfirmation ? 'text-muted-foreground' : 'text-tone-success'"
      aria-hidden="true"
    />
    <p :id="`${block.id}-prompt`" class="m-0 min-w-0 truncate text-body font-medium text-muted-foreground">{{ block.prompt }}</p>
    <p class="m-0 min-w-0 truncate text-body text-muted-foreground" data-agent-ui-submitted-choice>
      已选择：<b class="font-medium text-foreground">{{ submittedChoiceOption?.label ?? submittedChoiceValue }}</b>
    </p>
    <StatusBadge class="ml-auto shrink-0" :status="stateStatus" type="agentInteraction" size="small" />
  </section>

  <!-- 通用卡片：标题行 + 正文 + 底部操作区 -->
  <section
    v-else
    ref="interactionRef"
    class="agent-ui-interaction grid min-w-0 gap-0 overflow-hidden rounded-lg border border-border bg-card text-foreground"
    :data-state="readonly ? 'readonly' : undefined"
    :aria-labelledby="`${block.id}-prompt`"
    :aria-busy="submitting"
  >
    <header class="flex items-start justify-between gap-space-3 px-space-4 pt-space-4">
      <h2
        v-if="isActivityConfirmation"
        :id="`${block.id}-prompt`"
        class="m-0 min-w-0 text-body [overflow-wrap:anywhere]"
        :class="readonly ? 'font-medium text-muted-foreground' : 'font-semibold text-foreground'"
      >{{ activityHistory ? '客户活动' : '确认写入客户活动' }}</h2>
      <p
        v-else
        :id="`${block.id}-prompt`"
        class="m-0 min-w-0 text-body [overflow-wrap:anywhere]"
        :class="readonly ? 'font-medium text-muted-foreground' : 'font-semibold text-foreground'"
      >{{ block.prompt }}</p>
      <StatusBadge
        class="shrink-0"
        :status="isActivityConfirmation ? (activityHistory ? 'history' : 'pending') : stateStatus"
        type="agentInteraction"
        size="small"
        :label="isActivityConfirmation ? activityWaitingLabel : undefined"
      />
    </header>

    <div v-if="isActivityConfirmation" class="grid min-w-0 gap-space-3 px-space-4 pb-space-4 pt-space-3">
      <p
        v-if="activityFact('customer')"
        class="m-0 flex flex-wrap items-center gap-space-1 text-body"
        data-activity-customer
      >
        <b class="font-medium text-foreground">{{ activityFact('customer')?.value }}</b>
        <span class="text-muted-foreground" aria-hidden="true">/</span>
        <span class="text-muted-foreground">客户活动</span>
      </p>
      <p v-if="activityFact('summary')" class="m-0 text-body text-foreground" data-activity-summary>{{ activityFact('summary')?.value }}</p>
      <dl
        v-if="activityFact('next_action') || activityFact('customer_commitment') || activityFact('next_follow_time') || activityKindFact"
        class="m-0 grid gap-space-1 border-t border-border pt-space-3"
        data-activity-meta
      >
        <div
          v-if="activityFact('customer_commitment')"
          class="grid grid-cols-[72px_minmax(0,1fr)] gap-x-space-3 max-[639px]:grid-cols-[minmax(0,1fr)]"
          data-activity-prop="customer_commitment"
        >
          <dt class="text-caption leading-[var(--line-height-body)] text-muted-foreground">客户承诺</dt>
          <dd class="m-0 min-w-0 text-body text-foreground [overflow-wrap:anywhere]">{{ activityFact('customer_commitment')?.value }}</dd>
        </div>
        <div
          v-if="activityFact('next_action')"
          class="grid grid-cols-[72px_minmax(0,1fr)] gap-x-space-3 max-[639px]:grid-cols-[minmax(0,1fr)]"
          data-activity-prop="next_action"
        >
          <dt class="text-caption leading-[var(--line-height-body)] text-muted-foreground">下一步</dt>
          <dd class="m-0 min-w-0 text-body text-foreground [overflow-wrap:anywhere]">{{ activityFact('next_action')?.value }}</dd>
        </div>
        <div
          v-if="activityFact('next_follow_time')"
          class="grid grid-cols-[72px_minmax(0,1fr)] gap-x-space-3 max-[639px]:grid-cols-[minmax(0,1fr)]"
          data-activity-prop="next_follow_time"
        >
          <dt class="text-caption leading-[var(--line-height-body)] text-muted-foreground">跟进时间</dt>
          <dd class="m-0 min-w-0 text-body text-foreground [overflow-wrap:anywhere]">
            <span data-activity-time-value>{{ activityFact('next_follow_time')?.value }}</span><span v-if="activityTimeFact?.status_label" class="text-muted-foreground">（{{ activityTimeFact.status_label }}）</span>
          </dd>
        </div>
        <div
          v-if="activityKindFact"
          class="grid grid-cols-[72px_minmax(0,1fr)] gap-x-space-3 max-[639px]:grid-cols-[minmax(0,1fr)]"
          data-activity-prop="activity_kind"
        >
          <dt class="text-caption leading-[var(--line-height-body)] text-muted-foreground">活动类型</dt>
          <dd class="m-0 min-w-0">
            <div class="flex flex-wrap items-center gap-space-2">
              <span class="text-body font-medium text-foreground">{{ activityKindFact.value }}</span>
              <StatusBadge
                v-if="activityKindFact.status_label && !activityHistory"
                :status="activityKindFact.status_label"
                type="agentFact"
                size="small"
              />
              <Button
                v-if="(activityKindFact.options?.length ?? 0) > 0 && activityKindFact.status_label !== '未识别 · 需要确认' && isActive"
                type="button"
                variant="link"
                size="sm"
                class="justify-start px-0"
                @click="kindEditorOpen = !kindEditorOpen"
              >
                {{ kindEditorOpen ? '收起类型选项' : '修改活动类型' }}
              </Button>
            </div>
            <p
              v-if="activityKindFact.source && activityKindFact.status_label === '未识别 · 需要确认'"
              class="m-0 text-caption text-muted-foreground"
              data-agent-ui-kind-evidence
            >{{ activityKindFact.source }}</p>
          </dd>
        </div>
      </dl>
      <div
        v-if="activityKindFact && kindOptionsVisible(activityKindFact)"
        class="grid gap-space-2 rounded-md border border-border bg-background p-space-3"
      >
        <span :id="`${block.id}-kind-editor`" class="text-caption font-medium text-foreground">选择活动类型</span>
        <SegmentedChoiceControl
          :model-value="activityKindFact.value"
          :options="kindTileOptions(activityKindFact.options)"
          :disabled="controlsDisabled"
          :labelled-by="`${block.id}-kind-editor`"
          :id-prefix="`${block.id}-kind`"
          wrap
          class="[--segmented-choice-columns:2] sm:[--segmented-choice-columns:3]"
          @update:model-value="reviseActivityKind"
        />
      </div>
      <section v-if="activityChangeSummary" class="grid gap-space-1" data-activity-change>
        <p class="m-0 text-body text-foreground">{{ activityChangeSummary.value }}</p>
        <Button
          type="button"
          variant="link"
          size="sm"
          class="justify-start px-0"
          data-activity-comparison-link
          @click="openActivityComparison"
        >
          查看对比依据
        </Button>
      </section>
      <Collapsible
        v-if="showActivityBasis"
        v-model:open="basisOpen"
        class="grid gap-0 border-t border-border pt-space-1"
        data-activity-basis
      >
        <CollapsibleTrigger as-child>
          <button
            type="button"
            class="flex min-h-[var(--control-h-lg)] max-[767px]:min-h-touch-target w-full items-center gap-space-2 text-left text-caption text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronRight
              class="size-icon-sm shrink-0 transition-transform"
              :class="basisOpen ? 'rotate-90' : ''"
              aria-hidden="true"
            />
            查看参考与依据
          </button>
        </CollapsibleTrigger>
        <!-- 内容常驻 DOM（「查看对比依据」展开后要立刻把焦点移进去），收起时用 display:none 移出视觉与读屏。 -->
        <CollapsibleContent force-mount :class="basisOpen ? '' : 'hidden'">
          <div class="grid gap-space-2 pb-space-2">
            <section v-if="showActivityHistory" class="grid gap-space-2">
              <h3
                ref="activityHistoryHeadingRef"
                class="m-0 text-caption font-semibold text-foreground"
                tabindex="-1"
                data-activity-history-heading
              >历史对比</h3>
              <div v-if="activityComparisonPrevious" class="grid gap-space-1 rounded-md bg-muted px-space-3 py-space-2" data-activity-comparison-previous>
                <h4 class="m-0 text-caption font-medium text-foreground">此前</h4>
                <p class="m-0 text-body text-foreground">{{ activityComparisonPrevious.value }}</p>
                <p v-if="activityComparisonPrevious.source" class="m-0 text-caption text-muted-foreground">{{ activityComparisonPrevious.source }}</p>
              </div>
              <div v-if="activityComparisonCurrent" class="grid gap-space-1 rounded-md bg-muted px-space-3 py-space-2" data-activity-comparison-current>
                <h4 class="m-0 text-caption font-medium text-foreground">本次</h4>
                <p class="m-0 text-body text-foreground">{{ activityComparisonCurrent.value }}</p>
                <p v-if="activityComparisonCurrent.source" class="m-0 text-caption text-muted-foreground">{{ activityComparisonCurrent.source }}</p>
              </div>
              <p v-if="activityContextStatus" class="m-0 text-caption text-muted-foreground">{{ activityContextStatus.value }}</p>
              <div v-if="activityLegacyContext || activityEvidenceLines.length > 0" class="grid gap-space-1">
                <h4 class="m-0 text-caption font-medium text-foreground">历史参考背景</h4>
                <p v-if="activityLegacyContext" class="m-0 text-body text-foreground">{{ activityLegacyContext.source || activityLegacyContext.value }}</p>
                <p v-for="line in activityEvidenceLines" :key="line" class="m-0 text-body text-foreground">{{ line }}</p>
              </div>
              <ul v-if="activityNotices.length > 0" class="m-0 grid list-none gap-space-1 p-0">
                <li v-for="notice in activityNotices" :key="notice.key" class="text-caption text-muted-foreground">{{ notice.value }}</li>
              </ul>
            </section>
            <section v-if="activityOpportunity" class="grid gap-space-1" data-activity-opportunity>
              <h3 class="m-0 text-caption font-semibold text-foreground">参考商机</h3>
              <p class="m-0 text-body text-foreground">{{ activityOpportunity.value }}</p>
              <p class="m-0 text-caption text-muted-foreground">本次仅记录客户活动，不修改商机阶段。</p>
            </section>
            <Collapsible
              v-if="showActivityOrganizingBasis"
              v-slot="{ open }"
              class="grid gap-0 border-t border-border pt-space-1"
              data-activity-score
            >
              <CollapsibleTrigger as-child>
                <button
                  type="button"
                  class="flex min-h-[var(--control-h-lg)] max-[767px]:min-h-touch-target w-full items-center gap-space-2 text-left text-caption text-muted-foreground transition-colors hover:text-foreground"
                >
                  <ChevronRight
                    class="size-icon-sm shrink-0 transition-transform"
                    :class="open ? 'rotate-90' : ''"
                    aria-hidden="true"
                  />
                  内容评分与整理依据
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent force-mount :class="open ? '' : 'hidden'">
                <div class="grid gap-space-2 pb-space-1">
                  <div v-if="activityScoreFact || activityScoreReason" class="grid gap-space-1">
                    <h4 v-if="activityScoreFact" class="m-0 text-caption font-medium text-foreground">内容评分：{{ activityScoreFact.value }}</h4>
                    <p v-if="activityScoreReason" class="m-0 text-body text-foreground">{{ activityScoreReason.value }}</p>
                  </div>
                  <div v-if="activityTimeFact?.source" class="grid gap-space-1">
                    <h4 class="m-0 text-caption font-medium text-foreground">日期原话</h4>
                    <p class="m-0 text-body text-foreground">{{ activityTimeFact.source }}</p>
                  </div>
                  <div v-if="activitySourceFolded" class="grid gap-space-1">
                    <h4 class="m-0 text-caption font-medium text-foreground">类型来源</h4>
                    <p class="m-0 text-body text-foreground">{{ activitySourceFolded }}</p>
                  </div>
                  <p v-if="activityIgnoredNoise" class="m-0 text-caption text-muted-foreground" data-activity-ignored-noise>{{ activityIgnoredNoise.value }}</p>
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>

    <div v-else class="grid min-w-0 gap-space-3 px-space-4 pb-space-4 pt-space-3">
      <div v-if="block.facts.length > 0" class="grid gap-space-3" data-agent-ui-confirmation-facts>
        <section v-for="group in ['write', 'activity_kind', 'context', 'score']" :key="group" class="grid gap-space-2">
          <template v-if="block.facts.some(fact => (fact.group ?? 'write') === group)">
            <div :class="group === 'write' ? 'grid grid-cols-1 gap-x-space-3 gap-y-space-2 sm:grid-cols-2' : 'grid gap-x-space-3 gap-y-space-2'">
              <div
                v-for="fact in block.facts.filter(item => (item.group ?? 'write') === group)"
                :key="fact.key"
                class="grid min-w-0 content-start gap-space-1"
                :data-agent-ui-fact="fact.key"
              >
                <dt class="m-0 flex flex-wrap items-center justify-between gap-space-1 text-caption text-muted-foreground">
                  {{ fact.label }}
                  <StatusBadge v-if="fact.status_label" :status="fact.status_label" type="agentFact" size="small" />
                </dt>
                <dd class="m-0 truncate text-body font-medium text-foreground" :title="fact.value">{{ fact.value }}</dd>
                <p v-if="fact.source" class="m-0 text-caption text-muted-foreground">{{ fact.source }}</p>
                <Button
                  v-if="(fact.options?.length ?? 0) > 0 && fact.status_label !== '未识别 · 需要确认' && isActive"
                  type="button"
                  variant="link"
                  size="sm"
                  class="justify-start px-0"
                  @click="kindEditorOpen = !kindEditorOpen"
                >
                  {{ kindEditorOpen ? '收起类型选项' : '修改活动类型' }}
                </Button>
                <div v-if="kindOptionsVisible(fact)" class="grid gap-space-2 rounded-md border border-border bg-background p-space-3">
                  <span class="text-caption font-medium text-foreground">选择活动类型</span>
                  <SegmentedChoiceControl
                    :model-value="kindTileValue(fact)"
                    :options="kindTileOptions(fact.options)"
                    :disabled="controlsDisabled"
                    wrap
                    class="[--segmented-choice-columns:2] sm:[--segmented-choice-columns:3]"
                    @update:model-value="reviseActivityKind"
                  />
                </div>
              </div>
            </div>
          </template>
        </section>
      </div>

      <!-- 卡片级提示只由宿主挂在活动类型选择卡上（见 SalesAssistantChat.cardNoticeKey），所以只出现在通用卡片里。 -->
      <AgentUIBanner
        v-if="notice?.kind === 'failed'"
        tone="danger"
        :icon="AlertCircle"
        title="选择没有提交成功，请重新选择"
        data-agent-ui-card-notice="failed"
      >
        <template #actions>
          <Button
            type="button"
            variant="outline"
            size="sm"
            :disabled="disabled === true || locked === true || submitting"
            @click="retryNoticeChoice"
          >
            重新提交
          </Button>
        </template>
      </AgentUIBanner>
      <AgentUIBanner
        v-else-if="notice?.kind === 'invalid'"
        tone="danger"
        :icon="AlertCircle"
        title="请从卡片给出的活动类型中选择。"
        data-agent-ui-card-notice="invalid"
      />
      <AgentUIBanner
        v-else-if="notice?.kind === 'expired'"
        tone="neutral"
        :icon="Info"
        role="status"
        title="已在别处处理，已刷新"
        data-agent-ui-card-notice="expired"
      />

      <div v-if="isGenericConfirmation && confirmationDisabledHint" class="text-caption text-muted-foreground">
        {{ confirmationDisabledHint }}
      </div>

      <div
        v-if="cancelReasons.length > 0"
        v-show="cancelReasonsOpen"
        :id="`${block.id}-cancel-reasons`"
        ref="cancelReasonsRef"
        class="grid gap-space-2 rounded-md border border-border p-space-3"
        role="group"
        :aria-labelledby="`${block.id}-cancel-reasons-label`"
      >
        <p :id="`${block.id}-cancel-reasons-label`" class="m-0 text-body font-medium text-foreground">取消原因（选填）</p>
        <div class="flex flex-wrap gap-space-2">
          <Button
            v-for="reason in cancelReasons"
            :key="reason.value"
            type="button"
            variant="outline"
            :disabled="controlsDisabled || reason.disabled"
            @click="submitConfirmationCancel(reason.value)"
          >
            {{ reason.label }}
          </Button>
          <Button type="button" variant="ghost" :disabled="controlsDisabled" @click="submitConfirmationCancel()">
            跳过原因
          </Button>
        </div>
      </div>

      <template v-if="showsChoiceOptions && block.interaction_type === 'choice'">
        <div v-if="block.hint" class="grid gap-space-1" data-agent-ui-kind-hint>
          <p class="m-0 flex flex-wrap items-center gap-space-2 text-caption text-muted-foreground">
            <span>原文提到：</span>
            <Badge v-for="channel in kindHintChannels" :key="channel" variant="secondary">{{ channel }}</Badge>
            <span v-if="kindHintChannels.length === 0">{{ block.hint }}</span>
          </p>
          <p class="m-0 text-caption text-muted-foreground">
            <b class="font-semibold text-foreground">请按本次实际发生的沟通来选</b>；之后计划的会议不算本次活动。
          </p>
        </div>
        <div class="grid gap-space-2" data-agent-ui-choice>
          <SegmentedChoiceControl
            v-if="block.selection_mode === 'multiple'"
            multiple
            :model-value="selectedValues"
            :options="choiceTileOptions"
            :disabled="controlsDisabled"
            :labelled-by="`${block.id}-prompt`"
            :id-prefix="`${block.id}-option`"
            :invalid="selectionError !== null"
            :described-by="selectionError === null ? undefined : `${block.id}-selection-error`"
            wrap
            class="[--segmented-choice-columns:2]"
            @update:model-value="selectedValues = $event"
          />
          <SegmentedChoiceControl
            v-else
            :model-value="selectedValues[0] ?? ''"
            :options="choiceTileOptions"
            :disabled="controlsDisabled"
            :labelled-by="`${block.id}-prompt`"
            :id-prefix="`${block.id}-option`"
            :invalid="selectionError !== null"
            :described-by="selectionError === null ? undefined : `${block.id}-selection-error`"
            wrap
            class="[--segmented-choice-columns:2]"
            @update:model-value="handleOptionClick"
          />
        </div>
        <InputField
          v-if="block.business_action === 'resolve_temporal_choice'"
          :id="`${block.id}-manual-date`"
          :model-value="manualDate"
          label="手动输入其他日期"
          placeholder="例如：2026-10-30"
          helper-text="选择候选或输入完整日期后继续。"
          :disabled="controlsDisabled"
          @update:model-value="manualDate = String($event)"
          @keydown.enter.prevent="submitManualDate"
        />
        <p
          v-if="selectionError !== null"
          :id="`${block.id}-selection-error`"
          class="m-0 text-body text-foreground"
          role="alert"
        >
          {{ selectionError }}
        </p>
      </template>

      <p
        v-else-if="submittedTextField !== null"
        class="m-0 text-body text-foreground [overflow-wrap:anywhere]"
        data-agent-ui-submitted-text
      >
        <span class="font-medium text-muted-foreground">{{ submittedTextField.label }}：</span>{{ submittedTextField.value }}
      </p>

      <div v-else-if="block.interaction_type === 'choice' || block.interaction_type === 'confirmation'" class="hidden"></div>

      <form v-else-if="!(readonly && (block.interaction_type === 'text_input' || block.interaction_type === 'form'))" class="grid gap-space-3" novalidate @submit.prevent="submit">
        <template v-for="field in block.fields" :key="field.key">
          <TextareaField
            v-if="field.field_type === 'textarea'"
            :id="`${block.id}-${field.key}`"
            :label="field.label"
            :model-value="textValue(field)"
            :placeholder="field.placeholder ?? ''"
            :helper-text="field.source_label ?? ''"
            :required="field.required"
            :disabled="controlsDisabled"
            :error="visibleFieldError(field) ?? ''"
            rows="3"
            :minlength="field.min_length ?? undefined"
            :maxlength="field.max_length ?? undefined"
            :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
            @update:model-value="updateTextValue(field, $event)"
          />
          <InputField
            v-else-if="field.field_type === 'text' || field.field_type === 'date' || field.field_type === 'datetime'"
            :id="`${block.id}-${field.key}`"
            :label="field.label"
            :type="field.field_type === 'datetime' ? 'datetime-local' : field.field_type"
            :model-value="textValue(field)"
            :placeholder="field.placeholder ?? ''"
            :helper-text="field.source_label ?? ''"
            :required="field.required"
            :disabled="controlsDisabled"
            :error="visibleFieldError(field) ?? ''"
            :minlength="field.min_length ?? undefined"
            :maxlength="field.max_length ?? undefined"
            :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
            @update:model-value="updateTextValue(field, $event)"
          />
          <InputField
            v-else-if="field.field_type === 'number'"
            :id="`${block.id}-${field.key}`"
            :label="field.label"
            type="number"
            :model-value="numberValue(field) ?? ''"
            :placeholder="field.placeholder ?? ''"
            :helper-text="field.source_label ?? ''"
            :required="field.required"
            :disabled="controlsDisabled"
            :error="visibleFieldError(field) ?? ''"
            :min="field.minimum ?? undefined"
            :max="field.maximum ?? undefined"
            :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
            @update:model-value="updateNumberValue(field, $event)"
          />
          <SelectField
            v-else-if="field.field_type === 'select'"
            :id="`${block.id}-${field.key}`"
            :label="field.label"
            :options="availableFieldOptions(field)"
            :model-value="textValue(field)"
            :placeholder="field.placeholder ?? `请选择${field.label}`"
            :helper-text="field.source_label ?? ''"
            :required="field.required"
            :disabled="controlsDisabled || availableFieldOptions(field).length === 0"
            :error="visibleFieldError(field) ?? ''"
            :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
            @update:model-value="updateSelectValue(field, $event)"
          />
          <MultiSelectField
            v-else-if="field.field_type === 'multi_select'"
            :id="`${block.id}-${field.key}`"
            :label="field.label"
            :options="availableFieldOptions(field)"
            :model-value="selectedFieldValues(field)"
            :placeholder="field.placeholder ?? `请选择${field.label}`"
            :helper-text="field.source_label ?? ''"
            :required="field.required"
            :disabled="controlsDisabled || availableFieldOptions(field).length === 0"
            :error="visibleFieldError(field) ?? ''"
            :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
            @update:model-value="updateMultiSelectValue(field, $event)"
          />
          <CheckboxField
            v-else
            :id="`${block.id}-${field.key}`"
            :label="field.label"
            :helper-text="field.source_label ?? ''"
            :model-value="booleanValue(field)"
            :required="field.required"
            :disabled="controlsDisabled"
            :error="visibleFieldError(field) ?? ''"
            :data-agent-ui-error-focus="visibleFieldError(field) !== null ? 'true' : undefined"
            @update:model-value="updateBooleanValue(field, $event)"
          />
        </template>
      </form>
    </div>

    <footer
      v-if="(isActivityConfirmation && showsChoiceOptions) || isGenericConfirmation || canCancel || (!isActivityConfirmation && isActive && !submitsOnOptionClick)"
      class="flex flex-wrap items-center justify-end gap-space-2 border-t border-border px-space-4 py-space-3"
    >
      <p v-if="isActivityConfirmation && activityDisabledHint" class="m-0 min-w-0 flex-1 basis-full text-caption text-muted-foreground">
        {{ activityDisabledHint }}
      </p>
      <template v-if="isActivityConfirmation">
        <Button
          v-for="option in activityActionOptions"
          :key="option.value"
          type="button"
          :variant="option.value === 'confirm' ? 'default' : 'outline'"
          :loading="option.value === 'confirm' && submitting"
          :disabled="controlsDisabled || option.disabled"
          :aria-expanded="option.value === 'cancel' && cancelReasons.length > 0 ? cancelReasonsOpen : undefined"
          :aria-controls="option.value === 'cancel' && cancelReasons.length > 0 ? `${block.id}-cancel-reasons` : undefined"
          @click="handleOptionClick(option.value)"
        >
          {{ option.label }}
        </Button>
      </template>
      <template v-else-if="isGenericConfirmation">
        <Button
          type="button"
          variant="outline"
          :disabled="controlsDisabled || confirmationOptions.cancel?.disabled === true"
          @click="handleOptionClick('cancel')"
        >
          {{ confirmationOptions.cancel?.label }}
        </Button>
        <Button
          type="button"
          :loading="submitting"
          :disabled="controlsDisabled || confirmationOptions.confirm?.disabled === true"
          @click="handleOptionClick('confirm')"
        >
          {{ confirmationOptions.confirm?.label }}
        </Button>
      </template>
      <template v-else>
        <Button
          v-if="canCancel"
          type="button"
          variant="outline"
          :disabled="controlsDisabled"
          @click="cancel"
        >
          取消
        </Button>
        <Button
          v-if="isActive && !submitsOnOptionClick"
          type="button"
          :loading="submitting"
          :disabled="controlsDisabled"
          @click="submit"
        >
          {{ block.submit_label }}
        </Button>
      </template>
      <Button
        v-if="confirmationEdit"
        type="button"
        variant="outline"
        :disabled="controlsDisabled || confirmationEdit.disabled"
        @click="submitConfirmationEdit"
      >
        {{ confirmationEdit.label }}
      </Button>
    </footer>
  </section>
</template>
