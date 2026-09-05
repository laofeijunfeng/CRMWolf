import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const viewSources = {
  customers: readFileSync(resolve(process.cwd(), 'src/views/Customers.vue'), 'utf8'),
  leads: readFileSync(resolve(process.cwd(), 'src/views/Leads.vue'), 'utf8'),
  invoices: readFileSync(resolve(process.cwd(), 'src/views/Invoices.vue'), 'utf8'),
}

function declarationBody(source: string, declaration: string): string {
  const start = source.indexOf(declaration)
  expect(start, `missing declaration: ${declaration}`).toBeGreaterThanOrEqual(0)
  const nextDeclaration = source.indexOf('\nconst ', start + declaration.length)
  return source.slice(start, nextDeclaration === -1 ? source.length : nextDeclaration)
}

describe('critical list mutation refresh contract', () => {
  it('checks the final customer list refresh after every critical customer mutation', () => {
    const source = viewSources.customers

    expect(source).toContain('const refreshCustomerListAfterMutation = async')
    expect(declarationBody(source, 'const refreshCustomerListAfterMutation = async'))
      .toContain('const refreshed = await fetchCustomerList()')

    for (const declaration of [
      'const handleOpportunitySuccess = async',
      'const handleClaim = async',
      'const handleTransferSuccess = async',
      'const handleReturnModalOk = async',
      'const handleWin = async',
      'const handleLoseModalOk = async',
      'const handleInvalid = async',
      'const handleDelete = async',
    ]) {
      expect(declarationBody(source, declaration), declaration)
        .toContain('await refreshCustomerListAfterMutation(')
    }
  })

  it('checks the final lead list refresh after every critical lead mutation', () => {
    const source = viewSources.leads

    expect(source).toContain('const refreshLeadListAfterMutation = async')
    expect(declarationBody(source, 'const refreshLeadListAfterMutation = async'))
      .toContain('const refreshed = await fetchLeadList()')

    for (const declaration of [
      'const handleClaim = async',
      'const handleAssignModalOk = async',
      'const handleReturn = async',
      'const handleInvalidModalOk = async',
      'const handleDelete = async',
    ]) {
      expect(declarationBody(source, declaration), declaration)
        .toContain('await refreshLeadListAfterMutation(')
    }

    expect(source).toContain("@success=\"handleLeadMutationSuccess('线索创建')\"")
    expect(source).toContain("@success=\"handleLeadMutationSuccess('线索编辑')\"")
    expect(source).toContain("@success=\"handleLeadMutationSuccess('线索转化')\"")
  })

  it('checks the final invoice list refresh after every critical invoice mutation', () => {
    const source = viewSources.invoices

    expect(source).toContain('const refreshInvoiceListAfterMutation = async')
    expect(declarationBody(source, 'const refreshInvoiceListAfterMutation = async'))
      .toContain('const refreshed = await fetchInvoiceApplications()')

    for (const declaration of [
      'const handleInvoiceApplicationSuccess = async',
      'const handleSubmitApproval = async',
      'const handleWithdraw = async',
      'const handleDelete = async',
      'const handleInvoiceIssued = async',
    ]) {
      const body = declarationBody(source, declaration)
      expect(body, declaration).toContain('await ')
      expect(body, declaration).toMatch(/refreshInvoiceListAfterMutation|handleInvoiceMutationSuccess/)
    }
  })
})
