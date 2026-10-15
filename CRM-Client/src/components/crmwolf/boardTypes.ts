export type BoardValueType = 'count' | 'amount' | 'percentage'

export type BoardTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'muted'

export interface BoardMetricPresentation {
  key: string
  label: string
  value: string
  valueType: BoardValueType
  secondaryValue?: string
  secondaryLabel?: string
}

export interface BoardMetadataRow {
  key: string
  label: string
  value: string
}

export interface BoardCardPresentation {
  id: string | number
  title: string
  subtitle: string | null
  primaryValue: string | null
  dateLabel: string | null
  ownerLabel: string | null
  statusLabel: string
  metadata: readonly BoardMetadataRow[]
}

export interface BoardColumnPresentation {
  key: string
  label: string
  tone: BoardTone
  countLabel: string
  amountLabel: string | null
  cards: readonly BoardCardPresentation[]
  hasMore: boolean
  remainingCount: number
  drillThroughEnabled?: boolean
}

export interface BoardCardActivation {
  id: string | number
  columnKey: string
}

export interface BoardTrendPointPresentation {
  month: string
  values: Readonly<Record<string, string | number>>
}

export interface BoardTrendSeriesPresentation {
  key: string
  label: string
  color: string
  fillColor?: string
}

export interface BoardTrendPresentation {
  title: string
  description: string
  points: readonly BoardTrendPointPresentation[]
  series: readonly BoardTrendSeriesPresentation[]
}

export interface BoardProjection {
  metrics: readonly BoardMetricPresentation[]
  columns: readonly BoardColumnPresentation[]
  trend: BoardTrendPresentation | null
}

export interface BoardQueryScopeKey {
  teamId: number | null
  userId: string | null
  permissionFingerprint: string
}

export interface BoardSnapshotState<TResponse> {
  data: TResponse | null
  successfulQuerySignature: string | null
  currentQuerySignature: string | null
  canDrillThrough: boolean
  scopeKey: BoardQueryScopeKey
  scopeRevision: number
  permissionReady: boolean
  loading: boolean
  refreshing: boolean
  stale: boolean
  error: Error | null
  requestSequence: number
}

export interface UseBoardSnapshotOptions<TQuery, TResponse> {
  fetchBoard: (query: TQuery) => Promise<TResponse>
  getQuerySignature: (query: TQuery) => string
  getScopeKey: () => BoardQueryScopeKey
  getCurrentQuery: () => TQuery
  isPermissionReady: () => boolean
}

export interface BoardSnapshotController<TQuery, TResponse> extends BoardSnapshotState<TResponse> {
  refresh: (query: TQuery) => Promise<void>
  retry: () => Promise<void>
}
