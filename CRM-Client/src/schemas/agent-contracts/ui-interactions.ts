import { z } from 'zod'

import { EntityRefSchema, JsonValueSchema } from './common'

export const InteractionOptionSchema = z.object({
  value: z.string().min(1).max(500),
  label: z.string().min(1).max(200),
  description: z.string().max(1000).nullable().optional(),
  group: z.string().max(40).nullable().optional(),
  disabled: z.boolean().default(false),
  depends_on_value: z.string().min(1).max(500).nullable().optional(),
}).strict()

/** Server-issued direct-create forms (CRM-165); they can also be parked in 「待补充」. */
export const ENTITY_FORM_ACTIONS: readonly string[] = [
  'create_contact', 'create_invoice_title', 'create_deployment', 'create_customer', 'create_opportunity'
]
const CANCELLABLE_FORM_ACTIONS: readonly string[] = ['create_opportunity_proposal', 'edit_confirmation', ...ENTITY_FORM_ACTIONS]

export const InteractionFieldSchema = z.object({
  key: z.string().min(1).max(128).regex(/^[a-z][a-z0-9_]*$/),
  label: z.string().min(1).max(200),
  field_type: z.enum(['text', 'textarea', 'number', 'date', 'datetime', 'select', 'multi_select', 'boolean']),
  required: z.boolean().default(false),
  placeholder: z.string().max(200).nullable().optional(),
  default_value: JsonValueSchema.default(null),
  min_length: z.number().int().min(0).max(10000).nullable().optional(),
  max_length: z.number().int().min(1).max(10000).nullable().optional(),
  minimum: z.number().nullable().optional(),
  maximum: z.number().nullable().optional(),
  options: z.array(InteractionOptionSchema).max(50).default([]),
  source_label: z.string().max(40).nullable().optional(),
  depends_on_key: z.string().max(128).regex(/^[a-z][a-z0-9_]*$/).nullable().optional(),
  error_message: z.string().min(1).max(500).nullable().optional(),
  suggestions: z.array(z.string().min(1).max(200)).max(8).default([]),
}).strict().superRefine((field, context) => {
  if (field.min_length != null && field.max_length != null && field.min_length > field.max_length) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'min_length cannot exceed max_length', path: ['min_length'] })
  }
  if (field.minimum != null && field.maximum != null && field.minimum > field.maximum) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'minimum cannot exceed maximum', path: ['minimum'] })
  }
  const isSelect = field.field_type === 'select' || field.field_type === 'multi_select'
  if (isSelect && field.options.length === 0) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'select fields require options', path: ['options'] })
  } else if (!isSelect && field.options.length > 0) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'options are only valid for select fields', path: ['options'] })
  }
  if (field.depends_on_key != null && !isSelect) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'depends_on_key is only valid for select fields', path: ['depends_on_key'] })
  }
  if (field.depends_on_key == null && field.options.some(option => option.depends_on_value != null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'dependent options require depends_on_key', path: ['depends_on_key'] })
  }
  if (new Set(field.options.map(option => option.value)).size !== field.options.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'interaction field option values must be unique', path: ['options'] })
  }
  const isText = field.field_type === 'text' || field.field_type === 'textarea'
  if (isText && (field.min_length == null || field.max_length == null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'text fields require min_length and max_length' })
  }
  if (field.field_type === 'number' && (field.minimum == null || field.maximum == null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'number fields require minimum and maximum' })
  }
})

export const InteractionConfirmationFactSchema = z.object({
  key: z.string().min(1).max(128).regex(/^[a-z][a-z0-9_]*$/),
  label: z.string().min(1).max(200),
  value: z.string().min(1).max(10000),
  group: z.enum(['write', 'activity_kind', 'context', 'score']).optional(),
  status_label: z.string().max(40).nullable().optional(),
  source: z.string().max(1000).nullable().optional(),
  options: z.array(InteractionOptionSchema).max(10).default([])
}).strict()

export const OpenFollowUpDispositionCardItemSchema = z.object({
  item_id: z.string().min(1).max(32),
  title: z.string().min(1).max(255),
  owner_line: z.string().max(300).nullable().optional(),
  related: z.boolean().default(false),
  evidence_quote: z.string().max(255).nullable().optional(),
  evidence_reason: z.string().max(500).nullable().optional(),
  state: z.enum(['current', 'waiting', 'complete', 'hold', 'skip', 'failed', 'unknown']),
  result_title: z.string().max(80).nullable().optional(),
  result_message: z.string().max(500).nullable().optional()
}).strict()

const SecondaryActionSchema = InteractionOptionSchema.extend({ value: z.enum(['request_edit', 'suppress_week']) })
const CancelReasonSchema = InteractionOptionSchema.extend({
  value: z.enum(['wrong_customer', 'wrong_content', 'should_not_record', 'other']),
})

export const InteractionBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('interaction'),
  interaction_id: z.string().min(1).max(128),
  interaction_type: z.enum(['choice', 'form', 'confirmation', 'text_input']),
  business_action: z.string().min(1).max(128).nullable().optional(),
  presentation: z.enum(['COMPACT_TASK_COMPLETION', 'OPEN_FOLLOW_UP_DISPOSITION']).nullable().optional(),
  disposition_items: z.array(OpenFollowUpDispositionCardItemSchema).max(100).default([]),
  disposition_visible_count: z.number().int().min(1).max(100).nullable().optional(),
  state: z.enum(['ACTIVE', 'SUBMITTED', 'EXPIRED', 'CANCELLED', 'READ_ONLY']),
  prompt: z.string().min(1).max(10000),
  subject: EntityRefSchema.nullable().optional(),
  hint: z.string().max(400).nullable().optional(),
  fields: z.array(InteractionFieldSchema).max(20).default([]),
  facts: z.array(InteractionConfirmationFactSchema).max(20).default([]),
  options: z.array(InteractionOptionSchema).max(100).default([]),
  selection_mode: z.enum(['single', 'multiple']).nullable().optional(),
  min_selections: z.number().int().min(0).max(100).nullable().optional(),
  max_selections: z.number().int().min(1).max(100).nullable().optional(),
  allow_blank: z.boolean().nullable().optional(),
  allow_cancel: z.boolean().default(false),
  submit_on_select: z.boolean().optional(),
  submit_label: z.string().min(1).max(200).default('提交'),
  submit_action_id: z.string().min(1).max(128).nullable(),
  submitted_values: z.record(JsonValueSchema).nullable().optional(),
  secondary_action: SecondaryActionSchema.nullable().optional(),
  cancel_reasons: z.array(CancelReasonSchema).max(4).optional(),
}).strict()


export function validateInteractionBlock(
  block: z.infer<typeof InteractionBlockObjectSchema>,
  context: z.RefinementCtx
): void {
  if (block.state === 'ACTIVE' && block.submit_action_id == null) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'active interaction requires submit_action_id', path: ['submit_action_id'] })
  } else if (block.state !== 'ACTIVE' && block.submit_action_id != null) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'non-active interaction cannot expose submit_action_id', path: ['submit_action_id'] })
  }
  if (block.allow_cancel && !(
    (block.business_action === 'provide_follow_up_content' && ['text_input', 'form'].includes(block.interaction_type)) ||
    (block.interaction_type === 'form' && CANCELLABLE_FORM_ACTIONS.includes(block.business_action ?? ''))
  )) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'cancellation is only available for follow-up content input and assistant forms', path: ['allow_cancel'] })
  }
  if (new Set(block.options.map(option => option.value)).size !== block.options.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'interaction option values must be unique', path: ['options'] })
  }
  if (block.min_selections != null && block.max_selections != null && block.min_selections > block.max_selections) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'min_selections cannot exceed max_selections', path: ['min_selections'] })
  }
  if (block.presentation === 'COMPACT_TASK_COMPLETION' && (
    block.interaction_type !== 'choice' ||
    block.selection_mode !== 'single' ||
    block.min_selections !== 1 ||
    block.max_selections !== 1 ||
    block.submit_on_select !== true ||
    block.options.length !== 1 ||
    block.disposition_items.length > 0
  )) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'compact task completion requires one submit-on-select choice',
      path: ['presentation']
    })
  }
  if (block.presentation === 'OPEN_FOLLOW_UP_DISPOSITION') {
    const archivedLegacy = block.state !== 'ACTIVE' && block.selection_mode === 'single' &&
      block.min_selections === 1 && block.max_selections === 1 && block.options.length <= 50
    const batch = block.selection_mode === 'multiple' && block.min_selections === 0 &&
      block.max_selections === block.options.length && block.options.length === block.disposition_items.length &&
      block.options.every((option, index) => option.value === block.disposition_items[index]?.item_id)
    if (block.interaction_type !== 'choice' || block.submit_on_select === true ||
      block.disposition_items.length === 0 || (!batch && !archivedLegacy)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'open follow-up disposition requires one optional checkbox per frozen task',
        path: ['presentation']
      })
    }
  } else {
    if (block.disposition_items.length > 0 || block.disposition_visible_count != null) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'disposition items and link require the open follow-up presentation', path: ['presentation'] })
    }
    if (block.options.length > 50 || (block.max_selections ?? 0) > 50) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'generic interactions support at most 50 options', path: ['options'] })
    }
  }

  if (block.interaction_type === 'choice') {
    const minSelections = block.min_selections
    const maxSelections = block.max_selections
    const hasChoiceShape = block.fields.length === 0 && block.options.length > 0 && block.selection_mode != null &&
      minSelections != null && maxSelections != null && block.allow_blank == null
    if (!hasChoiceShape || maxSelections == null) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'choice requires options, selection mode, and bounds only' })
    } else {
      if (maxSelections > block.options.length) {
        context.addIssue({ code: z.ZodIssueCode.custom, message: 'max_selections cannot exceed option count', path: ['max_selections'] })
      }
      if (block.selection_mode === 'single' && maxSelections !== 1) {
        context.addIssue({ code: z.ZodIssueCode.custom, message: 'single choice requires max_selections=1', path: ['max_selections'] })
      }
    }
  } else if (block.interaction_type === 'form') {
    if (block.fields.length === 0 || block.options.length > 0 || block.selection_mode != null ||
      block.min_selections != null || block.max_selections != null || block.allow_blank != null) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'form requires fields and no top-level choice constraints' })
    }
  } else if (block.interaction_type === 'confirmation') {
    const values = new Set(block.options.map(option => option.value))
    if (block.fields.length > 0 || block.options.length !== 2 || block.selection_mode !== 'single' ||
      values.size !== 2 || !values.has('confirm') || !values.has('cancel') || block.min_selections != null ||
      block.max_selections != null || block.allow_blank != null) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'confirmation requires exactly one confirm and one cancel option' })
    }
  } else {
    const field = block.fields[0]
    const hasBoundedTextField = block.fields.length === 1 && field != null &&
      (field.field_type === 'text' || field.field_type === 'textarea') &&
      field.min_length != null && field.max_length != null
    if (!hasBoundedTextField || block.options.length > 0 || block.selection_mode != null ||
      block.min_selections != null || block.max_selections != null || block.allow_blank == null) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'text_input requires one bounded text field and allow_blank' })
    } else if (!block.allow_blank && field.min_length === 0) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'non-blank text_input requires min_length greater than zero' })
    }
  }

  if (block.facts.length > 0 && block.interaction_type !== 'confirmation') {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'facts are only valid for confirmation interactions',
      path: ['facts']
    })
  }

  if (block.submit_on_select === true) {
    const validSubmitShape = block.interaction_type === 'confirmation'
      ? block.selection_mode === 'single'
      : block.interaction_type === 'choice'
        && block.selection_mode === 'single'
        && block.min_selections === 1
        && block.max_selections === 1
    if (!validSubmitShape) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'submit_on_select requires an exact single-choice interaction',
        path: ['submit_on_select']
      })
    }
  }
  if (block.secondary_action != null) {
    const expected = block.interaction_type === 'confirmation' ? 'request_edit'
      : block.presentation === 'OPEN_FOLLOW_UP_DISPOSITION' ? 'suppress_week' : null
    if (block.state !== 'ACTIVE' || block.secondary_action.value !== expected) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'secondary_action is limited to confirmation edit and disposition weekly suppression', path: ['secondary_action'] })
    }
  }
  if (block.cancel_reasons != null && block.cancel_reasons.length > 0 && (block.state !== 'ACTIVE' || block.interaction_type !== 'confirmation' ||
    new Set(block.cancel_reasons.map(reason => reason.value)).size !== block.cancel_reasons.length)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'cancel_reasons are unique closed reasons on an active confirmation', path: ['cancel_reasons'] })
  }
}

export const InteractionBlockSchema = InteractionBlockObjectSchema.superRefine(validateInteractionBlock)
