import { describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, reactive, type PropType } from 'vue'
import SettingsReminderRulesPage from '@/views/settings/SettingsReminderRulesPage.vue'
import reminderRuleApi from '@/api/reminderRule'
import { ReminderObjectCatalogSchema, type ReminderObjectCatalog, type ReminderRule } from '@/schemas/reminderRule'

vi.mock('@/api/reminderRule', () => ({ default: { list: vi.fn().mockResolvedValue([]), listRuns: vi.fn().mockResolvedValue([]), catalog: vi.fn(), recipients: vi.fn().mockResolvedValue([]), create: vi.fn().mockResolvedValue({}), update: vi.fn(), setEnabled: vi.fn() } }))
const teamState = reactive({ currentTeam: { id: 1 } })
vi.mock('@/stores/team', () => ({ useTeamStore: (): typeof teamState => teamState }))
const permissionState = reactive({ read: true, create: true, publish: true, edit: true })
vi.mock('@/stores/permissions', () => ({ usePermissionStore: (): { hasPermission: (value: string) => boolean } => ({ hasPermission: (value: string): boolean => value === 'automation:read' ? permissionState.read : value === 'automation:create' ? permissionState.create : value === 'automation:publish' ? permissionState.publish : value === 'automation:edit' ? permissionState.edit : true }) }))
vi.mock('@/composables/useSettingsAccess', () => ({ useSettingsAccess: (): { canAccess: () => boolean, permissionsUnavailable: boolean, permissionsPending: boolean } => ({ canAccess: (): boolean => permissionState.read, permissionsUnavailable: false, permissionsPending: false }) }))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: (): void => undefined }))
const topBar = vi.hoisted((): { open: () => void, visible: () => boolean } => ({ open: (): void => undefined, visible: (): boolean => false }))
vi.mock('@/composables/useTopBarRegistration', () => ({ useTopBarRegistration: (config: { actions: () => { handler: () => void, visible: boolean }[] }): void => { topBar.open = (): void => { required(config.actions()[0]).handler() }; topBar.visible = (): boolean => required(config.actions()[0]).visible } }))

function required<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error('Missing reminder test fixture or editor element')
  return value
}

const catalog: ReminderObjectCatalog[] = [
  { object_type: 'business_journey', label: '业务旅程', recipients: [{ value: 'primary_opportunity_owner', label: '主商机负责人' }], fields: [
    { value: 'status', label: '旅程状态', operators: [{ value: 'in', label: '属于' }], options: [{ value: 'ACTIVE', label: '进行中' }, { value: 'WON', label: '已赢单' }] },
    ...['last_effective_event_at', 'started_at', 'closed_at', 'created_time'].map((value) => ({ value, label: `日期 ${value}`, operators: [{ value: 'older_than_days', label: '已过去至少 N 天' }] })),
    { value: 'customer_owner', label: '客户负责人', operators: [{ value: 'not_empty', label: '不为空' }] },
  ] },
  ...([
    ['opportunity', 'current_stage_entered_at', 'FOLLOWING', 'owner'],
    ['customer', 'last_activity_at', 'FOLLOWING', 'owner'],
    ['lead', 'last_modified_time', 'FOLLOWING', 'owner'],
    ['follow_up_task', 'due_at', 'OPEN', 'owner'],
    ['approval', 'created_time', 'PENDING', 'submitter'],
    ['payment_plan', 'due_date', 'PENDING', 'contract_owner'],
  ] as const).map(([object_type, dateField, status, owner]) => ({ object_type, label: object_type, recipients: [{ value: owner, label: '负责人' }], fields: [
    { value: 'status', label: '状态', operators: [{ value: 'in', label: '属于' }], options: [{ value: status, label: status }, ...(object_type === 'payment_plan' ? [{ value: 'OVERDUE', label: '逾期' }, { value: 'PARTIAL', label: '部分回款' }] : object_type === 'opportunity' ? [{ value: 'WON', label: '已赢单' }] : [])] },
    { value: dateField, label: `日期 ${dateField}`, operators: [{ value: 'older_than_days', label: '已过去至少 N 天' }, ...(['follow_up_task', 'payment_plan'].includes(object_type) ? [{ value: 'due_in_days', label: '到期前 N 天起（含逾期）' }] : [])] },
    ...(object_type === 'opportunity' ? [{ value: 'expected_closing_date', label: '预计成交日期', operators: [{ value: 'older_than_days', label: '已过去至少 N 天' }, { value: 'due_in_days', label: '到期前 N 天起（含逾期）' }] }] : []),
    { value: owner, label: '负责人', operators: [{ value: 'not_empty', label: '不为空' }] },
  ] })),
]
const savedRule: ReminderRule = {
  id: 42, name: '业务旅程定时提醒', object_type: 'business_journey', trigger: 'schedule', version: 2,
  status: null, inactive_days: null, date_field: null, offset_days: 0, require_no_new_activity: false,
  trigger_time: '09:00', conditions: [{ field: 'status', operator: 'in', value: ['ACTIVE'] }],
  recipients: ['primary_opportunity_owner'], message_title: '业务旅程提醒', message_template: '请关注业务旅程。',
  channels: ['feishu'], notify_once_per_window: true, enabled: true, sentence: '每天检查业务旅程',
  revision: 1, created_time: '2026-09-23T09:00:00', last_modified_time: '2026-09-23T09:00:00',
}

const Switch = defineComponent({
  props: { modelValue: { type: Boolean, default: false }, disabled: { type: Boolean, default: false } },
  emits: ['update:modelValue'],
  template: '<button type="button" role="switch" :aria-checked="String(modelValue)" :disabled="disabled" @click="$emit(\'update:modelValue\', !modelValue)" />',
})

const slot = { template: '<div><slot /></div>' }
const Select = defineComponent({ props: { modelValue: { type: String, default: '' } }, emits: ['update:modelValue'], template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>' })
const SelectItem = defineComponent({ props: { value: { type: String, required: true }, disabled: { type: Boolean, default: false } }, template: '<option :value="value" :disabled="disabled"><slot /></option>' })
const MultiSelect = defineComponent({ props: { modelValue: { type: Array as PropType<string[]>, required: true }, options: { type: Array as PropType<{ value: string, label: string }[]>, required: true } }, emits: ['update:modelValue'], template: '<div class="multi-select"><button v-for="option in options" :key="option.value" type="button" @click="$emit(\'update:modelValue\', modelValue.includes(option.value) ? modelValue.filter(value => value !== option.value) : [...modelValue, option.value])">{{ option.label }}</button></div>' })
async function mountEditor(catalogResponse: Promise<ReminderObjectCatalog[]> = Promise.resolve(catalog)): Promise<VueWrapper> {
  vi.mocked(reminderRuleApi.catalog).mockImplementation(() => catalogResponse)
  const wrapper = shallowMount(SettingsReminderRulesPage, { global: { stubs: {
    SettingsContent: slot, Sheet: slot, SheetContent: slot, SheetHeader: slot, SheetFooter: slot, SheetTitle: slot, SheetDescription: slot,
    Tabs: slot, TabsList: slot, TabsContent: slot, TabsTrigger: slot, Select, SelectContent: slot, SelectItem, SelectTrigger: slot, SelectValue: true,
    MultiSelect, Input: defineComponent({ props: { modelValue: { type: [String, Number], default: undefined }, value: { type: String, default: undefined }, type: { type: String, default: undefined }, min: { type: String, default: undefined } }, emits: ['update:modelValue'], template: '<input :value="modelValue ?? value" :type="type" :min="min" @input="$emit(\'update:modelValue\', $event.target.value)" />' }),
    Textarea: defineComponent({ props: { modelValue: { type: String, default: '' } }, emits: ['update:modelValue'], template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' }),
    Button: defineComponent({ props: { disabled: { type: Boolean, default: false } }, template: '<button :disabled="disabled"><slot /></button>' }),
    Label: slot, Badge: slot, ErrorState: defineComponent({ props: { title: { type: String, required: true }, description: { type: String, default: '' } }, template: '<div role="alert">{{ title }} {{ description }}</div>' }), Switch,
  } } })
  await flushPromises()
  if (topBar.visible()) topBar.open()
  await flushPromises()
  return wrapper
}

describe('reminder catalog editor', () => {
  it('uses catalog for each object, resets executable defaults, and saves a scheduled v2 rule', async () => {
    const wrapper = await mountEditor()
    expect(reminderRuleApi.catalog).toHaveBeenCalled()
    const object = wrapper.find('select')
    expect(object.findAll('option')).toHaveLength(7)
    expect(wrapper.text()).toContain('日期 last_effective_event_at')
    expect(wrapper.text()).toContain('日期 started_at')
    expect(wrapper.text()).toContain('日期 closed_at')
    expect(wrapper.text()).toContain('日期 created_time')
    expect(wrapper.text()).not.toContain('状态发生变化时提醒')
    for (const entry of catalog.slice(1)) {
      required(wrapper.findAllComponents(Select)[0]).vm.$emit('update:modelValue', entry.object_type)
      await flushPromises()
      expect(wrapper.text()).toContain(required(entry.fields[1]).label)
      expect(wrapper.text()).not.toContain('业务旅程名称')
      expect(wrapper.text()).toContain('09:00')
      expect(wrapper.text()).toContain('天')
      const save = required(wrapper.findAll('button').find(button => button.text().includes('保存并启用')))
      expect(save.attributes('disabled')).toBeUndefined()
      await save.trigger('click')
      await flushPromises()
      const payload = required(vi.mocked(reminderRuleApi.create).mock.lastCall)[0]
      expect(payload).toMatchObject({ version: 2, object_type: entry.object_type, trigger: 'schedule', trigger_time: '09:00', status: null, inactive_days: null, date_field: null, offset_days: 0, require_no_new_activity: false, channels: ['feishu'], notify_once_per_window: true })
      expect(payload.conditions).toEqual([
        { field: 'status', operator: 'in', value: entry.object_type === 'payment_plan' ? ['PENDING', 'OVERDUE', 'PARTIAL'] : [required(required(required(entry.fields[0]).options)[0]).value] },
        { field: required(entry.fields[1]).value, operator: ['follow_up_task', 'payment_plan'].includes(entry.object_type) ? 'due_in_days' : 'older_than_days', value: ['follow_up_task', 'payment_plan'].includes(entry.object_type) ? 0 : 7 },
      ])
      expect(payload.message_template).not.toContain('{业务旅程名称}')
    }
    wrapper.unmount()
  })

  it('edits deadline operator and days; rejects empty statuses, duplicate fields, and invalid days', async () => {
    const wrapper = await mountEditor()
    let selects = wrapper.findAllComponents(Select)
    let save = required(wrapper.findAll('button').find(button => button.text().includes('保存并启用')))
    required(selects[0]).vm.$emit('update:modelValue', 'opportunity')
    await flushPromises()
    selects = wrapper.findAllComponents(Select)
    required(selects[4]).vm.$emit('update:modelValue', 'expected_closing_date')
    await flushPromises()
    selects = wrapper.findAllComponents(Select)
    required(selects[5]).vm.$emit('update:modelValue', 'due_in_days')
    await flushPromises()
    save = required(wrapper.findAll('button').find(button => button.text().includes('保存并启用')))
    expect(save.attributes('disabled')).toBeDefined()
    const days = wrapper.find('input[type="number"]')
    await days.setValue('3')
    expect(save.attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('预计成交日期 到期前 3 天起（含逾期）')
    const statusSelect = wrapper.findComponent(MultiSelect)
    statusSelect.vm.$emit('update:modelValue', [])
    await flushPromises()
    expect(save.attributes('disabled')).toBeDefined()
    statusSelect.vm.$emit('update:modelValue', ['WON'])
    await flushPromises()
    await days.setValue('1.5')
    expect(save.attributes('disabled')).toBeDefined()
    await days.setValue('36501')
    expect(save.attributes('disabled')).toBeDefined()
    await days.setValue('36500')
    expect(save.attributes('disabled')).toBeUndefined()
    expect(days.attributes('max')).toBe('36500')
    await days.setValue('3')
    const add = required(wrapper.findAll('button').find(button => button.text().includes('并且')))
    await add.trigger('click')
    expect(save.attributes('disabled')).toBeDefined()
    selects = wrapper.findAllComponents(Select)
    const addedField = required(selects[6])
    expect(addedField.findAll('option').find(option => option.attributes('value') === 'status')?.attributes('disabled')).toBeDefined()
    addedField.vm.$emit('update:modelValue', 'owner')
    await flushPromises()
    expect(wrapper.findAll('button').find(button => button.text().includes('保存并启用'))?.attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('不为空')
    expect(wrapper.text()).toContain('已赢单')
    await required(wrapper.findAll('button').filter(button => button.attributes('aria-label') === '删除条件')[2]).trigger('click')
    await flushPromises()
    expect(wrapper.findAll('button').find(button => button.text().includes('保存并启用'))?.attributes('disabled')).toBeUndefined()
    await required(wrapper.findAll('button').find(button => button.text().includes('保存并启用'))).trigger('click')
    expect(required(vi.mocked(reminderRuleApi.create).mock.lastCall)[0]).toMatchObject({
      trigger_time: '09:00', object_type: 'opportunity', version: 2,
      conditions: [{ field: 'status', operator: 'in', value: ['WON'] }, { field: 'expected_closing_date', operator: 'due_in_days', value: 3 }],
    })
    wrapper.unmount()
  })

  it('saves selected journey date and daily time, then supports a status-only rule', async () => {
    const wrapper = await mountEditor()
    let selects = wrapper.findAllComponents(Select)
    required(selects[4]).vm.$emit('update:modelValue', 'started_at')
    await flushPromises()
    await wrapper.find('input[type="number"]').setValue('5')
    selects = wrapper.findAllComponents(Select)
    required(selects[1]).vm.$emit('update:modelValue', '16:30')
    await flushPromises()
    await required(wrapper.findAll('button').filter(button => button.attributes('aria-label') === '删除条件')[1]).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('仅有非日期条件的规则每个对象只提醒一次')
    await required(wrapper.findAll('button').find(button => button.text().includes('保存并启用'))).trigger('click')
    expect(required(vi.mocked(reminderRuleApi.create).mock.lastCall)[0]).toMatchObject({
      object_type: 'business_journey', trigger_time: '16:30',
      conditions: [{ field: 'status', operator: 'in', value: ['ACTIVE', 'WON'] }],
    })
    wrapper.unmount()
  })

  it('accepts server catalogs with null options on non-status fields', async () => {
    const serverCatalog = catalog.map(object => ({
      ...object,
      fields: object.fields.map(field => ({ ...field, options: field.value === 'status' ? field.options : null })),
    }))
    const response = ReminderObjectCatalogSchema.array().parse(serverCatalog)
    const wrapper = await mountEditor(Promise.resolve(response))
    expect(topBar.visible()).toBe(true)
    expect(wrapper.find('select').findAll('option')).toHaveLength(7)
    expect(wrapper.findAll('button').find(button => button.text().includes('保存并启用'))?.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('loads active explicit recipients and discards stale team results', async () => {
    teamState.currentTeam.id = 1
    vi.mocked(reminderRuleApi.recipients).mockResolvedValueOnce([{ id: '11', name: '甲团队成员' }])
    const wrapper = await mountEditor()
    expect(wrapper.text()).toContain('甲团队成员')
    let resolveOldCatalog: (value: ReminderObjectCatalog[]) => void = () => undefined
    const oldCatalog = new Promise<ReminderObjectCatalog[]>(resolve => { resolveOldCatalog = resolve })
    vi.mocked(reminderRuleApi.catalog).mockImplementationOnce(() => oldCatalog)
    teamState.currentTeam.id = 2
    await flushPromises()
    expect(vi.mocked(reminderRuleApi.catalog).mock.calls.length).toBeGreaterThan(1)
    expect(topBar.visible()).toBe(false)
    expect(wrapper.text()).not.toContain('甲团队成员')
    vi.mocked(reminderRuleApi.catalog).mockResolvedValueOnce(catalog.slice(1))
    teamState.currentTeam.id = 3
    await flushPromises()
    expect(wrapper.find('select').findAll('option')).toHaveLength(6)
    resolveOldCatalog(catalog)
    await flushPromises()
    expect(wrapper.find('select').findAll('option')).toHaveLength(6)
    wrapper.unmount()
    teamState.currentTeam.id = 1
  })

  it('does not offer enabled-rule creation without publish permission', async () => {
    permissionState.publish = false
    const wrapper = await mountEditor()
    expect(topBar.visible()).toBe(false)
    expect(wrapper.findAll('button').find(button => button.text().includes('保存并启用'))?.attributes('disabled')).toBeDefined()
    wrapper.unmount()
    permissionState.publish = true
  })

  it('does not expose a create editor when catalog cannot load', async () => {
    const wrapper = await mountEditor(Promise.reject(new Error('catalog unavailable')))
    expect(topBar.visible()).toBe(false)
    expect(required(wrapper.findAllComponents(Select)[0]).findAll('option')).toHaveLength(0)
    expect(wrapper.findAll('button').find(button => button.text().includes('保存并启用'))?.attributes('disabled')).toBeDefined()
    expect(wrapper.find('[role="alert"]').text()).toContain('提醒字段')
    wrapper.unmount()
  })
})

describe('saved reminder rules', () => {
  it('shows a newly saved rule enabled and persists an explicit toggle', async () => {
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([]).mockResolvedValueOnce([savedRule])
    vi.mocked(reminderRuleApi.create).mockResolvedValueOnce(savedRule)
    vi.mocked(reminderRuleApi.setEnabled).mockResolvedValueOnce({ ...savedRule, enabled: false })
    const wrapper = await mountEditor()
    await required(wrapper.findAll('button').find(button => button.text().includes('保存并启用'))).trigger('click')
    await flushPromises()
    const toggle = wrapper.find('[role="switch"]')
    expect(toggle.attributes('aria-checked')).toBe('true')
    await toggle.trigger('click')
    await flushPromises()
    expect(reminderRuleApi.setEnabled).toHaveBeenCalledWith(42, false, savedRule.revision)
    expect(toggle.attributes('aria-checked')).toBe('false')
    wrapper.unmount()
  })

  it('keeps the current enabled state when a stale toggle loses the race', async () => {
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([savedRule])
    vi.mocked(reminderRuleApi.setEnabled).mockRejectedValueOnce({ response: { status: 409, data: { detail: '提醒规则已被他人修改，请刷新后重试' } } })
    const wrapper = await mountEditor()
    await wrapper.find('[role="switch"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="switch"]').attributes('aria-checked')).toBe('true')
    expect(wrapper.text()).toContain('刷新后重试')
    wrapper.unmount()
  })

  it('keeps the switch at the latest list value when a toggle finishes during reload', async () => {
    let finishToggle: (value: ReminderRule) => void = () => undefined
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([savedRule]).mockResolvedValueOnce([{ ...savedRule, enabled: false, revision: 2 }])
    vi.mocked(reminderRuleApi.setEnabled).mockImplementationOnce(() => new Promise(resolve => { finishToggle = resolve }))
    const wrapper = await mountEditor()
    await wrapper.find('[role="switch"]').trigger('click')
    await required(wrapper.findAll('button').find(button => button.text().includes(savedRule.name))).trigger('click')
    await required(wrapper.findAll('button').find(button => button.text() === '保存修改')).trigger('click')
    await flushPromises()
    finishToggle({ ...savedRule, enabled: false, revision: 2 })
    await flushPromises()
    expect(wrapper.find('[role="switch"]').attributes('aria-checked')).toBe('false')
    wrapper.unmount()
  })

  it('does not replace an in-flight draft when another rule is opened', async () => {
    const second = { ...savedRule, id: 43, name: '另一条规则', revision: 4 }
    let finishSave: (value: ReminderRule) => void = () => undefined
    const pending = new Promise<ReminderRule>(resolve => { finishSave = resolve })
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([savedRule, second])
    vi.mocked(reminderRuleApi.update).mockImplementationOnce(() => pending)
    const wrapper = await mountEditor()
    await required(wrapper.findAll('button').find(button => button.text().includes(savedRule.name))).trigger('click')
    await wrapper.find('#reminder-rule-name').setValue('第一条草稿')
    const save = required(wrapper.findAll('button').find(button => button.text() === '保存修改')).trigger('click')
    await required(wrapper.findAll('button').find(button => button.text().includes('另一条规则'))).trigger('click')
    expect((wrapper.find('#reminder-rule-name').element as HTMLInputElement).value).toBe('第一条草稿')
    finishSave(savedRule)
    await save
    await flushPromises()
    expect(reminderRuleApi.update).toHaveBeenCalledWith(savedRule.id, expect.objectContaining({ name: '第一条草稿' }), savedRule.revision)
    expect(wrapper.text()).not.toContain('编辑提醒')
    wrapper.unmount()
  })

  it('lets an editor remove a recipient who left the team and then save', async () => {
    vi.mocked(reminderRuleApi.recipients).mockResolvedValueOnce([{ id: '9', name: '在职成员' }])
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([{ ...savedRule, recipients: ['user:8', 'user:9'] }])
    const wrapper = await mountEditor()
    await required(wrapper.findAll('button').find(button => button.text().includes(savedRule.name))).trigger('click')
    await required(wrapper.findAll('button').find(button => button.text().includes('已离开团队的成员 8'))).trigger('click')
    expect(required(wrapper.findAll('button').find(button => button.text() === '保存修改')).attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('keeps fetched rules visible when runs or member options fail to load', async () => {
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([savedRule])
    vi.mocked(reminderRuleApi.listRuns).mockRejectedValueOnce(new Error('运行记录暂不可用'))
    vi.mocked(reminderRuleApi.recipients).mockRejectedValueOnce(new Error('成员暂不可用'))
    const wrapper = await mountEditor()
    expect(wrapper.find('[aria-label="查看业务旅程定时提醒详情"]').exists()).toBe(true)
    expect(wrapper.find('[role="switch"]').attributes('aria-checked')).toBe('true')
    wrapper.unmount()
  })

  it('keeps fetched rules visible when the editor catalog is unavailable', async () => {
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([savedRule])
    const wrapper = await mountEditor(Promise.reject(new Error('catalog unavailable')))
    expect(wrapper.find('[aria-label="查看业务旅程定时提醒详情"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('does not load rules for a member who can edit but cannot read them', async () => {
    permissionState.read = false
    vi.mocked(reminderRuleApi.list).mockClear()
    permissionState.edit = true
    const wrapper = await mountEditor()
    expect(wrapper.text()).toContain('暂无访问权限')
    expect(reminderRuleApi.list).not.toHaveBeenCalled()
    wrapper.unmount()
    await flushPromises()
    permissionState.read = true
  })
})

describe('existing reminder details', () => {
  it('opens a saved v2 rule, edits its original values and keeps it disabled', async () => {
    vi.mocked(reminderRuleApi.create).mockClear()
    const disabled = { ...savedRule, enabled: false, name: '原始规则', trigger_time: '16:30', conditions: [{ field: 'status', operator: 'in', value: ['WON'] }], message_template: '原始内容' }
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([disabled]).mockResolvedValueOnce([{ ...disabled, name: '修改规则' }])
    vi.mocked(reminderRuleApi.update).mockResolvedValueOnce({ ...disabled, name: '修改规则' })
    permissionState.create = false
    permissionState.publish = false
    const wrapper = await mountEditor()
    expect(topBar.visible()).toBe(false)
    await required(wrapper.findAll('button').find(button => button.text().includes('原始规则'))).trigger('click')
    expect(wrapper.text()).toContain('编辑提醒')
    expect(wrapper.find('textarea').element.value).toBe('原始内容')
    expect(wrapper.text()).toContain('16:30')
    expect(wrapper.text()).toContain('已赢单')
    const inputs = wrapper.findAll('input')
    await required(inputs.find(input => input.attributes('placeholder') === '规则名称')).setValue('修改规则')
    await required(wrapper.findAll('button').find(button => button.text() === '保存修改')).trigger('click')
    await flushPromises()
    expect(reminderRuleApi.update).toHaveBeenCalledWith(42, expect.objectContaining({ name: '修改规则', trigger_time: '16:30', conditions: [{ field: 'status', operator: 'in', value: ['WON'] }] }), disabled.revision)
    expect(reminderRuleApi.create).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('修改规则')
    wrapper.unmount()
    permissionState.create = true
    permissionState.publish = true
  })

  it('shows legacy details without exposing an incompatible v2 save', async () => {
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([{ ...savedRule, version: 1, trigger: 'change' }])
    const wrapper = await mountEditor()
    await required(wrapper.findAll('button').find(button => button.text().includes(savedRule.name))).trigger('click')
    expect(wrapper.text()).toContain('旧版规则')
    expect(wrapper.findAll('button').some(button => button.text().includes('保存修改'))).toBe(false)
    wrapper.unmount()
  })

  it('retains the edited draft and shows conflict when another editor saved first', async () => {
    vi.mocked(reminderRuleApi.list).mockClear()
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([savedRule])
    vi.mocked(reminderRuleApi.update).mockRejectedValueOnce({ response: { status: 409, data: { detail: '提醒规则已被他人修改，请刷新后重试' } } })
    const wrapper = await mountEditor()
    await required(wrapper.findAll('button').find(button => button.text().includes(savedRule.name))).trigger('click')
    await wrapper.find('#reminder-rule-name').setValue('本地未保存草稿')
    await required(wrapper.findAll('button').find(button => button.text() === '保存修改')).trigger('click')
    await flushPromises()
    expect((wrapper.find('#reminder-rule-name').element as HTMLInputElement).value).toBe('本地未保存草稿')
    expect(wrapper.text()).toContain('刷新后重试')
    expect(reminderRuleApi.list).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('shows the stored legacy schedule and message details without editing them', async () => {
    const legacy = { ...savedRule, version: 1, name: '旧版完整详情', trigger: 'schedule' as const, status: 'ACTIVE', inactive_days: 7, date_field: null, offset_days: -2, trigger_time: '16:30', message_title: '回访标题', channels: ['in_app', 'feishu'], conditions: [{ field: 'status', operator: 'in', value: ['ACTIVE'] }] }
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([legacy])
    const wrapper = await mountEditor()
    await required(wrapper.findAll('button').find(button => button.text().includes('旧版完整详情'))).trigger('click')
    for (const detail of ['7 天', '16:30', '提前 2 天', '回访标题', '站内通知', '飞书通知', '进行中']) expect(wrapper.text()).toContain(detail)
    expect(wrapper.findAll('button').some(button => button.text().includes('保存修改'))).toBe(false)
    wrapper.unmount()
  })

  it('shows a legacy date rule field and offset without enabling editing', async () => {
    const legacy = { ...savedRule, version: 1, object_type: 'follow_up_task' as const, name: '旧版日期提醒', trigger: 'date' as const, status: 'OPEN', date_field: 'due_at', offset_days: -3, trigger_time: null, inactive_days: null, conditions: [] }
    vi.mocked(reminderRuleApi.list).mockResolvedValueOnce([legacy])
    const wrapper = await mountEditor()
    await required(wrapper.findAll('button').find(button => button.text().includes('旧版日期提醒'))).trigger('click')
    expect(wrapper.text()).toContain('due_at')
    expect(wrapper.text()).toContain('提前 3 天')
    expect(wrapper.findAll('button').some(button => button.text().includes('保存修改'))).toBe(false)
    wrapper.unmount()
  })
})
