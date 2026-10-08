/**
 * AI 解析线索/客户创建信息 API（SSE 流式）
 *
 * 解析结果仅用于回填表单，不创建业务数据。
 */
import { useUserStore } from '@/stores/user'

export interface LeadParsedInfo {
  lead_name: string | null
  source: string | null
  source_public_id: string | null
  city: string | null
  company_scale: string | null
  product: string | null
  product_public_id: string | null
  contact_name: string | null
  contact_phone: string | null
  missing_fields: string[]
}

export interface CustomerParsedInfo {
  account_name: string | null
  city: string | null
  company_scale: string | null
  source: string | null
  source_public_id: string | null
  product: string | null
  product_public_id: string | null
  industry_hint: string | null
  missing_fields: string[]
}

export interface CustomerParsedContact {
  contact_name: string | null
  contact_phone: string | null
  contact_position: string | null
  contact_gender: string | null
  contact_email: string | null
}

export interface EntityParseSSEEvent<TInfo, TContact = null> {
  event: 'status' | 'content' | 'parsed' | 'error'
  message?: string
  content?: string
  lead_info?: TInfo
  customer_info?: TInfo
  contact_info?: TContact
  thinking_process?: string
}

const streamParse = async <TInfo, TContact = null>(
  url: string,
  content: string,
  onEvent: (event: EntityParseSSEEvent<TInfo, TContact>) => void,
): Promise<void> => {
  const token = useUserStore().token
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token !== '' ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ content }),
  })

  if (!response.ok) {
    throw new Error(`HTTP error: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (reader === undefined || reader === null) {
    throw new Error('No response body')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const eventData = JSON.parse(line.slice(6)) as EntityParseSSEEvent<TInfo, TContact>
        onEvent(eventData)
        if (eventData.event === 'parsed' || eventData.event === 'error') {
          return
        }
      } catch {
        // 忽略单条事件解析错误，继续读流
      }
    }
  }
}

export const entityParseApi = {
  parseLead: (
    content: string,
    onEvent: (event: EntityParseSSEEvent<LeadParsedInfo>) => void,
  ): Promise<void> => streamParse<LeadParsedInfo>('/api/v1/leads/parse', content, onEvent),

  parseCustomer: (
    content: string,
    onEvent: (event: EntityParseSSEEvent<CustomerParsedInfo, CustomerParsedContact>) => void,
  ): Promise<void> =>
    streamParse<CustomerParsedInfo, CustomerParsedContact>('/api/v1/customers/ai/create/parse', content, onEvent),
}
