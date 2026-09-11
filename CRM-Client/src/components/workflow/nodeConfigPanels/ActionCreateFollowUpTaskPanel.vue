<script setup lang="ts">
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SelectField } from '@/components/crmwolf'

const props = defineProps<{ config: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:config': [patch: Record<string, unknown>] }>()
function update(field: string, value: string | number): void { emit('update:config', { [field]: String(value) }) }
const assigneeOptions = [
  { value: 'owner', label: '商机负责人' }, { value: 'role', label: '指定角色' }, { value: 'user', label: '指定用户' },
]
</script>
<template>
  <div data-testid="config-panel-action.create_follow_up_task" class="grid gap-4">
    <div class="grid gap-2"><Label for="config-title">任务标题</Label><Input id="config-title" data-testid="config-title" :model-value="String(props.config['title'] ?? '')" @update:model-value="value => update('title', value)" /></div>
    <SelectField id="config-assignee-strategy" label="负责人策略" :model-value="String(props.config['assignee_strategy'] ?? 'owner')" :options="assigneeOptions" @update:model-value="value => update('assignee_strategy', value)" />
    <div class="grid gap-2"><Label for="config-due-offset-days">截止偏移天数</Label><Input id="config-due-offset-days" type="number" :model-value="String(props.config['due_offset_days'] ?? 0)" @update:model-value="value => update('due_offset_days', value)" /></div>
  </div>
</template>
