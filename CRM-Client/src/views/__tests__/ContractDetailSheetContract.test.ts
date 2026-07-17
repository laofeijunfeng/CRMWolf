import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const readSource = (relativePath: string): string => {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf-8')
}

describe('ContractDetailSheet Task 2 contract', () => {
  it('integrates payment plans and the contract edit dialog using shadcn sheet boundaries', () => {
    const source = readSource('src/views/ContractDetailSheet.vue')

    expect(source).toContain("@/components/ContractPaymentPlans.vue")
    expect(source).toContain("@/components/dialogs/ContractFormDialog.vue")
    expect(source).toContain('<ContractPaymentPlans')
    expect(source).toContain('<ContractFormDialog')

    const sheetEnd = source.indexOf('</Sheet>')
    const editDialog = source.indexOf('<ContractFormDialog')
    expect(sheetEnd).toBeGreaterThan(-1)
    expect(editDialog).toBeGreaterThan(sheetEnd)
  })

  it('uses the generic approval process component and keeps edit/close footer actions', () => {
    const source = readSource('src/views/ContractDetailSheet.vue')

    expect(source).toContain("@/components/ApprovalProcessGeneric.vue")
    expect(source).toContain('<ApprovalProcessGeneric')
    expect(source).toContain(':entity-type="contractEntityType"')
    expect(source).toContain('@submitted="handleApprovalActionDone"')
    expect(source).toContain('@withdrawn="handleApprovalActionDone"')
    expect(source).toContain('canEditContract')
    expect(source).toContain('编辑合同')
    expect(source).toContain('关闭')
    expect(source).not.toContain(`Approval${'ProgressCompact'}`)
    expect(source).not.toContain('submitContractApproval')
    expect(source).not.toContain('cancelContractApproval')
  })

  it('gates draft edit by all permission or own permission plus creator match', () => {
    const source = readSource('src/views/ContractDetailSheet.vue')

    expect(source).toContain("if (contract?.status !== 'DRAFT') return false")
    expect(source).toContain("if (permissionStore.canEditAll('contract')) return true")
    expect(source).toContain("return permissionStore.canEditOwn('contract') && contract.creator_id === currentUserId.value")
    expect(source).not.toContain("permissionStore.canEditOwn('contract') || permissionStore.canEditAll('contract')")
  })
})
