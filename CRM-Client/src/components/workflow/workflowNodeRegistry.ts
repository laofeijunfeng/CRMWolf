import { type Component } from 'vue'
import { Bell, CheckCircle2, GitBranch, ListChecks, PlayCircle } from 'lucide-vue-next'
import TriggerOpportunityStagePanel from './nodeConfigPanels/TriggerOpportunityStagePanel.vue'
import ApprovalNodePanel from './nodeConfigPanels/ApprovalNodePanel.vue'
import ConditionBranchPanel from './nodeConfigPanels/ConditionBranchPanel.vue'
import ActionCreateFollowUpTaskPanel from './nodeConfigPanels/ActionCreateFollowUpTaskPanel.vue'
import ActionNotifyPanel from './nodeConfigPanels/ActionNotifyPanel.vue'

export const WORKFLOW_NODE_TYPES = [
  'trigger.opportunity_stage_changed',
  'approval.step',
  'control.condition',
  'action.create_follow_up_task',
  'action.notify',
] as const

export type WorkflowNodeType = typeof WORKFLOW_NODE_TYPES[number]
export type WorkflowNodeCategory = 'trigger' | 'control' | 'action'

export interface WorkflowNodeConfigPanelProps {
  config: Record<string, unknown>
  'onUpdate:config': (patch: Record<string, unknown>) => void
}

export interface WorkflowNodeTypeDefinition {
  type: WorkflowNodeType
  label: string
  category: WorkflowNodeCategory
  icon: Component
  component: Component
  defaults: () => Record<string, unknown>
  requiredFields: readonly string[]
  isTrigger: boolean
  summary: (config: Record<string, unknown>) => string
}

export const WORKFLOW_NODE_REGISTRY: Record<WorkflowNodeType, WorkflowNodeTypeDefinition> = {
  'trigger.opportunity_stage_changed': {
    type: 'trigger.opportunity_stage_changed', label: '商机阶段变化', category: 'trigger', icon: PlayCircle,
    component: TriggerOpportunityStagePanel, defaults: () => ({ from_stage: null, to_stage: '' }), requiredFields: ['to_stage'], isTrigger: true,
    summary: config => typeof config['to_stage'] === 'string' && config['to_stage'].trim() !== '' ? `目标阶段：${config['to_stage']}` : '未配置目标阶段',
  },
  'approval.step': {
    type: 'approval.step', label: '审批节点', category: 'action', icon: CheckCircle2,
    component: ApprovalNodePanel, defaults: () => ({ node_name: '', approve_role: '' }), requiredFields: ['node_name', 'approve_role'], isTrigger: false,
    summary: config => typeof config['node_name'] === 'string' && config['node_name'].trim() !== '' ? config['node_name'] : '未命名审批节点',
  },
  'control.condition': {
    type: 'control.condition', label: '条件分支', category: 'control', icon: GitBranch,
    component: ConditionBranchPanel, defaults: () => ({ field: '', operator: 'eq', value: '' }), requiredFields: ['field', 'operator', 'value'], isTrigger: false,
    summary: config => {
      const field = typeof config['field'] === 'string' ? config['field'] : ''
      const operator = typeof config['operator'] === 'string' ? config['operator'] : ''
      return field !== '' && operator !== '' ? `${field} ${operator}` : '未配置条件'
    },
  },
  'action.create_follow_up_task': {
    type: 'action.create_follow_up_task', label: '创建跟进任务', category: 'action', icon: ListChecks,
    component: ActionCreateFollowUpTaskPanel, defaults: () => ({ title: '', assignee_strategy: 'owner', due_offset_days: 0 }), requiredFields: ['title'], isTrigger: false,
    summary: config => typeof config['title'] === 'string' && config['title'].trim() !== '' ? config['title'] : '未命名跟进任务',
  },
  'action.notify': {
    type: 'action.notify', label: '发送通知', category: 'action', icon: Bell,
    component: ActionNotifyPanel, defaults: () => ({ notify_target: 'owner', message_template: '' }), requiredFields: ['notify_target'], isTrigger: false,
    summary: config => typeof config['notify_target'] === 'string' && config['notify_target'].trim() !== '' ? `通知：${config['notify_target']}` : '未配置通知对象',
  },
}
