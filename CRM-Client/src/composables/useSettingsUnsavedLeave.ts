import { onMounted, onUnmounted, ref, type Ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { logger } from '@/utils/logger'

export interface SettingsUnsavedLeaveOptions {
  isDirty: () => boolean
  isSubmitting: () => boolean
}

export interface SettingsUnsavedLeaveGuard {
  showLeaveConfirm: Ref<boolean>
  pendingPath: Ref<string | null>
  confirmLeave: () => void
  cancelLeave: () => void
}

export function useSettingsUnsavedLeave(
  options: SettingsUnsavedLeaveOptions,
): SettingsUnsavedLeaveGuard {
  const router = useRouter()
  const showLeaveConfirm = ref(false)
  const pendingPath = ref<string | null>(null)
  const allowNextNavigation = ref(false)

  const handleBeforeUnload = (event: BeforeUnloadEvent): void => {
    if (!options.isDirty() || options.isSubmitting()) return
    event.preventDefault()
    event.returnValue = ''
  }

  const navigateAfterLeaveDecision = async (path: string): Promise<void> => {
    allowNextNavigation.value = true
    try {
      await router.push(path)
    } catch (error: unknown) {
      allowNextNavigation.value = false
      logger.error('[SettingsUnsavedLeave]', '离开设置页失败', { error })
    }
  }

  const confirmLeave = (): void => {
    const path = pendingPath.value
    showLeaveConfirm.value = false
    pendingPath.value = null
    if (path !== null) {
      void navigateAfterLeaveDecision(path)
    }
  }

  const cancelLeave = (): void => {
    showLeaveConfirm.value = false
    pendingPath.value = null
  }

  onBeforeRouteLeave((to): boolean => {
    if (allowNextNavigation.value) {
      allowNextNavigation.value = false
      return true
    }
    if (options.isSubmitting() || !options.isDirty()) return true

    pendingPath.value = to.fullPath
    showLeaveConfirm.value = true
    return false
  })

  onMounted(() => {
    window.addEventListener('beforeunload', handleBeforeUnload)
  })

  onUnmounted(() => {
    window.removeEventListener('beforeunload', handleBeforeUnload)
  })

  return {
    showLeaveConfirm,
    pendingPath,
    confirmLeave,
    cancelLeave,
  }
}
