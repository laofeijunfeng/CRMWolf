import { describe, expect, it } from 'vitest'
import { getEmptyStateCopy, resolveDataViewState, toFeedbackError } from '../feedback'

describe('feedback state protocol', () => {
  it('keeps existing data visible while a refresh is in progress', () => {
    expect(resolveDataViewState({ loading: true, dataCount: 3, hasError: false })).toBe('refreshing')
    expect(resolveDataViewState({ loading: true, dataCount: 0, hasError: false })).toBe('loading')
  })

  it('does not represent a failed first load as an empty state', () => {
    expect(resolveDataViewState({ loading: false, dataCount: 0, hasError: true })).toBe('error')
  })

  it('provides distinct copy for filtered results', () => {
    expect(getEmptyStateCopy('filtered')).toEqual({
      title: '未找到匹配结果',
      description: '请调整筛选条件或清除筛选后重试',
    })
  })

  it('allows page-specific copy without changing the reason', () => {
    expect(getEmptyStateCopy('no-data', { title: '暂无待审批事项' })).toEqual({
      title: '暂无待审批事项',
      description: '当前范围内还没有可展示的记录',
    })
  })

  it('classifies permission and not-found errors with an explicit recovery path', () => {
    expect(toFeedbackError({ response: { status: 403 } }, '客户列表')).toMatchObject({
      kind: 'permission',
      variant: 'forbidden',
      retryable: false,
    })
    expect(toFeedbackError({ response: { status: 404 } }, '客户详情')).toMatchObject({
      kind: 'not-found',
      title: '客户详情不存在',
      retryable: false,
    })
  })

  it('uses write semantics for validation and network failures', () => {
    expect(toFeedbackError({ response: { status: 422 } }, '更新客户', { operation: 'write' })).toMatchObject({
      kind: 'validation',
      title: '更新客户校验失败',
      retryable: false,
    })
    expect(toFeedbackError({ code: 'ERR_NETWORK', message: 'Network Error' }, '登记回款', { operation: 'write' })).toMatchObject({
      kind: 'network',
      title: '登记回款失败',
      retryable: false,
    })
  })

  it('normalizes FastAPI validation locations into form field errors', () => {
    expect(toFeedbackError({
      response: {
        status: 422,
        data: {
          detail: [
            { loc: ['body', 'account_name'], msg: '客户名称不能为空', type: 'value_error' },
            { loc: ['body', 'default_procurement_method_id'], msg: '采购方式无效', type: 'value_error' },
          ],
        },
      },
    }, '更新客户', { operation: 'write' })).toMatchObject({
      kind: 'validation',
      fieldErrors: [
        { field: 'account_name', message: '客户名称不能为空', code: 'value_error' },
        { field: 'default_procurement_method_id', message: '采购方式无效', code: 'value_error' },
      ],
    })
  })

  it('preserves structured server field errors for form-level recovery', () => {
    expect(toFeedbackError({
      response: {
        status: 422,
        data: {
          detail: {
            message: '请检查表单内容',
            field_errors: [
              { field: 'account_name', code: 'required', message: '客户名称不能为空' },
            ],
            request_id: 'req_customer_1',
          },
        },
      },
    }, '更新客户', { operation: 'write' })).toMatchObject({
      kind: 'validation',
      description: '请检查表单内容',
      fieldErrors: [{ field: 'account_name', code: 'required', message: '客户名称不能为空' }],
      requestId: 'req_customer_1',
      status: 422,
    })
  })
})
