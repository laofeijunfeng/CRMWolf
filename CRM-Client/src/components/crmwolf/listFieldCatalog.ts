import type { ListFilterField, ListFilterFieldType } from './listFilterTypes'
import type { ListSortField } from './listSortTypes'

export type ListFieldType = ListFilterFieldType
export type ListFieldRole = 'keyword' | 'action' | 'decoration'

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
 * - 业务列默认同时打开筛选和排序
 * - 关键字、操作列、装饰列不默认打开筛排
 * - 关闭筛排必须写 `false` 并给出原因
 * - 开启筛选或排序时必须声明 `type`
 */
export interface ListFieldDefinition {
  key: string
  label: string
  /** 列展示可省略；筛选或排序开启时必填，决定控件类型。 */
  type?: ListFieldType
  options?: ListFieldOption[]
  role?: ListFieldRole
  column?: true | false | ListFieldColumnConfig
  filter?: true | false | ListFieldQueryConfig
  sort?: true | false | ListFieldQueryConfig
  export?: true | false | ListFieldExportConfig
  filterDisabledReason?: string
  sortDisabledReason?: string
}

export interface ListFieldExportConfig {
  key?: string
  label?: string
}

export interface DataTableExportField {
  fieldKey: string
  key: string
  label: string
  source: 'column' | 'export-only'
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
  exportFields: DataTableExportField[]
}

function isEnabled(value: unknown): value is true | object {
  return value === true || (typeof value === 'object' && value !== null)
}

function isBusinessColumn(field: ListFieldDefinition): boolean {
  return isEnabled(field.column) && field.role === undefined
}

export function isUnsafeExportKey(key: string): boolean {
  return key === 'id' || (
    key.endsWith('_id')
    && key !== 'public_id'
    && !key.endsWith('_public_id')
  )
}

function resolveListFieldExport(
  field: ListFieldDefinition
): { enabled: boolean; key: string; label: string } {
  const explicit = field.export
  const key = typeof explicit === 'object' && explicit !== null && explicit.key !== undefined && explicit.key !== ''
    ? explicit.key
    : field.key
  const label = typeof explicit === 'object' && explicit !== null && explicit.label !== undefined && explicit.label !== ''
    ? explicit.label
    : field.label
  const enabled = explicit !== undefined
    ? isEnabled(explicit)
    : isBusinessColumn(field) && !isUnsafeExportKey(key)
  if (enabled && isUnsafeExportKey(key)) {
    throw new Error(`List field export key "${key}" is unsafe`)
  }
  return { enabled, key, label }
}

export function resolveListFieldFilter(
  field: ListFieldDefinition
): true | false | ListFieldQueryConfig | undefined {
  if (field.filter !== undefined) return field.filter
  if (isBusinessColumn(field)) return true
  return undefined
}

export function resolveListFieldSort(
  field: ListFieldDefinition
): true | false | ListFieldQueryConfig | undefined {
  if (field.sort !== undefined) return field.sort
  if (isBusinessColumn(field)) return true
  return undefined
}

export function listFieldQueryKey(
  field: ListFieldDefinition,
  query: true | false | ListFieldQueryConfig | undefined = undefined
): string {
  const target = query === undefined ? resolveListFieldFilter(field) : query
  if (target !== undefined && target !== false && target !== true && target.apiKey !== undefined && target.apiKey !== '') {
    return target.apiKey
  }
  const fallback = field.filter !== undefined && field.filter !== false && field.filter !== true
    ? field.filter.apiKey
    : undefined
  const sortFallback = field.sort !== undefined && field.sort !== false && field.sort !== true
    ? field.sort.apiKey
    : undefined
  return fallback ?? sortFallback ?? field.key
}

function assertExportFields(fields: ListFieldDefinition[]): void {
  const seenExportKeys = new Set<string>()
  for (const field of fields) {
    const exportProjection = resolveListFieldExport(field)
    if (!exportProjection.enabled) continue
    if (seenExportKeys.has(exportProjection.key)) {
      throw new Error(`Duplicate list export field key: ${exportProjection.key}`)
    }
    seenExportKeys.add(exportProjection.key)
  }
}

function assertListFieldCatalog(fields: ListFieldDefinition[]): void {
  assertExportFields(fields)
  const seenKeys = new Set<string>()
  for (const field of fields) {
    if (seenKeys.has(field.key)) {
      throw new Error(`Duplicate list field key: ${field.key}`)
    }
    seenKeys.add(field.key)

    const filter = resolveListFieldFilter(field)
    const sort = resolveListFieldSort(field)
    if (isBusinessColumn(field) && filter === false && (field.filterDisabledReason === undefined || field.filterDisabledReason === '')) {
      throw new Error(`List field "${field.key}" disables filter without filterDisabledReason`)
    }
    if (isBusinessColumn(field) && sort === false && (field.sortDisabledReason === undefined || field.sortDisabledReason === '')) {
      throw new Error(`List field "${field.key}" disables sort without sortDisabledReason`)
    }
    if ((isEnabled(filter) || isEnabled(sort)) && field.type === undefined) {
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
  const exportFields: DataTableExportField[] = []
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

    const filter = resolveListFieldFilter(field)
    if (isEnabled(filter)) {
      filterFields.push(projectQueryField(field, filter))
    }

    const sort = resolveListFieldSort(field)
    if (isEnabled(sort)) {
      sortFields.push(projectQueryField(field, sort))
    }

    const exportProjection = resolveListFieldExport(field)
    if (exportProjection.enabled) {
      exportFields.push({
        fieldKey: field.key,
        key: exportProjection.key,
        label: exportProjection.label,
        source: isEnabled(field.column) ? 'column' : 'export-only'
      })
    }
  }

  return { columns, filterFields, sortFields, exportFields }
}
