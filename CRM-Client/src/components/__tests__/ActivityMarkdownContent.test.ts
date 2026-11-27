import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ActivityMarkdownContent from '../ActivityMarkdownContent.vue'

describe('ActivityMarkdownContent', () => {
  it('renders safe Markdown content and escapes raw HTML', () => {
    const wrapper = mount(ActivityMarkdownContent, {
      props: {
        content: '## 阶段结论\n- **客户确认预算**\n<script>alert(1)</script>',
      },
    })
    expect(wrapper.find('h2').text()).toBe('阶段结论')
    expect(wrapper.find('strong').text()).toBe('客户确认预算')
    expect(wrapper.html()).not.toContain('<script>')
    expect(wrapper.text()).toContain('<script>alert(1)</script>')
  })

  it('shows expand/collapse toggle when collapsible content overflows maxHeight', async () => {
    const wrapper = mount(ActivityMarkdownContent, {
      props: {
        content: '第一段\n\n第二段\n\n第三段\n\n第四段',
        collapsible: true,
        maxHeight: 80,
      },
    })

    const bodyEl = wrapper.find('.activity-markdown-body').element as HTMLElement
    Object.defineProperty(bodyEl, 'scrollHeight', { value: 240, configurable: true })

    await wrapper.setProps({ maxHeight: 79 })
    await nextTick()

    const toggle = wrapper.find('[data-activity-markdown-toggle]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toContain('展开全文')

    await toggle.trigger('click')
    expect(toggle.text()).toContain('收起')
  })
})
