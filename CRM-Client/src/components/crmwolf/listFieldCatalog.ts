import type { ListFilterField, ListFilterFieldType } from './listFilterTypes'
import type { ListSortField } from './listSortTypes'

export type ListFieldType = ListFilterFieldType

export interface ListFieldOption {
  value: string | number
  label: string
}

export interface ListFieldColumnConfig {
  width?: string
  align?: 'left' | 'center' | 'right'
  fixed?: 'left' | 'right' | undefined
  hideable?: boolean | undefined
  configurable?: boolean | undefined
  visible?: boolean | undefined
}

export interface ListFieldQueryConfig {
  /** 查询参数 / order_by 字段。默认使用字段 key，列偏好始终使用 key。 */
  apiKey?: string
  label?: string
  options?: ListFieldOption[]
}

/**
 * 列表字段注册表条目。
 *
 * DataTable 的列、筛选、排序、字段配置必须来自这份定义：
 * - `column` 控制表格列和字段配置
 * - `filter` 控制筛选下拉，且仅在列表查询接口支持时开启
 * - `sort` 控制排序下拉，且仅在 order_by 支持时开启
 * - 条件能力用 `false` 显式关闭，不要再拆出第二份字段清单
 * - 开启筛选或排序时必须声明 `type`，禁止默认成 text
 *
 * 三个工具不必展示同一组字段。关键字可以只有筛选，协作者或派生展示列可以只有列配置，
 * 开票时间可以只有排序。新增字段时只改这一条定义，不要再维护三份清单。
 */
export interface ListFieldDefinition {
  key: string
  label: string
  /** 列展示可省略；筛选或排序开启时必填，决定控件类型。 */
  type?: ListFieldType
  options?: ListFieldOption[]
  column?: true | false | ListFieldColumnConfig
  filter?: true | false | ListFieldQueryConfig
  sort?: true | false | ListFieldQueryConfig
}

export interface DataTableColumn {
  key: string
  title: string
  width?: string
  align?: 'left' | 'center' | 'right'
  fixed?: 'left' | 'right' | undefined
  hideable?: boolean | undefined
  configurable?: boolean | undefined
  visible?: boolean | undefined
}

export interface ProjectedListFields {
  columns: DataTableColumn[]
  filterFields: ListFilterField[]
  sortFields: ListSortField[]
}

function isEnabled(value: unknown): value is true | object {
  return value === true || (typeof value === 'object' && value !== null)
}

function assertListFieldCatalog(fields: ListFieldDefinition[]): void {
  const seenKeys = new Set<string>()
  for (const field of fields) {
    if (seenKeys.has(field.key)) {
      throw new Error(`Duplicate list field key: ${field.key}`)
    }
    seenKeys.add(field.key)
    if ((isEnabled(field.filter) || isEnabled(field.sort)) && field.type === undefined) {
      throw new Error(`List field "${field.key}" enables filter/sort but has no type`)
    }
  }
}

function queryConfig(value: true | ListFieldQueryConfig | undefined): ListFieldQueryConfig {
  if (value === true || value === undefined) return {}
  return value
}

function projectQueryField(
  field: ListFieldDefinition,
  query: true | ListFieldQueryConfig | undefined
): ListFilterField {
  const config = queryConfig(query)
  if (field.type === undefined) {
    throw new Error(`List field "${field.key}" enables filter/sort but has no type`)
  }
  const projected: ListFilterField = {
    key: config.apiKey ?? field.key,
    label: config.label ?? field.label,
    type: field.type
  }
  const options = config.options ?? field.options
  if (options !== undefined) {
    projected.options = options
  }
  return projected
}

export function defineListFields(fields: ListFieldDefinition[]): ListFieldDefinition[] {
  assertListFieldCatalog(fields)
  return fields
}

export function projectListFieldCatalog(fields: ListFieldDefinition[]): ProjectedListFields {
  assertListFieldCatalog(fields)
  const columns: DataTableColumn[] = []
  const filterFields: ListFilterField[] = []
  const sortFields: ListSortField[] = []

  for (const field of fields) {
    if (isEnabled(field.column)) {
      const column = field.column === true ? {} : field.column
      const projected: DataTableColumn = {
        key: field.key,
        title: field.label
      }
      if (column.width !== undefined) projected.width = column.width
      if (column.align !== undefined) projected.align = column.align
      if (column.fixed !== undefined) projected.fixed = column.fixed
      if (column.hideable !== undefined) projected.hideable = column.hideable
      if (column.configurable !== undefined) projected.configurable = column.configurable
      if (column.visible !== undefined) projected.visible = column.visible
      columns.push(projected)
    }

    if (isEnabled(field.filter)) {
      filterFields.push(projectQueryField(field, field.filter))
    }

    if (isEnabled(field.sort)) {
      sortFields.push(projectQueryField(field, field.sort))
    }
  }

  return { columns, filterFields, sortFields }
}
