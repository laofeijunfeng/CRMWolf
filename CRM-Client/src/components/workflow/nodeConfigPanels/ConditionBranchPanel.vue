<script setup lang="ts">
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SelectField } from '@/components/crmwolf'

const props = defineProps<{ config: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:config': [patch: Record<string, unknown>] }>()
function update(field: string, value: string | number): void { emit('update:config', { [field]: String(value) }) }
const operators = [
  { value: 'eq', label: '等于' }, { value: 'neq', label: '不等于' },
  { value: 'gt', label: '大于' }, { value: 'lt', label: '小于' }, { value: 'in', label: '包含于' },
]
</script>
<template>
  <div data-testid="config-panel-control.condition" class="grid gap-4">
    <div class="grid gap-2"><Label for="config-condition-field">字段</Label><Input id="config-condition-field" data-testid="config-condition-field" :model-value="String(props.config['field'] ?? '')" @update:model-value="value => update('field', value)" /></div>
    <SelectField id="config-condition-operator" label="操作符" :model-value="String(props.config['operator'] ?? 'eq')" :options="operators" @update:model-value="value => update('operator', value)" />
    <div class="grid gap-2"><Label for="config-condition-value">值</Label><Input id="config-condition-value" data-testid="config-condition-value" :model-value="String(props.config['value'] ?? '')" @update:model-value="value => update('value', value)" /></div>
  </div>
</template>
