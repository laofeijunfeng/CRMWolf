<script setup lang="ts">
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { SelectField } from '@/components/crmwolf'

const props = defineProps<{ config: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:config': [patch: Record<string, unknown>] }>()

function update(field: string, value: string | number | boolean): void {
  emit('update:config', { [field]: value })
}

const genderOptions = [
  { value: '1', label: '男' },
  { value: '2', label: '女' },
]
</script>

<template>
  <div data-testid="config-panel-crm.create_contact" class="grid gap-4">
    <div class="grid gap-2"><Label for="config-customer-ref">关联客户来源</Label><Input id="config-customer-ref" data-testid="config-customer-ref" :model-value="String(props.config['customer_ref'] ?? '')" @update:model-value="value => update('customer_ref', value)" /></div>
    <div class="grid gap-2"><Label for="config-contact-name">联系人姓名</Label><Input id="config-contact-name" data-testid="config-contact-name" :model-value="String(props.config['name'] ?? '')" @update:model-value="value => update('name', value)" /></div>
    <SelectField id="config-contact-gender" data-testid="config-contact-gender" label="性别" :model-value="String(props.config['gender'] ?? '1')" :options="genderOptions" required @update:model-value="value => update('gender', value)" />
    <div class="grid gap-2"><Label for="config-contact-position">职位</Label><Input id="config-contact-position" data-testid="config-contact-position" :model-value="String(props.config['position'] ?? '')" @update:model-value="value => update('position', value)" /></div>
    <div class="grid gap-2"><Label for="config-contact-mobile">手机号</Label><Input id="config-contact-mobile" data-testid="config-contact-mobile" :model-value="String(props.config['mobile'] ?? '')" @update:model-value="value => update('mobile', value)" /></div>
    <label class="flex items-center gap-2" for="config-contact-decision-maker"><Checkbox id="config-contact-decision-maker" data-testid="config-contact-decision-maker" :checked="Boolean(props.config['is_decision_maker'])" @update:checked="value => update('is_decision_maker', value)" /><span>决策人</span></label>
    <div class="grid gap-2"><Label for="config-contact-email">邮箱</Label><Input id="config-contact-email" data-testid="config-contact-email" :model-value="String(props.config['email'] ?? '')" @update:model-value="value => update('email', value)" /></div>
    <div class="grid gap-2"><Label for="config-contact-wechat-id">微信号</Label><Input id="config-contact-wechat-id" data-testid="config-contact-wechat-id" :model-value="String(props.config['wechat_id'] ?? '')" @update:model-value="value => update('wechat_id', value)" /></div>
    <div class="grid gap-2"><Label for="config-contact-remark">备注</Label><Input id="config-contact-remark" data-testid="config-contact-remark" :model-value="String(props.config['remark'] ?? '')" @update:model-value="value => update('remark', value)" /></div>
  </div>
</template>
