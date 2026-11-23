import { afterEach, describe, expect, it, vi } from 'vitest'
vi.mock('@/stores/user', () => ({ useUserStore: () => ({ token: 'token' }) }))
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }))

import { createSseSplitter, parseSseBlock, resolveAssistantApiBase, submitInputStream } from '@/api/assistant'

afterEach(() => {
  vi.unstubAllEnvs()
})

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

describe('assistant stream stage events', () => {
  it('delivers all nine server stages and ignores unknown stages', async () => {
    const stages = ['route', 'locate', 'context', 'judge', 'propose', 'classify', 'structure', 'quality_gate', 'write']
    const frames = [...stages, 'unrecognized'].map((stage, index) =>
      `event: stage\ndata: ${JSON.stringify({ stage, phase: 'done', ms: 20, seq: index + 1 })}\n\n`)
    frames.push('event: stage\ndata: {"stage":"context","phase":"failed","seq":11}\n\n')
    frames.push('event: stage\ndata: {"stage":"judge","phase":"unrecognized","seq":12}\n\n')
    const error = { code: 'AI_UNAVAILABLE', message: '建议生成失败', retryable: true, stage: 'propose', seq: 13 }
    frames.push(`event: error\ndata: ${JSON.stringify(error)}\n\n`)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(frames.join(''))))

    const onStage = vi.fn()
    const onError = vi.fn()
    const onNetworkLost = vi.fn()
    await submitInputStream('ast_one', { kind: 'text', client_request_id: 'client-req' }, {
      onAccepted: vi.fn(), onStage, onWaiting: vi.fn(), onError, onNetworkLost,
    })

    expect(onStage.mock.calls.flat()).toEqual([
      ...stages.map((stage, index) => ({ stage, phase: 'done', ms: 20, seq: index + 1 })),
      { stage: 'context', phase: 'failed', seq: 11 },
    ])
    expect(onError).toHaveBeenCalledWith(error)
    expect(onNetworkLost).not.toHaveBeenCalled()
  })
})
