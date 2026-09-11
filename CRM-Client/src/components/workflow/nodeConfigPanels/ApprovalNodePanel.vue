<script setup lang="ts">
import { onMounted, ref } from 'vue'
import roleApi, { type RoleResponse } from '@/api/role'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SelectField } from '@/components/crmwolf'

const props = defineProps<{ config: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:config': [patch: Record<string, unknown>] }>()
const roles = ref<RoleResponse[]>([])
const error = ref('')
const loading = ref(false)
function update(field: string, value: string | number): void { emit('update:config', { [field]: String(value) }) }

async function loadRoles(): Promise<void> {
  loading.value = true
  error.value = ''
  try { roles.value = await roleApi.getRoles() } catch { error.value = '无法加载审批角色，请确认角色管理权限后重试。' }
  finally { loading.value = false }
}
onMounted(() => { void loadRoles() })
</script>
<template>
  <div data-testid="config-panel-approval.step" class="grid gap-4">
    <div class="grid gap-2"><Label for="config-node-name">节点名称</Label><Input id="config-node-name" data-testid="config-node-name" :model-value="String(props.config['node_name'] ?? '')" @update:model-value="value => update('node_name', value)" /></div>
    <SelectField id="config-approve-role" data-testid="config-approve-role" label="审批角色" :model-value="String(props.config['approve_role'] ?? '')" :options="roles.map(role => ({ value: role.code, label: role.name }))" :disabled="loading" required @update:model-value="value => update('approve_role', value)" />
    <p v-if="error" class="text-sm text-wolf-danger" role="alert">{{ error }}</p>
  </div>
</template>
