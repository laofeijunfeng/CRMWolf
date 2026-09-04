import { z } from 'zod'

import { JsonValueSchema } from './common'

export const InteractionOptionSchema = z.object({
  value: z.string().min(1).max(500),
  label: z.string().min(1).max(200),
  description: z.string().max(1000).nullable().optional(),
  disabled: z.boolean().default(false)
}).strict()

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
  options: z.array(InteractionOptionSchema).max(50).default([])
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

export const InteractionBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('interaction'),
  interaction_id: z.string().min(1).max(128),
  interaction_type: z.enum(['choice', 'form', 'confirmation', 'text_input']),
  presentation: z.literal('COMPACT_TASK_COMPLETION').nullable().optional(),
  state: z.enum(['ACTIVE', 'SUBMITTED', 'EXPIRED', 'CANCELLED', 'READ_ONLY']),
  prompt: z.string().min(1).max(10000),
  fields: z.array(InteractionFieldSchema).max(20).default([]),
  options: z.array(InteractionOptionSchema).max(50).default([]),
  selection_mode: z.enum(['single', 'multiple']).nullable().optional(),
  min_selections: z.number().int().min(0).max(50).nullable().optional(),
  max_selections: z.number().int().min(1).max(50).nullable().optional(),
  allow_blank: z.boolean().nullable().optional(),
  submit_on_select: z.boolean().optional(),
  submit_label: z.string().min(1).max(200).default('提交'),
  submit_action_id: z.string().min(1).max(128).nullable(),
  submitted_values: z.record(JsonValueSchema).nullable().optional()
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
    block.options.length !== 1
  )) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'compact task completion requires one submit-on-select choice',
      path: ['presentation']
    })
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
}

export const InteractionBlockSchema = InteractionBlockObjectSchema.superRefine(validateInteractionBlock)
