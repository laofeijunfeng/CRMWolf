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
  selectedValues.value = submittedChoiceValue.value === null ? [] : [submittedChoiceValue.value]
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
const dispositionProgress = computed(() => (
  dispositionCurrentIndex.value === null
    ? `已处理 ${dispositionTotal.value} / ${dispositionTotal.value}`
    : `待确认 ${dispositionCurrentIndex.value} / ${dispositionTotal.value}`
))
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
const isActivityConfirmation = computed(() => props.block.business_action === 'confirm_activity_write')
const activityFact = (key: string): InteractionBlock['facts'][number] | undefined => props.block.facts.find(fact => fact.key === key)
const activityKindFact = computed(() => activityFact('activity_kind'))
const activityScoreFact = computed(() => activityFact('score'))
const activityScoreReason = computed(() => activityFact('score_reason'))
const activityContext = computed(() => activityFact('change_signal'))
const activityOpportunity = computed(() => activityFact('opportunity'))
const activityEvidence = computed(() => activityFact('context_evidence'))
const activityEvidenceLines = computed(() => (activityEvidence.value?.value ?? '').split('；').map(line => line.trim()).filter(line => line !== ''))
const activityNotices = computed(() => props.block.facts.filter(fact => fact.key.startsWith('context_notice_')))
const activitySourceFolded = computed(() => {
  const fact = activityKindFact.value
  if (fact === undefined || fact.source === null || fact.source === undefined || fact.source === '' || fact.status_label === '未识别 · 需要确认') return ''
  return fact.source
})
const showActivityBasis = computed(() => activitySourceFolded.value !== '' || activityEvidenceLines.value.length > 0)
const activityScoreNumber = computed(() => (activityScoreFact.value?.value ?? '').split('/')[0]?.trim() ?? '')
const activityPassed = computed(() => {
  const score = Number(activityScoreNumber.value)
  return Number.isFinite(score) && score >= 60
})
const activityHistory = computed(() => props.block.state === 'READ_ONLY')
const activityWaitingLabel = computed(() => {
  if (activityHistory.value) return '历史只读'
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
  if (label.includes('高置信度') || label.includes('词表兜底')) return 'is-success'
  return 'is-info'
})

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
    class="agent-ui-interaction grid gap-3 rounded-wolf-surface border border-[#bfdbfe] bg-white p-3"
    :aria-labelledby="`${block.id}-prompt`"
    :aria-busy="submitting"
  >
    <header class="flex items-start justify-between gap-3 border-b border-[#bfdbfe] bg-[#eff6ff] -m-3 mb-0 rounded-t-wolf-surface px-3 py-3">
      <div>
        <h4 class="m-0 text-[13px] font-semibold text-foreground">历史跟进任务</h4>
        <p class="m-0 mt-0.5 text-xs text-muted-foreground">该客户 · 你当前可操作的未完成任务</p>
      </div>
      <span class="shrink-0 text-xs font-semibold text-[#1d4ed8]">{{ dispositionProgress }}</span>
    </header>
    <p :id="`${block.id}-prompt`" class="m-0 text-[13px] text-[#334155]">{{ block.prompt }}</p>
    <ol class="m-0 grid list-none gap-0 p-0">
      <li
        v-for="(item, index) in dispositionItems"
        :key="item.item_id"
        class="grid gap-2 border-t border-border py-3"
        :class="item.state === 'current' ? 'border-l-2 border-l-[#2563eb] pl-3' : ''"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="m-0 text-sm font-semibold text-foreground">{{ index + 1 }} {{ item.title }}</p>
            <p v-if="item.owner_line" class="m-0 mt-0.5 text-xs text-muted-foreground">{{ item.owner_line }}</p>
          </div>
          <span class="shrink-0 text-xs text-[#1d4ed8]">{{ item.state === 'current' ? '当前待确认' : item.state === 'waiting' ? '待逐条确认' : item.result_title }}</span>
        </div>
        <div v-if="item.related" class="flex flex-wrap items-center gap-2" @mouseenter="evidenceOpenId = item.item_id" @mouseleave="evidenceOpenId = null">
          <span class="rounded-full border border-[#bfdbfe] bg-[#eff6ff] px-2 py-0.5 text-xs text-[#1d4ed8]">与本次跟进相关</span>
          <button
            type="button"
            class="min-h-11 px-1 text-xs text-[#1d4ed8] underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2563eb]"
            :aria-expanded="evidenceOpenId === item.item_id"
            :aria-describedby="`${block.id}-evidence-${item.item_id}`"
            @click="toggleEvidence(item.item_id)"
            @focus="evidenceOpenId = item.item_id"
          >
            {{ evidenceOpenId === item.item_id ? '依据已聚焦' : '查看依据' }}
          </button>
          <div
            v-if="evidenceOpenId === item.item_id"
            :id="`${block.id}-evidence-${item.item_id}`"
            role="tooltip"
            class="basis-full rounded-wolf border border-border bg-white p-3 text-xs leading-5"
          >
            <strong>关联依据</strong>
            <p v-if="item.evidence_quote" class="m-0 mt-1">本次跟进：“{{ item.evidence_quote }}”</p>
            <p v-if="item.evidence_reason" class="m-0 mt-1">{{ item.evidence_reason }}</p>
            <p class="m-0 mt-2 text-muted-foreground">关联仅用于提示，不代表任务已完成；仍由你逐条决定。</p>
          </div>
        </div>
        <div v-if="item.state === 'current' && isActive" class="grid gap-2 sm:grid-cols-3">
          <button
            v-for="option in block.options"
            :key="option.value"
            type="button"
            class="grid min-h-[52px] rounded-wolf border px-3 py-2 text-left"
            :class="option.value.endsWith(':complete') ? 'border-[#1d4ed8] bg-[#2563eb] text-white' : 'border-border bg-white'"
            :disabled="controlsDisabled || option.disabled"
            @click="handleOptionClick(option.value)"
          >
            <span class="text-sm font-semibold">{{ submitting && optionSelected(option.value) ? `${option.label}处理中…` : option.label }}</span>
            <small v-if="option.description" class="text-xs opacity-80">{{ option.description }}</small>
          </button>
        </div>
        <p v-if="item.state === 'current' && isActive" class="m-0 text-xs text-muted-foreground">只处理这一条，提交后继续下一条。</p>
        <p v-else-if="item.result_message" class="m-0 text-xs" :class="item.state === 'failed' ? 'text-[#b91c1c]' : item.state === 'unknown' ? 'text-[#92400e]' : item.state === 'complete' ? 'text-[#047857]' : 'text-muted-foreground'">{{ item.result_message }}</p>
      </li>
    </ol>
    <p class="m-0 text-xs text-muted-foreground">只有选择“已完成”才会更新这一条任务。“不管了”仅跳过本次，不代表与本次跟进无关。</p>
  </section>

  <section
    v-else
    ref="interactionRef"
    class="agent-ui-interaction grid rounded-wolf-surface p-3"
    :class="isActivityConfirmation
      ? (block.state === 'READ_ONLY' ? 'activity-card gap-0 overflow-hidden border border-dashed border-[#cbd5e1] bg-white p-0' : 'activity-card gap-0 overflow-hidden border border-[#e2e8f0] bg-white p-0')
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
        <p v-if="activityHistory" class="activity-note">仅回看当时冻结的内容，不代表当前客户状态。</p>
        <section class="activity-section">
          <div v-if="activityScoreFact" class="activity-section-head">
            <span class="activity-pill is-success">{{ activityPassed ? `质量通过 · ${activityScoreNumber} 分` : activityScoreFact.value }}</span>
          </div>
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
            <div v-if="activityFact('next_action')" class="activity-meta-row">
              <dt>下一步</dt>
              <dd>{{ activityFact('next_action')?.value }}</dd>
            </div>
            <div v-if="activityFact('customer_commitment')" class="activity-meta-row">
              <dt>客户承诺</dt>
              <dd>{{ activityFact('customer_commitment')?.value }}</dd>
            </div>
            <div v-if="activityFact('next_follow_time')" class="activity-meta-row">
              <dt>跟进时间</dt>
              <dd>{{ activityFact('next_follow_time')?.value }}</dd>
            </div>
            <div v-if="activityKindFact" class="activity-meta-row">
              <dt>活动类型</dt>
              <dd>
                <div class="activity-kind">
                  <span class="activity-kind-name">{{ activityKindFact.value }}</span>
                  <span v-if="activityKindFact.status_label" class="activity-pill" :class="activityKindPillClass">{{ activityKindFact.status_label }}</span>
                  <button v-if="(activityKindFact.options?.length ?? 0) > 0 && activityKindFact.status_label !== '未识别 · 需要确认'" type="button" class="activity-link" @click="kindEditorOpen = !kindEditorOpen">{{ kindEditorOpen ? '收起类型选项' : '修改类型' }}</button>
                </div>
                <p v-if="activityKindFact.source && activityKindFact.status_label === '未识别 · 需要确认'" class="activity-caption"><span>为什么需要选择：</span>{{ activityKindFact.source }}</p>
              </dd>
            </div>
          </dl>
          <div v-if="activityKindFact && kindOptionsVisible(activityKindFact)" class="activity-kind-editor">
            <div class="activity-kind-editor-head">
              <span>{{ activityKindFact.status_label === '未识别 · 需要确认' ? '选择活动类型' : '修改活动类型' }}</span>
              <span>{{ activityKindFact.status_label === '未识别 · 需要确认' ? '选择后才可确认' : '不会重新生成正文' }}</span>
            </div>
            <div class="activity-kind-options">
              <button v-for="option in activityKindFact.options ?? []" :key="option.value" type="button" class="activity-kind-option" :class="option.label === activityKindFact.value ? 'is-selected' : ''" :disabled="controlsDisabled || option.disabled" @click="reviseActivityKind(option.value)">{{ option.label }}</button>
            </div>
            <p>只修改“活动类型”字段，不改写活动标题、摘要或下一步。</p>
          </div>
        </section>
        <section v-if="activityContext" class="activity-context">
          <div class="activity-section-head">
            <div class="activity-context-title">
              <h3>客户上下文判断</h3>
              <span>AI 辅助</span>
            </div>
            <span class="activity-pill is-warning">{{ activityContext.value }}</span>
          </div>
          <p v-if="activityContext.source" class="activity-body">{{ activityContext.source }}</p>
          <p v-if="activityOpportunity" class="activity-inline"><span>关联商机</span><b>{{ activityOpportunity.value }}</b></p>
          <p class="activity-caption">不写入活动正文，不自动修改商机阶段。</p>
        </section>
        <ul v-if="activityNotices.length > 0" class="activity-notices">
          <li v-for="notice in activityNotices" :key="notice.key">{{ notice.value }}</li>
        </ul>
        <details v-if="showActivityBasis" class="activity-details activity-basis">
          <summary>查看依据</summary>
          <div>
            <p v-if="activitySourceFolded">识别来源：{{ activitySourceFolded }}</p>
            <p v-for="line in activityEvidenceLines" :key="line">{{ line }}</p>
          </div>
        </details>
        <details v-if="activityScoreReason" class="activity-details activity-score">
          <summary>查看评分依据 · 内容质量</summary>
          <div class="activity-score-body">
            <strong>{{ activityScoreFact?.value }} · {{ activityPassed ? '通过写入质量门禁' : '未通过写入质量门禁' }}</strong>
            <p>{{ activityScoreReason.value }}</p>
            <p class="activity-caption">质量通过不表示客户进展良好，也不替代上下文判断。</p>
          </div>
        </details>
      </div>
    </template>
    <p v-if="!isActivityConfirmation && block.state === 'READ_ONLY'" class="m-0 inline-flex w-fit items-center rounded-full border border-border bg-muted px-2 py-1 text-[11px] text-muted-foreground">历史消息 · 已回放</p>
    <header v-if="!isActivityConfirmation" class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 items-start gap-2">
        <span class="grid size-5 shrink-0 place-items-center rounded-wolf-sm bg-[#dbeafe] text-[11px] font-semibold text-[#1d4ed8]" aria-hidden="true">?</span>
        <p :id="`${block.id}-prompt`" class="m-0 text-[13px] font-semibold leading-5 text-foreground">{{ block.prompt }}</p>
      </div>
      <span class="shrink-0 rounded-full border border-[#bfdbfe] bg-[#eff6ff] px-2 py-0.5 text-[11px] font-medium text-[#1d4ed8]">{{ stateLabel }}</span>
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
                  {{ kindEditorOpen ? '收起类型选项' : '修改类型' }}
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
      v-if="submittedChoiceValue !== null"
      class="rounded-wolf border border-border bg-background px-3 py-2 text-sm text-foreground"
      data-agent-ui-submitted-choice
    >
      <span class="font-medium">已选择：</span>{{ submittedChoiceOption?.label ?? submittedChoiceValue }}
    </div>

    <template v-else-if="isActive && (block.interaction_type === 'choice' || block.interaction_type === 'confirmation')">
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
      <Button
        v-for="(option, index) in (isActivityConfirmation ? activityActionOptions : block.options)"
        :key="option.value"
        type="button"
        :variant="block.interaction_type === 'confirmation' && option.value === 'confirm' ? 'default' : 'outline'"
        class="min-h-11 h-auto justify-start gap-0.5 px-3 py-2 text-left"
        :class="[
          block.interaction_type === 'confirmation' ? '' : 'grid w-full bg-white',
          optionSelected(option.value) ? 'border-primary bg-accent text-accent-foreground' : '',
          isActivityConfirmation ? 'activity-action' : '', isActivityConfirmation && option.disabled ? 'border-[#cbd5e1] bg-[#e2e8f0] text-[#94a3b8] opacity-100' : ''
        ]"
        :aria-pressed="optionSelected(option.value)"
        :disabled="controlsDisabled || option.disabled"
        :data-agent-ui-error-focus="selectionError !== null && index === 0 ? 'true' : undefined"
        @click="handleOptionClick(option.value)"
      >
        <span>{{ submitting && optionSelected(option.value) ? `${option.label}处理中…` : option.label }}</span>
        <small v-if="option.description && block.interaction_type !== 'confirmation'" class="text-xs text-muted-foreground">
          {{ option.description }}
        </small>
      </Button>
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
    <p v-else-if="block.state === 'READ_ONLY' && (block.interaction_type === 'choice' || block.interaction_type === 'confirmation')" :class="isActivityConfirmation ? 'activity-history-note' : 'm-0 text-[11px] text-muted-foreground'">{{ isActivityConfirmation ? '历史交互只读，不可再次提交。' : '历史交互不再提供可再次提交的确认按钮。' }}</p>
    <div v-else-if="!isActive && (block.interaction_type === 'choice' || block.interaction_type === 'confirmation')" class="hidden"></div>

    <div
      v-else-if="submittedTextField !== null"
      class="rounded-wolf border border-border bg-background px-3 py-2 text-sm text-foreground"
      data-agent-ui-submitted-text
    >
      <span class="font-medium">{{ submittedTextField.label }}：</span>{{ submittedTextField.value }}
    </div>

    <p v-else-if="block.state === 'READ_ONLY' && (block.interaction_type === 'text_input' || block.interaction_type === 'form')" class="m-0 text-[11px] text-muted-foreground">历史交互不再提供可再次提交的确认按钮。</p>
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
  color: #020817;
  font-size: 14px;
  line-height: 22px;
  font-weight: 400;
}

.activity-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #edf2f7;
  padding: 12px 16px;
}

.activity-title {
  margin: 0;
  color: #020817;
  font-size: 15px;
  font-weight: 600;
  line-height: 22px;
}

.activity-main {
  display: grid;
  gap: 16px;
  padding: 16px;
}

.activity-note,
.activity-history-note {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  font-weight: 400;
  line-height: 18px;
}

.activity-note {
  border-radius: 8px;
  background: #f8fafc;
  padding: 8px 12px;
}

.activity-history-note {
  border-top: 1px solid #edf2f7;
  padding: 12px 16px;
}

.activity-section,
.activity-context,
.activity-score-body {
  display: grid;
  gap: 8px;
}

.activity-section-head,
.activity-kind,
.activity-kind-editor-head,
.activity-customer,
.activity-inline,
.activity-context-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.activity-section-head,
.activity-kind-editor-head {
  justify-content: space-between;
}

.activity-section-head > .activity-pill {
  margin-left: auto;
}

.activity-kicker,
.activity-context-title h3,
.activity-kind-editor-head span:first-child {
  margin: 0;
  color: #334155;
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.activity-kicker {
  color: #1d4ed8;
}

.activity-customer,
.activity-inline,
.activity-context-title span,
.activity-kind-editor-head {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  font-weight: 400;
  line-height: 20px;
}

.activity-customer b,
.activity-kind-name {
  color: #020817;
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
}

.activity-inline b {
  color: #334155;
  font-weight: 500;
}

.activity-body {
  margin: 0;
  color: #334155;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
}

.activity-meta {
  display: grid;
  gap: 8px;
  margin: 4px 0 0;
  border-top: 1px solid #edf2f7;
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
  color: #64748b;
  font-size: 13px;
  font-weight: 400;
  line-height: 20px;
}

.activity-meta-row dd {
  margin: 0;
  min-width: 0;
  color: #334155;
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
  color: #1d4ed8;
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
  color: #64748b;
  font-size: 12px;
  font-weight: 400;
  line-height: 18px;
}

.activity-kind .activity-caption {
  margin-top: 4px;
}

.activity-caption span {
  color: #475569;
  font-weight: 600;
}

.activity-pill {
  display: inline-flex;
  align-items: center;
  border: 1px solid transparent;
  border-radius: 5px;
  padding: 0 8px;
  font-size: 12px;
  font-weight: 500;
  line-height: 20px;
  white-space: nowrap;
}

.activity-pill.is-info,
.activity-card :deep(.is-info) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: #1d4ed8;
}

.activity-pill.is-success {
  border-color: #d1fae5;
  background: #ecfdf5;
  color: #047857;
}

.activity-pill.is-warning {
  border-color: #fde68a;
  background: #fffbeb;
  color: #b45309;
}

.activity-pill.is-muted {
  border-color: #e2e8f0;
  background: #f1f5f9;
  color: #64748b;
}

.activity-section > .activity-kind-editor {
  margin-top: 4px;
}

.activity-kind-editor {
  margin-top: 8px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #eff6ff;
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
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
  padding: 4px 10px;
  color: #334155;
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  cursor: pointer;
}

.activity-kind-option.is-selected {
  border-color: #2563eb;
  background: #2563eb;
  color: #fff;
}

.activity-kind-option:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.activity-kind-editor > p {
  margin-top: 8px;
}

.activity-context {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  padding: 12px;
}

.activity-notices {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.activity-notices li {
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: #fffbeb;
  padding: 10px 12px;
  color: #92400e;
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
}

.activity-details {
  border-top: 1px solid #e2e8f0;
  padding-top: 4px;
}

.activity-score {
  border-top-color: #edf2f7;
}

.activity-details summary {
  display: flex;
  align-items: center;
  min-height: 44px;
  color: #475569;
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  list-style: none;
  cursor: pointer;
}

.activity-details summary::-webkit-details-marker {
  display: none;
}

.activity-details > div > p,
.activity-score-body > p {
  margin: 0;
  color: #475569;
  font-size: 13px;
  font-weight: 400;
  line-height: 20px;
}

.activity-details > div > p {
  border-bottom: 1px solid #e2e8f0;
  padding: 8px 0;
}

.activity-details > div > p:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.activity-score-body {
  margin-top: 4px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  padding: 12px;
}

.activity-score-body strong {
  color: #334155;
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
}

.activity-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid #edf2f7;
  padding: 12px 16px;
}

.activity-actions-hint {
  margin-right: auto;
  color: #b45309;
}

.activity-card :deep(.activity-action) {
  height: auto;
  min-height: 44px;
  border-radius: 8px;
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

  .activity-header,
  .activity-section-head {
    align-items: flex-start;
  }
}

.activity-card :deep(.activity-action:disabled) {
  border-color: #cbd5e1;
  background: #e2e8f0;
  color: #94a3b8;
  opacity: 1;
}
</style>
