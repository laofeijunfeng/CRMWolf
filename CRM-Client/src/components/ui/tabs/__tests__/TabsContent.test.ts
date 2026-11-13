import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '..'

describe('Tabs content isolation', () => {
  it('retains forced content without exposing an inactive panel', async () => {
    const wrapper = mount({
      components: { Tabs, TabsContent, TabsList, TabsTrigger },
      template: `
        <Tabs default-value="first">
          <TabsList>
            <TabsTrigger value="first">First</TabsTrigger>
            <TabsTrigger value="second">Second</TabsTrigger>
          </TabsList>
          <TabsContent value="first" force-mount><input value="retained" /></TabsContent>
          <TabsContent value="second">Second content</TabsContent>
        </Tabs>
      `,
    })
    const panels = wrapper.findAll('[role="tabpanel"]')
    const retained = panels[0]?.get('input').element
    await wrapper.findAll('[role="tab"]')[1]?.trigger('mousedown', { button: 0 })
    expect(panels[0]?.attributes('data-state')).toBe('inactive')
    expect(panels[0]?.attributes('hidden')).toBeDefined()
    expect(panels[0]?.get('input').element).toBe(retained)
    expect(panels[1]?.attributes('hidden')).toBeUndefined()
    const selected = wrapper.get('[role="tab"][aria-selected="true"]')
    expect(selected.attributes('aria-controls')).toBe(panels[1]?.attributes('id'))
    expect(panels[1]?.attributes('aria-labelledby')).toBe(selected.attributes('id'))
    wrapper.unmount()
  })
  it('hides an inactive panel when force-mount is enabled dynamically', async () => {
    const wrapper = mount({
      components: { Tabs, TabsContent },
      props: { forced: Boolean },
      template: `<Tabs default-value="first"><TabsContent value="second" :force-mount="forced"><input /></TabsContent></Tabs>`,
    })
    await wrapper.setProps({ forced: true })
    await flushPromises()
    expect(wrapper.get('[role="tabpanel"]').attributes('hidden')).toBeDefined()
    expect(wrapper.findAll('input')).toHaveLength(1)
    wrapper.unmount()
  })
})
