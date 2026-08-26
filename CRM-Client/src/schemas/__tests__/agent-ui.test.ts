import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { z } from 'zod'

import {
  AgentChatRequestSchema,
  AgentUIActionSchema,
  AgentUIBlockSchema,
  AgentUIEnvelopeSchema,
  AgentUIStreamEventSchema,
  AgentTransportErrorEventSchema,
  InteractionBlockSchema,
  CRMQueryResultSchema,
  CRMQuerySpecSchema,
  QueryErrorSchema,
  RootContextSnapshotSchema,
  RootDecisionSchema
} from '../agent-contracts'

const fixturePath = resolve(
  process.cwd(),
  '../CRM-Server/tests/fixtures/agent_contracts/crm_agent_contract_examples.json'
)
const ExamplesSchema = z.object({
  root_decision: z.unknown(),
  root_context_snapshot: z.unknown(),
  query_spec: z.unknown(),
  query_result: z.unknown(),
  query_error: z.unknown(),
  completed_work_request: z.unknown(),
  completed_work_response: z.unknown(),
  completed_work_error: z.unknown(),
  agent_ui_envelope: z.unknown(),
  agent_ui_stream_events: z.array(z.unknown()),
  chat_requests: z.array(z.unknown())
}).strict()
const examples = ExamplesSchema.parse(JSON.parse(readFileSync(fixturePath, 'utf-8')))
const conformancePath = resolve(
  process.cwd(),
  '../CRM-Server/tests/fixtures/agent_contracts/crm_agent_contract_conformance.json'
)
const ConformanceCaseSchema = z.object({
  schema: z.enum([
    'RootDecision',
    'CRMQuerySpec',
    'CRMQueryResult',
    'QueryError',
    'AgentChatRequest',
    'AgentUIAction',
    'AgentUIBlock',
    'AgentUIEnvelope',
    'InteractionBlock',
    'AgentUIStreamEvent',
    'AgentTransportErrorEvent'
  ]),
  reason: z.string().optional(),
  payload: z.unknown()
}).strict()
const ConformanceCorpusSchema = z.object({
  valid: z.array(ConformanceCaseSchema),
  invalid: z.array(ConformanceCaseSchema)
}).strict()
const conformance = ConformanceCorpusSchema.parse(JSON.parse(readFileSync(conformancePath, 'utf-8')))
const conformanceSchemas = {
  RootDecision: RootDecisionSchema,
  CRMQuerySpec: CRMQuerySpecSchema,
  CRMQueryResult: CRMQueryResultSchema,
  QueryError: QueryErrorSchema,
  AgentChatRequest: AgentChatRequestSchema,
  AgentUIAction: AgentUIActionSchema,
  AgentUIBlock: AgentUIBlockSchema,
  AgentUIEnvelope: AgentUIEnvelopeSchema,
  InteractionBlock: InteractionBlockSchema,
  AgentUIStreamEvent: AgentUIStreamEventSchema,
  AgentTransportErrorEvent: AgentTransportErrorEventSchema
}

describe('CRM Agent frozen contracts', () => {
  it('parses backend-reviewed query and route examples', () => {
    expect(RootDecisionSchema.parse(examples.root_decision).route).toBe('QUERY')
    expect(RootContextSnapshotSchema.parse(examples.root_context_snapshot).previous_query?.resource).toBe('customer')
    expect(CRMQuerySpecSchema.parse(examples.query_spec).filters).toHaveLength(1)
    expect(CRMQueryResultSchema.parse(examples.query_result).status).toBe('PARTIAL')
    expect(QueryErrorSchema.parse(examples.query_error).code).toBe('QUERY_INVALID')
  })

  it('parses the backend-reviewed Agent UI example', () => {
    const envelope = AgentUIEnvelopeSchema.parse(examples.agent_ui_envelope)

    expect(envelope.schema_version).toBe('crm.agent.ui.v1')
    expect(envelope.blocks.map(block => block.type)).toEqual(['text', 'entity_list', 'pagination'])
  })

  it('parses delta and final Agent UI stream events', () => {
    const events = examples.agent_ui_stream_events.map(event => AgentUIStreamEventSchema.parse(event))
    const finalEvent = events[1]

    expect(events.map(event => event.phase)).toEqual(['delta', 'final'])
    expect(finalEvent?.phase).toBe('final')
    expect(AgentUIStreamEventSchema.safeParse({
      ...finalEvent,
      turn_id: 'turn_mismatch'
    }).success).toBe(false)
  })

  it('parses all typed request variants', () => {
    const requests = examples.chat_requests.map(request => AgentChatRequestSchema.parse(request))

    expect(requests.map(request => request.input.type)).toEqual([
      'text',
      'interaction_submission',
      'entity_action'
    ])
  })


  it('matches the backend cross-language conformance corpus', () => {
    for (const testCase of conformance.valid) {
      expect(conformanceSchemas[testCase.schema].safeParse(testCase.payload).success).toBe(true)
    }
    for (const testCase of conformance.invalid) {
      expect(conformanceSchemas[testCase.schema].safeParse(testCase.payload).success, testCase.reason).toBe(false)
    }
  })

  it('rejects unknown blocks and legacy chat fields', () => {
    expect(AgentUIBlockSchema.safeParse({ id: 'legacy', type: 'legacy_markdown', content: 'old' }).success).toBe(false)
    expect(AgentUIBlockSchema.safeParse({ id: 'unsafe', type: 'text', format: 'markdown', text: '摘要<script>alert(1)</script>' }).success).toBe(false)
    expect(AgentChatRequestSchema.safeParse({
      session_id: 123,
      client_request_id: '6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be',
      content: '旧协议'
    }).success).toBe(false)
  })

  it('keeps entity lists minimal and rejects mismatched entity references', () => {
    const entityRef = {
      ref_id: 'eref_customer_1',
      resource: 'customer',
      public_id: 'cus_1',
      display_name: '上海示例客户',
      result_set_id: 'rs_1'
    } as const
    const listBlock = {
      id: 'customers',
      type: 'entity_list',
      entity_type: 'customer',
      result_set_id: 'rs_1',
      total: 1,
      items: [{ entity_ref: entityRef }]
    } as const

    expect(AgentUIBlockSchema.safeParse(listBlock).success).toBe(true)
    expect(AgentUIBlockSchema.safeParse({
      ...listBlock,
      items: [{ entity_ref: entityRef, title: '旧标题' }]
    }).success).toBe(false)
    expect(AgentUIBlockSchema.safeParse({
      ...listBlock,
      items: [{ entity_ref: { ...entityRef, resource: 'contact' } }]
    }).success).toBe(false)
    expect(AgentUIBlockSchema.safeParse({
      ...listBlock,
      items: [{ entity_ref: { ...entityRef, result_set_id: 'rs_other' } }]
    }).success).toBe(false)
    expect(AgentUIBlockSchema.safeParse({
      id: 'customers_without_result_set',
      type: 'entity_list',
      entity_type: 'customer',
      total: 1,
      items: [{ entity_ref: { ...entityRef, result_set_id: null } }]
    }).success).toBe(true)
  })
})
