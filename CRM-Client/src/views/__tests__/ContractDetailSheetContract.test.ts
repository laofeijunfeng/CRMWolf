import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const readSource = (relativePath: string): string => {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf-8')
}

describe('ContractDetailSheet Task 2 contract', () => {
  it('integrates payment plans and the contract edit dialog using shadcn sheet boundaries', () => {
    const source = readSource('src/views/ContractDetailSheet.vue')

    expect(source).toContain("@/components/PaymentPlans.vue")
    expect(source).toContain("@/components/dialogs/ContractFormDialog.vue")
    expect(source).toContain('<PaymentPlans')
    expect(source).toContain('<ContractFormDialog')

    const sheetEnd = source.indexOf('</Sheet>')
    const editDialog = source.indexOf('<ContractFormDialog')
    expect(sheetEnd).toBeGreaterThan(-1)
    expect(editDialog).toBeGreaterThan(sheetEnd)
  })

  it('provides draft submit, draft edit, pending-review withdraw, and close footer actions', () => {
    const source = readSource('src/views/ContractDetailSheet.vue')

    expect(source).toContain('submitContractApproval')
    expect(source).toContain('cancelContractApproval')
    expect(source).toContain('canSubmitApproval')
    expect(source).toContain('canWithdrawApproval')
    expect(source).toContain('canEditContract')
    expect(source).toContain('提交审批')
    expect(source).toContain('撤回审批')
    expect(source).toContain('编辑合同')
    expect(source).toContain('关闭')
  })

  it('gates draft edit by all permission or own permission plus creator match', () => {
    const source = readSource('src/views/ContractDetailSheet.vue')

    expect(source).toContain("if (contract?.status !== 'DRAFT') return false")
    expect(source).toContain("if (permissionStore.canEditAll('contract')) return true")
    expect(source).toContain("return permissionStore.canEditOwn('contract') && contract.creator_id === currentUserId.value")
    expect(source).not.toContain("permissionStore.canEditOwn('contract') || permissionStore.canEditAll('contract')")
  })
})
