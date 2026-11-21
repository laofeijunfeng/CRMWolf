<script lang="ts">
import { teamApi, type RoleSimpleResponse, type TeamMemberResponse } from '@/api/team'

// 同一流程编辑器里每个节点一个选择器：并发挂载时共用同一次成员请求，请求结束即释放。
const inflightMembers = new Map<number, Promise<TeamMemberResponse[]>>()
const fetchMembers = (teamId: number): Promise<TeamMemberResponse[]> => {
  const pending = inflightMembers.get(teamId)
  if (pending) return pending
  const request = teamApi.getTeamMembers(teamId).finally(() => inflightMembers.delete(teamId))
  inflightMembers.set(teamId, request)
  return request
}
</script>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronRight, Loader2 } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { ApprovalNodeAssignees, ApprovalUserSelection } from '@/api/approvalFlow'
import { useTeamStore } from '@/stores/team'
import { handleApiError } from '@/utils/errorHandler'

const props = withDefaults(defineProps<{
  modelValue: ApprovalNodeAssignees
  id?: string | undefined
  disabled?: boolean
  placeholder?: string
}>(), { id: undefined, disabled: false, placeholder: '选择角色或人员' })

const emit = defineEmits<{ 'update:modelValue': [value: ApprovalNodeAssignees] }>()
const teamStore = useTeamStore()

const open = ref(false)
const members = ref<TeamMemberResponse[]>([])
const activeRole = ref<string | null>(null)
const loadingRoles = ref(false)

const directory = computed(() => {
  const entries = new Map<string, { role: RoleSimpleResponse; users: TeamMemberResponse[] }>()
  for (const user of members.value) {
    for (const role of user.roles) {
      const entry = entries.get(role.code)
      if (entry) entry.users.push(user)
      else entries.set(role.code, { role, users: [user] })
    }
  }
  return entries
})
const roles = computed(() => [...directory.value.values()].map(entry => entry.role))
const activeRoleCode = computed(() => activeRole.value ?? roles.value[0]?.code ?? null)
const activeRoleUsers = computed(() => (activeRoleCode.value !== null ? directory.value.get(activeRoleCode.value)?.users ?? [] : []))
const selectedCount = computed(() => props.modelValue.roles.length + props.modelValue.users.length)
const roleLabel = (code: string): string => directory.value.get(code)?.role.name ?? code
const userLabel = (user: ApprovalUserSelection): string => members.value.find(item => item.id === user.user_id)?.name ?? `成员 #${user.user_id}`
const roleSelected = (code: string): boolean => props.modelValue.roles.includes(code)
const selectedUser = (role: string, userId: number): boolean => props.modelValue.users.some(user => user.role === role && user.user_id === userId)
const roleUserCount = (code: string): number => props.modelValue.users.filter(user => user.role === code).length

const update = (next: ApprovalNodeAssignees): void => emit('update:modelValue', { roles: [...new Set(next.roles)], users: next.users.filter((user, index, list) => list.findIndex(item => item.role === user.role && item.user_id === user.user_id) === index) })
const toggleRole = (code: string, checked: boolean): void => {
  const nextRoles = checked ? [...props.modelValue.roles, code] : props.modelValue.roles.filter(item => item !== code)
  update({ roles: nextRoles, users: props.modelValue.users })
}
const toggleUser = (role: string, userId: number, checked: boolean): void => {
  const users = checked
    ? [...props.modelValue.users, { role, user_id: userId }]
    : props.modelValue.users.filter(user => !(user.role === role && user.user_id === userId))
  update({ roles: props.modelValue.roles, users })
}

// 触发器要直接显示角色/成员名称，所以挂载即加载成员，不等弹层打开。
watch((): number | undefined => teamStore.currentTeam?.id, async (teamId, _, onCleanup): Promise<void> => {
  members.value = []
  activeRole.value = null
  if (teamId === undefined) return
  let cancelled = false
  onCleanup(() => { cancelled = true })
  loadingRoles.value = true
  try {
    const result = await fetchMembers(teamId)
    if (!cancelled) members.value = result
  } catch (error: unknown) {
    if (!cancelled) handleApiError(error, '获取审批人员')
  } finally {
    if (!cancelled) loadingRoles.value = false
  }
}, { immediate: true })
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button :id="id" type="button" variant="outline" class="approval-approver-picker" :disabled="disabled">
        <span v-if="selectedCount === 0" class="text-muted-foreground">{{ placeholder }}</span>
        <span v-else class="approval-approver-picker__chips">
          <Badge v-for="code in props.modelValue.roles" :key="`role-${code}`" variant="secondary">{{ roleLabel(code) }}（全部）</Badge>
          <Badge v-for="user in props.modelValue.users" :key="`user-${user.role}-${user.user_id}`" variant="outline">{{ userLabel(user) }}</Badge>
        </span>
      </Button>
    </PopoverTrigger>
    <PopoverContent align="start" class="w-[32rem] max-w-[calc(100vw-2rem)] p-0">
      <div v-if="loadingRoles" class="approval-approver-picker__loading"><Loader2 class="h-4 w-4 animate-spin" />加载中...</div>
      <div v-else-if="roles.length === 0" class="p-3 text-sm text-muted-foreground">当前团队暂无可选角色</div>
      <div v-else class="approval-approver-picker__panes">
        <div class="approval-approver-picker__pane" role="group" aria-label="角色">
          <div class="approval-approver-picker__pane-title">角色</div>
          <div
            v-for="role in roles"
            :key="role.code"
            :class="['approval-approver-picker__role-row', { 'is-active': role.code === activeRoleCode }]"
          >
            <Checkbox :checked="roleSelected(role.code)" :aria-label="`选择角色${role.name}（全部）`" @update:checked="toggleRole(role.code, $event)" />
            <button
              type="button"
              class="approval-approver-picker__role-open"
              :aria-pressed="role.code === activeRoleCode"
              :aria-label="`${role.name} · 选具体人员`"
              @click="activeRole = role.code"
            >
              <span class="truncate">{{ role.name }}</span>
              <span v-if="roleUserCount(role.code) > 0" class="text-xs text-muted-foreground">{{ roleUserCount(role.code) }}</span>
              <ChevronRight class="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            </button>
          </div>
        </div>
        <div v-if="activeRoleCode" class="approval-approver-picker__pane" role="group" :aria-label="`${roleLabel(activeRoleCode)} · 选具体人员`">
          <div class="approval-approver-picker__pane-title">{{ roleLabel(activeRoleCode) }} · 选具体人员</div>
          <p v-if="roleSelected(activeRoleCode)" class="text-xs text-muted-foreground">已选整个角色，角色内全部成员都会收到</p>
          <label v-for="user in activeRoleUsers" :key="user.id" class="approval-approver-picker__member">
            <Checkbox
              :checked="roleSelected(activeRoleCode) || selectedUser(activeRoleCode, user.id)"
              :disabled="roleSelected(activeRoleCode)"
              :aria-label="`选择成员${user.name}`"
              @update:checked="toggleUser(activeRoleCode, user.id, $event)"
            />
            <span class="truncate">{{ user.name }}</span>
          </label>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>

<style scoped lang="scss">
.approval-approver-picker { width: 100%; height: auto; justify-content: flex-start; min-height: var(--control-h-md); padding-top: .25rem; padding-bottom: .25rem; white-space: normal; text-align: left; }
.approval-approver-picker__chips { display: flex; flex-wrap: wrap; gap: .25rem; }
.approval-approver-picker__loading { display: flex; align-items: center; gap: .5rem; min-height: 2.5rem; padding: .75rem; color: hsl(var(--muted-foreground)); font-size: var(--font-size-caption); }
.approval-approver-picker__panes { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); max-height: min(22rem, 60vh); }
.approval-approver-picker__pane { display: flex; flex-direction: column; gap: .125rem; min-height: 0; overflow-y: auto; padding: .5rem; }
.approval-approver-picker__pane + .approval-approver-picker__pane { border-left: 1px solid hsl(var(--border)); }
.approval-approver-picker__pane-title { padding: .25rem .5rem; color: hsl(var(--muted-foreground)); font-size: var(--font-size-caption); font-weight: 600; }
.approval-approver-picker__role-row { display: flex; align-items: center; gap: .25rem; min-height: var(--touch-target); padding-left: .5rem; border-radius: var(--radius-sm); }
.approval-approver-picker__role-row.is-active { background: var(--wash-hover); }
.approval-approver-picker__role-open { display: flex; flex: 1; min-width: 0; align-items: center; gap: .5rem; min-height: var(--touch-target); padding-right: .25rem; text-align: left; }
.approval-approver-picker__role-open > .truncate { flex: 1; }
.approval-approver-picker__member { display: flex; gap: .5rem; align-items: center; min-height: var(--touch-target); padding: .25rem .5rem; border-radius: var(--radius-sm); }
.approval-approver-picker__member:hover { background: var(--wash-hover); }
</style>
