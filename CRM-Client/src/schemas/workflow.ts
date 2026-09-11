import { z } from 'zod'

const WorkflowNodeSchema = z.object({
  id: z.string(),
  type: z.string(),
  position: z.object({ x: z.number(), y: z.number() }).passthrough(),
  config: z.record(z.unknown()),
}).passthrough()

const WorkflowEdgeSchema = z.object({
  id: z.string(),
  source: z.string(),
  target: z.string(),
}).passthrough()

export const WorkflowDslSchema = z.object({
  schema_version: z.literal(1),
  nodes: z.array(WorkflowNodeSchema),
  edges: z.array(WorkflowEdgeSchema),
}).passthrough()

export const WorkflowSummarySchema = z.object({
  id: z.number(),
  name: z.string(),
  description: z.string().nullable().optional(),
  status: z.enum(['draft', 'published', 'paused']),
  node_count: z.number().int().nonnegative(),
  created_time: z.string(),
  last_modified_time: z.string(),
}).passthrough()

export const WorkflowDetailSchema = WorkflowSummarySchema.extend({
  dsl: WorkflowDslSchema,
  created_by: z.number().nullable().optional(),
})

export type WorkflowNode = z.infer<typeof WorkflowNodeSchema>
export type WorkflowDsl = z.infer<typeof WorkflowDslSchema>
export type WorkflowSummary = z.infer<typeof WorkflowSummarySchema>
export type WorkflowDetail = z.infer<typeof WorkflowDetailSchema>
