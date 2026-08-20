import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { Select } from '@/components/ui/select'
import ListSortPopover from '../ListSortPopover.vue'

const attached: VueWrapper[] = []

async function openSortPopover(wrapper: VueWrapper): Promise<void> {
  const trigger = wrapper.findAll('button').find((button) => button.text().includes('排序'))
  if (trigger === undefined) {
    throw new Error('Sort popover trigger not found')
  }

  await trigger.trigger('click')
  await flushPromises()
  await nextTick()
}

function getSelectTriggers(): HTMLButtonElement[] {
  return Array.from(document.body.querySelectorAll<HTMLButtonElement>('button[role="combobox"]'))
}

describe('ListSortPopover', () => {
  afterEach(() => {
    while (attached.length > 0) {
      attached.pop()?.unmount()
    }
  })

  it('updates the direction label immediately when the selected field type changes', async () => {
    const wrapper = mount(ListSortPopover, {
      props: {
        fields: [
          { key: 'name', label: '客户名称', type: 'text' },
          { key: 'authorization_status', label: '授权状态', type: 'enum' }
        ],
        modelValue: []
      },
      attachTo: document.body
    })
    attached.push(wrapper)

    await openSortPopover(wrapper)
    expect(getSelectTriggers()[1]?.textContent).toContain('A-Z')

    const fieldSelect = wrapper.findAllComponents(Select)[0]
    if (fieldSelect === undefined) {
      throw new Error('Sort field select not found')
    }

    const fieldSelectVm = fieldSelect.vm as unknown as {
      $emit: (event: 'update:modelValue', value: string) => void
    }
    fieldSelectVm.$emit('update:modelValue', 'authorization_status')
    await flushPromises()
    await nextTick()

    expect(getSelectTriggers()[1]?.textContent).toContain('选项顺序')
    expect(getSelectTriggers()[1]?.textContent).not.toContain('A-Z')
  })
})
