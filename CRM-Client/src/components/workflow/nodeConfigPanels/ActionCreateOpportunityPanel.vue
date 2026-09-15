<script setup lang="ts">
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SelectField } from '@/components/crmwolf'

const props = defineProps<{ config: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:config': [patch: Record<string, unknown>] }>()

function update(field: string, value: string | number): void {
  emit('update:config', { [field]: value })
}

function updateNumber(field: string, value: string | number, nullable = false): void {
  if (nullable && value === '') {
    emit('update:config', { [field]: null })
    return
  }
  const numberValue = Number(value)
  emit('update:config', { [field]: Number.isNaN(numberValue) ? 0 : numberValue })
}

const licenseTypes = [
  { value: 'SUBSCRIPTION', label: '订阅制' },
  { value: 'PERPETUAL', label: '永久授权' },
]
const purchaseTypes = [
  { value: 'NEW', label: '新购' },
  { value: 'RENEWAL', label: '续费' },
  { value: 'EXPANSION', label: '扩容' },
]
const ownerStrategies = [
  { value: 'creator', label: '创建者' },
  { value: 'owner', label: '负责人' },
]
</script>

<template>
  <div data-testid="config-panel-crm.create_opportunity" class="grid gap-4">
    <div class="grid gap-2"><Label for="config-opportunity-customer-ref">关联客户来源</Label><Input id="config-opportunity-customer-ref" data-testid="config-opportunity-customer-ref" :model-value="String(props.config['customer_ref'] ?? '')" @update:model-value="value => update('customer_ref', value)" /></div>
    <div class="grid gap-2"><Label for="config-opportunity-product-id">产品对外 ID</Label><Input id="config-opportunity-product-id" data-testid="config-opportunity-product-id" :model-value="String(props.config['product_public_id'] ?? '')" @update:model-value="value => update('product_public_id', value)" /></div>
    <div class="grid gap-2"><Label for="config-opportunity-module-ids">产品模块对外 ID</Label><Input id="config-opportunity-module-ids" data-testid="config-opportunity-module-ids" :model-value="String(props.config['product_module_public_ids'] ?? '')" placeholder="逗号分隔" @update:model-value="value => update('product_module_public_ids', value)" /></div>
    <div class="grid gap-2"><Label for="config-opportunity-name">商机名称</Label><Input id="config-opportunity-name" data-testid="config-opportunity-name" :model-value="String(props.config['opportunity_name'] ?? '')" @update:model-value="value => update('opportunity_name', value)" /></div>
    <div class="grid gap-2"><Label for="config-total-amount">预计金额</Label><Input id="config-total-amount" data-testid="config-total-amount" type="number" :model-value="String(props.config['total_amount'] ?? 0)" @update:model-value="value => updateNumber('total_amount', value)" /></div>
    <div class="grid gap-2"><Label for="config-user-count">用户数</Label><Input id="config-user-count" data-testid="config-user-count" type="number" :model-value="String(props.config['user_count'] ?? 1)" @update:model-value="value => updateNumber('user_count', value)" /></div>
    <SelectField id="config-license-type" data-testid="config-license-type" label="授权类型" :model-value="String(props.config['license_type'] ?? 'SUBSCRIPTION')" :options="licenseTypes" required @update:model-value="value => update('license_type', value)" />
    <div class="grid gap-2"><Label for="config-subscription-years">订阅年限</Label><Input id="config-subscription-years" data-testid="config-subscription-years" type="number" :model-value="String(props.config['subscription_years'] ?? 1)" @update:model-value="value => updateNumber('subscription_years', value)" /></div>
    <SelectField id="config-purchase-type" data-testid="config-purchase-type" label="采购类型" :model-value="String(props.config['purchase_type'] ?? 'NEW')" :options="purchaseTypes" required @update:model-value="value => update('purchase_type', value)" />
    <div class="grid gap-2"><Label for="config-expected-closing-date">预计成交日期</Label><Input id="config-expected-closing-date" data-testid="config-expected-closing-date" type="date" :model-value="String(props.config['expected_closing_date'] ?? '')" @update:model-value="value => update('expected_closing_date', value)" /></div>
    <div class="grid gap-2"><Label for="config-decision-maker-count">决策人数</Label><Input id="config-decision-maker-count" data-testid="config-decision-maker-count" type="number" :model-value="props.config['decision_maker_count'] === null || props.config['decision_maker_count'] === undefined ? '' : String(props.config['decision_maker_count'])" @update:model-value="value => updateNumber('decision_maker_count', value, true)" /></div>
    <div class="grid gap-2"><Label for="config-procurement-method-id">采购方式 ID</Label><Input id="config-procurement-method-id" data-testid="config-procurement-method-id" type="number" :model-value="props.config['procurement_method_id'] === null || props.config['procurement_method_id'] === undefined ? '' : String(props.config['procurement_method_id'])" @update:model-value="value => updateNumber('procurement_method_id', value, true)" /></div>
    <div class="grid gap-2"><Label for="config-procurement-stage-id">采购阶段 ID</Label><Input id="config-procurement-stage-id" data-testid="config-procurement-stage-id" type="number" :model-value="props.config['procurement_stage_id'] === null || props.config['procurement_stage_id'] === undefined ? '' : String(props.config['procurement_stage_id'])" @update:model-value="value => updateNumber('procurement_stage_id', value, true)" /></div>
    <SelectField id="config-opportunity-owner-strategy" data-testid="config-opportunity-owner-strategy" label="负责人策略" :model-value="String(props.config['owner_strategy'] ?? 'creator')" :options="ownerStrategies" @update:model-value="value => update('owner_strategy', value)" />
  </div>
</template>
