import { defineListFields } from '@/components/crmwolf/listFieldCatalog'
import type { ListFieldDefinition, ListFieldOption } from '@/components/crmwolf/listFieldCatalog'

export const businessJourneyStageOptions: ListFieldOption[] = [
  { value: 'early_communication', label: '早期沟通' },
  { value: 'active_progress', label: '积极推进' },
  { value: 'closing_soon', label: '即将成交' },
  { value: 'contract_processing', label: '合同处理中' },
  { value: 'payment_processing', label: '回款处理中' },
  { value: 'invoice_processing', label: '开票处理中' },
  { value: 'completed', label: '已完成' },
  { value: 'lost', label: '已流失' }
]

export const businessJourneyPurchaseTypeOptions: ListFieldOption[] = [
  { value: 'NEW', label: '新购' },
  { value: 'RENEWAL', label: '续购' },
  { value: 'EXPANSION', label: '增购' }
]

export function createBusinessJourneyListFields(ownerOptions: ListFieldOption[]): ListFieldDefinition[] {
  return defineListFields([
    { key: 'name', label: '旅程名称', type: 'text', column: { width: '220px' }, filter: { apiKey: 'journey_name' }, sort: { apiKey: 'journey_name' } },
    { key: 'customer_name', label: '客户', type: 'text', column: { width: '190px' }, filter: true, sort: true },
    { key: 'current_board_stage', label: '当前阶段', type: 'enum', options: businessJourneyStageOptions, column: { width: '120px' }, filter: { apiKey: 'stage' }, sort: false, sortDisabledReason: '阶段由跨对象状态动态推断，请使用看板查看阶段顺序' },
    { key: 'primary_opportunity_name', label: '主商机', type: 'text', column: { width: '200px' }, filter: false, filterDisabledReason: '主商机仅作关联摘要', sort: false, sortDisabledReason: '主商机仅作关联摘要' },
    { key: 'product_name', label: '产品', type: 'text', column: { width: '140px' }, filter: true, sort: true },
    { key: 'amount', label: '金额', type: 'number', column: { width: '130px', align: 'right' }, filter: true, sort: true },
    { key: 'purchase_type', label: '采购类型', type: 'enum', options: businessJourneyPurchaseTypeOptions, column: { width: '110px' }, filter: true, sort: true },
    { key: 'owner_id', label: '负责人', type: 'enum', options: ownerOptions, column: { width: '120px' }, filter: true, sort: true },
    { key: 'last_event_at', label: '最近动态', type: 'date', column: { width: '150px' }, filter: true, sort: true },
    { key: 'expected_closing_date', label: '预计成交日期', type: 'date', column: { width: '140px' }, filter: true, sort: true }
  ])
}
