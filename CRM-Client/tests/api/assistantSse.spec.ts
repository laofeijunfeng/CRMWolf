import { describe, expect, it, vi } from 'vitest'
vi.mock('@/stores/user', () => ({ useUserStore: () => ({ token: 'token' }) }))
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }))

import { createSseSplitter, parseSseBlock, resolveAssistantApiBase, submitInputStream } from '@/api/assistant'

describe('SSE parser', () => {
  it('parses a named event with json data', () => {
    const parsed = parseSseBlock('event: accepted\ndata: {"turn_id":"t_1"}')
    expect(parsed).toEqual({ event: 'accepted', data: '{"turn_id":"t_1"}' })
  })

  it('returns null on blank or comment noise', () => {
    expect(parseSseBlock('')).toBeNull()
    expect(parseSseBlock(': keepalive')).toBeNull()
  })

  it('joins multi-line data payloads', () => {
    const parsed = parseSseBlock('event: stage\ndata: {"a":\ndata: 1}')
    expect(parsed?.data).toBe('{"a":1}')
  })

  it('splits chunks on frame boundaries only', () => {
    const split = createSseSplitter()
    // Real frames end every line with \n; chunks may cut anywhere.
    expect(split('event: a\n')).toEqual([])
    const first = split('data: 1\n\nevent: b\n')
    expect(first).toEqual(['event: a\ndata: 1'])
    const second = split('data: 2\n\n')
    expect(second).toEqual(['event: b\ndata: 2'])
    expect(split('')).toEqual([])
  })

  it('keeps partial frame buffered across chunks', () => {
    const split = createSseSplitter()
    split('event: stage\ndata: {"stage":"classify"')
    const blocks = split(',"phase":"start"}\n\n')
    expect(blocks).toEqual(['event: stage\ndata: {"stage":"classify","phase":"start"}'])
  })

  it('splits CRLF frames and flushes a legal tail frame', () => {
    const split = createSseSplitter()
    const blocks = split('event: accepted\r\ndata: {"turn_id":"t_1"}\r\n\r\n')
    expect(blocks).toEqual(['event: accepted\ndata: {"turn_id":"t_1"}'])
    split('event: waiting\ndata: {"ok":true}')
    expect(split.flush().map(parseSseBlock)).toEqual([{ event: 'waiting', data: '{"ok":true}' }])
  })
})

describe('assistant API base', () => {
  it('treats an empty build-time base as the nginx /api prefix', () => {
    expect(resolveAssistantApiBase('')).toBe('/api')
    expect(resolveAssistantApiBase('   ')).toBe('/api')
    expect(resolveAssistantApiBase(undefined)).toBe('/api')
    expect(resolveAssistantApiBase('/api')).toBe('/api')
  })

  it('posts the durable submit stream under /api when the base is empty', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 405, body: null })
    vi.stubGlobal('fetch', fetchMock)
    const lost = vi.fn()
    await submitInputStream('ast_one', { kind: 'text', text: '跟进', client_request_id: 'client-req' }, {
      onAccepted() { return undefined },
      onStage() { return undefined },
      onWaiting() { return undefined },
      onError() { return undefined },
      onNetworkLost: lost
    })
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/api/v1/assistant/tasks/ast_one/submit')
    expect(lost).toHaveBeenCalledTimes(1)
  })
})
