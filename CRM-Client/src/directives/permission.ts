import type { App, Directive, DirectiveBinding } from 'vue'
import { usePermissionStore } from '@/stores/permissions'

const permissionDirective: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding) {
    const { value } = binding
    
    if (value && typeof value === 'string') {
      const permissionStore = usePermissionStore()
      const hasPermission = permissionStore.hasPermission(value)
      
      if (!hasPermission) {
        el.parentNode?.removeChild(el)
      }
    } else {
      throw new Error('权限指令需要权限码作为字符串参数，如 v-permission="\'contract:create\'"')
    }
  },
  updated(el: HTMLElement, binding: DirectiveBinding) {
    const { value } = binding
    
    if (value && typeof value === 'string') {
      const permissionStore = usePermissionStore()
      const hasPermission = permissionStore.hasPermission(value)
      
      if (!hasPermission) {
        el.parentNode?.removeChild(el)
      }
    }
  }
}

const anyPermissionDirective: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding) {
    const { value } = binding
    
    if (value && Array.isArray(value)) {
      const permissionStore = usePermissionStore()
      const hasPermission = permissionStore.hasAnyPermission(value)
      
      if (!hasPermission) {
        el.parentNode?.removeChild(el)
      }
    } else {
      throw new Error('权限指令需要权限码数组作为参数，如 v-any-permission="[\'contract:create\', \'contract:edit_own\']"')
    }
  },
  updated(el: HTMLElement, binding: DirectiveBinding) {
    const { value } = binding
    
    if (value && Array.isArray(value)) {
      const permissionStore = usePermissionStore()
      const hasPermission = permissionStore.hasAnyPermission(value)
      
      if (!hasPermission) {
        el.parentNode?.removeChild(el)
      }
    }
  }
}

const allPermissionDirective: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding) {
    const { value } = binding
    
    if (value && Array.isArray(value)) {
      const permissionStore = usePermissionStore()
      const hasPermission = permissionStore.hasAllPermissions(value)
      
      if (!hasPermission) {
        el.parentNode?.removeChild(el)
      }
    } else {
      throw new Error('权限指令需要权限码数组作为参数，如 v-all-permission="[\'contract:create\', \'contract:edit_own\']"')
    }
  },
  updated(el: HTMLElement, binding: DirectiveBinding) {
    const { value } = binding
    
    if (value && Array.isArray(value)) {
      const permissionStore = usePermissionStore()
      const hasPermission = permissionStore.hasAllPermissions(value)
      
      if (!hasPermission) {
        el.parentNode?.removeChild(el)
      }
    }
  }
}

export function setupPermissionDirective(app: App) {
  app.directive('permission', permissionDirective)
  app.directive('any-permission', anyPermissionDirective)
  app.directive('all-permission', allPermissionDirective)
}

export default permissionDirective
