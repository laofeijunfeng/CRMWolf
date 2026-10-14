import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, effectScope, nextTick, reactive, ref } from 'vue'
import { useBoardSnapshot } from '../useBoardSnapshot'
import type { BoardQueryScopeKey } from '../boardTypes'

interface Query {
  search: string
}

interface Response {
  label: string
}
interface SnapshotController {
  loading: boolean
  refreshing: boolean
  data: Response | null
  error: Error | null
  stale: boolean
  canDrillThrough: boolean
  successfulQuerySignature: string | null
  currentQuerySignature: string | null
  scopeRevision: number
  requestSequence: number
  scopeKey: BoardQueryScopeKey
  permissionReady: boolean
  refresh: (query: Query) => Promise<void>
  retry: () => Promise<void>
}

interface Harness {
  query: Query
  scope: BoardQueryScopeKey
  permissionReady: boolean
  fetchBoard: ReturnType<typeof vi.fn<(query: Query) => Promise<Response>>>
  snapshot: SnapshotController
  stop: () => void
}

function createHarness(initial?: Partial<BoardQueryScopeKey>): Harness {
  const query = reactive<Query>({ search: 'acme' })
  const scope = reactive<BoardQueryScopeKey>({
    teamId: 7,
    userId: 'user-1',
    permissionFingerprint: 'customers.read,opportunities.read',
    ...initial,
  })
  const permissionReady = ref(true)
  const fetchBoard = vi.fn<(query: Query) => Promise<Response>>()
  const scopeEffect = effectScope()
  const snapshot = scopeEffect.run(() => useBoardSnapshot<Query, Response>({
    fetchBoard,
    getQuerySignature: (value) => value.search,
    getScopeKey: () => ({
      teamId: scope.teamId,
      userId: scope.userId,
      permissionFingerprint: scope.permissionFingerprint,
    }),
    getCurrentQuery: () => ({ search: query.search }),
    isPermissionReady: () => permissionReady.value,
  }))
  if (snapshot === undefined) throw new Error('snapshot scope did not start')

  return {
    query,
    scope,
    get permissionReady() {
      return permissionReady.value
    },
    set permissionReady(value: boolean) {
      permissionReady.value = value
    },
    fetchBoard,
    snapshot,
    stop: () => scopeEffect.stop(),
  }
}

describe('useBoardSnapshot', () => {
  const harnesses: Harness[] = []

  beforeEach(() => {
    harnesses.splice(0).forEach((harness) => harness.stop())
  })

  it('keeps the first failure blocking and retries the current query', async () => {
    const harness = createHarness()
    harnesses.push(harness)
    const initialError = new Error('offline')
    harness.fetchBoard.mockRejectedValueOnce(initialError)

    const failed = harness.snapshot.refresh(harness.query)
    expect(harness.snapshot.loading).toBe(true)
    expect(harness.snapshot.refreshing).toBe(false)
    await expect(failed).rejects.toBe(initialError)
    await flushPromises()

    expect(harness.snapshot.data).toBeNull()
    expect(harness.snapshot.loading).toBe(false)
    expect(harness.snapshot.error).toBe(initialError)
    expect(harness.snapshot.stale).toBe(false)
    expect(harness.snapshot.canDrillThrough).toBe(false)

    harness.query.search = 'current'
    harness.fetchBoard.mockResolvedValueOnce({ label: 'current' })
    await harness.snapshot.retry()

    expect(harness.fetchBoard).toHaveBeenLastCalledWith({ search: 'current' })
    expect(harness.snapshot.data).toEqual({ label: 'current' })
    expect(harness.snapshot.successfulQuerySignature).toBe('current')
    expect(harness.snapshot.currentQuerySignature).toBe('current')
    expect(harness.snapshot.error).toBeNull()
    expect(harness.snapshot.canDrillThrough).toBe(true)
  })

  it('preserves a successful snapshot when a later refresh fails', async () => {
    const harness = createHarness()
    harnesses.push(harness)
    harness.fetchBoard.mockResolvedValueOnce({ label: 'saved' })
    await harness.snapshot.refresh({ search: 'saved' })

    harness.query.search = 'next'
    const refreshError = new Error('refresh failed')
    harness.fetchBoard.mockRejectedValueOnce(refreshError)
    await expect(harness.snapshot.refresh({ search: 'next' })).rejects.toBe(refreshError)

    expect(harness.snapshot.data).toEqual({ label: 'saved' })
    expect(harness.snapshot.successfulQuerySignature).toBe('saved')
    expect(harness.snapshot.currentQuerySignature).toBe('next')
    expect(harness.snapshot.refreshing).toBe(false)
    expect(harness.snapshot.stale).toBe(true)
    expect(harness.snapshot.error).toBe(refreshError)
    expect(harness.snapshot.canDrillThrough).toBe(false)
  })

  it('discards a late response after a newer request starts', async () => {
    const harness = createHarness()
    harnesses.push(harness)
    let resolveFirst: (value: Response) => void = () => undefined
    const first = new Promise<Response>((resolve) => {
      resolveFirst = resolve
    })
    harness.fetchBoard.mockReturnValueOnce(first)
    const firstRequest = harness.snapshot.refresh({ search: 'old' })

    harness.fetchBoard.mockResolvedValueOnce({ label: 'new' })
    await harness.snapshot.refresh({ search: 'new' })
    resolveFirst({ label: 'old' })
    await firstRequest
    await flushPromises()

    expect(harness.snapshot.data).toEqual({ label: 'new' })
    expect(harness.snapshot.successfulQuerySignature).toBe('new')
    expect(harness.snapshot.stale).toBe(false)
    expect(harness.snapshot.error).toBeNull()
  })

  it('clears the snapshot synchronously when team, user, or permission scope changes', async () => {
    const harness = createHarness()
    harnesses.push(harness)
    harness.fetchBoard.mockResolvedValueOnce({ label: 'saved' })
    await harness.snapshot.refresh({ search: 'saved' })
    const revision = harness.snapshot.scopeRevision
    const sequence = harness.snapshot.requestSequence

    let resolveInFlight: (value: Response) => void = () => undefined
    const inFlight = new Promise<Response>((resolve) => {
      resolveInFlight = resolve
    })
    harness.fetchBoard.mockReturnValueOnce(inFlight)
    const request = harness.snapshot.refresh({ search: 'inflight' })

    harness.scope.teamId = 8
    await nextTick()

    expect(harness.snapshot.data).toBeNull()
    expect(harness.snapshot.successfulQuerySignature).toBeNull()
    expect(harness.snapshot.error).toBeNull()
    expect(harness.snapshot.stale).toBe(false)
    expect(harness.snapshot.canDrillThrough).toBe(false)
    expect(harness.snapshot.scopeRevision).toBeGreaterThan(revision)
    expect(harness.snapshot.requestSequence).toBeGreaterThan(sequence)

    resolveInFlight({ label: 'stale team' })
    await request
    await flushPromises()
    expect(harness.snapshot.data).toBeNull()

    harness.fetchBoard.mockResolvedValueOnce({ label: 'user scope' })
    await harness.snapshot.refresh({ search: 'user' })
    harness.scope.userId = 'user-2'
    await nextTick()
    expect(harness.snapshot.data).toBeNull()

    harness.fetchBoard.mockResolvedValueOnce({ label: 'permission scope' })
    await harness.snapshot.refresh({ search: 'permission' })
    harness.scope.permissionFingerprint = 'opportunities.read,customers.read'
    await nextTick()
    expect(harness.snapshot.data).toEqual({ label: 'permission scope' })
    expect(harness.snapshot.scopeKey.permissionFingerprint).toBe('customers.read,opportunities.read')

    harness.scope.permissionFingerprint = 'customers.read'
    await nextTick()
    expect(harness.snapshot.data).toBeNull()
  })

  it('disables drill-through while permissions are not ready', async () => {
    const harness = createHarness()
    harnesses.push(harness)
    harness.permissionReady = false
    harness.fetchBoard.mockResolvedValueOnce({ label: 'saved' })
    await harness.snapshot.refresh({ search: 'saved' })

    expect(harness.snapshot.permissionReady).toBe(false)
    expect(harness.snapshot.data).toEqual({ label: 'saved' })
    expect(harness.snapshot.canDrillThrough).toBe(false)

    const signature = computed(() => harness.snapshot.currentQuerySignature)
    harness.query.search = 'changed'
    await nextTick()
    expect(signature.value).toBe('changed')
    expect(harness.snapshot.canDrillThrough).toBe(false)
  })
})
