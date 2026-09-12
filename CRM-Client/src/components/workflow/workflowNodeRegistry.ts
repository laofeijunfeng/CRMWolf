import { type Component } from 'vue'
import { Bell, BriefcaseBusiness, Building2, CheckCircle2, GitBranch, ListChecks, PlayCircle, UserPlus } from 'lucide-vue-next'
import TriggerOpportunityStagePanel from './nodeConfigPanels/TriggerOpportunityStagePanel.vue'
import ApprovalNodePanel from './nodeConfigPanels/ApprovalNodePanel.vue'
import ConditionBranchPanel from './nodeConfigPanels/ConditionBranchPanel.vue'
import ActionCreateFollowUpTaskPanel from './nodeConfigPanels/ActionCreateFollowUpTaskPanel.vue'
import ActionNotifyPanel from './nodeConfigPanels/ActionNotifyPanel.vue'
import ActionCreateCustomerPanel from './nodeConfigPanels/ActionCreateCustomerPanel.vue'
import ActionCreateContactPanel from './nodeConfigPanels/ActionCreateContactPanel.vue'
import ActionCreateOpportunityPanel from './nodeConfigPanels/ActionCreateOpportunityPanel.vue'

export const WORKFLOW_NODE_TYPES = [
  'trigger.opportunity_stage_changed',
  'approval.step',
  'control.condition',
  'action.create_follow_up_task',
  'action.notify',
  'crm.create_customer',
  'crm.create_contact',
  'crm.create_opportunity',
] as const

export type WorkflowNodeType = typeof WORKFLOW_NODE_TYPES[number]
export type WorkflowNodeCategory = 'trigger' | 'crm' | 'action' | 'control' | 'approval'

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
    type: 'approval.step', label: '审批节点', category: 'approval', icon: CheckCircle2,
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
  'crm.create_customer': {
    type: 'crm.create_customer', label: '创建客户', category: 'crm', icon: Building2,
    component: ActionCreateCustomerPanel,
    defaults: () => ({ account_name: '', city: '', industry: '', address: '', company_scale: '', owner_strategy: 'creator', default_procurement_method_id: null }),
    requiredFields: ['account_name', 'city'], isTrigger: false,
    summary: config => typeof config['account_name'] === 'string' && config['account_name'].trim() !== '' ? config['account_name'] : '未命名客户',
  },
  'crm.create_contact': {
    type: 'crm.create_contact', label: '创建联系人', category: 'crm', icon: UserPlus,
    component: ActionCreateContactPanel,
    defaults: () => ({ customer_ref: '', name: '', gender: '1', position: '', mobile: '', is_decision_maker: false, email: '', wechat_id: '', remark: '' }),
    requiredFields: ['customer_ref', 'name', 'gender', 'position', 'mobile'], isTrigger: false,
    summary: config => typeof config['name'] === 'string' && config['name'].trim() !== '' ? config['name'] : '未命名联系人',
  },
  'crm.create_opportunity': {
    type: 'crm.create_opportunity', label: '创建商机', category: 'crm', icon: BriefcaseBusiness,
    component: ActionCreateOpportunityPanel,
    defaults: () => ({ customer_ref: '', opportunity_name: '', total_amount: 0, user_count: 1, license_type: 'SUBSCRIPTION', subscription_years: 1, purchase_type: 'NEW', expected_closing_date: '', decision_maker_count: null, procurement_method_id: null, procurement_stage_id: null, owner_strategy: 'creator' }),
    requiredFields: ['customer_ref', 'total_amount', 'user_count', 'license_type', 'purchase_type', 'expected_closing_date'], isTrigger: false,
    summary: config => typeof config['opportunity_name'] === 'string' && config['opportunity_name'].trim() !== '' ? config['opportunity_name'] : '未命名商机',
  },
}
