/**
 * header Store - Unit Tests
 *
 * Tests the header store for unified top-bar management
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useHeaderStore } from '../header'

// Mock handler function for tests
const mockHandler = (): void => {
  // Intentionally empty for test mock
}

describe('header store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('initial state', () => {
    it('should initialize with showBack=false', () => {
      const store = useHeaderStore()
      expect(store.showBack).toBe(false)
    })

    it('should initialize with backRoute=null', () => {
      const store = useHeaderStore()
      expect(store.backRoute).toBe(null)
    })

    it('should initialize with empty actions array', () => {
      const store = useHeaderStore()
      expect(store.actions).toEqual([])
    })

    it('should compute hasActions=false when actions empty', () => {
      const store = useHeaderStore()
      expect(store.hasActions).toBe(false)
    })
  })

  describe('setBack', () => {
    it('should set showBack to true', () => {
      const store = useHeaderStore()
      store.setBack(true)
      expect(store.showBack).toBe(true)
    })

    it('should set showBack to false', () => {
      const store = useHeaderStore()
      store.setBack(true)
      store.setBack(false)
      expect(store.showBack).toBe(false)
    })

    it('should set backRoute when provided', () => {
      const store = useHeaderStore()
      store.setBack(true, '/customers')
      expect(store.backRoute).toBe('/customers')
    })

    it('should set backRoute to null when not provided', () => {
      const store = useHeaderStore()
      store.setBack(true, '/customers')
      store.setBack(false)
      expect(store.backRoute).toBe(null)
    })
  })

  describe('setActions', () => {
    it('should set actions array', () => {
      const store = useHeaderStore()
      const actions = [
        { id: 'edit', label: '编辑', handler: mockHandler }
      ]
      store.setActions(actions)
      expect(store.actions).toEqual(actions)
      expect(store.hasActions).toBe(true)
    })

    it('should replace existing actions', () => {
      const store = useHeaderStore()
      store.setActions([{ id: 'edit', label: '编辑', handler: mockHandler }])
      store.setActions([{ id: 'delete', label: '删除', handler: mockHandler }])
      expect(store.actions.length).toBe(1)
      expect(store.actions[0].id).toBe('delete')
    })

    it('should clear actions when given empty array', () => {
      const store = useHeaderStore()
      store.setActions([{ id: 'edit', label: '编辑', handler: mockHandler }])
      store.setActions([])
      expect(store.actions).toEqual([])
      expect(store.hasActions).toBe(false)
    })
  })

  describe('addAction', () => {
    it('should add single action to existing actions', () => {
      const store = useHeaderStore()
      store.setActions([{ id: 'edit', label: '编辑', handler: mockHandler }])
      store.addAction({ id: 'delete', label: '删除', handler: mockHandler })
      expect(store.actions.length).toBe(2)
    })

    it('should add action when actions array is empty', () => {
      const store = useHeaderStore()
      store.addAction({ id: 'edit', label: '编辑', handler: mockHandler })
      expect(store.actions.length).toBe(1)
      expect(store.hasActions).toBe(true)
    })
  })

  describe('removeAction', () => {
    it('should remove action by id', () => {
      const store = useHeaderStore()
      store.setActions([
        { id: 'edit', label: '编辑', handler: mockHandler },
        { id: 'delete', label: '删除', handler: mockHandler }
      ])
      store.removeAction('edit')
      expect(store.actions.length).toBe(1)
      expect(store.actions[0].id).toBe('delete')
    })

    it('should not fail when removing non-existent action', () => {
      const store = useHeaderStore()
      store.setActions([{ id: 'edit', label: '编辑', handler: mockHandler }])
      store.removeAction('non-existent')
      expect(store.actions.length).toBe(1)
    })
  })

  describe('configure', () => {
    it('should configure all properties at once', () => {
      const store = useHeaderStore()
      const actions = [{ id: 'edit', label: '编辑', handler: mockHandler }]
      store.configure({
        showBack: true,
        backRoute: '/opportunities',
        actions
      })
      expect(store.showBack).toBe(true)
      expect(store.backRoute).toBe('/opportunities')
      expect(store.actions).toEqual(actions)
    })

    it('should only set provided properties', () => {
      const store = useHeaderStore()
      store.setBack(true, '/customers')
      store.configure({ showBack: false })
      expect(store.showBack).toBe(false)
      expect(store.backRoute).toBe('/customers') // unchanged
    })
  })

  describe('clear', () => {
    it('should reset all state to initial values', () => {
      const store = useHeaderStore()
      store.configure({
        showBack: true,
        backRoute: '/customers',
        actions: [{ id: 'edit', label: '编辑', handler: mockHandler }]
      })
      store.clear()
      expect(store.showBack).toBe(false)
      expect(store.backRoute).toBe(null)
      expect(store.actions).toEqual([])
      expect(store.hasActions).toBe(false)
    })
  })

  describe('hasActions computed', () => {
    it('should return true when actions has items', () => {
      const store = useHeaderStore()
      store.setActions([{ id: 'edit', label: '编辑', handler: mockHandler }])
      expect(store.hasActions).toBe(true)
    })

    it('should return false when actions is empty', () => {
      const store = useHeaderStore()
      expect(store.hasActions).toBe(false)
    })

    it('should update when actions change', () => {
      const store = useHeaderStore()
      store.setActions([{ id: 'edit', label: '编辑', handler: mockHandler }])
      expect(store.hasActions).toBe(true)
      store.setActions([])
      expect(store.hasActions).toBe(false)
    })
  })
})