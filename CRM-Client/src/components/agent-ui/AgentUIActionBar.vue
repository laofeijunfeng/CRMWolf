<script setup lang="ts">
import { Button } from '@/components/ui/button'
import type { AgentUIAction } from '@/schemas/agent-contracts'

defineProps<{
  actions: AgentUIAction[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  action: [actionId: string]
}>()
</script>

<template>
  <div v-if="actions.length > 0" class="flex flex-wrap gap-2" aria-label="可用操作">
    <Button
      v-for="action in actions"
      :key="action.action_id"
      type="button"
      size="sm"
      :variant="action.type === 'retry' ? 'outline' : 'secondary'"
      :disabled="disabled === true"
      @click="emit('action', action.action_id)"
    >
      {{ action.label }}
    </Button>
  </div>
</template>
