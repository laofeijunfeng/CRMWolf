<script setup lang="ts">
import { computed } from 'vue'
import { toast } from 'vue-sonner'
import { AlertTriangle } from 'lucide-vue-next'
import { usePermissionStore } from '@/stores/permissions'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

const permissionStore = usePermissionStore()
const visible = computed(() => permissionStore.loadState === 'error')
const retrying = computed(() => permissionStore.loadState === 'loading')

const retry = async (): Promise<void> => {
  try {
    await permissionStore.refreshPermissions()
    toast.success('权限已刷新')
  } catch {
    toast.error('权限刷新失败', { description: '请检查网络后再次重试。' })
  }
}
</script>

<template>
  <Alert v-if="visible" variant="warning" class="permission-status-banner">
    <AlertTriangle aria-hidden="true" />
    <div class="permission-status-banner__content">
      <AlertTitle>权限信息暂不可用</AlertTitle>
      <AlertDescription>
        为避免误操作，编辑、审批等受权限控制的操作已暂时隐藏。请重试权限同步，不影响已加载的数据。
      </AlertDescription>
    </div>
    <Button
      class="permission-status-banner__action"
      variant="outline"
      size="sm"
      :loading="retrying"
      @click="retry"
    >
      {{ retrying ? '同步中…' : '重试权限同步' }}
    </Button>
  </Alert>
</template>

<style scoped>
.permission-status-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0.75rem 1rem 0;
}

.permission-status-banner__content {
  min-width: 0;
  flex: 1;
}

.permission-status-banner__action {
  flex-shrink: 0;
}

@media (max-width: 640px) {
  .permission-status-banner {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .permission-status-banner__action {
    margin-left: 2rem;
  }
}
</style>
