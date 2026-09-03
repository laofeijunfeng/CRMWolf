/**
 * The small, serializable context model used by the detail drill-down host.
 *
 * A node intentionally contains identity and display context only. It must not
 * become a second cache of the full business object returned by an API.
 */
export type DetailObjectType =
  | 'customer'
  | 'opportunity'
  | 'contract'
  | 'payment-plan'
  | 'payment-record'

export type DetailContextSource =
  | 'list'
  | 'customer-detail'
  | 'related-object'
  | 'deep-link'

export interface DetailContextNode {
  type: DetailObjectType
  id: string
  label: string
  status?: string
  parentType?: DetailObjectType
  parentId?: string
  source: DetailContextSource
}
