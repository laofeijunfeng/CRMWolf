import type { EntityRef } from '@/schemas/agent-contracts'

/**
 * Agent only turns references into buttons when the host shell has a stable
 * detail surface for that resource. Other references stay readable so that a
 * missing deep-link target never looks like a broken click action.
 */
export const isAgentEntityOpenable = (entityRef: Pick<EntityRef, 'resource'>): boolean => (
  entityRef.resource === 'customer'
  || entityRef.resource === 'opportunity'
  || entityRef.resource === 'contract'
)

/**
 * Contract detail APIs currently use the numeric database id while Agent
 * references intentionally use strings. Keep the conversion strict and
 * bounded so malformed or unsafe ids cannot silently open the wrong record.
 */
export const parseAgentContractId = (publicId: string): number | null => {
  const normalized = publicId.trim()
  if (!/^\d+$/.test(normalized)) return null

  const parsed = Number(normalized)
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
}
