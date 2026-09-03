export type EmptyStateReason = 'no-data' | 'filtered' | 'not-created' | 'forbidden'

export type DataViewState = 'idle' | 'loading' | 'refreshing' | 'ready' | 'empty' | 'error'

export type FeedbackErrorKind =
  | 'validation'
  | 'permission'
  | 'authentication'
  | 'not-found'
  | 'conflict'
  | 'network'
  | 'server'
  | 'unknown'

export interface FeedbackError {
  title: string
  description: string
  kind?: FeedbackErrorKind
  retryable?: boolean
  variant?: 'error' | 'forbidden'
  fieldErrors?: FieldError[]
  status?: number
  requestId?: string
  canRefresh?: boolean
  canReopen?: boolean
  outcomeUnknown?: boolean
}

export interface FieldError {
  field: string
  message: string
  code?: string
}

export interface FeedbackErrorOptions {
  /** 写操作不能使用“加载失败”这样的读取语义。 */
  operation?: 'read' | 'write'
}

export interface EmptyStateCopy {
  title: string
  description: string
}

const EMPTY_STATE_COPY: Record<EmptyStateReason, EmptyStateCopy> = {
  'no-data': {
    title: '暂无数据',
    description: '当前范围内还没有可展示的记录',
  },
  filtered: {
    title: '未找到匹配结果',
    description: '请调整筛选条件或清除筛选后重试',
  },
  'not-created': {
    title: '还没有创建记录',
    description: '创建第一条记录后，它会显示在这里',
  },
  forbidden: {
    title: '暂无查看权限',
    description: '你没有权限查看此处内容，请联系管理员',
  },
}

export function getEmptyStateCopy(
  reason: EmptyStateReason,
  overrides: Partial<EmptyStateCopy> = {},
): EmptyStateCopy {
  const copy = EMPTY_STATE_COPY[reason]
  return {
    title: overrides.title ?? copy.title,
    description: overrides.description ?? copy.description,
  }
}

export function resolveDataViewState(options: {
  loading: boolean
  dataCount: number
  hasError: boolean
  explicitState?: DataViewState | null
}): DataViewState {
  if (options.explicitState !== undefined && options.explicitState !== null) return options.explicitState
  if (options.loading) return options.dataCount > 0 ? 'refreshing' : 'loading'
  if (options.hasError) return 'error'
  return options.dataCount > 0 ? 'ready' : 'empty'
}

export function toFeedbackError(
  error: unknown,
  context: string,
  options: FeedbackErrorOptions = {},
): FeedbackError {
  const candidate = typeof error === 'object' && error !== null
    ? error as {
        code?: string
        message?: string
        response?: { status?: number; data?: unknown }
      }
    : {}
  const status = candidate.response?.status
  const operation = options.operation ?? 'read'
  const failureTitle = operation === 'write' ? `${context}失败` : `${context}加载失败`
  const errorMessage = candidate.message?.toLowerCase() ?? ''
  const structuredError = readStructuredError(candidate.response?.data)
  const baseMeta = {
    ...(status !== undefined ? { status } : {}),
    ...(structuredError.fieldErrors.length > 0 ? { fieldErrors: structuredError.fieldErrors } : {}),
    ...(structuredError.requestId !== undefined ? { requestId: structuredError.requestId } : {}),
  }

  if (status === 403) {
    return {
      kind: 'permission',
      variant: 'forbidden',
      title: `你没有${context}的访问权限`,
      description: '请联系管理员确认权限后重试',
      retryable: false,
      canRefresh: true,
      ...baseMeta,
    }
  }

  if (status === 401) {
    return {
      kind: 'authentication',
      title: '登录已过期',
      description: '请重新登录后再访问此内容',
      retryable: false,
      ...baseMeta,
    }
  }

  if (status === 404) {
    return {
      kind: 'not-found',
      title: `${context}不存在`,
      description: operation === 'write'
        ? '该对象可能已被删除或移动，请刷新后确认最新状态'
        : '请返回上一页或重新定位后再试',
      retryable: false,
      canRefresh: operation === 'write',
      ...baseMeta,
    }
  }

  if (status === 409) {
    return {
      kind: 'conflict',
      title: `${context}已发生变化`,
      description: operation === 'write'
        ? '其他人可能已经修改了该对象，请刷新后确认最新状态'
        : '当前数据已更新，请重新加载后再试',
      retryable: false,
      canRefresh: true,
      canReopen: operation === 'write',
      ...baseMeta,
    }
  }

  if (status === 422) {
    return {
      kind: 'validation',
      title: `${context}校验失败`,
      description: structuredError.message ?? '请检查必填项和格式后再试',
      retryable: false,
      ...baseMeta,
    }
  }

  if (status !== undefined && status >= 500) {
    return {
      kind: 'server',
      title: failureTitle,
      description: '服务器暂时无法处理请求，请稍后重试',
      retryable: true,
      ...baseMeta,
    }
  }

  const isNetworkError = candidate.code === 'ERR_NETWORK'
    || candidate.code === 'ECONNABORTED'
    || errorMessage.includes('network error')
    || errorMessage.includes('failed to fetch')
    || errorMessage.includes('timeout')
  if (isNetworkError) {
    return {
      kind: 'network',
      title: failureTitle,
      description: operation === 'write'
        ? '网络中断，操作结果可能尚未确认，请先查询最新状态后再重试'
        : '网络不稳定或服务器无响应，请重试',
      retryable: operation !== 'write',
      outcomeUnknown: operation === 'write',
      ...baseMeta,
    }
  }

  return {
    kind: 'unknown',
    title: failureTitle,
    description: '请重试；如果问题持续存在，请联系管理员',
    ...baseMeta,
  }
}

interface StructuredError {
  message?: string
  requestId?: string
  fieldErrors: FieldError[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function asNonEmptyString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() !== '' ? value : undefined
}

function normalizeField(value: unknown): string | undefined {
  if (typeof value === 'string') return asNonEmptyString(value)
  if (!Array.isArray(value)) return undefined

  const path = value
    .filter((part): part is string | number => typeof part === 'string' || typeof part === 'number')
    .map(part => String(part))
    .filter(part => part !== 'body' && part !== 'query' && part !== 'path' && part !== 'form')
  return path.length > 0 ? path[path.length - 1] : undefined
}

function parseFieldErrorItem(item: unknown): FieldError | null {
  if (!isRecord(item)) return null
  const field = normalizeField(item['field'] ?? item['loc'] ?? item['path'] ?? item['name'])
  const message = asNonEmptyString(item['message'] ?? item['msg'] ?? item['detail'])
  if (field === undefined || message === undefined) return null
  const code = asNonEmptyString(item['code'] ?? item['type'])
  return { field, message, ...(code !== undefined ? { code } : {}) }
}

function asUnknownArray(value: unknown): unknown[] | undefined {
  return Array.isArray(value) ? value as unknown[] : undefined
}

function firstNonEmptyString(values: unknown[]): string | undefined {
  for (const value of values) {
    const candidate = asNonEmptyString(value)
    if (candidate !== undefined) return candidate
  }
  return undefined
}

function firstDetailMessage(detailValue: unknown): unknown {
  const detailItems = asUnknownArray(detailValue)
  if (detailItems === undefined || detailItems.length === 0) return undefined
  const firstItem = detailItems[0]
  return isRecord(firstItem) ? firstItem['msg'] : undefined
}

function readStructuredError(data: unknown): StructuredError {
  const empty: StructuredError = { fieldErrors: [] }
  if (!isRecord(data)) return empty

  const detailValue = data['detail']
  const detail = isRecord(detailValue) ? detailValue : data
  const nestedDetailsValue = detail['details']
  const nestedDetails = isRecord(nestedDetailsValue) ? nestedDetailsValue : undefined
  const detailItems = asUnknownArray(detailValue)
  const rawFieldErrors = detailItems
    ?? detail['field_errors'] ?? detail['fieldErrors'] ?? detail['errors'] ?? nestedDetails?.['fields']

  let fieldErrors: FieldError[] = []
  const fieldErrorItems = asUnknownArray(rawFieldErrors)
  if (fieldErrorItems !== undefined) {
    fieldErrors = fieldErrorItems
      .map(parseFieldErrorItem)
      .filter((item): item is FieldError => item !== null)
  } else if (isRecord(rawFieldErrors)) {
    fieldErrors = Object.entries(rawFieldErrors).flatMap(([field, value]) => {
      const normalizedMessage = asNonEmptyString(Array.isArray(value) ? firstNonEmptyString(value) : value)
      return normalizedMessage !== undefined ? [{ field, message: normalizedMessage }] : []
    })
  }

  const message = asNonEmptyString(
    (isRecord(detailValue) ? detailValue['message'] : undefined)
      ?? data['message']
      ?? firstDetailMessage(detailValue),
  )
  const requestId = asNonEmptyString(
    (isRecord(detailValue) ? detailValue['request_id'] ?? detailValue['requestId'] : undefined)
      ?? detail['request_id']
      ?? detail['requestId']
      ?? data['request_id'],
  )
  return {
    ...(message !== undefined ? { message } : {}),
    ...(requestId !== undefined ? { requestId } : {}),
    fieldErrors,
  }
}
