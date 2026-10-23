// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { field, makeTask, message, mocks, reply, show, view } from './assistantChatHarness'
import SalesAssistantChat from '@/components/sales-assistant/SalesAssistantChat.vue'

describe('continuous message visibility', () => {
  it('keeps a user bubble visible while Root is still working', async () => {
    let finish: ((v: ReturnType<typeof reply>) => void) | undefined
    mocks.text.mockReturnValue(new Promise<ReturnType<typeof reply>>((resolve) => { finish = resolve }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.find('textarea').setValue('慢回复测试')
    await wrapper.find('textarea').trigger('keydown.enter', { key: 'Enter' })
    expect(wrapper.text()).toContain('慢回复测试')
    expect(wrapper.text()).toContain('正在理解这次沟通')
    finish?.(reply(view({ messages: [message('user', '慢回复测试', null, 'user'), message('reply', '收到')] })))
    await flushPromises()
    expect(wrapper.text()).toContain('收到')
    expect(wrapper.text().match(/慢回复测试/g)).toHaveLength(1)
  })

  it('preserves an unfinished old draft when another customer becomes focused', async () => {
    const old = makeTask({ waiting: field() })
    const original = message('old', '旧稿还差客户名称', old)
    show(view({ focused_task: old, messages: [original] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    const next = makeTask({ public_id: 'ast_two', waiting: field({ prompt: '新稿还差下一步', field: 'next_action' }) })
    mocks.text.mockResolvedValue(reply(view({ version: 1, focused_task: next, messages: [original, message('new', '新稿还差下一步', next)] })))
    await wrapper.find('textarea').setValue('刚刚和河南双汇技术经理沟通了部署')
    await wrapper.find('textarea').trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.text()).toContain('旧稿还差客户名称')
    expect(wrapper.text()).toContain('新稿还差下一步')
    expect(mocks.command).not.toHaveBeenCalled()
  })

  it('restores a continuous transcript on a fresh mount, without a task list', async () => {
    show(view({ messages: [message('old', '上午会议已记录'), message('new', '下午电话继续记', null, 'user')] }))
    let wrapper = mount(SalesAssistantChat)
    await flushPromises()
    wrapper.unmount()
    wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).toContain('上午会议已记录')
    expect(wrapper.text()).toContain('下午电话继续记')
    expect(wrapper.text()).not.toContain('最近任务')
    expect(mocks.text).not.toHaveBeenCalled()
  })
})
