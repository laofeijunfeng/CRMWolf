<script setup lang="ts">
import { onMounted, ref } from 'vue'
import procurementApi, { type ProcurementMethodResponse, type ProcurementStageTemplate } from '@/api/procurement'
import { SelectField } from '@/components/crmwolf'

const props = defineProps<{ config: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:config': [patch: Record<string, unknown>] }>()
const stages = ref<ProcurementStageTemplate[]>([])
const loading = ref(false)
const error = ref('')

function update(field: string, value: string): void { emit('update:config', { [field]: value === '__any__' ? null : value }) }
async function loadStages(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const methods: ProcurementMethodResponse[] = await procurementApi.getProcurementMethods({ is_active: 1 })
    const responses = await Promise.all(methods.map(method => procurementApi.getProcurementMethod(method.id)))
    stages.value = responses.flatMap(response => response.stage_templates)
  } catch { error.value = '无法加载商机阶段选项，请检查采购阶段权限或稍后重试。' }
  finally { loading.value = false }
}
onMounted(() => { void loadStages() })
</script>
<template>
  <div data-testid="config-panel-trigger.opportunity_stage_changed" class="grid gap-4">
    <SelectField id="config-select-from-stage" data-testid="config-select-from-stage" label="原阶段" :model-value="String(props.config['from_stage'] ?? '__any__')" :options="[{ value: '__any__', label: '任意阶段' }, ...stages.map(stage => ({ value: stage.template_code, label: stage.stage_name }))]" :disabled="loading" @update:model-value="value => update('from_stage', value)" />
    <SelectField id="config-select-to-stage" data-testid="config-select-to-stage" label="目标阶段" :model-value="String(props.config['to_stage'] ?? '')" :options="stages.map(stage => ({ value: stage.template_code, label: stage.stage_name }))" :disabled="loading" required placeholder="请选择目标阶段" @update:model-value="value => update('to_stage', value)" />
    <p v-if="error" class="text-sm text-wolf-danger" role="alert">{{ error }}</p>
  </div>
</template>
