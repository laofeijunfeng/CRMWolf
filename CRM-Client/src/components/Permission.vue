<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <slot v-if="hasPermission"></slot>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePermissionStore } from '@/stores/permissions'

interface Props {
  // These props are intentionally optional because the component supports either code or codes.
  // eslint-disable-next-line vue/require-default-prop
  code?: string
  // eslint-disable-next-line vue/require-default-prop
  codes?: string[]
  mode?: 'any' | 'all'
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'all'
})

const permissionStore = usePermissionStore()

const hasPermission = computed(() => {
  if (permissionStore.loadState !== 'ready') return false

  if (typeof props.code === 'string' && props.code.length > 0) {
    return permissionStore.hasPermission(props.code)
  }
  
  if (Array.isArray(props.codes) && props.codes.length > 0) {
    if (props.mode === 'any') {
      return permissionStore.hasAnyPermission(props.codes)
    } else {
      return permissionStore.hasAllPermissions(props.codes)
    }
  }
  
  return false
})
</script>
