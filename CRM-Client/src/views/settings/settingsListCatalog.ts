import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'

export const SETTINGS_LIST_QUERY_DISABLED_REASON = '本期仍全量读取当前团队数据，未接入服务端 list-query'

export function settingsListColumn(
  field: Omit<ListFieldDefinition, 'filter' | 'sort' | 'filterDisabledReason' | 'sortDisabledReason'>,
): ListFieldDefinition {
  return {
    ...field,
    filter: false,
    sort: false,
    filterDisabledReason: SETTINGS_LIST_QUERY_DISABLED_REASON,
    sortDisabledReason: SETTINGS_LIST_QUERY_DISABLED_REASON,
  }
}
