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
      category: 'action',
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

    for (const definition of Object.values(WORKFLOW_NODE_REGISTRY)) {
      expect(definition.defaults()).toEqual(expect.any(Object))
      expect(definition.icon).toBeDefined()
      expect(definition.component).toBeDefined()
      expect(definition.summary(definition.defaults())).toEqual(expect.any(String))
    }
  })
})
