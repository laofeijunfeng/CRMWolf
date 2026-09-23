<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Plus, Trash2 } from 'lucide-vue-next'
import reminderRuleApi, { type ReminderRuleWrite } from '@/api/reminderRule'
import type { ReminderCondition, ReminderObjectCatalog, ReminderRecipient, ReminderRule, ReminderRuleRun } from '@/schemas/reminderRule'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import MultiSelect from '@/components/crmwolf/MultiSelect.vue'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import ErrorState from '@/components/ErrorState.vue'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { usePageTitle } from '@/composables/usePageTitle'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { getSettingsNavigationItem } from '@/settingsNavigation'
import { usePermissionStore } from '@/stores/permissions'
import { useTeamStore } from '@/stores/team'
import { toFeedbackError } from '@/types/feedback'
import type { FeedbackError } from '@/types/feedback'
import { handleApiError } from '@/utils/errorHandler'
import SettingsContent from '@/views/settings/SettingsContent.vue'

usePageTitle()

const REMINDER_TIME_OPTIONS = Array.from({ length: 21 }, (_, index) => {
  const minutes = 9 * 60 + index * 30
  const value = `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
  return { value, label: value }
})
const DEFAULT_CONDITIONS: Record<ReminderRule['object_type'], { statuses: string[], date: string, operator: string, days: number }> = {
  business_journey: { statuses: ['ACTIVE', 'WON'], date: 'last_effective_event_at', operator: 'older_than_days', days: 7 },
  opportunity: { statuses: ['FOLLOWING'], date: 'current_stage_entered_at', operator: 'older_than_days', days: 7 },
  customer: { statuses: ['FOLLOWING'], date: 'last_activity_at', operator: 'older_than_days', days: 7 },
  lead: { statuses: ['FOLLOWING'], date: 'last_modified_time', operator: 'older_than_days', days: 7 },
  follow_up_task: { statuses: ['OPEN'], date: 'due_at', operator: 'due_in_days', days: 0 },
  approval: { statuses: ['PENDING'], date: 'created_time', operator: 'older_than_days', days: 7 },
  payment_plan: { statuses: ['PENDING', 'OVERDUE', 'PARTIAL'], date: 'due_date', operator: 'due_in_days', days: 0 },
}

const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const { canAccess, permissionsUnavailable, permissionsPending } = useSettingsAccess()
const settingsItem = getSettingsNavigationItem('reminder-rules')
const hasAccess = computed(() => settingsItem !== undefined && canAccess(settingsItem))
const catalog = ref<ReminderObjectCatalog[]>([])
const catalogError = ref<FeedbackError | null>(null)
const canPublish = computed(() => permissionStore.hasPermission('automation:publish'))
const canCreate = computed(() => hasAccess.value && canPublish.value && permissionStore.hasPermission('automation:create') && catalog.value.length > 0 && catalogError.value === null)
const canEdit = computed(() => hasAccess.value && permissionStore.hasPermission('automation:edit') && catalog.value.length > 0 && catalogError.value === null)
const rules = ref<ReminderRule[]>([])
const runs = ref<ReminderRuleRun[]>([])
const teamMembers = ref<ReminderRecipient[]>([])
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const runsError = ref<FeedbackError | null>(null)
const recipientsError = ref<FeedbackError | null>(null)
const sheetOpen = ref(false)
const selectedRule = ref<ReminderRule | null>(null)
const saving = ref(false)
const saveError = ref<FeedbackError | null>(null)
const publishError = ref<FeedbackError | null>(null)
const draft = ref<ReminderRuleWrite>(blankRule())
let loadGeneration = 0
let editorSession = 0

function blankRule(): ReminderRuleWrite {
  return {
    version: 2,
    name: '',
    object_type: 'business_journey',
    trigger: 'schedule',
    status: null,
    inactive_days: null,
    date_field: null,
    offset_days: 0,
    require_no_new_activity: false,
    trigger_time: '09:00',
    conditions: [],
    recipients: [],
    message_title: '',
    message_template: '',
    channels: ['feishu'],
    notify_once_per_window: true,
  }
}

const activeObject = computed(() => catalog.value.find(item => item.object_type === draft.value.object_type))
const objectLabel = computed(() => activeObject.value?.label ?? '')
const fields = computed(() => activeObject.value?.fields ?? [])
const recipientChoices = computed(() => activeObject.value?.recipients ?? [])
const selectedTeamMembers = computed({
  get: () => draft.value.recipients.filter(value => value.startsWith('user:')).map(value => value.slice(5)),
  set: (userIds: string[]) => {
    draft.value.recipients = [
      ...draft.value.recipients.filter(value => !value.startsWith('user:')),
      ...userIds.map(id => `user:${id}`),
    ]
  },
})
const teamMemberOptions = computed(() => [
  ...draft.value.recipients
    .filter(value => value.startsWith('user:') && !teamMembers.value.some(member => member.id === value.slice(5)))
    .map(value => ({ value: value.slice(5), label: `已离开团队的成员 ${value.slice(5)}` })),
  ...teamMembers.value.map(member => ({ value: member.id, label: member.name })),
])
const conditionField = (condition: ReminderCondition): ReminderObjectCatalog['fields'][number] | undefined => fields.value.find(field => field.value === condition.field)
const conditionOptions = (condition: ReminderCondition): NonNullable<ReminderObjectCatalog['fields'][number]['options']> => conditionField(condition)?.options ?? []
const selectedObject = computed(() => catalog.value.find(item => item.object_type === selectedRule.value?.object_type))
const savedRecipientLabel = (recipient: string): string => selectedObject.value?.recipients.find(choice => choice.value === recipient)?.label
  ?? (recipient.startsWith('user:') ? teamMembers.value.find(member => member.id === recipient.slice(5))?.name : undefined)
  ?? recipient
const savedConditionLabel = (condition: ReminderCondition): string => {
  const field = selectedObject.value?.fields.find(item => item.value === condition.field)
  const operator = field?.operators.find(item => item.value === condition.operator)
  const value = Array.isArray(condition.value)
    ? conditionValues(condition).map(item => field?.options?.find(option => option.value === item)?.label ?? item).join('、')
    : typeof condition.value === 'boolean' ? (condition.value ? '是' : '否') : String(condition.value ?? '')
  return `${field?.label ?? condition.field} ${operator?.label ?? condition.operator}${value ? ` ${value}` : ''}`
}
const conditionValues = (condition: ReminderCondition): string[] => Array.isArray(condition.value) ? condition.value.filter((value): value is string => typeof value === 'string') : []

function defaultCondition(field: ReminderObjectCatalog['fields'][number]): ReminderCondition {
  const operator = field.operators[0]?.value ?? ''
  return {
    field: field.value,
    operator,
    value: operator === 'in' ? [] : operator === 'not_empty' ? true : '',
  }
}

function resetForObject(object: ReminderObjectCatalog, selectedUsers: string[] = []): void {
  const preferred = DEFAULT_CONDITIONS[object.object_type]
  const status = object.fields.find(field => field.value === 'status' && field.operators.some(op => op.value === 'in'))
  const date = object.fields.find(field => field.value === preferred.date && field.operators.some(op => op.value === preferred.operator))
  const conditions: ReminderCondition[] = []
  if (status) conditions.push({ field: status.value, operator: 'in', value: preferred.statuses.filter(value => status.options?.some(option => option.value === value) === true) })
  if (date) conditions.push({ field: date.value, operator: preferred.operator, value: preferred.days })
  draft.value = {
    ...blankRule(),
    object_type: object.object_type,
    name: `${object.label}定时提醒`,
    conditions,
    recipients: [...(object.recipients[0] ? [object.recipients[0].value] : []), ...selectedUsers],
    message_title: `${object.label}提醒`,
    message_template: `请关注${object.label}的最新进展。`,
  }
}

function addCondition(): void {
  const used = new Set((draft.value.conditions ?? []).map(item => item.field))
  const next = fields.value.find(field => !used.has(field.value))
  if (next) draft.value.conditions?.push(defaultCondition(next))
}

function removeCondition(index: number): void {
  draft.value.conditions?.splice(index, 1)
}

function changeConditionField(index: number, value: unknown): void {
  const next = fields.value.find(field => field.value === value)
  if (!next || draft.value.conditions?.some((item, position) => position !== index && item.field === next.value) === true) return
  draft.value.conditions?.splice(index, 1, defaultCondition(next))
}

function changeConditionOperator(index: number, value: unknown): void {
  const condition = draft.value.conditions?.[index]
  if (!condition || conditionField(condition)?.operators.some(operator => operator.value === value) !== true) return
  condition.operator = String(value)
  condition.value = value === 'in' ? [] : value === 'not_empty' ? true : ''
}

function updateConditionDays(condition: ReminderCondition, value: unknown): void {
  condition.value = value === '' ? '' : Number(value)
}

const canSaveDraft = computed(() => {
  const value = draft.value
  if (!activeObject.value || !(selectedRule.value ? canEdit.value && selectedRule.value.version === 2 : canCreate.value) || !REMINDER_TIME_OPTIONS.some(option => option.value === value.trigger_time)) return false
  if (!value.name.trim() || (value.message_title?.trim().length ?? 0) === 0 || !value.message_template.trim() || value.recipients.length === 0) return false
  if (value.recipients.some(recipient => !recipientChoices.value.some(choice => choice.value === recipient) && !(recipient.startsWith('user:') && teamMemberOptions.value.some(member => member.value === recipient.slice(5))))) return false
  const conditions = value.conditions ?? []
  if (!conditions.length || new Set(conditions.map(condition => condition.field)).size !== conditions.length) return false
  return conditions.every(condition => {
    const field = conditionField(condition)
    if (field?.operators.some(option => option.value === condition.operator) !== true) return false
    if (condition.operator === 'in') return Array.isArray(condition.value) && condition.value.length > 0 && new Set(condition.value).size === condition.value.length && condition.value.every(option => typeof option === 'string' && field.options?.some(choice => choice.value === option) === true)
    if (condition.operator === 'not_empty') return condition.value === true
    return (condition.operator === 'older_than_days' || condition.operator === 'due_in_days') && typeof condition.value === 'number' && Number.isInteger(condition.value) && condition.value >= 0 && condition.value <= 36500
  })
})

const sentence = computed(() => {
  const rows = (draft.value.conditions ?? []).map(condition => {
    const field = conditionField(condition)
    const operator = field?.operators.find(item => item.value === condition.operator)
    const value = condition.operator === 'in'
      ? conditionValues(condition).map(item => field?.options?.find(option => option.value === item)?.label ?? item).join('、')
      : condition.operator === 'not_empty' ? '' : ''
    return `${field?.label ?? condition.field} ${operator?.label?.replace('N', String(condition.value === '' ? '—' : condition.value)) ?? condition.operator}${value ? ` ${value}` : ''}`
  })
  const names = [
    ...recipientChoices.value.filter(choice => draft.value.recipients.includes(choice.value)).map(choice => choice.label),
    ...teamMembers.value.filter(member => draft.value.recipients.includes(`user:${member.id}`)).map(member => member.name),
  ]
  return `每天 ${draft.value.trigger_time ?? '—'} 检查${objectLabel.value}：${rows.length ? rows.join('，并且 ') : '请添加条件'}；满足时通知${names.join('、') || '待选择成员'}。`
})

const loadRules = async (expectedGeneration?: number): Promise<void> => {
  if (expectedGeneration !== undefined && expectedGeneration !== loadGeneration) return
  const generation = ++loadGeneration
  const teamId = teamStore.currentTeam?.id
  const isCurrent = (): boolean => generation === loadGeneration && teamStore.currentTeam?.id === teamId && hasAccess.value
  rules.value = []
  runs.value = []
  teamMembers.value = []
  catalog.value = []
  catalogError.value = null
  loadError.value = null
  runsError.value = null
  recipientsError.value = null
  publishError.value = null
  if (!sheetOpen.value) {
    saveError.value = null
    selectedRule.value = null
    draft.value = blankRule()
  }
  loading.value = hasAccess.value && teamId !== undefined
  if (!loading.value) return
  try {
    const nextCatalog = await reminderRuleApi.catalog()
    if (!isCurrent()) return
    catalog.value = nextCatalog
    if (nextCatalog.length === 0) catalogError.value = { title: '无法加载提醒字段', description: '服务端未提供可用的提醒对象。' }
  } catch (error: unknown) {
    if (!isCurrent()) return
    catalogError.value = toFeedbackError(error, '提醒字段')
  }
  try {
    const nextRules = await reminderRuleApi.list()
    if (!isCurrent()) return
    rules.value = nextRules
  } catch (error: unknown) {
    if (!isCurrent()) return
    loadError.value = toFeedbackError(error, '提醒规则')
  }
  try {
    const nextRuns = await reminderRuleApi.listRuns()
    if (!isCurrent()) return
    runs.value = nextRuns
  } catch (error: unknown) {
    if (!isCurrent()) return
    runsError.value = toFeedbackError(error, '运行记录')
  }
  try {
    const nextMembers = await reminderRuleApi.recipients()
    if (!isCurrent()) return
    teamMembers.value = nextMembers
  } catch (error: unknown) {
    if (!isCurrent()) return
    recipientsError.value = toFeedbackError(error, '团队成员')
  } finally {
    if (isCurrent()) loading.value = false
  }
}

const openCreate = (): void => {
  if (saving.value) return
  const first = catalog.value[0]
  if (!canCreate.value || !first) return
  selectedRule.value = null
  saveError.value = null
  resetForObject(first)
  editorSession += 1
  sheetOpen.value = true
}

const openRule = (rule: ReminderRule): void => {
  if (saving.value) return
  selectedRule.value = rule
  saveError.value = null
  if (rule.version === 2) {
    draft.value = {
      version: 2,
      name: rule.name,
      object_type: rule.object_type,
      trigger: rule.trigger,
      status: rule.status ?? null,
      inactive_days: rule.inactive_days ?? null,
      date_field: rule.date_field ?? null,
      offset_days: rule.offset_days ?? 0,
      require_no_new_activity: rule.require_no_new_activity,
      trigger_time: rule.trigger_time ?? null,
      conditions: rule.conditions.map(condition => ({ ...condition, value: condition.operator === 'in' ? conditionValues(condition) : condition.value })),
      recipients: [...rule.recipients],
      message_title: rule.message_title ?? null,
      message_template: rule.message_template,
      channels: rule.channels.filter((channel): channel is 'in_app' | 'feishu' => channel === 'in_app' || channel === 'feishu'),
      notify_once_per_window: rule.notify_once_per_window,
    }
  }
  editorSession += 1
  sheetOpen.value = true
}

const closeSheet = (): void => {
  if (saving.value) return
  sheetOpen.value = false
}

const selectObject = (value: unknown): void => {
  const object = catalog.value.find(item => item.object_type === value)
  if (!object) return
  const selectedUsers = draft.value.recipients.filter(recipient => recipient.startsWith('user:'))
  resetForObject(object, selectedUsers)
}

const updateObjectRecipients = (values: string[]): void => {
  draft.value.recipients = [
    ...values,
    ...draft.value.recipients.filter(value => value.startsWith('user:')),
  ]
}

const saveRule = async (): Promise<void> => {
  if (!canSaveDraft.value || saving.value) return
  const generation = loadGeneration
  const session = editorSession
  saveError.value = null
  saving.value = true
  try {
    if (selectedRule.value) await reminderRuleApi.update(selectedRule.value.id, draft.value, selectedRule.value.revision)
    else await reminderRuleApi.create(draft.value)
    if (generation !== loadGeneration || session !== editorSession) return
    sheetOpen.value = false
    toast.success(selectedRule.value ? '提醒规则已更新' : '提醒规则已启用')
    await loadRules(generation)
  } catch (error: unknown) {
    if (generation === loadGeneration && session === editorSession) {
      if (selectedRule.value && (error as { response?: { status?: number } })?.response?.status === 409) {
        saveError.value = { title: '提醒规则已被他人修改', description: '请刷新后重试；当前未保存的草稿仍保留在编辑器中。' }
      } else handleApiError(error, '保存提醒规则')
    }
  } finally {
    saving.value = false
  }
}

const toggleEnabled = async (rule: ReminderRule, enabled: boolean): Promise<void> => {
  if (!canPublish.value || saving.value) return
  const generation = loadGeneration
  const teamId = teamStore.currentTeam?.id
  publishError.value = null
  try {
    const updated = await reminderRuleApi.setEnabled(rule.id, enabled, rule.revision)
    if (generation !== loadGeneration || teamStore.currentTeam?.id !== teamId) return
    const current = rules.value.find(item => item.id === updated.id)
    if (current && current.revision <= updated.revision) {
      rules.value = rules.value.map(item => item.id === updated.id ? updated : item)
    }
  } catch (error: unknown) {
    if (generation === loadGeneration && teamStore.currentTeam?.id === teamId) {
      if ((error as { response?: { status?: number } })?.response?.status === 409) {
        publishError.value = { title: '提醒规则已被他人修改', description: '请刷新后重试。' }
      } else handleApiError(error, enabled ? '启用提醒规则' : '停用提醒规则')
    }
  }
}

useTopBarRegistration({
  actionDeps: [canCreate],
  actions: () => [{ id: 'create-reminder-rule', label: '新建规则', type: 'primary', icon: Plus, visible: canCreate.value, handler: openCreate }],
})

watch([hasAccess, (): number | undefined => teamStore.currentTeam?.id], (): void => { void loadRules() }, { immediate: true })
</script>

<template>
  <SettingsContent ariaLabel="提醒规则" description="当业务对象满足条件时通知相关人。规则按团队生效，不改变审批结果，也不自动修改客户、商机或回款。">
    <ErrorState v-if="permissionsUnavailable" variant="error" title="权限信息暂不可用" description="暂时无法确认你的团队设置权限。" />
    <ErrorState v-else-if="permissionsPending" variant="error" title="正在同步权限" description="正在确认你的访问权限，请稍候。" />
    <ErrorState v-else-if="!hasAccess" variant="forbidden" title="暂无访问权限" description="你没有访问提醒规则的权限。" />
    <Tabs v-else default-value="rules">
      <TabsList>
        <TabsTrigger value="rules">规则</TabsTrigger>
        <TabsTrigger value="runs">运行记录</TabsTrigger>
      </TabsList>
      <TabsContent value="rules">
        <ErrorState v-if="catalogError" variant="error" :title="catalogError.title" :description="catalogError.description" />
        <ErrorState v-if="recipientsError" variant="error" :title="recipientsError.title" :description="recipientsError.description" />
        <ErrorState v-if="publishError" variant="error" :title="publishError.title" :description="publishError.description" />
        <ErrorState v-if="loadError" variant="error" :title="loadError.title" :description="loadError.description" />
        <div v-if="!loadError && rules.length === 0" class="rounded-lg border border-dashed p-8 text-sm text-muted-foreground">
          {{ loading ? '正在加载提醒规则' : '还没有提醒规则。新建一条按字段条件每天检查的提醒。' }}
        </div>
        <div v-else-if="rules.length" class="divide-y">
          <article v-for="rule in rules" :key="rule.id" class="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 py-4">
            <Switch :model-value="rule.enabled" :disabled="!canPublish || saving" :aria-label="`${rule.enabled ? '停用' : '启用'}${rule.name}`" @update:model-value="toggleEnabled(rule, $event)" />
            <button type="button" class="min-w-0 rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-60" :disabled="saving" :aria-label="`查看${rule.name}详情`" @click="openRule(rule)"><span class="font-medium">{{ rule.name }}</span><span class="mt-1 block text-sm text-muted-foreground">{{ rule.version === 1 && rule.trigger === 'change' ? '旧版状态变化规则不执行，请停用后新建每日检查规则。' : rule.sentence }}</span></button>
            <Badge variant="secondary">{{ catalog.find(item => item.object_type === rule.object_type)?.label ?? rule.object_type }}</Badge>
          </article>
        </div>
      </TabsContent>
      <TabsContent value="runs">
        <ErrorState v-if="runsError" variant="error" :title="runsError.title" :description="runsError.description" />
        <div v-if="runs.length === 0" class="py-8 text-sm text-muted-foreground">还没有发出的提醒。</div>
        <article v-for="run in runs" :key="run.id" class="border-b py-4">
          <div class="font-medium">{{ run.message }}</div>
          <p class="mt-1 text-sm text-muted-foreground">送达 {{ run.sent_count }} 人，跳过 {{ run.skipped_count }} 人</p>
        </article>
      </TabsContent>
    </Tabs>
  </SettingsContent>

  <Sheet :open="sheetOpen" @update:open="(open: boolean): void => { if (!open) closeSheet() }">
    <SheetContent class="flex w-[min(1120px,calc(100vw-2rem))] max-w-none flex-col p-0 sm:max-w-none" @interact-outside="(event: Event): void => { if (saving) event.preventDefault() }" @escape-key-down="(event: Event): void => { if (saving) event.preventDefault() }">
      <SheetHeader class="px-4 pt-4 sm:px-6 sm:pt-6">
        <SheetTitle>{{ selectedRule ? selectedRule.version === 2 && canEdit ? '编辑提醒' : '提醒详情' : '新建提醒' }}</SheetTitle>
        <SheetDescription>{{ selectedRule && (selectedRule.version !== 2 || !canEdit) ? '查看已保存的规则内容。' : '设置触发时间和字段条件，再配置飞书消息。' }}</SheetDescription>
      </SheetHeader>
      <ErrorState v-if="saveError" variant="error" :title="saveError.title" :description="saveError.description" class="mx-4 mt-4 sm:mx-6" />
      <div v-if="selectedRule && (selectedRule.version !== 2 || !canEdit)" class="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
        <p v-if="selectedRule.version !== 2" class="text-sm text-muted-foreground">旧版规则仅供查看，不能使用新版编辑器修改。</p>
        <dl class="space-y-3 text-sm">
          <div><dt class="font-medium">名称</dt><dd>{{ selectedRule.name }}</dd></div>
          <div><dt class="font-medium">业务对象</dt><dd>{{ selectedObject?.label ?? selectedRule.object_type }}</dd></div>
          <div><dt class="font-medium">触发方式</dt><dd>{{ selectedRule.sentence }}</dd></div>
          <div v-if="selectedRule.status"><dt class="font-medium">状态</dt><dd>{{ selectedObject?.fields.find(field => field.value === 'status')?.options?.find(option => option.value === selectedRule?.status)?.label ?? selectedRule.status }}</dd></div>
          <div v-if="selectedRule.inactive_days !== null && selectedRule.inactive_days !== undefined"><dt class="font-medium">静默天数</dt><dd>{{ selectedRule.inactive_days }} 天</dd></div>
          <div v-if="selectedRule.date_field"><dt class="font-medium">日期字段</dt><dd>{{ selectedRule.date_field }}</dd></div>
          <div v-if="selectedRule.trigger_time"><dt class="font-medium">提醒时间</dt><dd>{{ selectedRule.trigger_time }}</dd></div>
          <div v-if="selectedRule.offset_days !== null && selectedRule.offset_days !== undefined"><dt class="font-medium">提前量</dt><dd>{{ selectedRule.offset_days < 0 ? `提前 ${-selectedRule.offset_days} 天` : selectedRule.offset_days > 0 ? `延后 ${selectedRule.offset_days} 天` : '当天' }}</dd></div>
          <div v-if="selectedRule.require_no_new_activity"><dt class="font-medium">附加条件</dt><dd>期间没有新的客户活动</dd></div>
          <div v-if="selectedRule.conditions.length"><dt class="font-medium">条件</dt><dd v-for="(condition, index) in selectedRule.conditions" :key="index">{{ savedConditionLabel(condition) }}</dd></div>
          <div><dt class="font-medium">接收人</dt><dd>{{ selectedRule.recipients.map(savedRecipientLabel).join('、') }}</dd></div>
          <div v-if="selectedRule.message_title"><dt class="font-medium">消息标题</dt><dd>{{ selectedRule.message_title }}</dd></div>
          <div><dt class="font-medium">通知渠道</dt><dd>{{ selectedRule.channels.map(channel => channel === 'in_app' ? '站内通知' : channel === 'feishu' ? '飞书通知' : channel).join('、') }}</dd></div>
          <div><dt class="font-medium">消息内容</dt><dd class="whitespace-pre-wrap">{{ selectedRule.message_template }}</dd></div>
        </dl>
      </div>
      <div v-else class="grid min-h-0 flex-1 gap-4 overflow-y-auto bg-muted/40 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        <section class="space-y-3">
          <h3 class="text-sm font-semibold">当以下情况发生时</h3>
          <div class="space-y-4 rounded-xl border bg-background p-4">
            <p class="text-xs text-muted-foreground">第 1 步</p>
            <div class="space-y-2"><Label for="reminder-rule-name">规则名称</Label><Input id="reminder-rule-name" :model-value="draft.name" placeholder="规则名称" @update:model-value="draft.name = String($event)" /></div>
            <div class="space-y-2">
              <Label>选择业务对象</Label>
              <Select :model-value="draft.object_type" @update:model-value="selectObject">
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem v-for="item in catalog" :key="item.object_type" :value="item.object_type">{{ item.label }}</SelectItem></SelectContent>
              </Select>
            </div>
            <div class="space-y-2">
              <Label>每日检查时间</Label>
              <Select :model-value="draft.trigger_time ?? '09:00'" @update:model-value="draft.trigger_time = String($event)">
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent class="max-h-72"><SelectItem v-for="option in REMINDER_TIME_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</SelectItem></SelectContent>
              </Select>
              <p class="text-xs text-muted-foreground">每天到点检查所有条件；日期字段变化后才重新提醒。仅有非日期条件的规则每个对象只提醒一次。</p>
            </div>
          </div>
          <div class="space-y-3 rounded-xl border bg-background p-4">
            <h4 class="text-sm font-medium">同时满足以下条件</h4>
            <div class="hidden grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.2fr)_auto] gap-2 px-3 text-xs text-muted-foreground sm:grid">
              <span>字段</span><span>条件</span><span>值</span><span class="w-9" />
            </div>
            <div v-for="(condition, index) in draft.conditions" :key="index" class="grid items-center gap-2 rounded-lg bg-muted/50 p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.2fr)_auto]">
              <Select :model-value="condition.field" @update:model-value="changeConditionField(index, $event)">
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="field in fields" :key="field.value" :value="field.value" :disabled="draft.conditions?.some((item, position) => item.field === field.value && position !== index) ?? false">{{ field.label }}</SelectItem>
                </SelectContent>
              </Select>
              <Select :model-value="condition.operator" @update:model-value="changeConditionOperator(index, $event)">
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem v-for="operator in conditionField(condition)?.operators ?? []" :key="operator.value" :value="operator.value">{{ operator.label }}</SelectItem></SelectContent>
              </Select>
              <MultiSelect v-if="condition.operator === 'in'" :model-value="conditionValues(condition)" :options="conditionOptions(condition)" placeholder="选择状态" @update:model-value="condition.value = $event" />
              <Input v-else-if="condition.operator === 'not_empty'" value="是" disabled aria-label="不为空" />
              <div v-else class="flex items-center gap-2"><Input :model-value="String(condition.value ?? '')" type="number" min="0" max="36500" step="1" aria-label="天数" @update:model-value="updateConditionDays(condition, $event)" /><span class="text-sm">天</span></div>
              <Button type="button" size="icon" variant="ghost" aria-label="删除条件" @click="removeCondition(index)"><Trash2 class="h-4 w-4" /></Button>
            </div>
            <Button type="button" variant="outline" size="sm" :disabled="draft.conditions?.length === fields.length" @click="addCondition"><Plus class="mr-1 h-4 w-4" />并且</Button>
          </div>
        </section>
        <div class="hidden items-center justify-center text-muted-foreground md:flex">→</div>
        <section class="space-y-3">
          <h3 class="text-sm font-semibold">就执行以下操作</h3>
          <div class="space-y-4 rounded-xl border bg-background p-4">
            <Button type="button" variant="secondary" class="justify-start">发送飞书消息</Button>
            <div class="space-y-2"><Label>对象成员</Label><MultiSelect :model-value="draft.recipients.filter(value => !value.startsWith('user:'))" :options="recipientChoices" placeholder="选择对象成员" @update:model-value="updateObjectRecipients" /></div>
            <div class="space-y-2"><Label>指定团队成员</Label><MultiSelect v-model="selectedTeamMembers" :options="teamMemberOptions" placeholder="选择一个或多个团队成员" /></div>
            <div class="space-y-2"><Label>标题</Label><Input :model-value="draft.message_title ?? ''" placeholder="填写飞书消息标题" @update:model-value="draft.message_title = String($event)" /></div>
            <div class="space-y-2"><Label>内容</Label><Textarea v-model="draft.message_template" class="min-h-40" /></div>
            <p class="rounded-lg bg-muted p-3 text-sm leading-6">{{ sentence }}</p>
          </div>
        </section>
      </div>
      <SheetFooter class="border-t px-4 py-4 sm:px-6"><Button variant="outline" :disabled="saving" @click="closeSheet">{{ selectedRule && (selectedRule.version !== 2 || !canEdit) ? '关闭' : '取消' }}</Button><Button v-if="!selectedRule || (selectedRule.version === 2 && canEdit)" :disabled="saving || !canSaveDraft" @click="saveRule">{{ selectedRule ? '保存修改' : '保存并启用' }}</Button></SheetFooter>
    </SheetContent>
  </Sheet>
</template>
