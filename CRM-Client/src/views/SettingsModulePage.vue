<template>
  <main class="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6" :aria-label="moduleItem?.label ?? '系统设置'">
    <div class="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
      <div class="space-y-1">
        <p class="text-sm font-medium text-primary">系统设置</p>
        <h1 class="text-2xl font-semibold tracking-tight">{{ moduleItem?.label ?? '系统设置' }}</h1>
        <p class="text-sm text-muted-foreground">{{ moduleItem?.description ?? '管理当前工作区的系统配置。' }}</p>
      </div>
      <Button v-if="hasAccess && legacyComponent !== null && !isPageEmbedded" type="button" @click="openLegacyConfig">
        {{ queryActionLabel }}
      </Button>
    </div>

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

    <Card v-else-if="moduleItem !== undefined && !isPageEmbedded">
      <CardHeader>
        <CardTitle>{{ moduleItem.label }}</CardTitle>
        <CardDescription>{{ migrationDescription }}</CardDescription>
      </CardHeader>
      <CardContent class="space-y-3">
        <div class="rounded-lg border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
          <p>{{ legacyComponent === null ? emptyDescription : '页面化迁移期间，系统继续复用现有配置能力；进入配置后，原有搜索、筛选、表单和权限规则保持不变。' }}</p>
          <p v-if="queryAction !== null" class="mt-2 text-primary">
            已识别旧链接操作：{{ queryActionLabel }}<span v-if="queryRecordId !== null">（记录 ID：{{ queryRecordId }}）</span>，点击上方按钮继续。
          </p>
        </div>
        <Button v-if="legacyComponent !== null" variant="outline" type="button" @click="openLegacyConfig">
          打开现有配置
        </Button>
      </CardContent>
    </Card>

    <component
      :is="legacyComponent"
      v-if="hasAccess && legacyComponent !== null"
      v-bind="legacyProps"
      @update:open="legacyOpen = $event"
    />
  </main>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch, type Component } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import ErrorState from '@/components/ErrorState.vue'
import { usePageTitle } from '@/composables/usePageTitle'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { getSettingsNavigationItem, type SettingsNavigationItem } from '@/settingsNavigation'

usePageTitle()

interface Props {
  module?: string
}

const props = defineProps<Props>()
const route = useRoute()
const { canAccess, permissionsUnavailable, permissionsPending } = useSettingsAccess()
const legacyOpen = ref(false)

const legacyComponents: Record<string, Component> = {
  members: defineAsyncComponent(() => import('@/components/system-config/TeamMemberSheet.vue')),
  roles: defineAsyncComponent(() => import('@/components/system-config/RoleSheet.vue')),
  'approval-flows': defineAsyncComponent(() => import('@/components/system-config/ApprovalFlowSheet.vue')),
  'acquisition-sources': defineAsyncComponent(() => import('@/components/system-config/AcquisitionSourcePanel.vue')),
  procurement: defineAsyncComponent(() => import('@/components/system-config/ProcurementMethodsPanel.vue')),
  ai: defineAsyncComponent(() => import('@/components/system-config/AIConfigSheet.vue')),
  notifications: defineAsyncComponent(() => import('@/components/system-config/NotificationSheet.vue')),
  integrations: defineAsyncComponent(() => import('@/components/system-config/LoginIntegrationSheet.vue')),
}

const migrationDescriptions: Record<string, string> = {
  team: '团队资料和高风险安全操作会在页面化迁移中补充完整的影响范围确认与审计反馈。',
  members: '成员列表、邀请和角色分配等短任务暂时复用现有配置能力。',
  roles: '角色列表、权限配置和成员查看暂时复用现有配置能力。',
  'approval-flows': '审批流程列表和节点编辑暂时复用现有配置能力，审批实例仍由审批中心负责。',
  'acquisition-sources': '获客来源搜索、状态筛选、启停和引用统计保持现有行为。',
  procurement: '采购方式及阶段模板继续保留现有版本锁定、引用检查和冲突反馈。',
  ai: '敏感密钥保持脱敏，连接测试和保存反馈继续复用现有能力。',
  notifications: '通知配置保存和测试能力暂时复用现有配置能力，后续补齐独立通知权限。',
  integrations: '团队级集成和个人飞书绑定保持边界分离，敏感信息不明文回显。',
}

const emptyDescriptions: Record<string, string> = {
  team: '当前团队基础信息将在页面化迁移中从团队成员管理中独立出来。',
  members: '暂无团队成员管理能力。',
  roles: '暂无角色管理能力。',
  'approval-flows': '暂无审批流程管理能力。',
  'acquisition-sources': '暂无获客来源管理能力。',
  procurement: '暂无采购方式管理能力。',
  ai: '暂无 AI 配置管理能力。',
  notifications: '暂无通知配置管理能力。',
  integrations: '暂无第三方集成管理能力。',
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

  if (moduleId.value === 'approval-flows' || moduleId.value === 'acquisition-sources' || moduleId.value === 'procurement') {
    if (queryAction.value !== null) props['action'] = queryAction.value
    if (queryRecordId.value !== null) props['recordId'] = queryRecordId.value
  }

  return props
})
const hasAccess = computed(() => moduleItem.value !== undefined && canAccess(moduleItem.value))
const accessLoading = computed(() => moduleItem.value?.scope === 'team' && permissionsPending.value)
const accessUnavailable = computed(() => moduleItem.value?.scope === 'team' && permissionsUnavailable.value && !hasAccess.value)

const queryAction = computed<'create' | 'edit' | null>(() => {
  const action = route.query['action']
  return action === 'create' || action === 'edit' ? action : null
})
const queryRecordId = computed(() => {
  const id = route.query['id'] ?? route.query['methodId'] ?? route.params['id'] ?? route.params['methodId']
  return typeof id === 'string' && id.length > 0 ? id : null
})
const queryActionLabel = computed(() => queryAction.value === 'edit' ? '继续编辑' : '进入配置')
const migrationDescription = computed(() => migrationDescriptions[moduleId.value ?? ''] ?? '设置模块正在迁移中。')
const emptyDescription = computed(() => emptyDescriptions[moduleId.value ?? ''] ?? '暂无可用的设置模块。')

const openLegacyConfig = (): void => {
  legacyOpen.value = true
}

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
