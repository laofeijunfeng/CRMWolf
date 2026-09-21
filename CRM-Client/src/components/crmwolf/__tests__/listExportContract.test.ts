import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'
import { isUnsafeExportKey } from '../listFieldCatalog'

type ExportManifest = Record<string, Record<string, { label: string; type: string }>>

interface StaticExportField {
  fieldKey: string
  exportKey: string
  label: string
}

const srcDir = resolve(process.cwd(), 'src')
const viewsDir = resolve(srcDir, 'views')
const manifest = JSON.parse(
  readFileSync(resolve(srcDir, 'components/crmwolf/listExportCatalogManifest.json'), 'utf8'),
) as ExportManifest

const dataTableViews = {
  'ApprovalCenter.vue': { resource: 'approvals', permission: 'approval:export' },
  'Contracts.vue': { resource: 'contracts', permission: 'contract:export' },
  'CustomerTracking.vue': { resource: 'follow_up_tasks', permission: 'follow_up_task:export' },
  'Customers.vue': { resource: 'customers', permission: 'customer:export' },
  'Invoices.vue': { resource: 'invoices', permission: 'invoice:export' },
  'Leads.vue': { resource: 'leads', permission: 'lead:export' },
  'Opportunities.vue': { resource: 'opportunities', permission: 'opportunity:export' },
  'PaymentPlans.vue': { resource: 'payment_plans', permission: 'payment:plan:export' },
  'PaymentRecords.vue': { resource: 'payment_records', permission: 'payment:record:export' },
} as const

function propertyName(property: ts.ObjectLiteralElementLike): string | undefined {
  if (!('name' in property) || property.name === undefined) return undefined
  if (ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)) return property.name.text
  return undefined
}

function propertyInitializer(
  object: ts.ObjectLiteralExpression,
  name: string,
): ts.Expression | undefined {
  const property = object.properties.find((candidate) => propertyName(candidate) === name)
  return property !== undefined && ts.isPropertyAssignment(property) ? property.initializer : undefined
}

function stringValue(expression: ts.Expression | undefined): string | undefined {
  return expression !== undefined && (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression))
    ? expression.text
    : undefined
}

function isEnabled(expression: ts.Expression | undefined): boolean {
  if (expression === undefined) return false
  if (expression.kind === ts.SyntaxKind.FalseKeyword) return false
  return expression.kind === ts.SyntaxKind.TrueKeyword || ts.isObjectLiteralExpression(expression)
}

function extractExportFields(viewName: string): StaticExportField[] {
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

  return fieldObjects.flatMap((object) => {
    const fieldKey = stringValue(propertyInitializer(object, 'key'))
    const fieldLabel = stringValue(propertyInitializer(object, 'label'))
    if (fieldKey === undefined || fieldLabel === undefined) return []
    const exportExpression = propertyInitializer(object, 'export')
    const columnExpression = propertyInitializer(object, 'column')
    const role = stringValue(propertyInitializer(object, 'role'))
    const businessColumn = isEnabled(columnExpression) && role === undefined
    const exportEnabled = exportExpression === undefined
      ? businessColumn && !isUnsafeExportKey(fieldKey)
      : isEnabled(exportExpression)
    if (!exportEnabled) return []

    let exportKey = fieldKey
    let exportLabel = fieldLabel
    if (exportExpression !== undefined && ts.isObjectLiteralExpression(exportExpression)) {
      exportKey = stringValue(propertyInitializer(exportExpression, 'key')) ?? fieldKey
      exportLabel = stringValue(propertyInitializer(exportExpression, 'label')) ?? fieldLabel
    }
    return [{ fieldKey, exportKey, label: exportLabel }]
  })
}

describe('DataTable frontend/backend list-export contract', () => {
  it('binds every covered DataTable through permission, title, and composable handler', () => {
    for (const [viewName, { permission }] of Object.entries(dataTableViews)) {
      const source = readFileSync(resolve(viewsDir, viewName), 'utf8')
      expect(source, `${viewName} export-enabled`).toMatch(/:export-enabled="canExport\w+"/)
      expect(source, `${viewName} export-title`).toMatch(/export-title="[^"]+"/)
      expect(source, `${viewName} export-handler`).toMatch(/:export-handler="export\w+Fields"/)
      expect(source, `${viewName} permission`).toContain(`permissionStore.hasPermission('${permission}')`)
      expect(source, `${viewName} current-query builder`).toMatch(/const current\w+ListContext/)
      expect(source, `${viewName} export uses current context`).toMatch(/const \{ tab, search, filters, sorts \} = current\w+ListContext\(\)/)
      expect(source, `${viewName} list query`).toContain('serializeListQuery')
    }
  })

  it('keeps every page export key/label in the generated manifest and never exports unsafe ids', () => {
    for (const [viewName, { resource }] of Object.entries(dataTableViews)) {
      const backendFields = manifest[resource]
      expect(backendFields, `${viewName} export catalog`).toBeDefined()
      if (backendFields === undefined) continue
      const exportFields = extractExportFields(viewName)
      expect(exportFields.length, `${viewName} export fields`).toBeGreaterThan(0)

      for (const field of exportFields) {
        expect(isUnsafeExportKey(field.exportKey), `${viewName} unsafe ${field.exportKey}`).toBe(false)
        const backendField = backendFields[field.exportKey]
        expect(backendField, `${viewName} export ${field.exportKey}`).toBeDefined()
        if (backendField === undefined) continue
        expect(backendField.label, `${viewName} export ${field.exportKey} label`).toBe(field.label)
      }
    }
  })
})
