import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

import App from '@/App.vue'

describe('App', () => {
  it('provides tooltip context to routed page content', () => {
    const wrapper = mount(App, {
      global: {
        components: { Tooltip, TooltipContent, TooltipTrigger },
        stubs: {
          Toast: true,
          ConfirmDialog: true,
          'router-view': {
            template: '<Tooltip><TooltipTrigger>复制</TooltipTrigger><TooltipContent>复制用户 ID</TooltipContent></Tooltip>',
          },
        },
      },
    })

    expect(wrapper.findComponent(TooltipProvider).exists()).toBe(true)
    expect(wrapper.text()).toContain('复制')
  })
})
