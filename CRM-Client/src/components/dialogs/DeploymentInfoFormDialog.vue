<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import deploymentApi, { type DeploymentInfoCreate } from '@/api/deployment'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  open: boolean
  customerId: number
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'success'): void
}

interface DeploymentForm {
  deploymentName: string
  serverAddress: string
  authorizedUsers: string
  isDefault: boolean
}

interface DeploymentFormErrors {
  deploymentName: string
  serverAddress: string
  authorizedUsers: string
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const submitting = ref(false)

const form = reactive<DeploymentForm>({
  deploymentName: '',
  serverAddress: '',
  authorizedUsers: '1',
  isDefault: false,
})

const errors = reactive<DeploymentFormErrors>({
  deploymentName: '',
  serverAddress: '',
  authorizedUsers: '',
})

const visible = computed({
  get: (): boolean => props.open,
  set: (value: boolean): void => emit('update:open', value),
})

function clearErrors(): void {
  errors.deploymentName = ''
  errors.serverAddress = ''
  errors.authorizedUsers = ''
}

function resetForm(): void {
  form.deploymentName = ''
  form.serverAddress = ''
  form.authorizedUsers = '1'
  form.isDefault = false
  clearErrors()
}

function validateForm(): boolean {
  clearErrors()

  if (form.deploymentName.trim() === '') {
    errors.deploymentName = '请输入部署名称'
  } else if (form.deploymentName.trim().length > 100) {
    errors.deploymentName = '部署名称不能超过 100 个字符'
  }

  if (form.serverAddress.trim() === '') {
    errors.serverAddress = '请输入服务器地址'
  } else if (!/^https?:\/\/.+/i.test(form.serverAddress.trim())) {
    errors.serverAddress = '服务器地址必须以 http:// 或 https:// 开头'
  } else if (form.serverAddress.trim().length > 500) {
    errors.serverAddress = '服务器地址不能超过 500 个字符'
  }

  const users = Number(form.authorizedUsers)
  if (form.authorizedUsers.trim() === '' || !Number.isInteger(users) || users < 1) {
    errors.authorizedUsers = '请输入大于 0 的整数'
  }

  return errors.deploymentName === ''
    && errors.serverAddress === ''
    && errors.authorizedUsers === ''
}

async function handleSubmit(): Promise<void> {
  if (submitting.value || !validateForm()) return

  const payload: DeploymentInfoCreate = {
    customer_id: props.customerId,
    deployment_name: form.deploymentName.trim(),
    server_address: form.serverAddress.trim(),
    authorized_users: Number(form.authorizedUsers),
    is_default: form.isDefault,
  }

  submitting.value = true
  try {
    await deploymentApi.create(payload)
    toast.success('部署信息已新增')
    visible.value = false
    emit('success')
  } catch (error: unknown) {
    handleApiError(error, '新增部署信息')
  } finally {
    submitting.value = false
  }
}

function handleCancel(): void {
  if (!submitting.value) {
    visible.value = false
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      resetForm()
    } else {
      clearErrors()
    }
  },
  { immediate: true }
)
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="deployment-dialog">
      <DialogHeader>
        <DialogTitle>新增部署信息</DialogTitle>
        <DialogDescription>填写客户的部署环境和授权规模，后续 License 申请会关联到部署信息。</DialogDescription>
      </DialogHeader>

      <form class="deployment-dialog__form" novalidate @submit.prevent="handleSubmit">
        <div class="deployment-dialog__field">
          <Label for="deployment-name" class="deployment-dialog__label">
            部署名称
            <span class="deployment-dialog__required" aria-hidden="true">*</span>
          </Label>
          <Input
            id="deployment-name"
            v-model="form.deploymentName"
            class="deployment-dialog__control h-11 min-h-11"
            placeholder="如：生产环境、测试环境"
            :disabled="submitting"
            :aria-invalid="errors.deploymentName !== ''"
            aria-describedby="deployment-name-error"
          />
          <p v-if="errors.deploymentName" id="deployment-name-error" class="deployment-dialog__error" role="alert">
            {{ errors.deploymentName }}
          </p>
        </div>

        <div class="deployment-dialog__field">
          <Label for="deployment-server" class="deployment-dialog__label">
            服务器地址
            <span class="deployment-dialog__required" aria-hidden="true">*</span>
          </Label>
          <Input
            id="deployment-server"
            v-model="form.serverAddress"
            class="deployment-dialog__control h-11 min-h-11"
            placeholder="https://crm.example.com:8891"
            :disabled="submitting"
            :aria-invalid="errors.serverAddress !== ''"
            aria-describedby="deployment-server-error"
          />
          <p v-if="errors.serverAddress" id="deployment-server-error" class="deployment-dialog__error" role="alert">
            {{ errors.serverAddress }}
          </p>
        </div>

        <div class="deployment-dialog__field">
          <Label for="deployment-users" class="deployment-dialog__label">
            授权人数
            <span class="deployment-dialog__required" aria-hidden="true">*</span>
          </Label>
          <Input
            id="deployment-users"
            v-model="form.authorizedUsers"
            type="number"
            inputmode="numeric"
            min="1"
            step="1"
            class="deployment-dialog__control h-11 min-h-11"
            placeholder="请输入授权人数"
            :disabled="submitting"
            :aria-invalid="errors.authorizedUsers !== ''"
            aria-describedby="deployment-users-error"
          />
          <p v-if="errors.authorizedUsers" id="deployment-users-error" class="deployment-dialog__error" role="alert">
            {{ errors.authorizedUsers }}
          </p>
        </div>

        <div class="deployment-dialog__switch-row">
          <Switch
            id="deployment-default"
            :checked="form.isDefault"
            :disabled="submitting"
            @update:checked="form.isDefault = $event"
          />
          <Label for="deployment-default" class="deployment-dialog__switch-label">设为默认部署</Label>
        </div>

        <DialogFooter class="deployment-dialog__footer">
          <Button type="button" variant="outline" :disabled="submitting" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :disabled="submitting">
            {{ submitting ? '保存中...' : '保存' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.deployment-dialog {
  max-width: 560px;
}

.deployment-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.deployment-dialog__field {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;
}

.deployment-dialog__label,
.deployment-dialog__switch-label {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.deployment-dialog__control {
  width: 100%;
}

.deployment-dialog__switch-row {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
}

.deployment-dialog__required,
.deployment-dialog__error {
  color: $wolf-danger-v2;
}

.deployment-dialog__error {
  margin: 0;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.deployment-dialog__footer {
  padding-top: $wolf-space-sm-v2;
}
</style>
