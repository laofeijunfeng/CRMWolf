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

import type { InteractionNotice } from './interactionNotice'

type InteractionBlock = Extract<AgentUIBlock, { type: 'interaction' }>
type InteractionField = InteractionBlock['fields'][number]

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

watch(() => props.locked, (locked, previous) => {
  if (previous !== true || locked === true || props.block.state !== 'ACTIVE') return
  const releaseTextInput = props.block.interaction_type === 'text_input'
  const releaseFollowUpForm = props.block.interaction_type === 'form'
    && props.block.business_action === 'provide_follow_up_content'
  if (releaseTextInput || releaseFollowUpForm) submitting.value = false
})

const isActive = computed(() => props.block.state === 'ACTIVE' && props.block.submit_action_id !== null)
const canCancel = computed(() => (
  isActive.value
  && props.block.allow_cancel === true
  && props.block.business_action === 'provide_follow_up_content'
  && (props.block.interaction_type === 'text_input' || props.block.interaction_type === 'form')
))
const isCompactTaskCompletion = computed(() => (
  props.block.presentation === 'COMPACT_TASK_COMPLETION'
))
const isOpenFollowUpDisposition = computed(() => (
  props.block.presentation === 'OPEN_FOLLOW_UP_DISPOSITION'
))
const dispositionItems = computed(() => props.block.disposition_items ?? [])
const dispositionTotal = computed(() => dispositionItems.value.length)
const dispositionCurrentIndex = computed(() => {
  const index = dispositionItems.value.findIndex(item => item.state === 'current')
  return index === -1 ? null : index + 1
})
const dispositionProgress = computed(() => `${dispositionCurrentIndex.value ?? dispositionTotal.value} / ${dispositionTotal.value}`)
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

const stateLabel = computed(() => {
  if (props.notice?.kind === 'expired') return '已过期'
  if (props.notice?.kind === 'failed') return '提交失败'
  if (submitting.value) return '处理中'
  return ({
    ACTIVE: '待处理',
    SUBMITTED: '已处理',
    EXPIRED: '已过期',
    CANCELLED: '已取消',
    READ_ONLY: '历史'
  })[props.block.state]
})

const stateLabelClass = computed(() => {
  if (props.notice?.kind === 'failed') return 'border-[#fecaca] bg-[#fef2f2] text-[#b91c1c]'
  if (props.notice?.kind === 'expired') return 'border-border bg-muted text-muted-foreground'
  return 'border-[#bfdbfe] bg-[#eff6ff] text-[#1d4ed8]'
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
const activityReferenceRef = ref<HTMLDetailsElement | null>(null)
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
const openActivityComparison = async (): Promise<void> => {
  if (activityReferenceRef.value === null) return
  activityReferenceRef.value.open = true
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
  return [cancel, confirm].filter((option): option is InteractionBlock['options'][number] => option !== undefined)
})
const activityKindPillClass = computed(() => {
  const label = activityKindFact.value?.status_label ?? ''
  if (label.includes('未识别')) return 'is-warning'
  if (label === '已识别') return 'is-success'
  return 'is-info'
})

const KIND_HINT_PREFIX = '原文提到：'
const kindHintChannels = computed((): string[] => {
  const hint = props.block.hint ?? ''
  if (!hint.startsWith(KIND_HINT_PREFIX)) return []
  return hint.slice(KIND_HINT_PREFIX.length).split('、').map(part => part.trim()).filter(part => part !== '')
})

interface ChoiceEntry { option: InteractionBlock['options'][number]; index: number }
interface ChoiceGroup { name: string | null; entries: ChoiceEntry[] }
const choiceOptions = computed(() => (
  isActivityConfirmation.value ? activityActionOptions.value : props.block.options
))
const choiceGroups = computed((): ChoiceGroup[] => {
  const groups: ChoiceGroup[] = []
  choiceOptions.value.forEach((option, index) => {
    const name = typeof option.group === 'string' && option.group !== '' ? option.group : null
    const current = groups[groups.length - 1]
    if (current !== undefined && current.name === name) {
      current.entries.push({ option, index })
      return
    }
    groups.push({ name, entries: [{ option, index }] })
  })
  return groups
})
const showsChoiceOptions = computed(() => (
  isActive.value
  && (props.block.interaction_type === 'choice' || props.block.interaction_type === 'confirmation')
  && props.notice?.kind !== 'expired'
))

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

const cancel = (): void => {
  const actionId = props.block.submit_action_id
  if (!canCancel.value || controlsDisabled.value || actionId === null) return
  submitting.value = true
  emit('submit', actionId, { cancel: true })
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
    void nextTick(() => {
      if (props.locked !== true && props.block.state === 'ACTIVE') submitting.value = false
    })
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
      grouped ? '' : 'rounded-wolf-surface border border-border',
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
    v-else-if="isOpenFollowUpDisposition"
    ref="interactionRef"
    class="agent-ui-interaction grid gap-0 rounded-wolf-surface border border-[#bfdbfe] bg-[#f8fbff] px-4 py-3.5"
    :aria-labelledby="`${block.id}-prompt`"
    :aria-busy="submitting"
  >
    <header class="flex items-start justify-between gap-3">
      <h4 :id="`${block.id}-prompt`" class="m-0 text-sm font-semibold text-foreground">历史跟进任务</h4>
      <span class="shrink-0 rounded-wolf-full border border-[#bfdbfe] bg-[#eff6ff] px-2 text-xs font-semibold leading-5 text-[#1d4ed8]" :aria-label="`第 ${dispositionProgress.split(' / ')[0]} 项，共 ${dispositionProgress.split(' / ')[1]} 项`">{{ dispositionProgress }}</span>
    </header>
    <p v-if="block.hint" class="m-0 mt-2 text-[13px] leading-5 text-[#334155]" data-agent-ui-disposition-summary>{{ block.hint }}</p>
    <ol class="m-0 mt-2.5 grid list-none gap-0 border-t border-[#e5eaf0] p-0">
      <li
        v-for="(item, index) in dispositionItems"
        :key="item.item_id"
        class="grid gap-1.5 border-b border-[#eef1f4] py-2.5 last:border-b-0"
      >
        <div class="flex items-start justify-between gap-2.5">
          <p class="m-0 min-w-0 text-sm text-foreground"><span class="mr-1.5 text-muted-foreground">{{ index + 1 }}</span>{{ item.title }}</p>
          <span
            class="shrink-0 rounded-wolf-full border px-2 text-xs leading-5"
            :class="item.state === 'current'
              ? 'border-[#bfdbfe] bg-[#eff6ff] text-[#1d4ed8]'
              : item.state === 'complete'
                ? 'border-[#d1fae5] bg-[#ecfdf5] text-[#22745e]'
                : item.state === 'unknown'
                  ? 'border-[#fed7aa] bg-[#fff7ed] text-[#b45309]'
                  : item.state === 'failed'
                    ? 'border-[#fecaca] bg-[#fef2f2] text-[#b91c1c]'
                    : 'border-[#e2e6eb] bg-[#f3f6f8] text-[#667180]'"
          >{{ item.state === 'current' ? '当前' : item.state === 'waiting' ? '待处理' : item.result_title }}</span>
        </div>
        <p v-if="item.owner_line" class="m-0 text-xs text-muted-foreground">{{ item.owner_line }}</p>
        <div v-if="item.related && item.evidence_quote" class="grid gap-1">
          <button
            type="button"
            class="inline-flex w-fit items-center text-xs text-[#1d4ed8] underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2563eb]"
            :aria-expanded="evidenceOpenId === item.item_id"
            :aria-controls="`${block.id}-evidence-${item.item_id}`"
            data-agent-ui-related-toggle
            @click="toggleEvidence(item.item_id)"
          >
            查看关联信息
          </button>
          <p
            v-if="evidenceOpenId === item.item_id"
            :id="`${block.id}-evidence-${item.item_id}`"
            class="m-0 rounded-wolf border border-[#e2e6eb] bg-white px-2.5 py-2 text-xs leading-5 text-[#334155]"
            data-agent-ui-related-line
          >
            本次跟进：“{{ item.evidence_quote }}”
          </p>
        </div>
        <div v-if="item.state === 'current' && isActive" class="grid grid-cols-3 gap-2">
          <button
            v-for="option in block.options"
            :key="option.value"
            type="button"
            class="rounded-wolf border border-[#cbd5e1] bg-white px-2.5 py-1.5 text-center text-[13px] text-foreground disabled:bg-[#f3f4f6] disabled:text-[#a0a7b0]"
            :disabled="controlsDisabled || option.disabled"
            @click="handleOptionClick(option.value)"
          >
            {{ submitting && optionSelected(option.value) ? `${option.label}处理中…` : option.label }}
          </button>
        </div>
        <p v-if="item.result_message && !(item.state === 'current' && isActive)" class="m-0 text-xs" :class="item.state === 'failed' ? 'text-[#b91c1c]' : item.state === 'unknown' ? 'text-[#b45309]' : item.state === 'complete' ? 'text-[#22745e]' : 'text-muted-foreground'">{{ item.result_message }}</p>
      </li>
    </ol>
  </section>

  <section
    v-else
    ref="interactionRef"
    class="agent-ui-interaction grid rounded-wolf-surface p-3"
    :class="isActivityConfirmation
      ? (block.state === 'READ_ONLY' ? 'activity-card gap-0 overflow-hidden border border-dashed border-border bg-card p-0' : 'activity-card gap-0 overflow-hidden border border-border bg-card p-0')
      : (block.state === 'READ_ONLY' ? 'gap-3 border border-dashed border-border bg-muted/40' : 'gap-3 border border-[#bfdbfe] bg-[#f8fbff]')"
    :aria-labelledby="`${block.id}-prompt`"
    :aria-busy="submitting"
  >
    <template v-if="isActivityConfirmation">
      <header class="activity-header">
        <h2 :id="`${block.id}-prompt`" class="activity-title">{{ activityHistory ? '客户活动' : '确认写入客户活动' }}</h2>
        <span class="activity-pill" :class="activityHistory ? 'is-muted' : 'is-info'">{{ activityWaitingLabel }}</span>
      </header>
      <div class="activity-main">
        <section class="activity-section">
          <p v-if="activityFact('customer')" class="activity-customer">
            <b>{{ activityFact('customer')?.value }}</b>
            <span aria-hidden="true">/</span>
            <span>客户活动</span>
          </p>
          <p v-if="activityFact('summary')" class="activity-body">{{ activityFact('summary')?.value }}</p>
          <dl
            v-if="activityFact('next_action') || activityFact('customer_commitment') || activityFact('next_follow_time') || activityKindFact"
            class="activity-meta"
          >
            <div v-if="activityFact('customer_commitment')" class="activity-meta-row">
              <dt>客户承诺</dt>
              <dd>{{ activityFact('customer_commitment')?.value }}</dd>
            </div>
            <div v-if="activityFact('next_action')" class="activity-meta-row">
              <dt>下一步</dt>
              <dd>{{ activityFact('next_action')?.value }}</dd>
            </div>
            <div v-if="activityFact('next_follow_time')" class="activity-meta-row">
              <dt>跟进时间</dt>
              <dd>
                <div class="activity-time">
                  <span class="activity-time-value">{{ activityFact('next_follow_time')?.value }}</span><span v-if="activityTimeFact?.status_label" class="activity-time-status">（{{ activityTimeFact.status_label }}）</span>
                </div>
              </dd>
            </div>
            <div v-if="activityKindFact" class="activity-meta-row">
              <dt>活动类型</dt>
              <dd>
                <div class="activity-kind">
                  <span class="activity-kind-name">{{ activityKindFact.value }}</span>
                  <span v-if="activityKindFact.status_label && !activityHistory" class="activity-pill" :class="activityKindPillClass">{{ activityKindFact.status_label }}</span>
                  <button v-if="(activityKindFact.options?.length ?? 0) > 0 && activityKindFact.status_label !== '未识别 · 需要确认'" type="button" class="activity-link" @click="kindEditorOpen = !kindEditorOpen">{{ kindEditorOpen ? '收起类型选项' : '修改活动类型' }}</button>
                </div>
                <p v-if="activityKindFact.source && activityKindFact.status_label === '未识别 · 需要确认'" class="activity-caption" data-agent-ui-kind-evidence>{{ activityKindFact.source }}</p>
              </dd>
            </div>
          </dl>
          <div v-if="activityKindFact && kindOptionsVisible(activityKindFact)" class="activity-kind-editor">
            <div class="activity-kind-editor-head">
              <span>选择活动类型</span>
            </div>
            <div class="activity-kind-options">
              <button v-for="option in activityKindFact.options ?? []" :key="option.value" type="button" class="activity-kind-option" :class="option.label === activityKindFact.value ? 'is-selected' : ''" :disabled="controlsDisabled || option.disabled" @click="reviseActivityKind(option.value)">{{ option.label }}</button>
            </div>
          </div>
        </section>
        <section v-if="activityChangeSummary" class="activity-change">
          <p class="activity-body">{{ activityChangeSummary.value }}</p>
          <button type="button" class="activity-link" data-activity-comparison-link @click="openActivityComparison">查看对比依据</button>
        </section>
        <details v-if="showActivityBasis" ref="activityReferenceRef" class="activity-details activity-basis">
          <summary>查看参考与依据</summary>
          <div class="activity-reference-body">
            <section v-if="showActivityHistory" class="activity-reference-section">
              <h3 ref="activityHistoryHeadingRef" class="activity-reference-heading" tabindex="-1" data-activity-history-heading>历史对比</h3>
              <div v-if="activityComparisonPrevious" class="activity-reference-quote" data-activity-comparison-previous>
                <h4>此前</h4>
                <p>{{ activityComparisonPrevious.value }}</p>
                <p v-if="activityComparisonPrevious.source" class="activity-caption">{{ activityComparisonPrevious.source }}</p>
              </div>
              <div v-if="activityComparisonCurrent" class="activity-reference-quote" data-activity-comparison-current>
                <h4>本次</h4>
                <p>{{ activityComparisonCurrent.value }}</p>
                <p v-if="activityComparisonCurrent.source" class="activity-caption">{{ activityComparisonCurrent.source }}</p>
              </div>
              <p v-if="activityContextStatus" class="activity-caption">{{ activityContextStatus.value }}</p>
              <div v-if="activityLegacyContext || activityEvidenceLines.length > 0" class="activity-reference-quote">
                <h4>历史参考背景</h4>
                <p v-if="activityLegacyContext">{{ activityLegacyContext.source || activityLegacyContext.value }}</p>
                <p v-for="line in activityEvidenceLines" :key="line">{{ line }}</p>
              </div>
              <ul v-if="activityNotices.length > 0" class="activity-reference-notices">
                <li v-for="notice in activityNotices" :key="notice.key">{{ notice.value }}</li>
              </ul>
            </section>
            <section v-if="activityOpportunity" class="activity-reference-section" data-activity-opportunity>
              <h3 class="activity-reference-heading">参考商机</h3>
              <p class="activity-body">{{ activityOpportunity.value }}</p>
              <p class="activity-caption">本次仅记录客户活动，不修改商机阶段。</p>
            </section>
            <details v-if="showActivityOrganizingBasis" class="activity-details activity-score">
              <summary>内容评分与整理依据</summary>
              <div class="activity-score-body">
                <div v-if="activityScoreFact || activityScoreReason" class="activity-reference-quote">
                  <h4 v-if="activityScoreFact">内容评分：{{ activityScoreFact.value }}</h4>
                  <p v-if="activityScoreReason">{{ activityScoreReason.value }}</p>
                </div>
                <div v-if="activityTimeFact?.source" class="activity-reference-quote">
                  <h4>日期原话</h4>
                  <p>{{ activityTimeFact.source }}</p>
                </div>
                <div v-if="activitySourceFolded" class="activity-reference-quote">
                  <h4>类型来源</h4>
                  <p>{{ activitySourceFolded }}</p>
                </div>
                <p v-if="activityIgnoredNoise" class="activity-caption" data-activity-ignored-noise>{{ activityIgnoredNoise.value }}</p>
              </div>
            </details>
          </div>
        </details>
      </div>
    </template>
    <header v-if="!isActivityConfirmation" class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 items-start gap-2">
        <span class="grid size-5 shrink-0 place-items-center rounded-wolf-sm bg-[#dbeafe] text-[11px] font-semibold text-[#1d4ed8]" aria-hidden="true">?</span>
        <p :id="`${block.id}-prompt`" class="m-0 text-[13px] font-semibold leading-5 text-foreground">{{ block.prompt }}</p>
      </div>
      <span class="shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium" :class="stateLabelClass">{{ stateLabel }}</span>
    </header>

    <div v-if="!isActivityConfirmation && block.facts.length > 0" class="grid gap-3" data-agent-ui-confirmation-facts>
      <section v-for="group in ['write', 'activity_kind', 'context', 'score']" :key="group" class="grid gap-2">
        <template v-if="block.facts.some(fact => (fact.group ?? 'write') === group)">
          <div :class="group === 'write' ? 'grid grid-cols-1 gap-2 sm:grid-cols-2' : 'grid gap-2'">
            <div
              v-for="fact in block.facts.filter(item => (item.group ?? 'write') === group)"
              :key="fact.key"
              class="min-w-0 rounded-wolf border border-border bg-white px-2.5 py-2"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <dt class="text-[11px] text-muted-foreground">{{ fact.label }}</dt>
                <span v-if="fact.status_label" class="rounded-full border border-[#bfdbfe] bg-[#eff6ff] px-2 py-0.5 text-[11px] text-[#1d4ed8]">{{ fact.status_label }}</span>
              </div>
              <dd class="m-0 mt-0.5 text-xs font-semibold text-foreground" :class="group === 'activity_kind' ? '' : 'truncate'" :title="fact.value">{{ fact.value }}</dd>
              <p v-if="fact.source" class="m-0 mt-1 text-[11px] leading-5 text-muted-foreground">{{ fact.source }}</p>
              <div v-if="(fact.options?.length ?? 0) > 0" class="mt-2 grid gap-2">
                <button
                  v-if="fact.status_label !== '未识别 · 需要确认'"
                  type="button"
                  class="w-fit text-xs text-primary underline-offset-2 hover:underline"
                  @click="kindEditorOpen = !kindEditorOpen"
                >
                  {{ kindEditorOpen ? '收起类型选项' : '修改活动类型' }}
                </button>
                <div v-if="kindOptionsVisible(fact)" class="flex flex-wrap gap-2">
                  <button
                    v-for="option in fact.options ?? []"
                    :key="option.value"
                    type="button"
                    class="min-h-11 rounded-wolf border px-3 text-xs"
                    :class="option.value === fact.value || option.label === fact.value ? 'border-primary bg-accent text-accent-foreground' : 'border-border bg-white'"
                    :disabled="controlsDisabled || option.disabled"
                    @click="reviseActivityKind(option.value)"
                  >
                    {{ option.label }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </template>
      </section>
    </div>

    <div
      v-if="notice?.kind === 'failed'"
      class="rounded-wolf border border-[#fecaca] bg-[#fef2f2] px-3 py-2"
      data-agent-ui-card-notice="failed"
    >
      <p class="m-0 text-xs leading-5 text-[#b91c1c]">选择没有提交成功，请重新选择</p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        class="mt-2 min-h-9 border-[#fecaca] bg-white text-[#b91c1c] hover:bg-[#fef2f2]"
        :disabled="disabled === true || locked === true || submitting"
        @click="retryNoticeChoice"
      >
        重新提交
      </Button>
    </div>
    <p
      v-else-if="notice?.kind === 'invalid'"
      class="m-0 rounded-wolf border border-[#fecaca] bg-[#fef2f2] px-3 py-2 text-xs leading-5 text-[#b91c1c]"
      data-agent-ui-card-notice="invalid"
    >
      请从卡片给出的活动类型中选择。
    </p>
    <p
      v-else-if="notice?.kind === 'expired'"
      class="m-0 rounded-wolf border border-border bg-muted/50 px-3 py-2 text-xs leading-5 text-muted-foreground"
      data-agent-ui-card-notice="expired"
    >
      已在别处处理，已刷新
    </p>

    <div
      v-if="submittedChoiceValue !== null"
      class="rounded-wolf border border-border bg-background px-3 py-2 text-sm text-foreground"
      data-agent-ui-submitted-choice
    >
      <span class="font-medium">已选择：</span>{{ submittedChoiceOption?.label ?? submittedChoiceValue }}
    </div>

    <template v-else-if="showsChoiceOptions">
      <div
        class="gap-2"
        :class="block.interaction_type === 'confirmation' ? (isActivityConfirmation ? 'activity-actions' : 'flex flex-wrap') : 'grid grid-cols-1 sm:grid-cols-2'"
        role="group"
        :aria-invalid="selectionError !== null"
        :aria-describedby="selectionError === null ? undefined : `${block.id}-selection-error`"
      >
      <p
        v-if="isActivityConfirmation && block.options.some(option => option.disabled && option.description)"
        class="activity-actions-hint"
      >
        {{ block.options.find(option => option.disabled && option.description)?.description }}
      </p>
      <div
        v-if="block.hint"
        class="col-span-full rounded-wolf border border-[#e2e8f0] bg-white px-3 py-2"
        data-agent-ui-kind-hint
      >
        <p class="m-0 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          <span>原文提到：</span>
          <span
            v-for="channel in kindHintChannels"
            :key="channel"
            class="rounded border border-[#e2e8f0] bg-[#f8fafc] px-1.5 py-0.5 text-[11px] text-foreground"
          >{{ channel }}</span>
          <span v-if="kindHintChannels.length === 0">{{ block.hint }}</span>
        </p>
        <p class="m-0 mt-1 text-xs leading-5 text-foreground">
          <b class="font-semibold">请按本次实际发生的沟通来选</b>；之后计划的会议不算本次活动。
        </p>
      </div>
      <template v-for="(group, groupIndex) in choiceGroups" :key="`${group.name ?? ''}#${groupIndex}`">
        <p v-if="group.name" class="col-span-full m-0 mt-1 text-[11px] font-medium text-muted-foreground">{{ group.name }}</p>
        <Button
          v-for="entry in group.entries"
          :key="entry.option.value"
          type="button"
          :variant="block.interaction_type === 'confirmation' && entry.option.value === 'confirm' ? 'default' : 'outline'"
          class="min-h-11 h-auto justify-start gap-0.5 px-3 py-2 text-left"
          :class="[
            block.interaction_type === 'confirmation' ? '' : 'grid w-full bg-white',
            block.business_action === 'resolve_temporal_choice' ? 'min-w-0 grid-cols-1 whitespace-normal [overflow-wrap:anywhere]' : '',
            optionSelected(entry.option.value) ? 'border-primary bg-accent text-accent-foreground' : '',
            isActivityConfirmation ? 'activity-action' : '', isActivityConfirmation && entry.option.disabled ? 'border-[#cbd5e1] bg-[#e2e8f0] text-[#94a3b8] opacity-100' : ''
          ]"
          :aria-pressed="optionSelected(entry.option.value)"
          :disabled="controlsDisabled || entry.option.disabled"
          :data-agent-ui-error-focus="selectionError !== null && entry.index === 0 ? 'true' : undefined"
          @click="handleOptionClick(entry.option.value)"
        >
          <span>{{ submitting && optionSelected(entry.option.value) ? `${entry.option.label}处理中…` : entry.option.label }}</span>
          <small v-if="entry.option.description && block.interaction_type !== 'confirmation'" class="text-xs text-muted-foreground">
            {{ entry.option.description }}
          </small>
        </Button>
      </template>
        <p
          v-if="!isActivityConfirmation && block.interaction_type === 'confirmation' && block.options.some(option => option.disabled && option.description)"
          class="m-0 basis-full text-xs text-muted-foreground"
        >
          {{ block.options.find(option => option.disabled && option.description)?.description }}
        </p>
        <p
          v-if="selectionError !== null"
          :id="`${block.id}-selection-error`"
          class="m-0 text-sm text-destructive"
          role="alert"
        >
          {{ selectionError }}
        </p>
      </div>
      <div v-if="block.business_action === 'resolve_temporal_choice'" class="grid gap-1.5">
        <label class="text-[13px] font-semibold text-foreground" :for="`${block.id}-manual-date`">手动输入其他日期</label>
        <input
          :id="`${block.id}-manual-date`"
          v-model="manualDate"
          type="text"
          class="min-h-11 rounded-wolf border border-border bg-white px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          placeholder="例如：2026-10-30"
          :disabled="controlsDisabled"
          @keydown.enter.prevent="submitManualDate"
        />
        <p class="m-0 text-[11px] text-muted-foreground">选择候选或输入完整日期后继续。</p>
      </div>
    </template>
    <div v-else-if="block.interaction_type === 'choice' || block.interaction_type === 'confirmation'" class="hidden"></div>

    <div
      v-else-if="submittedTextField !== null"
      class="rounded-wolf border border-border bg-background px-3 py-2 text-sm text-foreground"
      data-agent-ui-submitted-text
    >
      <span class="font-medium">{{ submittedTextField.label }}：</span>{{ submittedTextField.value }}
    </div>

    <div v-else-if="block.state === 'READ_ONLY' && (block.interaction_type === 'text_input' || block.interaction_type === 'form')" class="hidden"></div>
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
      v-if="canCancel"
      type="button"
      variant="outline"
      size="sm"
      class="min-h-11"
      :disabled="controlsDisabled"
      @click="cancel"
    >
      取消
    </Button>

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

<style scoped>
.activity-card {
  gap: 0;
  min-width: 0;
  color: hsl(var(--card-foreground));
  overflow-wrap: anywhere;
  font-size: 14px;
  line-height: 22px;
  font-weight: 400;
}

.activity-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid hsl(var(--border));
  padding: 12px 16px;
}

.activity-title {
  margin: 0;
  min-width: 0;
  color: hsl(var(--foreground));
  font-size: 15px;
  font-weight: 600;
  line-height: 22px;
}

.activity-main {
  display: grid;
  gap: 16px;
  min-width: 0;
  padding: 16px 16px 8px;
}

.activity-section,
.activity-change,
.activity-score-body {
  display: grid;
  min-width: 0;
  gap: 8px;
}

.activity-kind,
.activity-kind-editor-head,
.activity-customer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.activity-kind-editor-head {
  justify-content: space-between;
}

.activity-kind-editor-head span:first-child {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.activity-customer,
.activity-kind-editor-head {
  margin: 0;
  color: hsl(var(--muted-foreground));
  font-size: 13px;
  font-weight: 400;
  line-height: 20px;
}

.activity-customer b,
.activity-kind-name,
.activity-time-value {
  color: hsl(var(--foreground));
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
}

.activity-time-status {
  color: hsl(var(--muted-foreground));
  font-size: 13px;
}

.activity-body {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
}

.activity-meta {
  display: grid;
  gap: 8px;
  margin: 4px 0 0;
  border-top: 1px solid hsl(var(--border));
  padding-top: 12px;
}

.activity-meta-row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  column-gap: 12px;
  align-items: start;
}

.activity-meta-row dt {
  margin: 0;
  padding-top: 1px;
  color: hsl(var(--muted-foreground));
  font-size: 13px;
  font-weight: 400;
  line-height: 20px;
}

.activity-meta-row dd {
  margin: 0;
  min-width: 0;
  color: hsl(var(--foreground));
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
}

.activity-link {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  border: 0;
  background: transparent;
  padding: 0;
  color: hsl(var(--primary));
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.activity-caption,
.activity-kind-editor > p,
.activity-actions-hint {
  margin: 0;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
  font-weight: 400;
  line-height: 18px;
}

.activity-kind .activity-caption {
  margin-top: 4px;
}

.activity-pill {
  display: inline-flex;
  align-items: center;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 0 8px;
  font-size: 12px;
  font-weight: 500;
  line-height: 20px;
  max-width: 100%;
}

.activity-pill.is-info,
.activity-card :deep(.is-info) {
  border-color: hsl(var(--primary) / 0.2);
  background: hsl(var(--primary) / 0.08);
  color: hsl(var(--primary));
}

.activity-pill.is-success {
  border-color: hsl(var(--success) / 0.3);
  background: hsl(var(--success) / 0.08);
  color: hsl(var(--foreground));
}

.activity-pill.is-warning {
  border-color: hsl(var(--warning) / 0.4);
  background: hsl(var(--warning) / 0.12);
  color: hsl(var(--foreground));
}

.activity-pill.is-muted {
  border-color: hsl(var(--border));
  background: hsl(var(--muted));
  color: hsl(var(--muted-foreground));
}

.activity-section > .activity-kind-editor {
  margin-top: 4px;
}

.activity-kind-editor {
  margin-top: 8px;
  border: 1px solid hsl(var(--primary) / 0.2);
  border-radius: 12px;
  background: hsl(var(--primary) / 0.08);
  padding: 12px;
}

.activity-kind-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.activity-kind-option {
  min-height: 44px;
  max-width: 100%;
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
  background: hsl(var(--background));
  padding: 8px 12px;
  color: hsl(var(--foreground));
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  cursor: pointer;
}

.activity-kind-option.is-selected {
  border-color: hsl(var(--primary));
  background: hsl(var(--primary));
  color: hsl(var(--primary-foreground));
}

.activity-kind-option:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.activity-kind-editor > p {
  margin-top: 8px;
}

.activity-reference-body,
.activity-reference-section,
.activity-reference-quote {
  display: grid;
  min-width: 0;
  gap: 8px;
}

.activity-reference-body {
  gap: 12px;
}

.activity-reference-heading,
.activity-reference-quote h4,
.activity-reference-quote p {
  margin: 0;
  font-size: 13px;
  line-height: 20px;
}

.activity-reference-heading,
.activity-reference-quote h4 {
  color: hsl(var(--foreground));
  font-weight: 600;
}

.activity-reference-quote p {
  color: hsl(var(--muted-foreground));
}

.activity-reference-notices {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  color: hsl(var(--muted-foreground));
  font-size: 13px;
  line-height: 20px;
  list-style: none;
}

.activity-details {
  min-width: 0;
  border-top: 1px solid hsl(var(--border));
}

.activity-details > summary {
  display: flex;
  align-items: center;
  gap: 8px;
  box-sizing: border-box;
  min-height: 44px;
  padding: 8px 0;
  color: hsl(var(--muted-foreground));
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  list-style: none;
  cursor: pointer;
}

.activity-details > summary::before {
  width: 6px;
  height: 6px;
  flex-shrink: 0;
  border-right: 1px solid currentColor;
  border-bottom: 1px solid currentColor;
  content: '';
  transform: rotate(-45deg);
}

.activity-details[open] > summary::before {
  transform: rotate(45deg);
}

.activity-details > summary::-webkit-details-marker {
  display: none;
}

.activity-details > summary:focus-visible,
.activity-reference-heading:focus,
.activity-link:focus-visible,
.activity-kind-option:focus-visible {
  border-radius: 6px;
  outline: 2px solid hsl(var(--ring));
  outline-offset: 2px;
}

.activity-score-body {
  min-width: 0;
  padding-bottom: 8px;
}

.activity-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid hsl(var(--border));
  padding: 12px 16px;
}

.activity-actions-hint {
  margin-right: auto;
  color: hsl(var(--foreground));
}

.activity-card :deep(.activity-action) {
  height: auto;
  min-height: 44px;
  border-radius: 6px;
  padding-right: 16px;
  padding-left: 16px;
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
}

@media (max-width: 640px) {
  .activity-meta-row {
    grid-template-columns: minmax(0, 1fr);
    row-gap: 2px;
  }

  .activity-meta-row dt {
    padding-top: 0;
  }

  .activity-header {
    align-items: flex-start;
  }
}

.activity-card :deep(.activity-action:disabled) {
  border-color: hsl(var(--border));
  background: hsl(var(--muted));
  color: hsl(var(--muted-foreground));
  opacity: 1;
}
</style>
