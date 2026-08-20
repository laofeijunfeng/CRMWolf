import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import ts from 'typescript'
import { listFilterOperatorsByType } from '../listFilterTypes'

type BackendCatalogManifest = Record<
  string,
  Record<string, {
    type: 'text' | 'enum' | 'number' | 'date'
    filterable: boolean
    sortable: boolean
    ops: string[]
  }>
>

interface StaticQueryCapability {
  enabled: boolean
  apiKey?: string
}

interface StaticListField {
  key: string
  type?: 'text' | 'enum' | 'number' | 'date'
  role?: string
  columnEnabled: boolean
  filter: StaticQueryCapability
  sort: StaticQueryCapability
  filterDisabledReason?: string
  sortDisabledReason?: string
}

const srcDir = resolve(process.cwd(), 'src')
const viewsDir = resolve(srcDir, 'views')
const manifest = JSON.parse(
  readFileSync(resolve(srcDir, 'components/crmwolf/listQueryCatalogManifest.json'), 'utf8')
) as BackendCatalogManifest

const dataTableViews = {
  'ApprovalCenter.vue': 'approvals',
  'Contracts.vue': 'contracts',
  'CustomerTracking.vue': 'follow_up_tasks',
  'Customers.vue': 'customers',
  'Invoices.vue': 'invoices',
  'Leads.vue': 'leads',
  'Opportunities.vue': 'opportunities',
  'PaymentPlans.vue': 'payment_plans',
  'PaymentRecords.vue': 'payment_records'
} as const

function propertyName(property: ts.ObjectLiteralElementLike): string | undefined {
  if (!('name' in property) || property.name === undefined) return undefined
  if (ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)) return property.name.text
  return undefined
}

function propertyInitializer(
  object: ts.ObjectLiteralExpression,
  name: string
): ts.Expression | undefined {
  const property = object.properties.find((candidate) => propertyName(candidate) === name)
  return property !== undefined && ts.isPropertyAssignment(property) ? property.initializer : undefined
}

function stringValue(expression: ts.Expression | undefined): string | undefined {
  return expression !== undefined && (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression))
    ? expression.text
    : undefined
}

function enabledValue(expression: ts.Expression | undefined): boolean {
  return expression?.kind === ts.SyntaxKind.TrueKeyword || expression !== undefined && ts.isObjectLiteralExpression(expression)
}

function queryCapability(expression: ts.Expression | undefined, defaultEnabled: boolean): StaticQueryCapability {
  const enabled = expression === undefined ? defaultEnabled : enabledValue(expression)
  if (!enabled) return { enabled: false }
  if (expression !== undefined && ts.isObjectLiteralExpression(expression)) {
    const apiKey = stringValue(propertyInitializer(expression, 'apiKey'))
    return apiKey === undefined ? { enabled: true } : { enabled: true, apiKey }
  }
  return { enabled: true }
}

function extractFields(viewName: string): StaticListField[] {
  const source = readFileSync(resolve(viewsDir, viewName), 'utf8')
  const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)?.[1]
  if (script === undefined) throw new Error(`${viewName} has no TypeScript setup script`)

  const sourceFile = ts.createSourceFile(viewName, script, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  let fieldsInitializer: ts.Expression | undefined

  function findFields(node: ts.Node): void {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === 'fields') {
      fieldsInitializer = node.initializer
      return
    }
    ts.forEachChild(node, findFields)
  }
  findFields(sourceFile)

  if (fieldsInitializer === undefined) throw new Error(`${viewName} does not declare fields`)

  const fieldObjects: ts.ObjectLiteralExpression[] = []
  function collectFieldObjects(node: ts.Node): void {
    if (ts.isObjectLiteralExpression(node)) {
      const key = stringValue(propertyInitializer(node, 'key'))
      const label = stringValue(propertyInitializer(node, 'label'))
      if (key !== undefined && label !== undefined) fieldObjects.push(node)
    }
    ts.forEachChild(node, collectFieldObjects)
  }
  collectFieldObjects(fieldsInitializer)

  return fieldObjects.map((object) => {
    const key = stringValue(propertyInitializer(object, 'key'))
    if (key === undefined) throw new Error(`${viewName} contains a field without a static key`)
    const type = stringValue(propertyInitializer(object, 'type')) as StaticListField['type']
    const role = stringValue(propertyInitializer(object, 'role'))
    const columnExpression = propertyInitializer(object, 'column')
    const columnEnabled = enabledValue(columnExpression)
    const businessColumn = columnEnabled && role === undefined
    const filterExpression = propertyInitializer(object, 'filter')
    const sortExpression = propertyInitializer(object, 'sort')

    const field: StaticListField = {
      key,
      columnEnabled,
      filter: queryCapability(filterExpression, businessColumn),
      sort: queryCapability(sortExpression, businessColumn)
    }
    if (type !== undefined) field.type = type
    if (role !== undefined) field.role = role
    const filterDisabledReason = stringValue(propertyInitializer(object, 'filterDisabledReason'))
    const sortDisabledReason = stringValue(propertyInitializer(object, 'sortDisabledReason'))
    if (filterDisabledReason !== undefined) field.filterDisabledReason = filterDisabledReason
    if (sortDisabledReason !== undefined) field.sortDisabledReason = sortDisabledReason
    return field
  })
}

function queryKey(field: StaticListField, capability: StaticQueryCapability): string {
  return capability.apiKey ?? field.key
}

describe('DataTable frontend/backend list-query contract', () => {
  it('keeps every enabled frontend filter and sort key/type/operator in the backend catalog', () => {
    for (const [viewName, catalogName] of Object.entries(dataTableViews)) {
      const backendFields = manifest[catalogName]
      expect(backendFields, `${viewName} backend catalog`).toBeDefined()

      for (const field of extractFields(viewName)) {
        for (const [capabilityName, capability] of [
          ['filter', field.filter],
          ['sort', field.sort]
        ] as const) {
          if (!capability.enabled) continue
          const key = queryKey(field, capability)
          const backendField = backendFields?.[key]
          expect(backendField, `${viewName} ${capabilityName} ${key}`).toBeDefined()
          expect(backendField?.type, `${viewName} ${capabilityName} ${key} type`).toBe(field.type)
          if (capabilityName === 'filter') {
            expect(backendField?.filterable, `${viewName} filter ${key} expression`).toBe(true)
            const expectedOperators: readonly string[] =
              field.type === undefined
                ? []
                : listFilterOperatorsByType[field.type].map((operator) => operator.value)
            expect(backendField?.ops, `${viewName} filter ${key} operators`).toEqual(
              expect.arrayContaining([...expectedOperators])
            )
          } else {
            expect(backendField?.sortable, `${viewName} sort ${key} expression`).toBe(true)
          }
        }
      }
    }
  })

  it('requires a reason whenever a business column explicitly disables filter or sort', () => {
    for (const viewName of Object.keys(dataTableViews)) {
      for (const field of extractFields(viewName)) {
        if (!field.columnEnabled || field.role === 'action' || field.role === 'decoration') continue
        if (!field.filter.enabled) {
          expect(field.filterDisabledReason, `${viewName} filter ${field.key}`).toBeTruthy()
        }
        if (!field.sort.enabled) {
          expect(field.sortDisabledReason, `${viewName} sort ${field.key}`).toBeTruthy()
        }
      }
    }
  })

  it('uses only the unified server query protocol on all paginated DataTable pages', () => {
    for (const viewName of Object.keys(dataTableViews)) {
      const source = readFileSync(resolve(viewsDir, viewName), 'utf8')
      expect(source, viewName).toContain('serializeListQuery')
      expect(source, viewName).not.toContain("from '@/utils/listFilters'")
      expect(source, viewName).not.toContain('getPrimarySort')
      expect(source, viewName).not.toContain('serializeListSorts')
    }
  })

  it('does not reintroduce client-side filtering, sorting, or slicing in CustomerTracking', () => {
    const source = readFileSync(resolve(viewsDir, 'CustomerTracking.vue'), 'utf8')
    expect(source).not.toContain('applyFilters')
    expect(source).not.toContain('applySorts')
    expect(source).not.toContain('filteredRows')
    expect(source).not.toContain('pagedRows')
    expect(source).not.toMatch(/\.slice\s*\(/)
  })
})
