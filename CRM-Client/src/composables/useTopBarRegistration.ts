import { onActivated, onMounted, toValue, watch, type MaybeRefOrGetter, type WatchSource } from 'vue'
import { useHeaderStore, type HeaderAction, type TabItem } from '@/stores/header'

interface UseTopBarRegistrationOptions {
  tabs?: MaybeRefOrGetter<TabItem[] | null>
  activeTab?: MaybeRefOrGetter<string>
  actions?: () => HeaderAction[]
  actionDeps?: WatchSource[]
}

export function useTopBarRegistration(options: UseTopBarRegistrationOptions): void {
  const headerStore = useHeaderStore()

  const register = (): void => {
    const tabs = options.tabs === undefined ? undefined : toValue(options.tabs)
    const activeTab = options.activeTab === undefined ? undefined : toValue(options.activeTab)

    if (tabs !== undefined) {
      headerStore.setTabs(tabs, activeTab)
    }
    if (options.actions !== undefined) {
      headerStore.setActions(options.actions())
    }
  }

  onMounted(register)
  onActivated(register)
  watch(
    [
      (): TabItem[] | null | undefined => options.tabs === undefined ? undefined : toValue(options.tabs),
      (): string | undefined => options.activeTab === undefined ? undefined : toValue(options.activeTab),
      ...(options.actionDeps ?? [])
    ],
    register,
    { immediate: true }
  )
}
