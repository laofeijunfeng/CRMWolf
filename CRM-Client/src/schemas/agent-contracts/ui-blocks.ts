import { z } from 'zod'

import { CRMResourceSchema, EntityRefSchema } from './common'
import { AgentErrorCodeSchema, AgentUIActionSchema, AgentUIValueSchema } from './ui-actions'
import { InteractionBlockObjectSchema, validateInteractionBlock } from './ui-interactions'
import { containsRawHtml, restrictedMarkdownError } from './markdown'

export const EntityFieldSchema = z.object({
  key: z.string().min(1).max(128),
  label: z.string().min(1).max(200),
  value: AgentUIValueSchema
}).strict()

export const EntityListItemSchema = z.object({
  entity_ref: EntityRefSchema
}).strict()

const TextBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('text'),
  format: z.enum(['plain', 'markdown']),
  text: z.string().max(10000)
}).strict()

const EntityListBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('entity_list'),
  entity_type: CRMResourceSchema,
  items: z.array(EntityListItemSchema).max(100).default([]),
  total: z.number().int().nonnegative(),
  result_set_id: z.string().min(1).max(128).nullable().optional()
}).strict()

export const EntityCardSectionSchema = z.object({
  key: z.string().min(1).max(128),
  title: z.string().max(200).nullable().optional(),
  fields: z.array(EntityFieldSchema).max(12).default([])
}).strict()

const EntityCardBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('entity_card'),
  entity_type: CRMResourceSchema,
  ref_id: z.string().min(1).max(128),
  title: z.string().min(1).max(200),
  sections: z.array(EntityCardSectionSchema).max(8).default([]),
  actions: z.array(AgentUIActionSchema).max(5).default([])
}).strict()

export const TableColumnSchema = z.object({
  key: z.string().min(1).max(128),
  label: z.string().min(1).max(200),
  align: z.enum(['left', 'center', 'right']).default('left')
}).strict()

export const TableCellSchema = z.object({
  column_key: z.string().min(1).max(128),
  value: AgentUIValueSchema
}).strict()

export const TableRowSchema = z.object({
  id: z.string().min(1).max(128),
  cells: z.array(TableCellSchema).max(20).default([])
}).strict().superRefine((row, context) => {
  const keys = row.cells.map(cell => cell.column_key)
  if (new Set(keys).size !== keys.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'table row column_key values must be unique', path: ['cells'] })
  }
})

const TableBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('table'),
  columns: z.array(TableColumnSchema).min(1).max(20),
  rows: z.array(TableRowSchema).max(100).default([]),
  caption: z.string().max(200).nullable().optional()
}).strict()

export const TimelineItemSchema = z.object({
  id: z.string().min(1).max(128),
  occurred_at: z.string().min(1).max(64),
  title: z.string().min(1).max(200),
  description: z.string().max(10000).nullable().optional(),
  actor: z.string().max(200).nullable().optional(),
  status: z.string().max(128).nullable().optional()
}).strict()

const TimelineBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('timeline'),
  items: z.array(TimelineItemSchema).max(100).default([])
}).strict()

export const ProcessItemSchema = z.object({
  key: z.string().min(1).max(128).regex(/^[a-z][a-z0-9_]*$/),
  title: z.string().min(1).max(200),
  status: z.enum(['PENDING', 'RUNNING', 'COMPLETED', 'WAITING', 'FAILED', 'CANCELLED']),
  description: z.string().max(2000).nullable().optional()
}).strict()

const ProcessBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('process'),
  title: z.string().min(1).max(200),
  items: z.array(ProcessItemSchema).min(1).max(20)
}).strict()

export const AgentUIMetricSchema = z.object({
  key: z.string().min(1).max(128),
  label: z.string().min(1).max(200),
  value: AgentUIValueSchema,
  change: AgentUIValueSchema.nullable().optional()
}).strict()

const MetricGroupBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('metric_group'),
  metrics: z.array(AgentUIMetricSchema).min(1).max(12)
}).strict()

const NoticeBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('notice'),
  tone: z.enum(['info', 'success', 'warning']),
  title: z.string().max(200).nullable().optional(),
  text: z.string().min(1).max(10000)
}).strict()

const ErrorBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('error'),
  code: AgentErrorCodeSchema,
  title: z.string().min(1).max(200),
  message: z.string().min(1).max(10000),
  retryable: z.boolean(),
  trace_id: z.string().min(1).max(128).nullable().optional()
}).strict()

const ActionResultBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('action_result'),
  action_id: z.string().min(1).max(128),
  status: z.enum(['SUCCESS', 'FAILED', 'CANCELLED']),
  title: z.string().min(1).max(200),
  message: z.string().min(1).max(10000),
  entity_ref: EntityRefSchema.nullable().optional()
}).strict()

const PaginationBlockObjectSchema = z.object({
  id: z.string().min(1).max(128),
  type: z.literal('pagination'),
  result_set_id: z.string().min(1).max(128),
  range_start: z.number().int().min(1),
  range_end: z.number().int().min(1),
  total: z.number().int().nonnegative().nullable().optional(),
  previous_action_id: z.string().min(1).max(128).nullable().optional(),
  next_action_id: z.string().min(1).max(128).nullable().optional()
}).strict()

const RawAgentUIBlockSchema = z.discriminatedUnion('type', [
  TextBlockObjectSchema,
  EntityListBlockObjectSchema,
  EntityCardBlockObjectSchema,
  TableBlockObjectSchema,
  TimelineBlockObjectSchema,
  ProcessBlockObjectSchema,
  MetricGroupBlockObjectSchema,
  NoticeBlockObjectSchema,
  ErrorBlockObjectSchema,
  InteractionBlockObjectSchema,
  ActionResultBlockObjectSchema,
  PaginationBlockObjectSchema
])

export const AgentUIBlockSchema = RawAgentUIBlockSchema.superRefine((block, context) => {
  if (block.type === 'text') {
    const markdownError = block.format === 'markdown'
      ? restrictedMarkdownError(block.text)
      : containsRawHtml(block.text) ? 'text blocks must not contain raw HTML' : null
    if (markdownError !== null) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: markdownError, path: ['text'] })
    }
  }

  if (block.type === 'entity_list') {
    if (block.items.some(item => item.entity_ref.resource !== block.entity_type)) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'entity resource must match entity_type', path: ['items'] })
    }
    const resultSetId = block.result_set_id ?? null
    if (block.items.some(item => (item.entity_ref.result_set_id ?? null) !== resultSetId)) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'entity result_set_id must match list result_set_id', path: ['items'] })
    }
  }

  if (block.type === 'table') {
    const columnKeys = block.columns.map(column => column.key)
    if (new Set(columnKeys).size !== columnKeys.length) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'table column keys must be unique', path: ['columns'] })
    }
    const allowedKeys = new Set(columnKeys)
    if (block.rows.some(row => row.cells.some(cell => !allowedKeys.has(cell.column_key)))) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'table row references an unknown column_key', path: ['rows'] })
    }
  }

  if (block.type === 'process') {
    const keys = block.items.map(item => item.key)
    if (new Set(keys).size !== keys.length) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'process item keys must be unique', path: ['items'] })
    }
  }

  if (block.type === 'pagination') {
    if (block.range_end < block.range_start) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'range_end cannot be less than range_start', path: ['range_end'] })
    }
    if (block.total != null && block.range_end > block.total) {
      context.addIssue({ code: z.ZodIssueCode.custom, message: 'range_end cannot exceed total', path: ['range_end'] })
    }
  }

  if (block.type === 'interaction') validateInteractionBlock(block, context)

})

export type AgentUIBlock = z.infer<typeof AgentUIBlockSchema>
