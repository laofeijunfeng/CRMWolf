import request from '@/utils/request'

export interface TodoCount {
  lead: number
  customer: number
  opportunity: number
  payment: number
  total: number
}

export interface CalendarMonthResponse {
  year: number
  month: number
  todos: Record<string, TodoCount>
}

export interface LeadFollowUpTodo {
  id: number
  lead_id: number
  lead_name: string
  contact_name: string
  contact_phone: string
  next_action: string | null
  next_follow_time: string | null
  is_overdue: boolean
}

export interface CustomerFollowUpTodo {
  id: number
  customer_id: number
  account_name: string
  next_action: string | null
  next_follow_time: string | null
  is_overdue: boolean
}

export interface OpportunityTodo {
  id: number
  opportunity_name: string
  customer_name: string
  total_amount: number
  expected_closing_date: string
  current_stage_name: string | null
  is_overdue: boolean
}

export interface PaymentPlanTodo {
  id: number
  contract_id: number
  contract_name: string
  customer_name: string
  stage_name: string
  planned_amount: number
  due_date: string
  is_overdue: boolean
}

export interface CalendarDateDetailResponse {
  date: string
  lead_follow_ups: LeadFollowUpTodo[]
  customer_follow_ups: CustomerFollowUpTodo[]
  opportunities: OpportunityTodo[]
  payment_plans: PaymentPlanTodo[]
  total_count: number
}

// FollowUp AI 跟进相关类型
export interface FollowUpParseRequest {
  todo_type: string
  todo_id: number
  user_input: string
}

export interface ParsedAction {
  skill: string
  action: string
  params: Record<string, any>
}

export interface FollowUpParseResponse {
  actions: ParsedAction[]
  reply_text: string
  context: TodoContextResponse
}

export interface FollowUpExecuteRequest {
  actions: ParsedAction[]
}

export interface FollowUpExecuteResult {
  success: boolean
  message: string
  data?: Record<string, any>
}

export interface FollowUpExecuteResponse {
  success: boolean
  message: string
  results: FollowUpExecuteResult[]
}

export interface TodoContextResponse {
  todo_type: string
  todo_id: number
  entity_type: string
  entity_id: number
  entity_info: Record<string, any>
  current_next_follow_time: string | null
  current_next_action: string | null
}

export const calendarApi = {
  getMonthTodos: (year: number, month: number) => {
    return request.get<CalendarMonthResponse>('/v1/calendar/todos', {
      params: { year, month }
    })
  },

  getDateTodos: (date: string) => {
    return request.get<CalendarDateDetailResponse>('/v1/calendar/todos/date', {
      params: { date }
    })
  },

  getTodoContext: (todoType: string, todoId: number) => {
    return request.get<TodoContextResponse>(`/v1/calendar/todos/${todoType}/${todoId}/context`)
  },

  parseFollowUp: (data: FollowUpParseRequest) => {
    return request.post<FollowUpParseResponse>('/v1/calendar/follow-up/parse', data)
  },

  executeFollowUp: (data: FollowUpExecuteRequest) => {
    return request.post<FollowUpExecuteResponse>('/v1/calendar/follow-up/execute', data)
  }
}