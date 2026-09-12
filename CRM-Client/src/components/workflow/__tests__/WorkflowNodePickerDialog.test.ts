import { mount } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import WorkflowNodePickerDialog, { type WorkflowNodePickerItem } from '../WorkflowNodePickerDialog.vue'
beforeAll(() => { HTMLElement.prototype.scrollIntoView = () => undefined })

const items: WorkflowNodePickerItem[] = [
  { type: 'trigger.opportunity_stage_changed', label: '商机阶段变化', description: '当商机阶段发生变化时触发', category: 'trigger', icon: 'span', isTrigger: true },
  { type: 'control.condition', label: '条件分支', description: '按字段条件选择分支', category: 'control', icon: 'span', isTrigger: false },
  { type: 'action.notify', label: '发送通知', description: '向负责人发送通知', category: 'action', icon: 'span', isTrigger: false },
]

function mountPicker(triggerUsed = false, opener: HTMLElement | null = null) {
  return mount(WorkflowNodePickerDialog, { props: { open: true, nodeTypes: items, triggerUsed, opener }, attachTo: document.body })
}
async function mountedPicker(triggerUsed = false, opener: HTMLElement | null = null) {
  const wrapper = mountPicker(triggerUsed, opener)
  await nextTick()
  await nextTick()
  return wrapper
}
function bodyText(): string { return document.body.textContent ?? '' }
function bodyGet(selector: string): HTMLElement {
  const element = document.body.querySelector<HTMLElement>(selector)
  if (element === null) throw new Error(`Missing ${selector}`)
  return element
}
afterEach(() => { document.body.innerHTML = '' })

describe('WorkflowNodePickerDialog', () => {
  it('renders categorized node groups', async () => {
    const wrapper = await mountedPicker()
    expect(bodyText()).toContain('触发器')
    expect(bodyText()).toContain('控制')
    expect(bodyText()).toContain('动作')
    expect(bodyText()).toContain('商机阶段变化')
    expect(bodyText()).toContain('条件分支')
    expect(bodyText()).toContain('发送通知')
    wrapper.unmount()
  })
  it('searches by label, description, and type', async () => {
    const wrapper = await mountedPicker()
    const input = bodyGet('[data-testid="workflow-node-picker-search"]') as HTMLInputElement
    input.value = '负责人'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    expect(bodyText()).toContain('发送通知')
    expect(bodyText()).not.toContain('条件分支')
    input.value = 'control.condition'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    expect(bodyText()).toContain('条件分支')
    expect(bodyText()).not.toContain('发送通知')
    wrapper.unmount()
  })
  it('disables triggers with an explanatory reason when a trigger is already used', async () => {
    const wrapper = await mountedPicker(true)
    const trigger = bodyGet('[data-testid="workflow-picker-item-trigger.opportunity_stage_changed"]')
    expect(trigger.getAttribute('aria-disabled')).toBe('true')
    expect(trigger.textContent).toContain('工作流只能有一个触发器')
    wrapper.unmount()
  })
  it('emits the selected type and closes the dialog', async () => {
    const wrapper = await mountedPicker()
    bodyGet('[data-testid="workflow-picker-item-action.notify"]').click()
    await nextTick()
    expect(wrapper.emitted('select')).toEqual([['action.notify']])
    expect(wrapper.emitted('update:open')).toEqual([[false]])
    wrapper.unmount()
  })
  it('closes on Escape and close button', async () => {
    const wrapper = await mountedPicker()
    bodyGet('[role="dialog"]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick()
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    bodyGet('[aria-label="关闭"]').click()
    await nextTick()
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    wrapper.unmount()
  })
  it('restores a connected opener after Escape but skips selection focus when detached', async () => {
    const opener = document.createElement('button')
    document.body.append(opener)
    const wrapper = await mountedPicker(false, opener)
    bodyGet('[role="dialog"]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await wrapper.setProps({ open: false })
    await nextTick()
    expect(document.activeElement).toBe(opener)
    await wrapper.setProps({ open: true })
    await nextTick()
    bodyGet('[data-testid="workflow-picker-item-action.notify"]').click()
    opener.remove()
    await wrapper.setProps({ open: false })
    await nextTick()
    expect(document.activeElement).not.toBe(opener)
    expect(opener.isConnected).toBe(false)
    wrapper.unmount()
  })
})
