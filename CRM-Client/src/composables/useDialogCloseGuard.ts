import { nextTick, ref, type ComputedRef, type Ref } from 'vue'

interface DialogCloseGuardOptions {
  isDirty: Ref<boolean> | ComputedRef<boolean>
  submitting: Ref<boolean> | ComputedRef<boolean>
  emitOpen: (open: boolean) => void
}

interface DialogCloseGuard {
  showConfirmDialog: Ref<boolean>
  handleOpenChange: (open: boolean) => void
  handleParentClose: () => boolean
  handleConfirmOpenChange: (open: boolean) => void
  requestClose: () => void
  continueEditing: () => void
  confirmDiscard: () => void
  approveClose: () => void
  reset: () => void
}

/**
 * Keeps a controlled Dialog open while it has unsaved changes and provides a
 * consistent discard-confirmation flow for Escape, backdrop, close-button,
 * cancel-button, and parent-driven close requests.
 */
export function useDialogCloseGuard({
  isDirty,
  submitting,
  emitOpen,
}: DialogCloseGuardOptions): DialogCloseGuard {
  const showConfirmDialog = ref(false)
  const closeApproved = ref(false)
  const suppressStaleOpen = ref(false)
  const focusReturnTarget = ref<HTMLElement | null>(null)

  function captureFocus(): void {
    if (typeof document === 'undefined') return
    const activeElement = document.activeElement
    focusReturnTarget.value = activeElement instanceof HTMLElement ? activeElement : null
  }

  function restoreFocus(): void {
    const target = focusReturnTarget.value
    focusReturnTarget.value = null
    if (target === null || !target.isConnected) return

    void nextTick(() => {
      target.focus({ preventScroll: true })
    })
  }

  function openDiscardConfirmation(): void {
    if (!showConfirmDialog.value) captureFocus()
    showConfirmDialog.value = true
  }

  function approveClose(): void {
    closeApproved.value = true
    suppressStaleOpen.value = true
  }

  function requestClose(): void {
    if (submitting.value || showConfirmDialog.value) return

    if (isDirty.value) {
      openDiscardConfirmation()
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
   * Dialog before showing the discard confirmation so the parent cannot
   * silently discard input.
   *
   * Returns true when the close was blocked and the caller must skip cleanup.
   */
  function handleParentClose(): boolean {
    if (closeApproved.value) {
      closeApproved.value = false
      showConfirmDialog.value = false
      focusReturnTarget.value = null
      return false
    }

    if (submitting.value) {
      emitOpen(true)
      return true
    }

    if (isDirty.value) {
      emitOpen(true)
      openDiscardConfirmation()
      return true
    }

    showConfirmDialog.value = false
    focusReturnTarget.value = null
    return false
  }

  function continueEditing(): void {
    showConfirmDialog.value = false
    restoreFocus()
  }

  function confirmDiscard(): void {
    showConfirmDialog.value = false
    approveClose()
    focusReturnTarget.value = null
    emitOpen(false)
  }

  function handleConfirmOpenChange(open: boolean): void {
    if (open) {
      openDiscardConfirmation()
      return
    }

    // Covers Escape and the AlertDialog overlay close. A dismissal of the
    // confirmation is never treated as approval to discard the form.
    if (showConfirmDialog.value) {
      showConfirmDialog.value = false
      restoreFocus()
    }
  }

  function reset(): void {
    showConfirmDialog.value = false
    closeApproved.value = false
    suppressStaleOpen.value = false
    focusReturnTarget.value = null
  }

  return {
    showConfirmDialog,
    handleOpenChange,
    handleParentClose,
    handleConfirmOpenChange,
    requestClose,
    continueEditing,
    confirmDiscard,
    approveClose,
    reset,
  }
}
