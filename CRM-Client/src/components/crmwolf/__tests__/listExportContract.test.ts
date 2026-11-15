import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'
import { isUnsafeExportKey } from '../listFieldCatalog'

type ExportManifest = Record<string, Record<string, { label: string; type: string }>>

interface StaticExportField {
  exportKey: string
}

const srcDir = resolve(process.cwd(), 'src')
const viewsDir = resolve(srcDir, 'views')
const manifest = JSON.parse(
  readFileSync(resolve(srcDir, 'components/crmwolf/listExportCatalogManifest.json'), 'utf8'),
) as ExportManifest

const dataTableViews = {
  'ApprovalCenter.vue': { resource: 'approvals' },
  'Contracts.vue': { resource: 'contracts' },
  'CustomerTracking.vue': { resource: 'follow_up_tasks' },
  'Customers.vue': { resource: 'customers' },
  'Invoices.vue': { resource: 'invoices' },
  'Leads.vue': { resource: 'leads' },
  'Opportunities.vue': { resource: 'opportunities' },
  'PaymentPlans.vue': { resource: 'payment_plans' },
  'PaymentRecords.vue': { resource: 'payment_records' },
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
    if (exportExpression !== undefined && ts.isObjectLiteralExpression(exportExpression)) {
      exportKey = stringValue(propertyInitializer(exportExpression, 'key')) ?? fieldKey
    }
    return [{ exportKey }]
  })
}

describe('DataTable frontend/backend list-export contract', () => {

  it('keeps every page export key in the generated manifest and never exports unsafe ids', () => {
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
      }
    }
  })

})
