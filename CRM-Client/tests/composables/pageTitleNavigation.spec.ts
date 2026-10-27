import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, type VNode } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { usePageTitle } from '@/composables/usePageTitle'
import { usePageTitleStore } from '@/stores/pageTitle'
import SalesAssistant from '@/views/SalesAssistant.vue'
import NotFound from '@/views/NotFound.vue'

const Layout = defineComponent({
  template: `<router-view v-slot="{ Component, route }">
    <KeepAlive><component :is="Component" v-if="route.meta.keepAlive" /></KeepAlive>
    <component :is="Component" v-if="!route.meta.keepAlive" />
  </router-view>`,
})

const SettingsPage = defineComponent({
  setup: (): (() => VNode) => {
    usePageTitle()
    return (): VNode => h('main', 'settings')
  },
})

describe('page title during cached assistant navigation', () => {
  it.each(['/settings/integrations', '/settings/agent-run-log'])(
    'does not let the departing %s page clear the newly activated assistant title',
    async (path) => {
      const pinia = createPinia()
      setActivePinia(pinia)
      const title = usePageTitleStore()
      const router = createRouter({
        history: createMemoryHistory(),
        routes: [
          { path: '/assistant', component: SalesAssistant, meta: { keepAlive: true, title: '销售助手' } },
          { path: '/settings/integrations', component: SettingsPage, meta: { title: '第三方集成' } },
          { path: '/settings/agent-run-log', component: NotFound, meta: { title: '找不到页面' } },
        ],
      })
      await router.push('/assistant')
      const wrapper = mount(Layout, { global: { plugins: [pinia, router], stubs: { SalesAssistantChat: true } } })
      try {
        await flushPromises()
        expect(title.title).toBe('销售助手')
        await router.push(path)
        await flushPromises()
        expect(title.title).toBe(path.endsWith('integrations') ? '第三方集成' : '找不到页面')
        await router.push('/assistant')
        await flushPromises()
        expect(title.title).toBe('销售助手')
      } finally {
        wrapper.unmount()
      }
    },
  )
})
