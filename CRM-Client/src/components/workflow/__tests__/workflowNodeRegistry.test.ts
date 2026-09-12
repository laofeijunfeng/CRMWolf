import { describe, expect, it } from 'vitest'
import { WORKFLOW_NODE_REGISTRY, type WorkflowNodeType } from '../workflowNodeRegistry'

describe('WORKFLOW_NODE_REGISTRY', () => {
  it('registers every shared workflow node type', () => {
    const types: WorkflowNodeType[] = [
      'trigger.opportunity_stage_changed',
      'approval.step',
      'control.condition',
      'action.create_follow_up_task',
      'action.notify',
      'crm.create_customer',
      'crm.create_contact',
      'crm.create_opportunity',
    ]

    expect(Object.keys(WORKFLOW_NODE_REGISTRY).sort()).toEqual(types.sort())
  })

  it('provides category, label, defaults, and required fields for each type', () => {
    expect(WORKFLOW_NODE_REGISTRY['trigger.opportunity_stage_changed']).toMatchObject({
      category: 'trigger',
      label: '商机阶段变化',
      requiredFields: ['to_stage'],
      isTrigger: true,
    })
    expect(WORKFLOW_NODE_REGISTRY['approval.step']).toMatchObject({
      category: 'approval',
      label: '审批节点',
      requiredFields: ['node_name', 'approve_role'],
      isTrigger: false,
    })
    expect(WORKFLOW_NODE_REGISTRY['control.condition']).toMatchObject({
      category: 'control',
      label: '条件分支',
      requiredFields: ['field', 'operator', 'value'],
      isTrigger: false,
    })
    expect(WORKFLOW_NODE_REGISTRY['action.create_follow_up_task']).toMatchObject({
      category: 'action',
      label: '创建跟进任务',
      requiredFields: ['title'],
      isTrigger: false,
    })
    expect(WORKFLOW_NODE_REGISTRY['action.notify']).toMatchObject({
      category: 'action',
      label: '发送通知',
      requiredFields: ['notify_target'],
      isTrigger: false,
    })
    expect(WORKFLOW_NODE_REGISTRY['crm.create_customer']).toMatchObject({
      category: 'crm',
      label: '创建客户',
      requiredFields: ['account_name', 'city'],
      isTrigger: false,
    })
    expect(WORKFLOW_NODE_REGISTRY['crm.create_customer'].defaults()).toEqual({
      account_name: '', city: '', industry: '', address: '', company_scale: '', owner_strategy: 'creator', default_procurement_method_id: null,
    })
    expect(WORKFLOW_NODE_REGISTRY['crm.create_contact']).toMatchObject({
      category: 'crm',
      label: '创建联系人',
      requiredFields: ['customer_ref', 'name', 'gender', 'position', 'mobile'],
      isTrigger: false,
    })
    expect(WORKFLOW_NODE_REGISTRY['crm.create_contact'].defaults()).toEqual({
      customer_ref: '', name: '', gender: '1', position: '', mobile: '', is_decision_maker: false, email: '', wechat_id: '', remark: '',
    })
    expect(WORKFLOW_NODE_REGISTRY['crm.create_opportunity']).toMatchObject({
      category: 'crm',
      label: '创建商机',
      requiredFields: ['customer_ref', 'total_amount', 'user_count', 'license_type', 'purchase_type', 'expected_closing_date'],
      isTrigger: false,
    })
    expect(WORKFLOW_NODE_REGISTRY['crm.create_opportunity'].defaults()).toEqual({
      customer_ref: '', opportunity_name: '', total_amount: 0, user_count: 1, license_type: 'SUBSCRIPTION', subscription_years: 1, purchase_type: 'NEW', expected_closing_date: '', decision_maker_count: null, procurement_method_id: null, procurement_stage_id: null, owner_strategy: 'creator',
    })

    for (const definition of Object.values(WORKFLOW_NODE_REGISTRY)) {
      expect(definition.defaults()).toEqual(expect.any(Object))
      expect(definition.icon).toBeDefined()
      expect(definition.component).toBeDefined()
      expect(definition.summary(definition.defaults())).toEqual(expect.any(String))
    }
  })

  it('summarizes CRM resource nodes', () => {
    expect(WORKFLOW_NODE_REGISTRY['crm.create_customer'].summary({ account_name: 'Acme' })).toBe('Acme')
    expect(WORKFLOW_NODE_REGISTRY['crm.create_contact'].summary({ name: '王总' })).toBe('王总')
    expect(WORKFLOW_NODE_REGISTRY['crm.create_opportunity'].summary({ opportunity_name: '续费项目' })).toBe('续费项目')
  })
})
