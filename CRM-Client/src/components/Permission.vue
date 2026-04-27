<template>
  <slot v-if="hasPermission"></slot>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePermissionStore } from '@/stores/permissions'

interface Props {
  code?: string
  codes?: string[]
  mode?: 'any' | 'all'
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'all'
})

const permissionStore = usePermissionStore()

const hasPermission = computed(() => {
  if (props.code) {
    return permissionStore.hasPermission(props.code)
  }
  
  if (props.codes && props.codes.length > 0) {
    if (props.mode === 'any') {
      return permissionStore.hasAnyPermission(props.codes)
    } else {
      return permissionStore.hasAllPermissions(props.codes)
    }
  }
  
  return false
})
</script>
