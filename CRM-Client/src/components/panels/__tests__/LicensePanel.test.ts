import { mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, type VNode } from 'vue'
import { describe, expect, it } from 'vitest'
import LicensePanel from '../LicensePanel.vue'
import type { DeploymentInfoResponse } from '@/api/deployment'
import type { LicenseApplicationResponse } from '@/api/licenseApplication'

const deployment: DeploymentInfoResponse = {
  id: 42,
  customer_id: 'cus_1',
  team_id: 1,
  deployment_name: '生产环境',
  server_address: 'https://crm.example.com',
  authorized_users: null,
  is_default: true,
  created_time: '2026-08-20T10:00:00Z',
  last_modified_time: '2026-08-20T10:00:00Z'
}


const licenseApplication = (status: LicenseApplicationResponse['status']): LicenseApplicationResponse => ({
  id: 7,
  team_id: 1,
  application_number: 'LIC-20260820-0001',
  customer_id: 'cus_1',
  deployment_info_id: null,
  contract_id: null,
  authorized_users: 10,
  expiry_date: '2026-12-31',
  license_type: 'TRIAL',
  enterprise_id: null,
  supported_modules: null,
  server_license_code: null,
  client_license_code: null,
  remark: null,
  license_code: null,
  status,
  applicant_id: 'user_1',
  approver_id: null,
  approved_time: null,
  created_time: '2026-08-20T10:00:00Z',
  last_modified_time: '2026-08-20T10:00:00Z',
  customer_name: '测试客户',
  deployment_name: null,
  contract_name: null
})

const ListCardStub = defineComponent({
  props: {
    title: { type: String, required: true },
    items: { type: Array, required: true }
  },
  setup(props, { slots }): () => VNode {
    return () => h('section', { class: 'list-card-stub' }, [
      h('h3', props.title),
      ...(props.items as DeploymentInfoResponse[]).map((item): VNode => h('div', { class: 'list-card-item-stub' }, [
        slots['itemMain']?.({ item }),
        slots['itemActions']?.({ item })
      ]))
    ])
  }
})

const mountPanel = (options: { canDeleteDeployment?: boolean; canDeleteApplication?: boolean; licenseApplications?: LicenseApplicationResponse[] } = {}): VueWrapper => mount(LicensePanel, {
  props: {
    customerId: 'cus_1',
    licenseApplications: options.licenseApplications ?? [],
    deployments: [deployment],
    showLicenseApplications: options.licenseApplications !== undefined,
    canDeleteDeployment: options.canDeleteDeployment ?? true,
    canDeleteApplication: options.canDeleteApplication ?? false
  },
  global: {
    stubs: {
      ListCard: ListCardStub,
      Server: true,
      Button: defineComponent({
        inheritAttrs: true,
        setup(_, { attrs, slots }): () => VNode {
          return () => h('button', attrs, slots['default']?.())
        }
      }),
      Badge: defineComponent({
        setup(_, { slots }): () => VNode {
          return () => h('span', slots['default']?.())
        }
      })
    }
  }
})

describe('LicensePanel deployment actions', () => {
  it('emits the deployment id when the delete icon is clicked', async () => {
    const wrapper = mountPanel()

    const deleteButton = wrapper.get('[aria-label="删除部署信息 生产环境"]')
    await deleteButton.trigger('click')

    expect(wrapper.emitted('delete-deployment')).toEqual([[42]])
  })

  it('hides the delete icon when deletion is not allowed', () => {
    const wrapper = mountPanel({ canDeleteDeployment: false })

    expect(wrapper.find('[aria-label="删除部署信息 生产环境"]').exists()).toBe(false)
  })
})


describe('LicensePanel license application actions', () => {
  it('shows and emits deletion for draft applications when allowed', async () => {
    const wrapper = mountPanel({
      canDeleteApplication: true,
      licenseApplications: [licenseApplication('DRAFT')]
    })

    const deleteButton = wrapper.get('[aria-label="删除许可证申请 LIC-20260820-0001"]')
    await deleteButton.trigger('click')

    expect(wrapper.emitted('delete-application')).toEqual([[7]])
  })

  it('hides deletion for non-draft applications', () => {
    const wrapper = mountPanel({
      canDeleteApplication: true,
      licenseApplications: [licenseApplication('PENDING')]
    })

    expect(wrapper.find('[aria-label="删除许可证申请 LIC-20260820-0001"]').exists()).toBe(false)
  })

  it('hides deletion when application deletion is not allowed', () => {
    const wrapper = mountPanel({
      canDeleteApplication: false,
      licenseApplications: [licenseApplication('DRAFT')]
    })

    expect(wrapper.find('[aria-label="删除许可证申请 LIC-20260820-0001"]').exists()).toBe(false)
  })
})
