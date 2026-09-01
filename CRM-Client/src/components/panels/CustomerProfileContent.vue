<script setup lang="ts">
import { computed, type Component } from 'vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Check, CircleDot, GitBranch, MessageSquare, Pin, RefreshCw } from 'lucide-vue-next'
import HoverPreviewTooltip from '@/components/HoverPreviewTooltip.vue'
import {
  Stepper,
  StepperIndicator,
  StepperItem,
  StepperSeparator,
  StepperTitle
} from '@/components/ui/stepper'
import type { CustomerProfileEvidence, CustomerProfileResponse, CustomerProfileRecord } from '@/schemas/customerProfile'

interface Props {
  profile: CustomerProfileResponse | null
  evidence: CustomerProfileEvidence[]
  customerName: string
  customer?: CustomerProfileRecord | null
  refreshing: boolean
}

interface ProfileRow {
  label: string
  value: string
  wide?: boolean
}

interface ChangeTimelineRow {
  occurredAt: unknown
  title: string
  description: string
  journeyName: string
  stage: string
  icon: Component
  toneClass: string
  record: CustomerProfileRecord
}

interface JourneyTimelineRow {
  occurredAt: unknown
  journeyName: string
  stage: string
  fact: string
  impact: string
  record: CustomerProfileRecord
}

const props = defineProps<Props>()
const emit = defineEmits<{ refresh: [] }>()

const stringValue = (value: unknown, fallback = ''): string => {
  if (typeof value === 'string') return value.trim() || fallback
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return fallback
}

const objectValue = (value: unknown): CustomerProfileRecord => (
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as CustomerProfileRecord : {}
)

const arrayValue = (value: unknown): CustomerProfileRecord[] => (
  Array.isArray(value)
    ? value.filter((item): item is CustomerProfileRecord => item !== null && typeof item === 'object' && !Array.isArray(item))
    : []
)

const formatDate = (value: unknown): string => {
  const text = stringValue(value)
  if (!text) return ''
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return text
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
}

const profile = computed(() => props.profile)
const sections = computed(() => profile.value?.sections)
const currentSituation = computed(() => sections.value?.current_situation ?? {})
const longTermContext = computed(() => sections.value?.long_term_context ?? {})
const customer = computed(() => ({
  ...objectValue(longTermContext.value['customer']),
  ...objectValue(props.customer)
}))
const contacts = computed(() => arrayValue(longTermContext.value['contacts']).filter((item) => stringValue(item['name'])))
const journeys = computed(() => {
  const active = (sections.value?.current_journeys ?? []).filter((item) => stringValue(item['name']))
  const history = arrayValue(longTermContext.value['journey_history']).filter((item) => stringValue(item['name']))
  const seen = new Set<string>()
  return [...active, ...history].filter((item, index) => {
    const key = stringValue(item['id']) || `${stringValue(item['name'])}-${index}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})
const isActiveJourney = (item: CustomerProfileRecord): boolean => /^(ACTIVE|active|进行中|推进中)$/.test(stringValue(item['status']))
const activeJourneys = computed(() => journeys.value.filter(isActiveJourney))
const demandBackground = computed(() => objectValue(currentSituation.value['demand_background']))
const demandItems = computed(() => arrayValue(demandBackground.value['items']).filter((item) => stringValue(item['statement'])))
const changes = computed(() => (sections.value?.important_changes ?? []).filter((item) => stringValue(item['change']) || stringValue(item['title'])))
const process = computed(() => (sections.value?.follow_up_process ?? []).filter((item) => (
  stringValue(item['customer_expression']) || stringValue(item['sales_follow_up']) || stringValue(item['business_change'])
)))
const followUps = computed(() => (sections.value?.recorded_follow_ups ?? []).filter((item) => (
  stringValue(item['title']) || stringValue(item['content']) || stringValue(item['status'])
)))
const opportunities = computed(() => {
  const fromContext = arrayValue(longTermContext.value['opportunities'])
  const fromJourneys = journeys.value.flatMap((journey) => arrayValue(journey['opportunities']))
  const seen = new Set<string>()
  return [...fromContext, ...fromJourneys].filter((item, index) => {
    const key = stringValue(item['id']) || `${stringValue(item['name'])}-${index}`
    if (seen.has(key)) return false
    seen.add(key)
    return Boolean(stringValue(item['name']) || stringValue(item['stage']))
  })
})
const contracts = computed(() => {
  const fromContext = arrayValue(longTermContext.value['contracts'])
  const fromJourneys = journeys.value.flatMap((journey) => arrayValue(journey['contracts']))
  const seen = new Set<string>()
  return [...fromContext, ...fromJourneys].filter((item, index) => {
    const key = stringValue(item['id']) || stringValue(item['contract_number']) || `${index}`
    if (seen.has(key)) return false
    seen.add(key)
    return Boolean(stringValue(item['contract_number']) || stringValue(item['contract_name']) || stringValue(item['status']))
  })
})

const currentStage = computed(() => {
  const activeStage = activeJourneys.value[0]?.['current_stage']
  return stringValue(activeStage ?? journeys.value[0]?.['current_stage'])
})
const customerStatusLabel = (value: unknown): string => ({
  '0': '跟进中',
  '1': '已成交',
  '2': '已输单',
  '3': '已沉寂'
}[stringValue(value)] ?? stringValue(value))
const journeyStatusLabel = computed(() => {
  if (activeJourneys.value.length > 0) return '业务旅程进行中'
  if (journeys.value.length > 0) return '业务旅程已记录'
  return ''
})
const licenseLabel = computed(() => {
  const type = stringValue(customer.value['license_type']).toUpperCase()
  const expiry = formatDate(customer.value['license_expiry_date'])
  if (type === 'TRIAL') return `试用 License${expiry ? `，有效期至 ${expiry}` : ''}`
  if (type === 'OFFICIAL') return `正式 License${expiry ? `，有效期至 ${expiry}` : ''}`
  return stringValue(customer.value['product_status'])
})
const badgeTone = (value: string): string => {
  if (/已成交|已完成|已通过|正式|成功|已闭环/.test(value)) return 'profile-badge--success'
  if (/已输单|失败|未通过|风险|逾期/.test(value)) return 'profile-badge--danger'
  if (/跟进中|进行中|推进|试用|审批中|待/.test(value)) return 'profile-badge--warning'
  return 'profile-badge--neutral'
}
const headerStatusItems = computed(() => [
  customerStatusLabel(customer.value['status']),
  stringValue(customer.value['industry_name']) || stringValue(customer.value['industry']),
  licenseLabel.value,
  journeyStatusLabel.value
].filter(Boolean).map((label) => ({ label, className: badgeTone(label) })))
const isCompactStatus = (value: string): boolean => value.length <= 18 && !/[，。；：]/.test(value)
const isTagLabel = (label: string): boolean => ['客户状态', '当前产品状态', '商机阶段', '审批状态', '合同状态', '授权方式'].includes(label)
const ownerName = computed(() => {
  const ownerInfo = objectValue(customer.value['owner_info'])
  return stringValue(ownerInfo['name']) || stringValue(customer.value['owner_name'])
})
const managementSummary = computed(() => stringValue(currentSituation.value['summary']))

const overviewRows = computed<ProfileRow[]>(() => [
  { label: '所属行业', value: stringValue(customer.value['industry_name']) || stringValue(customer.value['industry']) },
  { label: '所在城市', value: stringValue(customer.value['city']) },
  { label: '公司规模', value: stringValue(customer.value['company_scale']) },
  { label: '客户来源', value: stringValue(customer.value['source']) },
  { label: '客户状态', value: customerStatusLabel(customer.value['status']) },
  { label: '当前产品状态', value: licenseLabel.value },
  { label: '研发侧规模', value: stringValue(customer.value['研发侧规模']) || stringValue(customer.value['team_size']) },
  { label: '当前业务旅程', value: activeJourneys.value.length > 1
    ? `${activeJourneys.value.length} 条并行旅程${currentStage.value ? `，当前阶段主要为${currentStage.value}` : ''}`
    : activeJourneys.value[0]
      ? `${stringValue(activeJourneys.value[0]['name'])}${currentStage.value ? `，${currentStage.value}` : ''}`
      : currentStage.value },
].filter((row) => row.value))
const companyInfoGroups = computed(() => [
  { label: '组织架构', value: stringValue(customer.value['organization_structure']) || stringValue(customer.value['team_composition']) || stringValue(customer.value['研发组织']) },
  { label: '技术与研发特征', value: stringValue(customer.value['technical_characteristics']) || stringValue(customer.value['研发协作方式']) }
].filter((item) => item.value))

const relationshipLabel = (contact: CustomerProfileRecord): string => {
  const labels: string[] = []
  if (contact['is_primary'] === true || contact['is_primary'] === 1) labels.push('当前主联系人')
  if (contact['is_decision_maker'] === true || contact['is_decision_maker'] === 1) labels.push('决策人')
  if (labels.length === 0 && stringValue(contact['position'])) labels.push(stringValue(contact['position']))
  return labels.join(' / ')
}
const relationshipRows = computed(() => contacts.value.map((contact) => ({
  role: stringValue(contact['name']),
  position: relationshipLabel(contact) || stringValue(contact['position']),
  status: stringValue(contact['relationship_status']) || stringValue(contact['remark'])
})))
const relationshipSummary = computed(() => stringValue(longTermContext.value['relationship_summary']) || stringValue(currentSituation.value['relationship_summary']))

const needNarrative = computed(() => stringValue(demandBackground.value['summary']))
const demandParagraphs = computed(() => {
  const paragraphs: string[] = []
  if (needNarrative.value) {
    if (!paragraphs.includes(needNarrative.value)) paragraphs.push(needNarrative.value)
  } else {
    paragraphs.push(...demandItems.value.map((item) => stringValue(item['statement'])).filter(Boolean))
  }
  return paragraphs
})

const journeyNarrative = computed(() => {
  const explicit = stringValue(longTermContext.value['journey_summary']) || stringValue(currentSituation.value['journey_summary'])
  if (explicit) return explicit
  if (activeJourneys.value.length === 0) return ''
  const stages = [...new Set(activeJourneys.value.map((item) => stringValue(item['current_stage'])).filter(Boolean))]
  const usage = demandItems.value.some((item) => stringValue(item['topic']) === 'usage_expansion')
  const procurement = demandItems.value.some((item) => stringValue(item['topic']) === 'procurement')
  const journeyPhrase = activeJourneys.value.length > 1
    ? `当前有 ${activeJourneys.value.length} 条并行业务旅程${stages.length ? `，均处于${stages.join('、')}阶段` : ''}`
    : `当前业务旅程${stages.length ? `处于${stages[0]}阶段` : '正在推进'}`
  const schemeNames = opportunities.value.map((item) => stringValue(item['name'])).filter(Boolean).slice(0, 3)
  const schemePhrase = schemeNames.length > 0 ? `，对应${schemeNames.join('、')}等方案` : ''
  const businessPhrase = usage && procurement ? '业务主线已从实际使用和授权范围评估延伸到采购预算与付款安排' : usage ? '业务主线已从产品试用延伸到实际使用和授权范围评估' : '业务主线仍围绕需求确认和方案评估展开'
  return `${businessPhrase}；${journeyPhrase}${schemePhrase}。`
})
const journeyHeading = computed(() => {
  const explicit = stringValue(longTermContext.value['journey_title']) || stringValue(currentSituation.value['journey_title'])
  if (explicit) return `业务旅程：${explicit}`
  const names = activeJourneys.value.map((item) => stringValue(item['name'])).filter(Boolean)
  return names.length > 0 ? `业务旅程：${names.join('、')}` : '业务旅程'
})
const journeyTimeline = computed<JourneyTimelineRow[]>(() => {
  const rows: JourneyTimelineRow[] = []
  for (const journey of journeys.value) {
    for (const event of arrayValue(journey['timeline'])) {
      const fact = stringValue(event['summary'])
      if (!fact) continue
      const type = stringValue(event['type'])
      const stage = stringValue(event['stage']) || stringValue(journey['current_stage']) || (fact.match(/(?:推进到|进入)：?([^，。]+)/)?.[1] ?? '')
      const impact = stringValue(event['impact']) || ({
        opportunity_created: '业务旅程开始进入商机推进',
        opportunity_stage_changed: '商业阶段发生变化',
        opportunity_approved: '交易进入审批通过状态',
        follow_up_task_status: '推进事项状态发生变化',
        customer_activity_recorded: '补充客户需求与使用事实'
      }[type] ?? '')
      rows.push({
        occurredAt: event['occurred_at'],
        journeyName: stringValue(journey['name']),
        stage,
        fact,
        impact,
        record: event
      })
    }
  }
  const seen = new Set<string>()
  return rows
    .sort((left, right) => String(left.occurredAt ?? '').localeCompare(String(right.occurredAt ?? '')))
    .filter((row) => {
      const key = `${String(row.occurredAt ?? '')}-${row.fact}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .slice(-20)
})

const currentAssessmentRows = computed(() => {
  const configured = arrayValue(currentSituation.value['business_status_rows'])
    .map((item) => ({
      dimension: stringValue(item['dimension']) || stringValue(item['label']),
      current: stringValue(item['current']) || stringValue(item['status']),
      judgement: stringValue(item['judgement']) || stringValue(item['assessment'])
    }))
    .filter((row) => row.dimension && (row.current || row.judgement))
  if (configured.length > 0) return configured

  const topicLabels: Record<string, string> = {
    usage_expansion: '技术采用',
    internal_validation: '决策关系',
    reporting: '需求匹配',
    procurement: '商业推进'
  }
  const rows = demandItems.value.map((item) => {
    const topic = stringValue(item['topic'])
    return {
      dimension: topicLabels[topic] ?? '需求匹配',
      current: stringValue(item['statement']),
      judgement: stringValue(item['status'])
    }
  })
  const dimensions = new Set(rows.map((row) => row.dimension))
  if (!dimensions.has('商业推进') && opportunities.value.length > 0) {
    rows.push({
      dimension: '商业推进',
      current: `${opportunities.value.length} 条商机记录${currentStage.value ? `，当前主要处于“${currentStage.value}”阶段` : ''}`,
      judgement: ''
    })
  }
  if (!dimensions.has('授权连续性') && licenseLabel.value) {
    rows.push({ dimension: '授权连续性', current: licenseLabel.value, judgement: '' })
  }
  return rows.filter((row) => row.current || row.judgement)
})

const dateSortValue = (value: unknown): number => {
  const timestamp = new Date(stringValue(value)).getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}

const dateKey = (value: unknown): string => {
  const text = stringValue(value)
  if (!text) return ''
  const timestamp = dateSortValue(text)
  return timestamp > 0 ? new Date(timestamp).toISOString().slice(0, 10) : text.slice(0, 10)
}

const journeyForChange = (record: CustomerProfileRecord): CustomerProfileRecord | undefined => {
  const journeyId = stringValue(record['journey_id'])
  if (!journeyId) return undefined
  return journeys.value.find((journey) => stringValue(journey['id']) === journeyId)
}

const changePresentation = (record: CustomerProfileRecord): Pick<ChangeTimelineRow, 'title' | 'icon' | 'toneClass'> => {
  const title = stringValue(record['title'])
  if (/待办/.test(title) || stringValue(record['task_id'])) {
    return { title: '跟进事项有更新', icon: Check, toneClass: 'profile-change-step__indicator--success' }
  }
  if (/旅程|阶段/.test(title) || stringValue(record['event_type']) === 'STAGE_CHANGED') {
    return { title: title || '业务旅程有变化', icon: GitBranch, toneClass: 'profile-change-step__indicator--primary' }
  }
  if (/状态/.test(title) || stringValue(record['event_type']) === 'STATUS_CHANGED') {
    return { title: title || '业务状态有变化', icon: CircleDot, toneClass: 'profile-change-step__indicator--warning' }
  }
  return { title: title || '客户进展有变化', icon: MessageSquare, toneClass: 'profile-change-step__indicator--neutral' }
}

const changeTimelineRows = computed((): ChangeTimelineRow[] => {
  const rows = changes.value
    .map((item) => {
      const presentation = changePresentation(item)
      const journey = journeyForChange(item)
      return {
        occurredAt: item['occurred_at'],
        title: presentation.title,
        description: stringValue(item['change']) || stringValue(item['summary']) || stringValue(item['description']),
        journeyName: stringValue(item['journey_name']) || stringValue(journey?.['name']),
        stage: stringValue(item['stage']) || stringValue(journey?.['current_stage']),
        icon: presentation.icon,
        toneClass: presentation.toneClass,
        record: item
      }
    })
    .filter((row) => row.description)
    .sort((left, right) => dateSortValue(right.occurredAt) - dateSortValue(left.occurredAt))

  const grouped: ChangeTimelineRow[] = []
  for (const row of rows) {
    const previous = grouped[grouped.length - 1]
    const shouldMerge = Boolean(
      previous
      && row.title === '跟进事项有更新'
      && previous.title === row.title
      && dateKey(previous.occurredAt) === dateKey(row.occurredAt)
    )

    if (!shouldMerge || !previous) {
      grouped.push(row)
      continue
    }

    previous.description = `${previous.description}；${row.description}`
    previous.record = {
      ...previous.record,
      evidence_refs: [...new Set([
        ...recordEvidenceRefs(previous.record),
        ...recordEvidenceRefs(row.record)
      ])]
    }
  }

  return grouped.slice(0, 20)
})
const riskItems = computed(() => [
  ...arrayValue(currentSituation.value['risks']),
  ...arrayValue(longTermContext.value['risks'])
].filter((item) => stringValue(item['statement']) || stringValue(item['content'])))
const closureRows = computed(() => [
  ...process.value.map((item) => ({
    item: stringValue(item['title']) || '业务跟进记录',
    status: stringValue(item['status']) || (stringValue(item['customer_expression']) ? '客户侧已有反馈' : '销售侧已记录'),
    impact: stringValue(item['business_change']) || stringValue(item['customer_expression']) || stringValue(item['sales_follow_up']),
    record: item
  })),
  ...followUps.value.map((item) => ({
    item: stringValue(item['title']) || stringValue(item['content']),
    status: stringValue(item['status']),
    impact: stringValue(item['content']),
    record: item
  }))
].filter((item) => item.item || item.status || item.impact).slice(-12))

const approvalLabel = (value: unknown): string => ({
  approved: '已通过',
  APPROVED: '已通过',
  pending: '审批中',
  PENDING: '审批中',
  rejected: '未通过',
  REJECTED: '未通过'
}[stringValue(value)] ?? stringValue(value))

const formatAmount = (value: unknown): string => {
  const text = stringValue(value)
  if (!text) return ''
  const amount = Number(text.replace(/,/g, ''))
  if (!Number.isFinite(amount)) return text
  return `${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(amount)} 元`
}

const formatPeopleCount = (value: unknown): string => {
  const text = stringValue(value)
  return text ? `${text} 人` : ''
}

const contractStatusForOpportunity = (item: CustomerProfileRecord): string => {
  const explicit = stringValue(item['contract_status'])
  if (explicit) return explicit
  const journeyId = stringValue(item['deal_journey_id'])
  const relatedContract = journeyId
    ? contracts.value.find((contract) => stringValue(contract['deal_journey_id']) === journeyId)
    : undefined
  return stringValue(relatedContract?.['status']) || '当前未记录合同'
}

const transactionRows = (item: CustomerProfileRecord): ProfileRow[] => [
  { label: '商机名称', value: stringValue(item['name']) },
  { label: '商机编号', value: stringValue(item['opportunity_number']) || stringValue(item['code']) },
  { label: '商机阶段', value: stringValue(item['stage']) },
  { label: '赢单概率', value: stringValue(item['win_probability']) ? `${stringValue(item['win_probability'])}%` : '' },
  { label: '商机金额', value: formatAmount(item['amount']) },
  { label: '用户数', value: formatPeopleCount(item['user_count']) },
  { label: '授权方式', value: stringValue(item['license_type']).toUpperCase() === 'SUBSCRIPTION' ? `订阅${stringValue(item['subscription_years']) ? ` ${stringValue(item['subscription_years'])} 年` : ''}` : stringValue(item['license_type']) },
  { label: '预计成交日期', value: formatDate(item['expected_closing_date']) },
  { label: '审批状态', value: approvalLabel(item['approval_phase']) },
  { label: '合同状态', value: contractStatusForOpportunity(item) }
].filter((row) => row.value)

const transactionDifference = (item: CustomerProfileRecord): string => (
  stringValue(item['current_difference']) || stringValue(item['difference']) || stringValue(item['change_summary'])
)

const recordEvidenceRefs = (record: CustomerProfileRecord): string[] => {
  const refs = record['evidence_refs']
  if (!Array.isArray(refs)) return []
  return refs.flatMap((value): string[] => {
    if (typeof value === 'string') return [value]
    return [stringValue(objectValue(value)['evidence_key'])].filter(Boolean)
  })
}

const evidenceMap = computed(() => new Map(props.evidence.map((item) => [item.evidence_key, item])))
const evidenceItems = computed(() => {
  const ordered: CustomerProfileEvidence[] = []
  const seen = new Set<string>()
  for (const ref of profile.value?.evidence_refs ?? []) {
    const key = stringValue(ref['evidence_key']) || stringValue(ref['evidence_id'])
    const item = key ? evidenceMap.value.get(key) : undefined
    if (item && !seen.has(item.evidence_key)) {
      ordered.push(item)
      seen.add(item.evidence_key)
    }
  }
  for (const item of props.evidence) if (!seen.has(item.evidence_key)) ordered.push(item)
  return ordered
})
const evidenceIndex = computed(() => new Map(evidenceItems.value.map((item, index) => [item.evidence_key, index + 1])))
const evidenceFor = (record: CustomerProfileRecord): CustomerProfileEvidence[] => (
  recordEvidenceRefs(record)
    .map((ref) => evidenceMap.value.get(ref))
    .filter((item): item is CustomerProfileEvidence => item !== undefined)
)
const evidenceNumber = (item: CustomerProfileEvidence): number => evidenceIndex.value.get(item.evidence_key) ?? 0
const sourceLabel = (sourceType: string): string => ({
  customer_activity: '跟进记录',
  deal_journey_event: '业务旅程',
  follow_up_task: '待办记录',
  sales_commitment: '销售承诺',
  customer_fact: '客户事实'
}[sourceType] ?? '业务记录')
const evidenceRows = (item: CustomerProfileEvidence): { label: string; value: string }[] => [
  { label: '来源', value: sourceLabel(item.source_type) },
  { label: '标题', value: stringValue(item.title) },
  { label: '时间', value: formatDate(item.occurred_at) },
  { label: '原文', value: stringValue(item.snippet) }
].filter((row) => row.value)

const hasContent = computed(() => Boolean(profile.value) && (
  managementSummary.value || overviewRows.value.length > 0 || companyInfoGroups.value.length > 0 || contacts.value.length > 0
  || demandParagraphs.value.length > 0 || journeys.value.length > 0 || currentAssessmentRows.value.length > 0
  || changeTimelineRows.value.length > 0 || riskItems.value.length > 0 || closureRows.value.length > 0 || opportunities.value.length > 0 || contracts.value.length > 0
))
</script>

<template>
  <div class="profile-document">
    <header class="profile-header">
      <div class="profile-header__heading">
        <h1>{{ customerName }}</h1>
        <div v-if="headerStatusItems.length > 0" class="profile-header__statuses" aria-label="客户状态">
          <Badge
            v-for="item in headerStatusItems"
            :key="item.label"
            variant="outline"
            :class="['profile-badge', item.className]"
          >
            {{ item.label }}
          </Badge>
        </div>
        <div v-if="ownerName || customer?.['created_time'] || profile?.freshness.profile_as_of" class="profile-header__meta">
          <span v-if="ownerName"><strong>负责人</strong>{{ ownerName }}</span>
          <span v-if="customer?.['created_time']"><strong>客户创建</strong>{{ formatDate(customer['created_time']) }}</span>
          <span v-if="profile?.freshness.profile_as_of"><strong>最近更新</strong>{{ formatDate(profile.freshness.profile_as_of) }}</span>
        </div>
      </div>
      <div class="profile-header__actions">
        <Button variant="ghost" size="icon" class="profile-refresh" :disabled="refreshing" aria-label="刷新客户档案" @click="emit('refresh')">
          <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': refreshing }" />
        </Button>
      </div>
    </header>

    <div v-if="profile?.profile_status === 'STALE'" class="profile-notice profile-notice--warning">已有新记录，当前档案等待更新。</div>
    <div v-else-if="profile?.profile_status === 'UPDATING'" class="profile-notice profile-notice--info">档案正在更新，当前展示上一版内容。</div>
    <div v-else-if="profile?.profile_status === 'FAILED'" class="profile-notice profile-notice--error">本次档案更新未完成，当前展示上一版内容。</div>

    <div v-if="profile === null || profile?.profile_status === 'NOT_READY' || !hasContent" class="profile-empty-state">
      <p>客户档案尚未形成</p>
      <Button variant="outline" size="sm" :disabled="refreshing" @click="emit('refresh')">
        <RefreshCw class="mr-2 h-4 w-4" :class="{ 'animate-spin': refreshing }" />
        重新整理
      </Button>
    </div>

    <div v-else class="profile-sections">
      <Card v-if="managementSummary" class="profile-card profile-card--summary">
        <CardHeader class="profile-card__header">
          <h2 class="profile-card__title"><Pin aria-hidden="true" class="profile-card__icon" />客户摘要</h2>
        </CardHeader>
        <CardContent class="profile-card__content">
          <p class="profile-prose profile-prose--summary">
            {{ managementSummary }}
            <template v-for="evidenceItem in evidenceFor(currentSituation)" :key="evidenceItem.evidence_key">
              <HoverPreviewTooltip :rows="evidenceRows(evidenceItem)" :min-width="280"><span class="evidence-index">[{{ evidenceNumber(evidenceItem) }}]</span></HoverPreviewTooltip>
            </template>
          </p>
        </CardContent>
      </Card>

      <Card v-if="overviewRows.length > 0" class="profile-card">
        <CardHeader class="profile-card__header"><h2 class="profile-card__title">客户概况</h2></CardHeader>
        <CardContent class="profile-card__content">
          <div class="attributes-grid">
            <div v-for="row in overviewRows" :key="row.label" class="attribute-item">
              <span class="attribute-label">{{ row.label }}</span>
              <Badge v-if="isTagLabel(row.label) && isCompactStatus(row.value)" variant="outline" :class="['profile-badge', badgeTone(row.value)]">{{ row.value }}</Badge>
              <span v-else class="attribute-value">{{ row.value }}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card v-if="companyInfoGroups.length > 0" class="profile-card">
        <CardHeader class="profile-card__header"><h2 class="profile-card__title">公司情况</h2></CardHeader>
        <CardContent class="profile-card__content">
          <div class="info-groups">
            <div v-for="group in companyInfoGroups" :key="group.label" class="info-group">
              <h3 class="info-group__label">{{ group.label }}</h3>
              <p class="profile-prose">{{ group.value }}<template v-for="evidenceItem in evidenceFor(customer)" :key="evidenceItem.evidence_key"><HoverPreviewTooltip :rows="evidenceRows(evidenceItem)" :min-width="280"><span class="evidence-index">[{{ evidenceNumber(evidenceItem) }}]</span></HoverPreviewTooltip></template></p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card v-if="relationshipRows.length > 0 || relationshipSummary" class="profile-card">
        <CardHeader class="profile-card__header"><h2 class="profile-card__title">客户关系</h2></CardHeader>
        <CardContent class="profile-card__content">
          <div v-if="relationshipRows.length > 0" class="contact-list" role="list">
            <div v-for="(row, index) in relationshipRows" :key="`${row.role}-${index}`" class="contact-item" role="listitem">
              <div class="contact-item__identity">
                <strong>{{ row.role }}</strong>
                <span v-if="row.position" class="contact-item__position">{{ row.position }}</span>
              </div>
              <Badge v-if="row.status && isCompactStatus(row.status)" variant="outline" :class="['profile-badge', badgeTone(row.status)]">{{ row.status }}</Badge>
              <span v-else-if="row.status" class="contact-item__status">{{ row.status }}</span>
            </div>
          </div>
          <p v-if="relationshipSummary" class="profile-prose profile-prose--secondary">{{ relationshipSummary }}</p>
        </CardContent>
      </Card>

      <Card v-if="demandParagraphs.length > 0" class="profile-card">
        <CardHeader class="profile-card__header"><h2 class="profile-card__title">项目需求背景</h2></CardHeader>
        <CardContent class="profile-card__content">
          <p v-for="(paragraph, index) in demandParagraphs" :key="index" class="profile-prose">
            {{ paragraph }}
            <template v-if="index === demandParagraphs.length - 1">
              <template v-for="item in demandItems" :key="stringValue(item['topic'])"><template v-for="evidenceItem in evidenceFor(item)" :key="evidenceItem.evidence_key"><HoverPreviewTooltip :rows="evidenceRows(evidenceItem)" :min-width="280"><span class="evidence-index">[{{ evidenceNumber(evidenceItem) }}]</span></HoverPreviewTooltip></template></template>
            </template>
          </p>
        </CardContent>
      </Card>

      <Card v-if="journeys.length > 0" class="profile-card">
        <CardHeader class="profile-card__header">
          <div class="profile-card__heading-row">
            <h2 class="profile-card__title">{{ journeyHeading }}</h2>
            <Badge v-if="journeyStatusLabel" variant="outline" :class="['profile-badge', badgeTone(journeyStatusLabel)]">{{ journeyStatusLabel }}</Badge>
          </div>
        </CardHeader>
        <CardContent class="profile-card__content">
          <p v-if="journeyNarrative" class="profile-prose">{{ journeyNarrative }}</p>
          <div v-if="journeyTimeline.length > 0" class="journey-timeline" role="list">
            <article v-for="(row, index) in journeyTimeline" :key="`${String(row.occurredAt)}-${index}`" class="journey-event" role="listitem">
              <div class="journey-event__rail" aria-hidden="true"><span class="journey-event__dot" /></div>
              <div class="journey-event__body">
                <div class="journey-event__meta">
                  <time>{{ formatDate(row.occurredAt) }}</time>
                  <span v-if="row.journeyName && journeys.length > 1" class="journey-event__journey">{{ row.journeyName }}</span>
                  <Badge v-if="row.stage" variant="outline" class="profile-badge profile-badge--neutral">{{ row.stage }}</Badge>
                </div>
                <p class="journey-event__fact">{{ row.fact }}<template v-for="evidenceItem in evidenceFor(row.record)" :key="evidenceItem.evidence_key"><HoverPreviewTooltip :rows="evidenceRows(evidenceItem)" :min-width="280"><span class="evidence-index">[{{ evidenceNumber(evidenceItem) }}]</span></HoverPreviewTooltip></template></p>
                <p v-if="row.impact" class="journey-event__impact">{{ row.impact }}</p>
              </div>
            </article>
          </div>
        </CardContent>
      </Card>

      <Card v-if="currentAssessmentRows.length > 0" class="profile-card">
        <CardHeader class="profile-card__header"><h2 class="profile-card__title">当前业务状态</h2></CardHeader>
        <CardContent class="profile-card__content">
          <div class="status-grid">
            <article v-for="row in currentAssessmentRows" :key="row.dimension" class="status-item">
              <span class="status-item__label">{{ row.dimension }}</span>
              <p class="status-item__current">{{ row.current }}</p>
              <Badge v-if="row.judgement && isCompactStatus(row.judgement)" variant="outline" :class="['profile-badge', badgeTone(row.judgement)]">{{ row.judgement }}</Badge>
              <p v-else-if="row.judgement" class="status-item__judgement">{{ row.judgement }}</p>
            </article>
          </div>
        </CardContent>
      </Card>

      <Card v-if="changeTimelineRows.length > 0" class="profile-card">
        <CardHeader class="profile-card__header"><h2 class="profile-card__title">重要变化</h2></CardHeader>
        <CardContent class="profile-card__content">
          <Stepper
            :model-value="changeTimelineRows.length"
            orientation="vertical"
            class="profile-change-stepper"
            aria-label="客户重要变化时间线"
          >
            <StepperItem
              v-for="(row, index) in changeTimelineRows"
              :key="`${String(row.occurredAt)}-${row.title}-${index}`"
              :step="index + 1"
              class="profile-change-step"
            >
              <div class="profile-change-step__marker" aria-hidden="true">
                <StepperIndicator :class="['profile-change-step__indicator', row.toneClass]">
                  <component :is="row.icon" class="profile-change-step__icon" />
                </StepperIndicator>
                <StepperSeparator v-if="index < changeTimelineRows.length - 1" class="profile-change-step__separator" />
              </div>
              <div class="profile-change-step__content">
                <div class="profile-change-step__heading">
                  <StepperTitle class="profile-change-step__title">{{ row.title }}</StepperTitle>
                  <time class="profile-change-step__date">{{ formatDate(row.occurredAt) }}</time>
                </div>
                <div v-if="row.journeyName || row.stage" class="profile-change-step__meta">
                  <span v-if="row.journeyName">{{ row.journeyName }}</span>
                  <Badge v-if="row.stage" variant="outline" class="profile-badge profile-badge--neutral">{{ row.stage }}</Badge>
                </div>
                <p class="profile-change-step__description">
                  {{ row.description }}<template v-for="evidenceItem in evidenceFor(row.record)" :key="evidenceItem.evidence_key"><HoverPreviewTooltip :rows="evidenceRows(evidenceItem)" :min-width="280"><span class="evidence-index">[{{ evidenceNumber(evidenceItem) }}]</span></HoverPreviewTooltip></template>
                </p>
              </div>
            </StepperItem>
          </Stepper>
        </CardContent>
      </Card>

      <Card v-if="riskItems.length > 0" class="profile-card profile-card--risk">
        <CardHeader class="profile-card__header"><h2 class="profile-card__title">风险与未决问题</h2></CardHeader>
        <CardContent class="profile-card__content">
          <ul class="profile-list"><li v-for="(item, index) in riskItems" :key="index">{{ stringValue(item['statement']) || stringValue(item['content']) }}<template v-for="evidenceItem in evidenceFor(item)" :key="evidenceItem.evidence_key"><HoverPreviewTooltip :rows="evidenceRows(evidenceItem)" :min-width="280"><span class="evidence-index">[{{ evidenceNumber(evidenceItem) }}]</span></HoverPreviewTooltip></template></li></ul>
        </CardContent>
      </Card>

      <Card v-if="closureRows.length > 0" class="profile-card">
        <CardHeader class="profile-card__header"><h2 class="profile-card__title">最近的业务闭环</h2></CardHeader>
        <CardContent class="profile-card__content">
          <div class="closure-list" role="list">
            <article v-for="(row, index) in closureRows" :key="index" class="closure-item" role="listitem">
              <div class="closure-item__heading"><strong>{{ row.item }}</strong><Badge v-if="row.status && isCompactStatus(row.status)" variant="outline" :class="['profile-badge', badgeTone(row.status)]">{{ row.status }}</Badge></div>
              <p v-if="row.impact" class="closure-item__impact">{{ row.impact }}<template v-for="evidenceItem in evidenceFor(row.record)" :key="evidenceItem.evidence_key"><HoverPreviewTooltip :rows="evidenceRows(evidenceItem)" :min-width="280"><span class="evidence-index">[{{ evidenceNumber(evidenceItem) }}]</span></HoverPreviewTooltip></template></p>
            </article>
          </div>
        </CardContent>
      </Card>

      <section v-if="opportunities.length > 0" class="profile-transaction-section" aria-labelledby="transaction-heading">
        <div class="profile-section-heading"><h2 id="transaction-heading" class="profile-card__title">商机交易信息</h2><span class="profile-section-heading__count">{{ opportunities.length }} 条商机</span></div>
        <div class="transaction-list">
          <Card v-for="(opportunity, opportunityIndex) in opportunities" :key="stringValue(opportunity['id'], String(opportunityIndex))" class="transaction-card">
            <CardHeader class="transaction-card__header">
              <div class="transaction-card__title"><strong>{{ stringValue(opportunity['name']) || `商机 ${opportunityIndex + 1}` }}</strong><Badge v-if="stringValue(opportunity['stage'])" variant="outline" :class="['profile-badge', badgeTone(stringValue(opportunity['stage']))]">{{ stringValue(opportunity['stage']) }}</Badge></div>
            </CardHeader>
            <CardContent class="transaction-card__content">
              <div class="attributes-grid attributes-grid--transaction">
                <div v-for="row in transactionRows(opportunity)" :key="row.label" class="attribute-item">
                  <span class="attribute-label">{{ row.label }}</span>
                  <Badge v-if="isTagLabel(row.label) && isCompactStatus(row.value)" variant="outline" :class="['profile-badge', badgeTone(row.value)]">{{ row.value }}</Badge>
                  <span v-else class="attribute-value">{{ row.value }}</span>
                </div>
              </div>
              <p v-if="transactionDifference(opportunity)" class="transaction-card__difference">{{ transactionDifference(opportunity) }}<template v-for="evidenceItem in evidenceFor(opportunity)" :key="evidenceItem.evidence_key"><HoverPreviewTooltip :rows="evidenceRows(evidenceItem)" :min-width="280"><span class="evidence-index">[{{ evidenceNumber(evidenceItem) }}]</span></HoverPreviewTooltip></template></p>
            </CardContent>
          </Card>
        </div>
      </section>

      <section v-if="contracts.length > 0" class="profile-transaction-section" aria-labelledby="contracts-heading">
        <div class="profile-section-heading"><h2 id="contracts-heading" class="profile-card__title">合同信息</h2><span class="profile-section-heading__count">{{ contracts.length }} 份合同</span></div>
        <div class="contract-list">
          <Card v-for="(item, index) in contracts" :key="stringValue(item['id'], String(index))" class="contract-card">
            <CardContent class="contract-card__content">
              <div class="contract-card__heading"><strong>{{ stringValue(item['contract_name']) || stringValue(item['contract_number']) }}</strong><Badge v-if="stringValue(item['status'])" variant="outline" :class="['profile-badge', badgeTone(stringValue(item['status']))]">{{ stringValue(item['status']) }}</Badge></div>
              <div class="attributes-grid attributes-grid--contract">
                <div v-if="stringValue(item['contract_number'])" class="attribute-item"><span class="attribute-label">合同编号</span><span class="attribute-value">{{ stringValue(item['contract_number']) }}</span></div>
                <div v-if="stringValue(item['amount'])" class="attribute-item"><span class="attribute-label">合同金额</span><span class="attribute-value">{{ formatAmount(item['amount']) }}</span></div>
                <div v-if="stringValue(item['payment_status'])" class="attribute-item"><span class="attribute-label">回款状态</span><Badge variant="outline" :class="['profile-badge', badgeTone(stringValue(item['payment_status']))]">{{ stringValue(item['payment_status']) }}</Badge></div>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.profile-document {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  line-height: 1.6;
}

.profile-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  margin-bottom: $wolf-section-gap-v2;
  padding-bottom: $wolf-space-md-v2;
  border-bottom: 1px solid $wolf-border-default-v2;
}
.profile-header__heading { min-width: 0; }
.profile-header__heading h1 { margin: 0; color: $wolf-text-primary-v2; font-size: $wolf-font-size-title-v2; font-weight: $wolf-font-weight-semibold-v2; line-height: 1.4; }
.profile-header__statuses { display: flex; flex-wrap: wrap; gap: $wolf-space-xs-v2 $wolf-space-sm-v2; margin-top: $wolf-space-sm-v2; }
.profile-header__meta { display: flex; flex-wrap: wrap; gap: $wolf-space-xs-v2 $wolf-space-lg-v2; margin-top: $wolf-space-sm-v2; color: $wolf-text-tertiary-v2; font-size: $wolf-font-size-caption-v2; }
.profile-header__meta strong { margin-right: $wolf-space-xs-v2; color: $wolf-text-secondary-v2; font-weight: $wolf-font-weight-medium-v2; }
.profile-header__actions { display: flex; flex: 0 0 auto; align-items: center; }
.profile-refresh { color: $wolf-text-tertiary-v2; }

.profile-badge { display: inline-flex; width: fit-content; max-width: 100%; padding: 2px $wolf-space-sm-v2; border-radius: $wolf-radius-full-v2; font-size: $wolf-font-size-caption-v2; font-weight: $wolf-font-weight-medium-v2; line-height: 1.35; white-space: nowrap; }
.profile-badge--neutral { border-color: $wolf-border-default-v2; background: $wolf-bg-muted-v2; color: $wolf-text-secondary-v2; }
.profile-badge--success { border-color: $wolf-success-bg-v2; background: $wolf-success-bg-v2; color: $wolf-success-text-v2; }
.profile-badge--warning { border-color: $wolf-warning-bg-v2; background: $wolf-warning-bg-v2; color: $wolf-warning-text-v2; }
.profile-badge--danger { border-color: $wolf-danger-bg-v2; background: $wolf-danger-bg-v2; color: $wolf-danger-text-v2; }

.profile-notice { margin-bottom: $wolf-space-md-v2; padding: $wolf-space-sm-v2 $wolf-space-md-v2; border: 1px solid; border-radius: $wolf-radius-v2; font-size: $wolf-font-size-auxiliary-v2; }
.profile-notice--warning { border-color: $wolf-warning-bg-v2; background: $wolf-warning-bg-v2; color: $wolf-warning-text-v2; }
.profile-notice--info { border-color: $wolf-primary-light-v2; background: $wolf-primary-light-v2; color: $wolf-primary-v2; }
.profile-notice--error { border-color: $wolf-danger-bg-v2; background: $wolf-danger-bg-v2; color: $wolf-danger-text-v2; }
.profile-empty-state { display: flex; align-items: center; justify-content: space-between; gap: $wolf-space-md-v2; padding: $wolf-space-lg-v2; border: 1px solid $wolf-border-default-v2; border-radius: $wolf-radius-xl-v2; background: $wolf-bg-card-v2; color: $wolf-text-tertiary-v2; }
.profile-empty-state p { margin: 0; }
.profile-sections { display: flex; flex-direction: column; gap: $wolf-card-gap-v2; }
.profile-card { min-width: 0; overflow: hidden; }
.profile-card--summary { border-left: 3px solid $wolf-primary-v2; }
.profile-card--risk { border-left: 3px solid $wolf-warning-v2; }
.profile-card__header { padding: $wolf-space-md-v2 $wolf-card-padding-v2 $wolf-space-sm-v2; }
.profile-card__content { padding: 0 $wolf-card-padding-v2 $wolf-card-padding-v2; }
.profile-card__heading-row { display: flex; align-items: center; justify-content: space-between; gap: $wolf-space-md-v2; }
.profile-card__title { display: flex; min-width: 0; align-items: center; gap: $wolf-space-sm-v2; margin: 0; color: $wolf-text-primary-v2; font-size: $wolf-font-size-title-v2; font-weight: $wolf-font-weight-semibold-v2; line-height: 1.4; }
.profile-card__icon { width: 16px; height: 16px; flex: 0 0 auto; color: $wolf-primary-v2; }
.profile-prose { margin: 0; color: $wolf-text-secondary-v2; line-height: 1.8; }
.profile-prose + .profile-prose { margin-top: $wolf-space-sm-v2; }
.profile-prose--summary { color: $wolf-text-primary-v2; font-weight: $wolf-font-weight-medium-v2; }
.profile-prose--secondary { margin-top: $wolf-space-md-v2; padding-top: $wolf-space-md-v2; border-top: 1px solid $wolf-border-light-v2; }

.attributes-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: $wolf-space-md-v2 $wolf-space-lg-v2; }
.attribute-item { display: flex; min-width: 0; flex-direction: column; gap: $wolf-space-xs-v2; }
.attribute-label, .info-group__label, .status-item__label { color: $wolf-text-tertiary-v2; font-size: $wolf-font-size-caption-v2; line-height: 1.4; }
.attribute-value { color: $wolf-text-secondary-v2; font-size: $wolf-font-size-body-v2; font-weight: $wolf-font-weight-medium-v2; line-height: 1.6; overflow-wrap: anywhere; }
.attributes-grid--transaction { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.attributes-grid--contract { grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: $wolf-space-md-v2; }

.info-groups { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: $wolf-space-lg-v2; }
.info-group { min-width: 0; }
.info-group__label { display: block; margin: 0 0 $wolf-space-xs-v2; font-weight: $wolf-font-weight-medium-v2; }
.info-group .profile-prose { overflow-wrap: anywhere; }
.contact-list, .closure-list { display: flex; flex-direction: column; }
.contact-item, .closure-item { display: flex; align-items: center; justify-content: space-between; gap: $wolf-space-md-v2; min-width: 0; padding: $wolf-space-md-v2 0; border-bottom: 1px solid $wolf-border-light-v2; }
.contact-item:first-child, .closure-item:first-child { padding-top: 0; }
.contact-item:last-child, .closure-item:last-child { padding-bottom: 0; border-bottom: 0; }
.contact-item__identity { display: flex; min-width: 0; flex-direction: column; gap: $wolf-space-xs-v2; }
.contact-item__identity strong, .closure-item__heading strong { color: $wolf-text-primary-v2; font-weight: $wolf-font-weight-medium-v2; }
.contact-item__position, .contact-item__status { color: $wolf-text-tertiary-v2; font-size: $wolf-font-size-caption-v2; }

.journey-timeline { margin-top: $wolf-space-lg-v2; }
.journey-event { display: grid; grid-template-columns: 18px minmax(0, 1fr); column-gap: $wolf-space-md-v2; min-width: 0; }
.journey-event + .journey-event { margin-top: $wolf-space-md-v2; }
.journey-event__rail { position: relative; display: flex; justify-content: center; }
.journey-event__rail::after { position: absolute; top: 15px; bottom: -$wolf-space-md-v2; width: 1px; background: $wolf-border-default-v2; content: ''; }
.journey-event:last-child .journey-event__rail::after { display: none; }
.journey-event__dot { z-index: 1; width: 9px; height: 9px; margin-top: 4px; border: 2px solid $wolf-primary-v2; border-radius: 50%; background: $wolf-bg-card-v2; }
.journey-event__meta { display: flex; flex-wrap: wrap; align-items: center; gap: $wolf-space-xs-v2 $wolf-space-sm-v2; color: $wolf-text-tertiary-v2; font-size: $wolf-font-size-caption-v2; }
.journey-event__journey { color: $wolf-text-secondary-v2; }
.journey-event__fact { margin: $wolf-space-xs-v2 0 0; color: $wolf-text-primary-v2; line-height: 1.7; }
.journey-event__impact { margin: $wolf-space-xs-v2 0 0; color: $wolf-text-tertiary-v2; font-size: $wolf-font-size-auxiliary-v2; line-height: 1.6; }

.status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr)); gap: $wolf-space-md-v2; }
.status-item { min-width: 0; padding: $wolf-space-md-v2; border: 1px solid $wolf-border-light-v2; border-radius: $wolf-radius-v2; background: $wolf-bg-muted-v2; }
.status-item__current { margin: $wolf-space-xs-v2 0 $wolf-space-sm-v2; color: $wolf-text-primary-v2; line-height: 1.7; overflow-wrap: anywhere; }
.status-item__judgement { margin: 0; color: $wolf-text-tertiary-v2; font-size: $wolf-font-size-auxiliary-v2; line-height: 1.6; }

.profile-change-stepper { display: grid; width: 100%; gap: $wolf-space-md-v2; }
.profile-change-step { display: grid; grid-template-columns: 20px minmax(0, 1fr); align-items: stretch; gap: $wolf-space-md-v2; }
.profile-change-step__marker { display: flex; min-height: 0; flex-direction: column; align-items: center; }
.profile-change-step__indicator { display: flex; width: 20px; height: 20px; flex: 0 0 auto; align-items: center; justify-content: center; margin-top: 1px; border: 0; border-radius: $wolf-radius-full-v2; color: $wolf-text-inverse-v2; font-size: 0; line-height: 0; }
.profile-change-step__indicator--success { background: $wolf-success-v2; box-shadow: 0 0 0 4px $wolf-success-bg-v2; }
.profile-change-step__indicator--primary { background: $wolf-primary-v2; box-shadow: 0 0 0 4px $wolf-primary-light-v2; }
.profile-change-step__indicator--warning { background: $wolf-warning-v2; box-shadow: 0 0 0 4px $wolf-warning-bg-v2; color: $wolf-warning-text-v2; }
.profile-change-step__indicator--neutral { background: $wolf-text-tertiary-v2; box-shadow: 0 0 0 4px $wolf-bg-muted-v2; }
.profile-change-step__icon { width: 12px; height: 12px; }
.profile-change-step__separator { width: 1px; min-height: $wolf-space-md-v2; flex: 1; margin-top: 8px; background: $wolf-border-light-v2; }
.profile-change-step__content { min-width: 0; padding-bottom: $wolf-space-xs-v2; }
.profile-change-step__heading { display: flex; align-items: baseline; justify-content: space-between; gap: $wolf-space-md-v2; }
.profile-change-step__title { min-width: 0; color: $wolf-text-primary-v2; font-size: $wolf-font-size-caption-v2; font-weight: $wolf-font-weight-semibold-v2; line-height: $wolf-line-height-body-v2; text-align: left; }
.profile-change-step__date { flex: 0 0 auto; color: $wolf-text-tertiary-v2; font-size: $wolf-font-size-auxiliary-v2; white-space: nowrap; }
.profile-change-step__meta { display: flex; flex-wrap: wrap; align-items: center; gap: $wolf-space-xs-v2 $wolf-space-sm-v2; margin-top: 2px; color: $wolf-text-secondary-v2; font-size: $wolf-font-size-auxiliary-v2; }
.profile-change-step__description { margin: $wolf-space-xs-v2 0 0; color: $wolf-text-secondary-v2; line-height: 1.7; overflow-wrap: anywhere; }

.profile-list { margin: 0; padding-left: 20px; color: $wolf-text-secondary-v2; }
.profile-list li { padding-left: $wolf-space-xs-v2; line-height: 1.8; }
.profile-list li + li { margin-top: $wolf-space-sm-v2; }
.closure-item { align-items: flex-start; flex-direction: column; gap: $wolf-space-xs-v2; }
.closure-item__heading { display: flex; align-items: center; justify-content: space-between; gap: $wolf-space-md-v2; width: 100%; }
.closure-item__impact { margin: 0; color: $wolf-text-secondary-v2; line-height: 1.7; }

.profile-transaction-section { display: flex; flex-direction: column; gap: $wolf-space-md-v2; }
.profile-section-heading { display: flex; align-items: center; justify-content: space-between; gap: $wolf-space-md-v2; }
.profile-section-heading__count { color: $wolf-text-tertiary-v2; font-size: $wolf-font-size-caption-v2; }
.transaction-list, .contract-list { display: flex; flex-direction: column; gap: $wolf-space-md-v2; }
.transaction-card, .contract-card { min-width: 0; overflow: hidden; }
.transaction-card__header { padding: $wolf-space-md-v2 $wolf-card-padding-v2 $wolf-space-sm-v2; }
.transaction-card__content, .contract-card__content { padding: 0 $wolf-card-padding-v2 $wolf-card-padding-v2; }
.transaction-card__title, .contract-card__heading { display: flex; align-items: center; justify-content: space-between; gap: $wolf-space-md-v2; min-width: 0; }
.transaction-card__title strong, .contract-card__heading strong { min-width: 0; color: $wolf-text-primary-v2; font-weight: $wolf-font-weight-semibold-v2; overflow-wrap: anywhere; }
.transaction-card__difference { margin: $wolf-space-lg-v2 0 0; padding-top: $wolf-space-md-v2; border-top: 1px solid $wolf-border-light-v2; color: $wolf-text-secondary-v2; line-height: 1.7; }
.contract-card__content { padding-top: $wolf-space-md-v2; }

.evidence-index { display: inline-block; margin-left: 3px; color: $wolf-primary-v2; font-size: $wolf-font-size-caption-v2; line-height: 1; cursor: help; }

@media (max-width: 900px) {
  .attributes-grid, .attributes-grid--transaction { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .profile-header { align-items: flex-start; }
  .profile-header__meta { gap: $wolf-space-xs-v2 $wolf-space-md-v2; }
  .profile-card__heading-row, .profile-section-heading { align-items: flex-start; flex-direction: column; }
  .info-groups, .status-grid, .attributes-grid, .attributes-grid--transaction, .attributes-grid--contract { grid-template-columns: 1fr; }
  .profile-change-step__heading { align-items: flex-start; flex-direction: column; gap: 2px; }
  .profile-change-step__date { white-space: normal; }
}
</style>
