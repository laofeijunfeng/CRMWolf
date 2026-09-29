import { describe, expect, it } from 'vitest'

import { createSseSplitter, parseSseBlock } from '@/api/assistant'

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
})
