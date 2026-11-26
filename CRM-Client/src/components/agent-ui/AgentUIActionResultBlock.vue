<script setup lang="ts">
import { computed } from 'vue'
import { AlertCircle, CheckCircle2, CircleSlash2 } from 'lucide-vue-next'

import AgentUIBanner from './AgentUIBanner.vue'
import { Button } from '@/components/ui/button'
import type { AgentUIBlock, EntityRef } from '@/schemas/agent-contracts'
import { isAgentEntityOpenable } from '@/components/agent/agentEntityNavigation'

type ActionResultBlock = Extract<AgentUIBlock, { type: 'action_result' }>

const props = defineProps<{ block: ActionResultBlock }>()
const CUSTOMER_PREFIX = '客户：'
const messageLines = computed(() => {
  const lines = props.block.message.split('\n').map(line => line.trim()).filter(line => line !== '')
  return lines.length > 0 ? lines : [props.block.message]
})
const multiline = computed(() => messageLines.value.length > 1)
const customerRef = computed<EntityRef | null>(() => (
  props.block.subject ?? (props.block.entity_ref?.resource === 'customer' ? props.block.entity_ref : null)
))
// The customer line carries the customer link itself; no separate link row beside it.
const customerLineIndex = computed(() => (
  customerRef.value ? messageLines.value.findIndex(line => line.startsWith(CUSTOMER_PREFIX)) : -1
))
const openableCustomer = computed<EntityRef | null>(() => (
  customerRef.value && isAgentEntityOpenable(customerRef.value) ? customerRef.value : null
))
const openableEntity = computed<EntityRef | null>(() => (
  props.block.entity_ref && isAgentEntityOpenable(props.block.entity_ref) ? props.block.entity_ref : null
))

const emit = defineEmits<{
  'open-entity': [entityRef: EntityRef]
}>()

const iconByStatus = {
  SUCCESS: CheckCircle2,
  FAILED: AlertCircle,
  CANCELLED: CircleSlash2
} satisfies Record<ActionResultBlock['status'], unknown>

const toneByStatus = {
  SUCCESS: 'success',
  FAILED: 'danger',
  CANCELLED: 'neutral'
} as const satisfies Record<ActionResultBlock['status'], string>
</script>

<template>
  <AgentUIBanner
    :tone="toneByStatus[block.status]"
    :icon="iconByStatus[block.status]"
    :title="block.title"
    :role="block.status === 'FAILED' ? 'alert' : 'status'"
  >
    <p
      v-for="(line, index) in messageLines"
      :key="index"
      :class="['m-0', multiline ? 'text-body text-foreground' : 'text-caption text-muted-foreground']"
    >
      <template v-if="index === customerLineIndex && openableCustomer">
        {{ CUSTOMER_PREFIX }}<Button
          type="button"
          variant="link"
          class="h-auto p-0 align-baseline"
          :aria-label="`打开${openableCustomer.display_name}详情`"
          @click="emit('open-entity', openableCustomer)"
        >{{ line.slice(CUSTOMER_PREFIX.length) }}</Button>
      </template>
      <template v-else>{{ line }}</template>
    </p>
    <template v-if="customerLineIndex < 0">
      <Button
        v-if="openableEntity"
        type="button"
        variant="link"
        size="sm"
        class="max-w-full justify-start"
        :aria-label="`打开${openableEntity.display_name}详情`"
        @click="emit('open-entity', openableEntity)"
      >
        {{ openableEntity.display_name }}
      </Button>
      <p v-else-if="block.entity_ref" class="m-0 max-w-full truncate text-caption text-muted-foreground">
        {{ block.entity_ref.display_name }}
      </p>
    </template>
  </AgentUIBanner>
</template>
