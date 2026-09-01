import { mount, type VueWrapper } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CustomerProfileContent from '../CustomerProfileContent.vue'
import type { CustomerProfileEvidence, CustomerProfileResponse } from '@/schemas/customerProfile'

const baseProfile = (sections: CustomerProfileResponse['sections']): CustomerProfileResponse => ({
  customer_id: 'customer-1',
  profile_status: 'READY',
  current_profile_version: 'profile-v1',
  profile_version_number: 1,
  schema_version: 'v2',
  freshness: {
    profile_as_of: '2026-08-20T10:00:00Z',
    latest_business_event_at: '2026-08-20T10:00:00Z',
    is_stale: false,
    stale_reason: null
  },
  sections,
  evidence_refs: [],
  links: {
    changes: '/changes',
    evidence: '/evidence',
    journeys: '/journeys',
    follow_ups: '/follow-ups',
    versions: '/versions'
  }
})

const emptySections: CustomerProfileResponse['sections'] = {
  current_situation: {},
  current_journeys: [],
  important_changes: [],
  long_term_context: {},
  follow_up_process: [],
  recorded_follow_ups: []
}

const evidence: CustomerProfileEvidence[] = [{
  evidence_key: 'activity:10',
  source_type: 'customer_activity',
  source_id: '10',
  source_version: null,
  occurred_at: '2026-08-20T10:00:00Z',
  title: '技术验证沟通',
  snippet: '客户提出需要支持多站点部署。',
  visibility: 'VISIBLE',
  availability: 'AVAILABLE',
  link: '/activities/10',
  reason: null
}]

const mountProfile = (profile: CustomerProfileResponse, profileEvidence = evidence): VueWrapper => mount(CustomerProfileContent, {
  props: {
    profile,
    evidence: profileEvidence,
    customerName: '测试客户',
    refreshing: false
  },
  global: {
    stubs: {
      Badge: { template: '<span><slot /></span>' },
      Button: { template: '<button><slot /></button>' },
      RefreshCw: { template: '<span />' },
      Pin: { template: '<span />' },
      HoverPreviewTooltip: { template: '<span class="evidence-stub"><slot /></span>' }
    }
  }
}) as VueWrapper

describe('CustomerProfileContent', () => {
  it('hides empty sections without explanatory placeholder copy', () => {
    const wrapper = mountProfile(baseProfile(emptySections))
    const text = wrapper.text()

    expect(text).not.toContain('暂无记录')
    expect(text).not.toContain('尚未形成稳定记录')
    expect(text).not.toContain('未命名事项')
    expect(text).not.toContain('已确认事项')
    expect(text).not.toContain('跟进过程')
    expect(text).not.toContain('后续事项')
  })

  it('renders a readable customer 360 with company, journey, process and follow-ups', () => {
    const profile = baseProfile({
      current_situation: {
        summary: '客户正在推进平台技术验证。',
        demand_background: {
          summary: '希望先完成多站点部署验证，再评估后续采购。',
          items: [{
            statement: '需要支持多站点部署。',
            status: '已提出',
            evidence_refs: ['activity:10']
          }]
        }
      },
      current_journeys: [{
        id: 'journey-1',
        name: '平台技术验证',
        status: '进行中',
        current_stage: '试用验证',
        timeline: [{
          type: 'follow_up_task_status',
          summary: '待办“确认技术验证结果”状态由“待完成”变为“已完成”。',
          occurred_at: '2026-08-20T10:00:00Z'
        }],
        next_steps: [{ title: '确认技术验证结果', status: '已完成' }]
      }],
      important_changes: [{
        change: '技术验证已完成，业务旅程进入评估阶段。',
        occurred_at: '2026-08-20T10:00:00Z',
        evidence_refs: ['activity:10']
      }],
      long_term_context: {
        customer: {
          industry_name: '科研服务',
          company_scale: '中型',
          city: '广州',
          address: '广州市天河区',
          company_website: 'https://example.com',
          organization_structure: '研发团队与项目组协同推进',
          technical_characteristics: '支持多站点部署验证，技术团队参与方案评估'
        },
        facts: [{ content: '客户具备多站点部署场景。', evidence_refs: ['activity:10'] }],
        contacts: [{
          id: 'contact-1',
          name: '李老师',
          position: '项目负责人',
          is_primary: true,
          is_decision_maker: true
        }],
        opportunities: [{
          id: 'opportunity-1',
          name: '平台技术验证',
          stage: '需求确认',
          amount: '29000.00',
          user_count: 50,
          license_type: 'SUBSCRIPTION',
          subscription_years: 1,
          approval_phase: 'approved'
        }]
      },
      follow_up_process: [{
        title: '技术验证阶段',
        occurred_at: '2026-08-18T10:00:00Z',
        customer_expression: '客户反馈平台满足当前验证要求。',
        sales_follow_up: '销售记录已完成验证结果确认。',
        activity_count: 2,
        evidence_refs: ['activity:10']
      }],
      recorded_follow_ups: [{
        title: '确认技术验证结果',
        content: '核对验证结果并记录。',
        status: '已完成',
        due_at: '2026-08-20T10:00:00Z',
        evidence_refs: ['activity:10']
      }]
    })

    const wrapper = mountProfile(profile)
    const text = wrapper.text()

    expect(text).toContain('客户摘要')
    expect(text).not.toContain('📌')
    expect(text).toContain('项目需求背景')
    expect(text).toContain('公司情况')
    expect(text).toContain('研发团队与项目组协同推进')
    expect(text).toContain('支持多站点部署验证，技术团队参与方案评估')
    expect(text).toContain('客户关系')
    expect(text).toContain('李老师')
    expect(text).toContain('当前主联系人 / 决策人')
    expect(text).not.toContain('客户具备多站点部署场景')
    expect(text).toContain('业务旅程：平台技术验证')
    expect(text).toContain('当前业务状态')
    expect(text).not.toContain('当前判断 / 业务推进概览')
    expect(text).toContain('平台技术验证')
    expect(text).toContain('最近的业务闭环')
    expect(text).not.toContain('跟进过程')
    expect(text).not.toContain('后续事项')
    expect(text).toContain('商机交易信息')
    expect(text).toContain('商机名称')
    expect(text).not.toContain('当前记录')
    expect(wrapper.findAll('table')).toHaveLength(0)
    expect(text).toContain('29,000 元')
    expect(text).toContain('50 人')
    expect(text).toContain('当前未记录合同')
    expect(text).toContain('[1]')
    expect(text).toContain('待办“确认技术验证结果”状态由“待完成”变为“已完成”。')
  })

  it('renders important changes as a newest-first stepper and groups same-day task updates', () => {
    const wrapper = mountProfile(baseProfile({
      current_situation: {
        business_status_rows: [{
          dimension: '商业推进',
          current: '当前仅有一条业务状态，应占满可用宽度。'
        }]
      },
      current_journeys: [{
        id: 'journey-1',
        name: '平台技术验证',
        status: '进行中',
        current_stage: '方案评估'
      }],
      important_changes: [
        {
          title: '跟进待办状态变化',
          task_id: 'task-1',
          change: '待办“确认技术验证结果”状态由“待完成”变为“已完成”。',
          occurred_at: '2026-08-20T11:00:00Z'
        },
        {
          title: '跟进待办状态变化',
          task_id: 'task-2',
          change: '待办“补充评估资料”状态由“待完成”变为“已完成”。',
          occurred_at: '2026-08-20T10:00:00Z'
        },
        {
          title: '业务旅程阶段变化',
          event_type: 'STAGE_CHANGED',
          change: '业务旅程进入方案评估阶段。',
          occurred_at: '2026-08-19T10:00:00Z'
        }
      ],
      long_term_context: {},
      follow_up_process: [],
      recorded_follow_ups: []
    }))

    const steps = wrapper.findAll('.profile-change-step')

    expect(wrapper.find('.profile-change-stepper').exists()).toBe(true)
    expect(steps).toHaveLength(2)
    expect(steps[0]?.text()).toContain('确认技术验证结果')
    expect(steps[0]?.text()).toContain('补充评估资料')
    expect(steps[1]?.text()).toContain('业务旅程进入方案评估阶段。')
    expect(wrapper.text()).not.toContain('之前')
    expect(wrapper.text()).not.toContain('现在')
    expect(wrapper.text()).not.toContain('—')
    expect(wrapper.find('.status-grid').exists()).toBe(true)
  })

  it('keeps the finished-profile reading order stable', () => {
    const profile = baseProfile({
      current_situation: {
        summary: '客户正在推进平台技术验证。',
        demand_background: {
          summary: '希望先完成验证，再评估采购。',
          items: [{ statement: '需要支持多站点部署。' }]
        }
      },
      current_journeys: [{
        id: 'journey-1',
        name: '平台技术验证',
        status: '进行中',
        current_stage: '试用验证',
        timeline: [{ summary: '完成技术验证。', occurred_at: '2026-08-20T10:00:00Z' }]
      }],
      important_changes: [{ change: '技术验证完成。' }],
      long_term_context: {
        customer: {
          industry_name: '科研服务',
          city: '广州',
          organization_structure: '研发团队与项目组协同推进',
          technical_characteristics: '支持多站点部署验证'
        },
        contacts: [{ name: '李老师', position: '项目负责人' }],
        opportunities: [{ name: '平台技术验证', stage: '需求确认' }]
      },
      follow_up_process: [{ title: '技术验证阶段', business_change: '验证完成。' }],
      recorded_follow_ups: []
    })

    const wrapper = mountProfile(profile)
    const headings = wrapper.findAll('h2').map((heading) => heading.text())

    expect(headings).toEqual([
      '客户摘要',
      '客户概况',
      '公司情况',
      '客户关系',
      '项目需求背景',
      '业务旅程：平台技术验证',
      '当前业务状态',
      '重要变化',
      '最近的业务闭环',
      '商机交易信息'
    ])
  })

  it('renders evidence references as compact inline indexes', () => {
    const wrapper = mountProfile(baseProfile({
      current_situation: {
        demand_background: {
          items: [{ statement: '客户提出多站点部署需求。', evidence_refs: ['activity:10'] }]
        }
      },
      current_journeys: [],
      important_changes: [],
      long_term_context: {},
      follow_up_process: [],
      recorded_follow_ups: []
    }))

    expect(wrapper.find('.evidence-stub').text()).toBe('[1]')
    expect(wrapper.text()).not.toContain('依据：')
  })
})
