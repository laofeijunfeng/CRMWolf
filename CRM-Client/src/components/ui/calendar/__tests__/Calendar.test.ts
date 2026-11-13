import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { CalendarDate } from '@internationalized/date'
import Calendar from '../Calendar.vue'

describe('Calendar', () => {
  // radix-vue counted weekStartsOn from the locale's first weekday; zh-CN grids start on Monday.
  it('starts weeks on Monday for the default zh-CN locale', () => {
    const wrapper = mount(Calendar, { props: { defaultValue: new CalendarDate(2026, 11, 13) } })

    const firstRowDays = wrapper.find('tbody tr').findAll('[data-value]').map(cell => cell.attributes('data-value'))
    expect(wrapper.findAll('th').map(cell => cell.text())).toEqual(['一', '二', '三', '四', '五', '六', '日'])
    expect(firstRowDays[0]).toBe('2026-10-26')
  })
})
