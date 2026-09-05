import type { App, Directive, DirectiveBinding } from 'vue'
import { watchEffect } from 'vue'
import { usePermissionStore } from '@/stores/permissions'

type PermissionValue = string | string[]
type PermissionCheck = (store: ReturnType<typeof usePermissionStore>, value: PermissionValue) => boolean

interface PermissionDirectiveState {
  stop: () => void
  value: PermissionValue
  originallyHidden: boolean
  originallyAriaHidden: string | null
}

const states = new WeakMap<HTMLElement, PermissionDirectiveState>()

const getPermissionValue = (binding: DirectiveBinding): PermissionValue => {
  const value = binding.value as unknown
  if (typeof value === 'string' && value.length > 0) return value
  if (Array.isArray(value) && value.every(item => typeof item === 'string')) return value
  throw new Error('权限指令需要权限码作为字符串或字符串数组参数')
}

const isAllowed = (
  store: ReturnType<typeof usePermissionStore>,
  value: PermissionValue,
  check: PermissionCheck,
): boolean => store.loadState === 'ready' && check(store, value)

const setVisibility = (
  el: HTMLElement,
  allowed: boolean,
  state: PermissionDirectiveState,
): void => {
  // Do not remove the node. Removing it during the initial permission load
  // makes it impossible for a later successful response to restore the action.
  // ``hidden`` keeps the DOM/component alive while still failing closed.
  if (allowed) {
    el.hidden = state.originallyHidden
    if (state.originallyAriaHidden === null) {
      el.removeAttribute('aria-hidden')
    } else {
      el.setAttribute('aria-hidden', state.originallyAriaHidden)
    }
  } else {
    el.hidden = true
    el.setAttribute('aria-hidden', 'true')
  }
}

const mountPermissionDirective = (
  el: HTMLElement,
  binding: DirectiveBinding,
  check: PermissionCheck,
): void => {
  const value = getPermissionValue(binding)
  states.get(el)?.stop()

  const state: PermissionDirectiveState = {
    stop: () => undefined,
    value,
    originallyHidden: el.hidden,
    originallyAriaHidden: el.getAttribute('aria-hidden'),
  }
  states.set(el, state)

  const permissionStore = usePermissionStore()
  state.stop = watchEffect(() => {
    setVisibility(el, isAllowed(permissionStore, state.value, check), state)
  })
}

const updatePermissionDirective = (
  el: HTMLElement,
  binding: DirectiveBinding,
  check: PermissionCheck,
): void => {
  const state = states.get(el)
  const nextValue = getPermissionValue(binding)
  if (state === undefined || JSON.stringify(state.value) !== JSON.stringify(nextValue)) {
    mountPermissionDirective(el, binding, check)
  }
}

const unmountPermissionDirective = (el: HTMLElement): void => {
  states.get(el)?.stop()
  states.delete(el)
}

const createPermissionDirective = (check: PermissionCheck): Directive => ({
  mounted(el: HTMLElement, binding: DirectiveBinding): void {
    mountPermissionDirective(el, binding, check)
  },
  updated(el: HTMLElement, binding: DirectiveBinding): void {
    updatePermissionDirective(el, binding, check)
  },
  beforeUnmount(el: HTMLElement): void {
    unmountPermissionDirective(el)
  },
})

const permissionDirective = createPermissionDirective((store, value) =>
  typeof value === 'string' ? store.hasPermission(value) : store.hasAllPermissions(value),
)

const anyPermissionDirective = createPermissionDirective((store, value) =>
  Array.isArray(value) ? store.hasAnyPermission(value) : store.hasPermission(value),
)

const allPermissionDirective = createPermissionDirective((store, value) =>
  Array.isArray(value) ? store.hasAllPermissions(value) : store.hasPermission(value),
)

export function setupPermissionDirective(app: App): void {
  app.directive('permission', permissionDirective)
  app.directive('any-permission', anyPermissionDirective)
  app.directive('all-permission', allPermissionDirective)
}

export default permissionDirective
