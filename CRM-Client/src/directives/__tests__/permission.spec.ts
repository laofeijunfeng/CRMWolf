import { defineComponent, nextTick } from 'vue'
import { mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { setupPermissionDirective } from '@/directives/permission'
import { usePermissionStore } from '@/stores/permissions'
import type { PermissionResponse } from '@/schemas/auth'

const TestSubject = defineComponent({
  template: `
    <div>
      <button v-permission="'customer:create'">创建客户</button>
      <button v-any-permission="['customer:edit:all', 'customer:edit:own']">编辑客户</button>
      <button v-all-permission="['customer:view:all', 'customer:edit:all']">维护客户</button>
    </div>
  `,
})

const permission = (code: string): PermissionResponse => ({
  id: 1,
  code,
  name: code,
  resource: code.split(':')[0] ?? 'resource',
  action: code.split(':')[1] ?? 'action',
  scope: null,
  description: null,
})

describe('permission directives', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  const getButton = (wrapper: VueWrapper, position: number): Omit<DOMWrapper<HTMLButtonElement>, 'exists'> =>
    wrapper.get<HTMLButtonElement>(`button:nth-of-type(${position})`)

  const mountSubject = (): { wrapper: VueWrapper; store: ReturnType<typeof usePermissionStore> } => {
    const wrapper = mount(TestSubject, {
      global: {
        plugins: [
          (app): void => setupPermissionDirective(app),
        ],
      },
    })
    const store = usePermissionStore()
    return { wrapper, store }
  }

  it('hides protected nodes while loading and restores them after permissions are ready', async () => {
    const { wrapper, store } = mountSubject()
    const createButton = getButton(wrapper, 1)

    expect(createButton.element.hidden).toBe(true)
    expect(createButton.attributes('aria-hidden')).toBe('true')

    store.permissions = [permission('customer:create')]
    store.loadState = 'ready'
    await nextTick()

    expect(createButton.element.hidden).toBe(false)
    expect(createButton.attributes('aria-hidden')).toBeUndefined()
    wrapper.unmount()
  })

  it('fails closed when permission loading fails', async () => {
    const { wrapper, store } = mountSubject()
    const createButton = getButton(wrapper, 1)

    store.loadState = 'error'
    store.permissions = [permission('customer:create')]
    await nextTick()

    expect(createButton.element.hidden).toBe(true)
    expect(createButton.attributes('aria-hidden')).toBe('true')
    wrapper.unmount()
  })

  it('reacts to permission changes without removing the node', async () => {
    const { wrapper, store } = mountSubject()
    const editButton = getButton(wrapper, 2)

    store.permissions = [permission('customer:edit:all')]
    store.loadState = 'ready'
    await nextTick()
    expect(editButton.element.hidden).toBe(false)

    store.permissions = []
    await nextTick()
    expect(editButton.element.hidden).toBe(true)
    expect(wrapper.find('button:nth-of-type(2)').exists()).toBe(true)
    wrapper.unmount()
  })

  it('applies any/all semantics independently', async () => {
    const { wrapper, store } = mountSubject()
    const editButton = getButton(wrapper, 2)
    const maintainButton = getButton(wrapper, 3)

    store.permissions = [permission('customer:edit:own')]
    store.loadState = 'ready'
    await nextTick()

    expect(editButton.element.hidden).toBe(false)
    expect(maintainButton.element.hidden).toBe(true)

    store.permissions = [permission('customer:view:all'), permission('customer:edit:all')]
    await nextTick()
    expect(maintainButton.element.hidden).toBe(false)
    wrapper.unmount()
  })
})
