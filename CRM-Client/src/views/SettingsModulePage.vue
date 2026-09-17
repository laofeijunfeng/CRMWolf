<template>
  <SettingsContent :ariaLabel="moduleItem?.label ?? '系统设置'" :description="moduleItem?.description ?? ''">
    <ErrorState
      v-if="moduleItem === undefined"
      variant="error"
      title="设置模块不存在"
      description="请从左侧设置菜单选择有效的配置模块。"
    />
    <div v-else-if="accessLoading" class="settings-access-loading" role="status" aria-live="polite">
      <div class="settings-access-loading__bar" />
      <p>正在确认设置权限…</p>
    </div>
    <ErrorState
      v-else-if="accessUnavailable"
      variant="error"
      title="权限信息暂不可用"
      description="为避免误操作，该设置模块暂时不可用。请在顶部重试权限同步后再继续。"
    />
    <ErrorState
      v-else-if="!hasAccess"
      variant="forbidden"
      title="暂无访问权限"
      description="你没有访问此设置模块的权限，请联系团队管理员。"
    />

    <component
      :is="legacyComponent"
      v-if="hasAccess && legacyComponent !== null"
      v-bind="legacyProps"
      @update:open="legacyOpen = $event"
    />
  </SettingsContent>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch, type Component } from 'vue'
import { useRoute } from 'vue-router'
import ErrorState from '@/components/ErrorState.vue'
import { usePageTitle } from '@/composables/usePageTitle'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { getSettingsNavigationItem, type SettingsNavigationItem } from '@/settingsNavigation'
import SettingsContent from '@/views/settings/SettingsContent.vue'

usePageTitle()

interface Props {
  module?: string
}

const props = defineProps<Props>()
const route = useRoute()
const { canAccess, isOwner, permissionsUnavailable, permissionsPending } = useSettingsAccess()
const legacyOpen = ref(false)

const legacyComponents: Record<string, Component> = {
  members: defineAsyncComponent(() => import('@/components/system-config/TeamMemberSheet.vue')),
  roles: defineAsyncComponent(() => import('@/components/system-config/RoleSheet.vue')),
  'approval-flows': defineAsyncComponent(() => import('@/components/system-config/ApprovalFlowSheet.vue')),
  'approval-flows-new': defineAsyncComponent(() => import('@/views/ApprovalFlowsNew.vue')),
  'acquisition-sources': defineAsyncComponent(() => import('@/components/system-config/AcquisitionSourcePanel.vue')),
  procurement: defineAsyncComponent(() => import('@/components/system-config/ProcurementMethodsPanel.vue')),
  ai: defineAsyncComponent(() => import('@/components/system-config/AIConfigSheet.vue')),
  products: defineAsyncComponent(() => import('@/components/system-config/ProductPanel.vue')),
  notifications: defineAsyncComponent(() => import('@/components/system-config/NotificationSheet.vue')),
  integrations: defineAsyncComponent(() => import('@/components/system-config/LoginIntegrationSheet.vue')),
}

const moduleId = computed(() => {
  const raw = props.module ?? route.params['module']
  if (raw === 'procurement-methods') return 'procurement'
  return typeof raw === 'string' ? raw : undefined
})
const moduleItem = computed<SettingsNavigationItem | undefined>(() => {
  const id = moduleId.value
  return id === undefined ? undefined : getSettingsNavigationItem(id)
})
const isPageEmbedded = computed(() => moduleItem.value?.legacyComponentKey !== undefined)
const legacyComponent = computed<Component | null>(() => {
  const key = moduleItem.value?.legacyComponentKey
  return key === undefined ? null : legacyComponents[key] ?? null
})
const legacyProps = computed<Record<string, unknown>>(() => {
  const props: Record<string, unknown> = isPageEmbedded.value
    ? { active: true, embedded: true }
    : { open: legacyOpen.value }

  if (moduleId.value === 'approval-flows' || moduleId.value === 'approval-flows-new' || moduleId.value === 'acquisition-sources' || moduleId.value === 'procurement' || moduleId.value === 'products') {
    if (queryAction.value !== null) props['action'] = queryAction.value
    if (queryRecordId.value !== null) props['recordId'] = queryRecordId.value
  }

  return props
})
const hasAccess = computed(() => moduleItem.value !== undefined && canAccess(moduleItem.value))
const accessLoading = computed(() => {
  const item = moduleItem.value
  if (item?.scope !== 'team' || !permissionsPending.value) return false
  return !isOwner.value || item.allowOwnerBypass === false
})
const accessUnavailable = computed(() => moduleItem.value?.scope === 'team' && permissionsUnavailable.value && !hasAccess.value)

const queryAction = computed<'create' | 'edit' | null>(() => {
  const action = route.query['action']
  return action === 'create' || action === 'edit' ? action : null
})
const queryRecordId = computed(() => {
  const id = route.query['id'] ?? route.query['methodId'] ?? route.params['id'] ?? route.params['methodId']
  return typeof id === 'string' && id.length > 0 ? id : null
})

watch(
  () => [route.query['action'], route.query['id'], route.query['methodId'], hasAccess.value] as const,
  ([action, id, methodId, access]) => {
    if (access !== true || legacyComponent.value === null) return
    if (action === 'create' || action === 'edit' || typeof id === 'string' || typeof methodId === 'string') {
      legacyOpen.value = true
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.settings-access-loading {
  display: flex;
  min-height: 200px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.settings-access-loading__bar {
  width: min(320px, 80%);
  height: 12px;
  border-radius: 999px;
  background: hsl(var(--muted));
  animation: settings-access-pulse 1.2s ease-in-out infinite;
}

@keyframes settings-access-pulse {
  0%,
  100% { opacity: 0.55; }
  50% { opacity: 1; }
}
</style>
