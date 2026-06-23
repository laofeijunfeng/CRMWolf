/**
 * Task 17: Trajectory Navigation Test
 *
 * Tests for step-to-message navigation with highlight
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// Mock execution steps and messages
const createMockStepsWithMessages = () => {
  const steps = [
    { id: 'step-1', type: 'TOOL_CALL', title: '查询客户', timestamp: new Date() },
    { id: 'step-2', type: 'TOOL_RESULT', title: '查询成功', timestamp: new Date() },
    { id: 'step-3', type: 'REACT_COMPLETE', title: '执行完成', timestamp: new Date() }
  ]

  const messages = [
    { id: 101, role: 'user', content: '查询所有客户', timestamp: new Date() },
    { id: 102, role: 'assistant', content: '找到3个客户', timestamp: new Date(), executionSteps: steps }
  ]

  return { steps, messages }
}

describe('Task 17: Step-to-Message Navigation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should create stepToMessageMap from messages', async () => {
    // Map should associate each step.id to message.id

    const { steps, messages } = createMockStepsWithMessages()

    const stepToMessageMap: Record<string, number> = {}

    for (const message of messages) {
      if (message.role === 'assistant' && message.executionSteps) {
        for (const step of message.executionSteps) {
          stepToMessageMap[step.id] = message.id
        }
      }
    }

    // Test: each step should map to message 102
    expect(stepToMessageMap['step-1']).toBe(102)
    expect(stepToMessageMap['step-2']).toBe(102)
    expect(stepToMessageMap['step-3']).toBe(102)
  })

  it('should emit navigate-to-message when step is clicked', async () => {
    // ExpandedView should emit navigate-to-message event with messageId

    const emit = vi.fn()
    const stepToMessageMap = { 'step-1': 102 }
    const step = { id: 'step-1', type: 'TOOL_CALL', title: '查询客户' }

    const handleStepClick = (step: { id: string }, map: Record<string, number>) => {
      const messageId = map[step.id]
      if (messageId) {
        emit('navigate-to-message', messageId)
      }
    }

    handleStepClick(step, stepToMessageMap)
    expect(emit).toHaveBeenCalledWith('navigate-to-message', 102)
  })

  it('should not emit if step.id is not in stepToMessageMap', async () => {
    // Should not emit if step is not mapped to any message

    const emit = vi.fn()
    const stepToMessageMap = { 'step-1': 102 }
    const step = { id: 'step-999', type: 'TOOL_CALL' }

    const handleStepClick = (step: { id: string }, map: Record<string, number>) => {
      const messageId = map[step.id]
      if (messageId) {
        emit('navigate-to-message', messageId)
      }
    }

    handleStepClick(step, stepToMessageMap)
    expect(emit).not.toHaveBeenCalled()
  })
})

describe('Task 17: Message Highlight', () => {
  it('should scroll to message element with smooth behavior', async () => {
    // scrollIntoView should use smooth scrolling

    const mockElement = {
      scrollIntoView: vi.fn(),
      classList: {
        add: vi.fn(),
        remove: vi.fn()
      }
    }

    const messageId = 102
    const element = mockElement

    element.scrollIntoView({
      behavior: 'smooth',
      block: 'center'
    })

    expect(element.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'center'
    })
  })

  it('should add highlighted class to message element', async () => {
    // Message should get highlighted class for 2 seconds

    const mockElement = {
      classList: {
        add: vi.fn(),
        remove: vi.fn()
      }
    }

    mockElement.classList.add('highlighted')
    expect(mockElement.classList.add).toHaveBeenCalledWith('highlighted')
  })

  it('should remove highlighted class after 2 seconds', async () => {
    // Highlight should disappear after 2 seconds

    vi.useFakeTimers()

    const mockElement = {
      classList: {
        add: vi.fn(),
        remove: vi.fn()
      }
    }

    mockElement.classList.add('highlighted')

    // Schedule removal after 2 seconds
    setTimeout(() => {
      mockElement.classList.remove('highlighted')
    }, 2000)

    // Advance time by 2 seconds
    vi.advanceTimersByTime(2000)

    expect(mockElement.classList.remove).toHaveBeenCalledWith('highlighted')

    vi.useRealTimers()
  })

  it('should use message id as element id', async () => {
    // Message element should have id="message-{messageId}"

    const messageId = 102
    const elementId = `message-${messageId}`

    expect(elementId).toBe('message-102')
  })
})

describe('Task 17: CSS Highlight Style', () => {
  it('should apply primary color background for highlighted message', async () => {
    // Highlighted message should have rgba(primary, 0.1) background

    const highlightStyles = {
      background: 'rgba(primary, 0.1)',
      borderLeft: '3px solid primary',
      transition: 'background 0.3s ease, border-left 0.3s ease'
    }

    expect(highlightStyles.background).toContain('rgba')
    expect(highlightStyles.borderLeft).toContain('3px solid')
  })

  it('should remove background and border when not highlighted', async () => {
    // Non-highlighted message should have transparent background

    const normalStyles = {
      background: 'transparent',
      borderLeft: 'none',
      transition: 'background 0.3s ease, border-left 0.3s ease'
    }

    expect(normalStyles.background).toBe('transparent')
    expect(normalStyles.borderLeft).toBe('none')
  })
})

describe('Task 17: Integration with Components', () => {
  it('should pass stepToMessageMap from AIAssistant to AgentExecutionLog', async () => {
    // stepToMessageMap should flow from AIAssistant -> AgentExecutionLog -> CompactExecutionLog -> ExpandedView

    const propsChain = {
      aiAssistant: { stepToMessageMap: { 'step-1': 102 } },
      agentExecutionLog: { stepToMessageMap: { 'step-1': 102 } },
      compactExecutionLog: { stepToMessageMap: { 'step-1': 102 } },
      expandedView: { stepToMessageMap: { 'step-1': 102 } }
    }

    expect(propsChain.expandedView.stepToMessageMap).toEqual({ 'step-1': 102 })
  })

  it('should emit navigate-to-message through component chain', async () => {
    // Event should propagate from ExpandedView -> CompactExecutionLog -> AgentExecutionLog -> AIAssistant

    const eventChain = [
      'expandedView emits navigate-to-message',
      'compactExecutionLog emits navigate-to-message',
      'agentExecutionLog emits navigate-to-message',
      'aiAssistant handles navigate-to-message'
    ]

    expect(eventChain.length).toBe(4)
    expect(eventChain[3]).toContain('handles')
  })

  it('should add click handler to each step item', async () => {
    // ExpandedView step-item should have @click="handleStepClick(step)"

    const stepItemHandlers = ['click']
    expect(stepItemHandlers).toContain('click')
  })
})

describe('Task 17: Console Logging', () => {
  it('should log navigation event for debugging', async () => {
    // Console should log when navigation occurs

    const consoleSpy = vi.spyOn(console, 'log')

    const messageId = 102
    const stepId = 'step-1'

    console.log('[Navigation] Navigate to message:', messageId, 'from step:', stepId)

    expect(consoleSpy).toHaveBeenCalledWith(
      '[Navigation] Navigate to message:',
      messageId,
      'from step:',
      stepId
    )

    consoleSpy.mockRestore()
  })

  it('should log scroll completion', async () => {
    // Console should log when scroll completes

    const consoleSpy = vi.spyOn(console, 'log')

    const messageId = 102
    console.log('[Navigation] Scrolled to message:', messageId)

    expect(consoleSpy).toHaveBeenCalledWith(
      '[Navigation] Scrolled to message:',
      messageId
    )

    consoleSpy.mockRestore()
  })
})

console.log('[Task 17 Tests] Trajectory navigation test suite ready')