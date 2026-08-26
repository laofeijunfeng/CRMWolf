<script setup lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

import { Button } from '@/components/ui/button'
import type { AgentUIBlock } from '@/schemas/agent-contracts'

type PaginationBlock = Extract<AgentUIBlock, { type: 'pagination' }>

defineProps<{
  block: PaginationBlock
  disabled?: boolean
}>()

const emit = defineEmits<{
  action: [actionId: string]
}>()
</script>

<template>
  <nav class="flex items-center justify-between gap-3 text-xs text-muted-foreground" aria-label="查询结果分页">
    <span>
      第 {{ block.range_start }}–{{ block.range_end }} 条<span v-if="block.total !== null && block.total !== undefined">，共 {{ block.total }} 条</span>
    </span>
    <div class="flex gap-1">
      <Button
        type="button"
        variant="outline"
        size="sm"
        :disabled="disabled === true || !block.previous_action_id"
        aria-label="上一页"
        @click="block.previous_action_id && emit('action', block.previous_action_id)"
      >
        <ChevronLeft class="h-4 w-4" aria-hidden="true" />
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        :disabled="disabled === true || !block.next_action_id"
        aria-label="下一页"
        @click="block.next_action_id && emit('action', block.next_action_id)"
      >
        <ChevronRight class="h-4 w-4" aria-hidden="true" />
      </Button>
    </div>
  </nav>
</template>
