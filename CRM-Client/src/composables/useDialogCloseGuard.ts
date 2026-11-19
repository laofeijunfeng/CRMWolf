import { nextTick, ref, type ComputedRef, type Ref } from 'vue'
import { confirmDiscardChanges } from '@/utils/confirmDialog'

interface DialogCloseGuardOptions {
  isDirty: Ref<boolean> | ComputedRef<boolean>
  submitting: Ref<boolean> | ComputedRef<boolean>
  emitOpen: (open: boolean) => void
}

interface DialogCloseGuard {
  handleOpenChange: (open: boolean) => void
  handleParentClose: () => boolean
  requestClose: () => void
  approveClose: () => void
  reset: () => void
}

/**
 * Keeps a controlled Dialog open while it has unsaved changes and routes every
 * close path (Escape, backdrop, close button, cancel button, parent-driven
 * close) through the shared discard confirmation (`confirmDiscardChanges`).
 */
export function useDialogCloseGuard({
  isDirty,
  submitting,
  emitOpen,
}: DialogCloseGuardOptions): DialogCloseGuard {
  const confirming = ref(false)
  const closeApproved = ref(false)
  const suppressStaleOpen = ref(false)
  let focusReturnTarget: HTMLElement | null = null

  function captureFocus(): void {
    if (typeof document === 'undefined') return
    const activeElement = document.activeElement
    focusReturnTarget = activeElement instanceof HTMLElement ? activeElement : null
  }

  function restoreFocus(): void {
    const target = focusReturnTarget
    focusReturnTarget = null
    if (target === null || !target.isConnected) return

    void nextTick(() => {
      target.focus({ preventScroll: true })
    })
  }

  function approveClose(): void {
    closeApproved.value = true
    suppressStaleOpen.value = true
  }

  async function askDiscard(): Promise<void> {
    confirming.value = true
    captureFocus()
    let discard = false
    try {
      discard = await confirmDiscardChanges('close')
    } finally {
      confirming.value = false
    }

    if (!discard) {
      restoreFocus()
      return
    }

    approveClose()
    focusReturnTarget = null
    emitOpen(false)
  }

  function requestClose(): void {
    if (submitting.value || confirming.value) return

    if (isDirty.value) {
      void askDiscard()
      return
    }

    approveClose()
    emitOpen(false)
  }

  function handleOpenChange(open: boolean): void {
    if (open) {
      // Reka/Radix can emit a stale `true` both while a controlled close is
      // propagating and after the parent has applied `false`. Ignore it until
      // the parent explicitly opens this dialog again (which calls reset).
      if (closeApproved.value || suppressStaleOpen.value) return
      emitOpen(true)
      return
    }

    requestClose()
  }

  /**
   * Handles a parent changing v-model:open directly to false. Re-open the
   * Dialog before asking for discard confirmation so the parent cannot
   * silently discard input.
   *
   * Returns true when the close was blocked and the caller must skip cleanup.
   */
  function handleParentClose(): boolean {
    if (closeApproved.value) {
      // Keep the approval token until the parent explicitly re-opens the
      // dialog. A successful close can be followed by unrelated prop updates
      // while `open` is still false; those updates must not be mistaken for a
      // new parent-driven close of dirty form state.
      focusReturnTarget = null
      return false
    }

    if (submitting.value) {
      emitOpen(true)
      return true
    }

    if (isDirty.value) {
      emitOpen(true)
      if (!confirming.value) void askDiscard()
      return true
    }

    focusReturnTarget = null
    return false
  }

  function reset(): void {
    closeApproved.value = false
    suppressStaleOpen.value = false
    focusReturnTarget = null
  }

  return {
    handleOpenChange,
    handleParentClose,
    requestClose,
    approveClose,
    reset,
  }
}
