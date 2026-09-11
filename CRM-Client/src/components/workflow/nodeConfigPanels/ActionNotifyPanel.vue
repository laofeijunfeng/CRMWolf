<script setup lang="ts">
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { SelectField } from '@/components/crmwolf'

const props = defineProps<{ config: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:config': [patch: Record<string, unknown>] }>()
function update(field: string, value: string | number | undefined): void {
  if (value === undefined) return
  emit('update:config', { [field]: String(value) })
}
const targets = [
  { value: 'owner', label: '负责人' }, { value: 'role', label: '角色' }, { value: 'users', label: '指定用户' },
]
</script>
<template>
  <div data-testid="config-panel-action.notify" class="grid gap-4">
    <SelectField id="config-notify-target" label="通知对象" :model-value="String(props.config['notify_target'] ?? 'owner')" :options="targets" required @update:model-value="value => update('notify_target', value)" />
    <div class="grid gap-2"><Label for="config-message-template">消息模板</Label><Textarea id="config-message-template" data-testid="config-message-template" :model-value="String(props.config['message_template'] ?? '')" @update:model-value="value => update('message_template', value)" /></div>
    <div class="grid gap-2"><Label for="config-notify-recipient">接收方（可选）</Label><Input id="config-notify-recipient" :model-value="String(props.config['recipient'] ?? '')" @update:model-value="value => update('recipient', value)" /></div>
  </div>
</template>
