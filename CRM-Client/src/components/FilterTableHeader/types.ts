/**
 * FilterTableHeader 组件类型定义
 */

/** 篮选类型 */
export type FilterType = 'search' | 'select' | 'daterange' | 'numrange'

/** 下拉选项 */
export interface SelectOption {
  value: string | number
  label: string
}

/** 筛选配置 */
export interface FilterConfig {
  type: FilterType
  placeholder?: string
  options?: SelectOption[]
  multiple?: boolean
  min?: number
  max?: number
}

/** 表头配置 */
export interface HeaderConfig {
  label: string
  field: string
  filter?: FilterConfig
  sortable?: boolean
  minWidth?: number | string
  width?: number | string
  fixed?: 'left' | 'right' | boolean
}

/** 筛选值 */
export interface FilterValue {
  search?: string
  select?: string | number | string[] | null
  daterange?: [string, string] | null
  numrange?: [number | null, number | null]
}

/** 排序状态 */
export interface SortState {
  field: string
  order: 'asc' | 'desc' | null
}