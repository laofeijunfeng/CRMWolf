import { reactive, watch } from 'vue'
import type {
  BoardQueryScopeKey,
  BoardSnapshotController,
  BoardSnapshotState,
  UseBoardSnapshotOptions,
} from './boardTypes'

interface BoardRequestCapture {
  sequence: number
  scopeRevision: number
}

function sortedPermissionFingerprint(fingerprint: string): string {
  return fingerprint
    .split(',')
    .map((permission) => permission.trim())
    .filter((permission) => permission.length > 0)
    .sort()
    .join(',')
}

function normalizeScopeKey(scopeKey: BoardQueryScopeKey): BoardQueryScopeKey {
  return {
    teamId: scopeKey.teamId,
    userId: scopeKey.userId,
    permissionFingerprint: sortedPermissionFingerprint(scopeKey.permissionFingerprint),
  }
}

function sameScope(left: BoardQueryScopeKey, right: BoardQueryScopeKey): boolean {
  return left.teamId === right.teamId
    && left.userId === right.userId
    && sortedPermissionFingerprint(left.permissionFingerprint) === sortedPermissionFingerprint(right.permissionFingerprint)
}

export function useBoardSnapshot<TQuery, TResponse>(
  options: UseBoardSnapshotOptions<TQuery, TResponse>,
): BoardSnapshotController<TQuery, TResponse> {
  const state = reactive({
    data: null,
    successfulQuerySignature: null,
    currentQuerySignature: null,
    canDrillThrough: false,
    scopeKey: normalizeScopeKey(options.getScopeKey()),
    scopeRevision: 0,
    permissionReady: options.isPermissionReady(),
    loading: false,
    refreshing: false,
    stale: false,
    error: null,
    requestSequence: 0,
  }) as BoardSnapshotState<TResponse>

  function syncDrillThrough(): void {
    state.canDrillThrough = state.permissionReady
      && state.data !== null
      && state.error === null
      && state.successfulQuerySignature !== null
      && state.successfulQuerySignature === state.currentQuerySignature
  }

  function clearSnapshot(): void {
    state.scopeRevision += 1
    state.requestSequence += 1
    state.data = null
    state.successfulQuerySignature = null
    state.error = null
    state.stale = false
    state.loading = false
    state.refreshing = false
    state.canDrillThrough = false
  }

  function isCurrent(capture: BoardRequestCapture): boolean {
    return capture.sequence === state.requestSequence
      && capture.scopeRevision === state.scopeRevision
  }

  async function refresh(query: TQuery): Promise<void> {
    const signature = options.getQuerySignature(query)
    const hasSnapshot = state.data !== null
    state.currentQuerySignature = signature
    state.permissionReady = options.isPermissionReady()
    state.requestSequence += 1
    state.loading = !hasSnapshot
    state.refreshing = hasSnapshot
    state.error = null
    syncDrillThrough()

    const capture: BoardRequestCapture = {
      sequence: state.requestSequence,
      scopeRevision: state.scopeRevision,
    }

    try {
      const response = await options.fetchBoard(query)
      if (!isCurrent(capture)) return
      state.data = response
      state.successfulQuerySignature = signature
      state.error = null
      state.stale = false
    } catch (caught) {
      if (!isCurrent(capture)) return
      const error = caught instanceof Error ? caught : new Error('看板加载失败')
      state.error = error
      if (state.data === null) {
        state.stale = false
      } else {
        state.stale = true
      }
      throw error
    } finally {
      if (isCurrent(capture)) {
        state.loading = false
        state.refreshing = false
        state.permissionReady = options.isPermissionReady()
        syncDrillThrough()
      }
    }
  }

  async function retry(): Promise<void> {
    await refresh(options.getCurrentQuery())
  }

  watch(
    () => options.getScopeKey(),
    (nextScope, previousScope) => {
      state.scopeKey = normalizeScopeKey(nextScope)
      if (previousScope !== undefined && !sameScope(nextScope, previousScope)) {
        clearSnapshot()
      }
    },
    { flush: 'sync' },
  )

  watch(
    () => options.isPermissionReady(),
    (ready) => {
      state.permissionReady = ready
      syncDrillThrough()
    },
    { flush: 'sync' },
  )

  watch(
    () => options.getQuerySignature(options.getCurrentQuery()),
    (signature) => {
      state.currentQuerySignature = signature
      syncDrillThrough()
    },
    { flush: 'sync' },
  )

  return Object.assign(state, { refresh, retry })
}
