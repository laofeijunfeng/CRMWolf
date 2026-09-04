import { flushPromises, shallowMount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LeadDetailSheet from '../LeadDetailSheet.vue'
import { leadApi, type LeadDetail } from '@/api/lead'

const leadDetail: LeadDetail = {
  id: 'lead-1',
  public_id: 'LEAD-001',
  lead_name: '测试线索',
  source: '官网',
  city: '上海',
  contact_name: '张三',
  contact_phone: '13800138000',
  company_scale: '1-50人',
  owner_id: '1',
  owner_info: { id: '1', name: '负责人', avatar_url: '' },
  status: 1,
  creator_id: '1',
  creator_info: { id: '1', name: '创建人', avatar_url: '' },
  created_time: '2026-09-04T00:00:00Z',
  last_modified_time: '2026-09-04T00:00:00Z',
  version: 1,
  follow_ups: [],
}

describe('LeadDetailSheet component resolution', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the lead detail without unresolved component warnings', async () => {
    vi.spyOn(leadApi, 'getLeadDetail').mockResolvedValue(leadDetail)
    const warnings: string[] = []

    const wrapper = shallowMount(LeadDetailSheet, {
      props: {
        leadId: leadDetail.id,
        visible: true,
      },
      global: {
        plugins: [createPinia()],
        config: {
          warnHandler: (message: string): void => {
            warnings.push(message)
          },
        },
      },
    })
    await flushPromises()

    expect(warnings.filter(message => message.includes('Failed to resolve component'))).toEqual([])
    wrapper.unmount()
  })
})
