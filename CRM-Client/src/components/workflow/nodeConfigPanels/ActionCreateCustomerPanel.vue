<script setup lang="ts">
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SelectField } from '@/components/crmwolf'

const props = defineProps<{ config: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:config': [patch: Record<string, unknown>] }>()

function update(field: string, value: string | number | null): void {
  emit('update:config', { [field]: value })
}

const ownerStrategies = [
  { value: 'creator', label: '创建者' },
  { value: 'owner', label: '负责人' },
]
</script>

<template>
  <div data-testid="config-panel-crm.create_customer" class="grid gap-4">
    <div class="grid gap-2"><Label for="config-account-name">客户公司名称</Label><Input id="config-account-name" data-testid="config-account-name" :model-value="String(props.config['account_name'] ?? '')" @update:model-value="value => update('account_name', value)" /></div>
    <div class="grid gap-2"><Label for="config-city">所在城市</Label><Input id="config-city" data-testid="config-city" :model-value="String(props.config['city'] ?? '')" @update:model-value="value => update('city', value)" /></div>
    <div class="grid gap-2"><Label for="config-industry">所属行业</Label><Input id="config-industry" data-testid="config-industry" :model-value="String(props.config['industry'] ?? '')" @update:model-value="value => update('industry', value)" /></div>
    <div class="grid gap-2"><Label for="config-address">地址</Label><Input id="config-address" data-testid="config-address" :model-value="String(props.config['address'] ?? '')" @update:model-value="value => update('address', value)" /></div>
    <div class="grid gap-2"><Label for="config-company-scale">公司规模</Label><Input id="config-company-scale" data-testid="config-company-scale" :model-value="String(props.config['company_scale'] ?? '')" @update:model-value="value => update('company_scale', value)" /></div>
    <SelectField id="config-owner-strategy" data-testid="config-owner-strategy" label="负责人策略" :model-value="String(props.config['owner_strategy'] ?? 'creator')" :options="ownerStrategies" @update:model-value="value => update('owner_strategy', value)" />
    <div class="grid gap-2"><Label for="config-default-procurement-method-id">默认采购方式 ID</Label><Input id="config-default-procurement-method-id" data-testid="config-default-procurement-method-id" type="number" :model-value="props.config['default_procurement_method_id'] === null || props.config['default_procurement_method_id'] === undefined ? '' : String(props.config['default_procurement_method_id'])" @update:model-value="value => update('default_procurement_method_id', value === '' ? null : Number(value))" /></div>
  </div>
</template>
