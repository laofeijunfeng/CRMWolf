import { onMounted, onUnmounted } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { confirmDiscardChanges } from '@/utils/confirmDialog'

export interface RouteLeaveGuardOptions {
  isDirty: () => boolean
  isSubmitting: () => boolean
}

export interface RouteLeaveGuard {
  /** Let the next navigation leave without confirmation (e.g. after a successful save). */
  allowNextNavigation: () => void
}

/**
 * Asks for the shared discard confirmation before leaving a route with unsaved
 * changes, and arms the browser `beforeunload` prompt for reload/close.
 */
export function useRouteLeaveGuard(options: RouteLeaveGuardOptions): RouteLeaveGuard {
  let allowNext = false
  let pending: Promise<boolean> | null = null

  const handleBeforeUnload = (event: BeforeUnloadEvent): void => {
    if (!options.isDirty() || options.isSubmitting()) return
    event.preventDefault()
    event.returnValue = ''
  }

  onBeforeRouteLeave((): boolean | Promise<boolean> => {
    if (allowNext) {
      allowNext = false
      return true
    }
    if (options.isSubmitting() || !options.isDirty()) return true

    // A second navigation while the dialog is open reuses the same decision.
    pending ??= confirmDiscardChanges('leave').finally(() => {
      pending = null
    })
    return pending
  })

  onMounted(() => {
    window.addEventListener('beforeunload', handleBeforeUnload)
  })

  onUnmounted(() => {
    window.removeEventListener('beforeunload', handleBeforeUnload)
  })

  return {
    allowNextNavigation: (): void => {
      allowNext = true
    },
  }
}
