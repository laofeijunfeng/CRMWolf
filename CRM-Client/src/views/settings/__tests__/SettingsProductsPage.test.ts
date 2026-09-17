import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsProductsPage from '@/views/settings/SettingsProductsPage.vue'
import productApi from '@/api/product'
import { useHeaderStore } from '@/stores/header'
import { usePermissionStore } from '@/stores/permissions'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'

const mocks = vi.hoisted(() => ({
  product: {
    public_id: 'prd_1',
    id: 'prd_1',
    name: 'CRM 产品',
    description: '基础 CRM',
    is_active: true,
    created_by: 'u',
    updated_by: null,
    created_time: '2026-01-01T00:00:00',
    updated_time: '2026-01-01T00:00:00',
    modules: [
      {
        public_id: 'prm_1',
        id: 'prm_1',
        name: '基础模块',
        description: null,
        module_role: 'BASE' as const,
        is_active: true,
        sort_order: 0,
        created_by: 'u',
        updated_by: null,
        created_time: '2026-01-01T00:00:00',
        updated_time: '2026-01-01T00:00:00',
      },
      {
        public_id: 'prm_2',
        id: 'prm_2',
        name: '增强模块',
        description: null,
        module_role: 'ADD_ON' as const,
        is_active: true,
        sort_order: 1,
        created_by: 'u',
        updated_by: null,
        created_time: '2026-01-01T00:00:00',
        updated_time: '2026-01-01T00:00:00',
      },
    ],
  },
  routeQuery: {} as Record<string, string | undefined>,
}))

vi.mock('@/api/product', () => ({
  default: {
    list: vi.fn().mockResolvedValue([mocks.product]),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    createModule: vi.fn(),
    updateModule: vi.fn(),
    deleteModule: vi.fn(),
  },
}))

vi.mock('@/utils/confirmDialog', () => ({
  confirmDialog: vi.fn().mockResolvedValue(true),
  confirmDelete: vi.fn().mockResolvedValue(true),
}))

vi.mock('vue-router', async () => {
  const { reactive } = await import('vue')
  mocks.routeQuery = reactive(mocks.routeQuery)
  return {
    useRoute: (): { meta: { title: string }; query: Record<string, string | undefined> } => ({
      meta: { title: '产品管理' },
      query: mocks.routeQuery,
    }),
  }
})

const dataTableStub = {
  props: ['data', 'emptyTitle', 'emptyDescription', 'loadError', 'getRowActions'],
  emits: ['retry'],
  template: `
    <div>
      <div v-if="loadError" role="alert">
        <strong>{{ loadError.title }}</strong>
        <button data-testid="product-list-retry" @click="$emit('retry')">重新加载</button>
      </div>
      <template v-else>
        <div v-for="row in data" :key="row.public_id || row.id">
          <slot name="cell-name" :row="row" />
          <slot name="cell-status" :row="row" />
          <slot name="cell-modules" :row="row" />
          <slot name="mobile-actions" :row="row" />
        </div>
        <div v-if="data.length === 0">
          <p>{{ emptyTitle }}</p>
          <p>{{ emptyDescription }}</p>
        </div>
      </template>
    </div>
  `,
}

const tableRowActionsStub = {
  props: ['row', 'primaryActions', 'secondaryActions'],
  template: `
    <div>
      <button
        v-for="action in [...(primaryActions || []), ...(secondaryActions || [])].filter((item) => item.visible !== false)"
        :key="action.label"
        type="button"
        @click="action.handler(row)"
      >
        {{ action.label }}
      </button>
    </div>
  `,
}

const stubs = {
  DataTable: dataTableStub,
  TableRowActions: tableRowActionsStub,
  SettingsContent: { template: '<main><slot /></main>' },
  Dialog: {
    name: 'Dialog',
    props: ['open'],
    template: '<div v-if="open" data-testid="product-dialog"><slot /></div>',
  },
  Button: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  Input: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  Textarea: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  Badge: { template: '<span><slot /></span>' },
  DialogContent: { template: '<div><slot /></div>' },
  DialogHeader: { template: '<div><slot /></div>' },
  DialogTitle: { template: '<h2><slot /></h2>' },
  DialogDescription: { template: '<div><slot /></div>' },
  DialogFooter: { template: '<div><slot /></div>' },
  FormField: { template: '<div><slot :componentField="{}" /></div>' },
  FormControl: { template: '<div><slot /></div>' },
  FormItem: { template: '<div><slot /></div>' },
  FormLabel: { template: '<label><slot /></label>' },
  FormMessage: { template: '<span><slot /></span>' },
}

const formSubmitStubs = Object.fromEntries(
  Object.entries(stubs).filter(([key]) => ![
    'FormField',
    'FormControl',
    'FormItem',
    'FormLabel',
    'FormMessage',
    'Input',
    'Textarea',
  ].includes(key)),
)

function setPermissions(codes: string[]): void {
  const store = usePermissionStore()
  store.loadState = 'ready'
  store.permissions = codes.map((code, index) => ({
    id: index + 1,
    code,
    name: code,
    resource: code.split(':')[0] ?? code,
    action: code.split(':')[1] ?? '',
  }))
}

function seedPinia(codes: string[]): void {
  setActivePinia(createPinia())
  const teamStore = useTeamStore()
  const userStore = useUserStore()
  teamStore.currentTeam = {
    id: 7,
    name: '演示团队',
    code: 'DEMO',
    owner_id: '42',
    created_at: '2026-01-01T00:00:00Z',
  }
  userStore.userInfo = {
    id: 42,
    name: '团队所有者',
    email: 'owner@example.com',
    status: 'active',
    created_at: null,
    updated_at: null,
  }
  setPermissions(codes)
}

function mountPage(extraStubs: Record<string, unknown> = stubs): VueWrapper {
  return mount(SettingsProductsPage, { global: { stubs: extraStubs } })
}

function hasVisibleCreateAction(): boolean {
  return useHeaderStore().actions.some((action) => action.label === '新建产品' && action.visible !== false)
}

function hasButton(wrapper: VueWrapper, label: string): boolean {
  return wrapper.findAll('button').some((button) => button.text() === label)
}

describe('SettingsProductsPage', () => {
  beforeEach(() => {
    mocks.routeQuery.action = undefined
    mocks.routeQuery.id = undefined
    vi.mocked(productApi.list).mockReset()
    vi.mocked(productApi.list).mockResolvedValue([mocks.product])
    vi.mocked(productApi.create).mockReset()
    vi.mocked(productApi.createModule).mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('does not list products when the owner lacks product:view', async () => {
    seedPinia([])
    const wrapper = mountPage()
    await flushPromises()
    expect(productApi.list).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂无访问权限')
    wrapper.unmount()
  })

  it('lists products after permissions become ready with product:view', async () => {
    seedPinia([])
    const permissionStore = usePermissionStore()
    permissionStore.loadState = 'loading'
    const wrapper = mountPage()
    await flushPromises()
    expect(productApi.list).not.toHaveBeenCalled()

    permissionStore.permissions = [{
      id: 1,
      code: 'product:view',
      name: 'product:view',
      resource: 'product',
      action: 'view',
    }]
    permissionStore.loadState = 'ready'
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalledTimes(1))
    expect(wrapper.text()).toContain('CRM 产品')
    wrapper.unmount()
  })


  it('shows product data to a read-only user without maintenance buttons', async () => {
    seedPinia(['product:view'])
    const wrapper = mountPage()
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.text()).toContain('CRM 产品')
    expect(wrapper.text()).toContain('基础模块')
    expect(hasVisibleCreateAction()).toBe(false)
    expect(hasButton(wrapper, '新建产品')).toBe(false)
    expect(hasButton(wrapper, '编辑')).toBe(false)
    expect(hasButton(wrapper, '删除')).toBe(false)
    wrapper.unmount()
  })

  it('shows add-on module deletion for editors without product deletion permission', async () => {
    seedPinia(['product:view', 'product:edit'])
    const wrapper = mountPage()
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(hasButton(wrapper, '删除模块')).toBe(true)
    expect(hasButton(wrapper, '删除')).toBe(false)
    wrapper.unmount()
  })

  it('shows editor controls while keeping base module protected', async () => {
    seedPinia(['product:view', 'product:create', 'product:edit', 'product:delete'])
    const wrapper = mountPage()
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.text()).toContain('CRM 产品')
    expect(hasVisibleCreateAction()).toBe(true)
    expect(hasButton(wrapper, '新增模块')).toBe(true)
    expect(wrapper.findAll('button').filter((button) => button.text() === '删除模块')).toHaveLength(1)
    wrapper.unmount()
  })

  it('does not open an edit dialog for a read-only edit deep link', async () => {
    seedPinia(['product:view'])
    mocks.routeQuery.action = 'edit'
    mocks.routeQuery.id = 'prd_1'
    const wrapper = mountPage()
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.find('h2').exists()).toBe(false)
    expect(hasButton(wrapper, '保存')).toBe(false)
    expect(hasButton(wrapper, '编辑')).toBe(false)
    wrapper.unmount()
  })

  it('opens a create dialog when the route action is create', async () => {
    seedPinia(['product:view', 'product:create'])
    const wrapper = mountPage()
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.find('h2').exists()).toBe(false)
    mocks.routeQuery.action = 'create'
    await flushPromises()
    expect(wrapper.find('h2').text()).toBe('新建产品')
    expect(hasButton(wrapper, '保存')).toBe(true)
    wrapper.unmount()
  })

  it('opens a pending create deep link when permissions become ready', async () => {
    setActivePinia(createPinia())
    const teamStore = useTeamStore()
    teamStore.currentTeam = {
      id: 7,
      name: '演示团队',
      code: 'DEMO',
      owner_id: '42',
      created_at: '2026-01-01T00:00:00Z',
    }
    const store = usePermissionStore()
    store.loadState = 'loading'
    store.permissions = []
    mocks.routeQuery.action = 'create'
    const wrapper = mountPage()
    await flushPromises()
    expect(productApi.list).not.toHaveBeenCalled()
    expect(wrapper.find('h2').exists()).toBe(false)

    setPermissions(['product:view', 'product:create'])
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.find('h2').text()).toBe('新建产品')
    wrapper.unmount()
  })

  it('does not reopen create Dialog when the list length changes', async () => {
    seedPinia(['product:view', 'product:create'])
    mocks.routeQuery.action = 'create'

    let resolveProducts: ((value: typeof mocks.product[]) => void) | undefined
    vi.mocked(productApi.list).mockImplementation(() => new Promise((resolve) => {
      resolveProducts = resolve
    }))

    const wrapper = mountPage()
    await nextTick()
    expect(wrapper.find('[data-testid="product-dialog"]').exists()).toBe(true)

    const dialog = wrapper.findComponent({ name: 'Dialog' }) as unknown as {
      vm: { $emit: (event: 'update:open', value: boolean) => void }
    }
    dialog.vm.$emit('update:open', false)
    await nextTick()
    expect(wrapper.find('[data-testid="product-dialog"]').exists()).toBe(false)

    resolveProducts?.([mocks.product])
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await nextTick()
    expect(wrapper.find('[data-testid="product-dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('tells a viewer without create permission to contact the team admin when the list is empty', async () => {
    seedPinia(['product:view'])
    vi.mocked(productApi.list).mockResolvedValueOnce([])
    const wrapper = mountPage()
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.text()).toContain('你没有创建产品的权限')
    wrapper.unmount()
  })

  it('renders a retryable error instead of an empty state and recovers after retry', async () => {
    seedPinia(['product:view'])
    vi.mocked(productApi.list)
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce([mocks.product])
    const wrapper = mountPage()
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('产品加载失败')
    expect(wrapper.find('button[data-testid="product-list-retry"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('暂无产品')
    await wrapper.get('button[data-testid="product-list-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('CRM 产品')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('creates a product from the product form instead of the module form', async () => {
    seedPinia(['product:view', 'product:create'])
    mocks.routeQuery.action = 'create'
    vi.mocked(productApi.create).mockResolvedValueOnce(mocks.product)
    const wrapper = mount(SettingsProductsPage, {
      global: { stubs: formSubmitStubs },
      attachTo: document.body,
    })
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()

    const form = wrapper.get('form')
    expect(form.find('input[name="code"]').exists()).toBe(false)
    await form.get('input[name="name"]').setValue('CRMWolf')
    await form.get('textarea[name="description"]').setValue('客户关系管理平台')
    await form.get('button[type="submit"]').trigger('click')
    await vi.waitFor(() => {
      expect(productApi.create).toHaveBeenCalledWith({
        name: 'CRMWolf',
        description: '客户关系管理平台',
      })
    })
    expect(productApi.createModule).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
