import type { SubmitAssistantInput } from '@/api/assistant'
import type { AgentUIBlock } from '@/schemas/agent-contracts/ui-blocks'
import type { AssistantRejectReason, AssistantTaskView, TaskWaiting } from '@/schemas/assistant-contracts'

export type InteractionBlock = Extract<AgentUIBlock, { type: 'interaction' }>

export interface ReplyLabelContext {
  block?: Pick<InteractionBlock, 'options'> | undefined
  profileProposals?: AssistantTaskView['profile_proposals']
}

export const ACTIVITY_KIND_LABELS: Record<string, string> = {
  FOLLOW_UP: '普通跟进',
  PHONE_FOLLOW_UP: '电话跟进',
  WECHAT_FOLLOW_UP: '微信跟进',
  EMAIL_FOLLOW_UP: '邮件跟进',
  VISIT_FOLLOW_UP: '拜访跟进',
  OTHER_FOLLOW_UP: '其他跟进',
  ONLINE_MEETING: '线上会议',
  OFFLINE_MEETING: '线下会议'
}

export const REJECT_REASON_LABELS: Record<AssistantRejectReason, string> = {
  wrong_customer: '客户不对',
  wrong_content: '内容不对',
  should_not_record: '不该记录',
  other: '其他'
}

function candidateLabel(waiting: TaskWaiting | null, choice?: string): string | null {
  if (waiting === null || choice === undefined || choice === '') return null
  const candidate = waiting.candidates?.find((item) => item.id === choice)
  if (candidate === undefined) return null
  if ('label' in candidate) {
    const label = candidate.label.trim()
    if (label !== '') return label
  }
  if ('account_name' in candidate) {
    const accountName = candidate.account_name.trim()
    if (accountName !== '') return accountName
  }
  return null
}

function stripKindPrefix(summary: string, label: string, kind?: string): string {
  let result = summary.trim()
  const prefixes = [`${label}：`, `${label}:`]
  const moduleLabels: Record<string, string> = {
    contact_create: '联系人',
    contact_supplement: '联系人',
    invoice_title_create: '开票抬头',
    deployment_create: '部署信息'
  }
  const moduleLabel = kind !== undefined ? moduleLabels[kind] : undefined
  if (moduleLabel !== undefined && moduleLabel !== label) {
    prefixes.push(`${moduleLabel}：`, `${moduleLabel}:`)
  }
  if (kind === 'contact_supplement') {
    prefixes.push('补充已有联系人：', '补充已有联系人:', '补充 ', '更新 ')
  }
  for (const prefix of prefixes) {
    if (result.startsWith(prefix)) result = result.slice(prefix.length).trim()
  }
  return result
}

function profileProposalLabel(
  choice: string | undefined,
  waiting: TaskWaiting,
  context?: ReplyLabelContext
): string {
  if (choice === 'none') {
    return candidateLabel(waiting, choice) ?? '全部不保存'
  }
  if (choice !== undefined && choice.includes(':')) {
    const sepIndex = choice.indexOf(':')
    const action = choice.slice(0, sepIndex)
    const rawIndex = choice.slice(sepIndex + 1)
    if ((action === 'go' || action === 'skip') && /^\d+$/.test(rawIndex)) {
      const option = context?.block?.options.find((item) => item.value === choice)
      const optionLabel = option?.label.trim() ?? ''
      const actionLabel = optionLabel !== ''
        ? optionLabel
        : (candidateLabel(waiting, choice) ?? (action === 'go' ? '打开建档表单' : '不保存'))
      const optionGroup = option?.group?.trim() ?? ''
      if (optionGroup !== '') {
        return `${actionLabel}：${optionGroup}`
      }
      const idx = Number(rawIndex)
      const row = context?.profileProposals?.find((item) => item.index === idx) ?? context?.profileProposals?.[idx]
      if (row !== undefined) {
        const stripped = stripKindPrefix(row.summary, row.label, row.kind)
        const rawGroup = `${row.label}：${stripped || row.summary}`
        const chars = Array.from(rawGroup)
        const group = chars.length <= 40 ? rawGroup : chars.slice(0, 40).join('')
        return `${actionLabel}：${group}`
      }
      return actionLabel
    }
  }
  return candidateLabel(waiting, choice) ?? '选择'
}

function dispositionLabel(input: SubmitAssistantInput, waiting: TaskWaiting | null): string {
  const choices = input.choices ?? []
  const suppressWeek = input.suppress_week === true
  if (choices.length === 0) {
    return suppressWeek ? '本周不再提示' : '暂不标记完成'
  }
  const titles = choices
    .map((itemId) => candidateLabel(waiting, itemId))
    .filter((label): label is string => label !== null)
  let base: string
  if (choices.length === 1 && titles.length === 1) {
    base = `标记完成：${titles[0]}`
  } else if (titles.length > 0) {
    base = `标记完成 ${choices.length} 项：${titles[0]} 等`
  } else {
    base = `标记完成 ${choices.length} 项`
  }
  return suppressWeek ? `${base} · 本周不再提示` : base
}

/** Mirror CRM-Server history.command_label so optimistic user bubbles match server persistence verbatim. */
export function assistantCommandReplyLabel(
  input: SubmitAssistantInput,
  waiting: TaskWaiting | null,
  context?: ReplyLabelContext
): string {
  if (input.kind === 'cancel') return '算了，不记了'
  if (input.kind === 'revise_activity_kind') {
    const label = input.choice !== undefined ? ACTIVITY_KIND_LABELS[input.choice] : undefined
    return label !== undefined ? `改为${label}` : '修改活动类型'
  }
  if (input.kind === 'confirm') {
    if (input.choice === 'confirm') {
      return waiting?.confirmation_payload?.kind === 'activity_write' ? '确认写入' : '确认'
    }
    const reason = input.reason !== undefined ? REJECT_REASON_LABELS[input.reason] : undefined
    return reason !== undefined ? `取消（${reason}）` : '取消'
  }
  if (input.kind === 'request_edit') return '修改内容'
  if (input.kind === 'submit_form') {
    if (input.choice === 'cancel') {
      return waiting?.type === 'CONFIRMATION_EDIT' ? '取消修改' : '取消'
    }
    if (input.choice === 'defer') return '稍后补充'
    return '提交'
  }
  if (waiting?.type === 'FOLLOW_UP_DISPOSITION' || input.choices !== undefined) {
    return dispositionLabel(input, waiting)
  }
  if (waiting?.type === 'PROFILE_PROPOSALS') {
    return profileProposalLabel(input.choice, waiting, context)
  }
  if (waiting?.type === 'ENTITY_DEFERRED') {
    const matched = candidateLabel(waiting, input.choice)
    if (matched !== null) return matched
    if (input.choice === 'resume') return '继续填写'
    if (input.choice === 'cancel') return '不要了'
    return '选择'
  }
  if (waiting?.type === 'OBJECT_SELECTION') {
    const matched = candidateLabel(waiting, input.choice)
    if (matched !== null) return matched
    const typed = input.text?.trim() ?? ''
    if (typed !== '') return typed
    if (waiting.field === 'opportunity') return '选择商机'
    if (waiting.field === 'intent') return '选择意图'
    return '选择客户'
  }
  if (waiting?.type === 'ACTIVITY_KIND') {
    const mapped = input.choice !== undefined ? ACTIVITY_KIND_LABELS[input.choice] : undefined
    return mapped ?? candidateLabel(waiting, input.choice) ?? '选择活动类型'
  }
  if (waiting?.field === 'temporal_choice') {
    const matched = candidateLabel(waiting, input.choice)
    if (matched !== null) return matched
    const typed = input.text?.trim() ?? ''
    if (typed !== '') return typed
    return '选择时间'
  }
  if (input.choice === 'EXPLICITLY_NONE') {
    const typed = input.text?.trim() ?? ''
    return typed !== '' ? typed : '暂无下一步行动'
  }
  const typed = input.text?.trim() ?? ''
  if (typed !== '') return typed
  const matched = candidateLabel(waiting, input.choice)
  if (matched !== null) return matched
  return '选择'
}
