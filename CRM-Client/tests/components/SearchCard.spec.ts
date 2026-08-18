import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import SearchCard from '@/components/crmwolf/SearchCard.vue'

const SelectFieldStub = defineComponent({
  name: 'SelectField',
  props: {
    options: {
      type: Array,
      default: () => [],
    },
    ariaLabel: {
      type: String,
      default: '',
    },
  },
  setup(props) {
    return () => h('div', {
      'data-testid': `select-${props.ariaLabel}`,
      'data-options': JSON.stringify(props.options),
    })
  },
})

function mountSearchCard(sourceOptions?: Array<{ value: string; label: string }>) {
  return mount(SearchCard, {
    props: sourceOptions === undefined ? {} : { sourceOptions },
    global: {
      stubs: {
        SelectField: SelectFieldStub,
      },
    },
  })
}

describe('SearchCard acquisition source options', () => {
  it('does not hardcode the old Chinese source enum', () => {
    const wrapper = mountSearchCard()
    const sourceSelect = wrapper.get('[data-testid="select-筛选来源"]')
    const options = JSON.parse(sourceSelect.attributes('data-options') ?? '[]') as Array<{ value: string; label: string }>

    expect(options).toEqual([{ value: '__all__', label: '全部来源' }])
    expect(options.map(option => option.label)).not.toContain('线上注册')
  })

  it('uses the source options provided by the parent', () => {
    const wrapper = mountSearchCard([
      { value: 'acq_referral', label: '朋友介绍' },
    ])
    const sourceSelect = wrapper.get('[data-testid="select-筛选来源"]')
    const options = JSON.parse(sourceSelect.attributes('data-options') ?? '[]') as Array<{ value: string; label: string }>

    expect(options).toEqual([
      { value: '__all__', label: '全部来源' },
      { value: 'acq_referral', label: '朋友介绍' },
    ])
  })
})
