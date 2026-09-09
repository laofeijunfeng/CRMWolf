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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { InputField } from '@/components/crmwolf'
import deploymentApi, { type DeploymentInfoResponse } from '@/api/deployment'
import type { DeploymentInfoCreate } from '@/schemas/deployment'
import { handleApiError } from '@/utils/errorHandler'
import { useDialogCloseGuard } from '@/composables/useDialogCloseGuard'

interface Props {
  open: boolean
  customerId: string
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'success', deployment: DeploymentInfoResponse): void
}

interface DeploymentForm {
  deploymentName: string
  serverAddress: string
  isDefault: boolean
}

interface DeploymentFormErrors {
  deploymentName: string
  serverAddress: string
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const submitting = ref(false)

const form = reactive<DeploymentForm>({
  deploymentName: '',
  serverAddress: '',
  isDefault: false,
})
const initialFormSnapshot = ref(JSON.stringify(form))

const errors = reactive<DeploymentFormErrors>({
  deploymentName: '',
  serverAddress: '',
})

const visible = computed({
  get: (): boolean => props.open,
  set: (value: boolean): void => emit('update:open', value),
})
const isDirty = computed(() => JSON.stringify(form) !== initialFormSnapshot.value)

const closeGuard = useDialogCloseGuard({
  isDirty,
  submitting,
  emitOpen: (open) => emit('update:open', open),
})
const showConfirmDialog = closeGuard.showConfirmDialog

function clearErrors(): void {
  errors.deploymentName = ''
  errors.serverAddress = ''
}

function resetForm(): void {
  form.deploymentName = ''
  form.serverAddress = ''
  form.isDefault = false
  clearErrors()
  initialFormSnapshot.value = JSON.stringify(form)
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

  return errors.deploymentName === ''
    && errors.serverAddress === ''
}

async function handleSubmit(): Promise<void> {
  if (submitting.value || !validateForm()) return

  const payload: DeploymentInfoCreate = {
    customer_id: props.customerId,
    deployment_name: form.deploymentName.trim(),
    server_address: form.serverAddress.trim(),
    is_default: form.isDefault,
  }

  submitting.value = true
  try {
    const createdDeployment = await deploymentApi.create(payload)
    toast.success('部署信息已新增')
    closeGuard.approveClose()
    visible.value = false
    emit('success', createdDeployment)
  } catch (error: unknown) {
    handleApiError(error, '新增部署信息')
  } finally {
    submitting.value = false
  }
}

function handleCancel(): void {
  closeGuard.requestClose()
}

function handleOpenChange(open: boolean): void {
  closeGuard.handleOpenChange(open)
}

function confirmCancel(): void {
  closeGuard.confirmDiscard()
}

function continueEditing(): void {
  closeGuard.continueEditing()
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      closeGuard.reset()
      resetForm()
    } else {
      if (closeGuard.handleParentClose()) return
      clearErrors()
    }
  },
  { immediate: true }
)

</script>

<template>
  <Dialog :open="props.open" @update:open="handleOpenChange">
    <DialogContent class="deployment-dialog">
      <DialogHeader>
        <DialogTitle>新增部署信息</DialogTitle>
        <DialogDescription>填写客户的部署环境，后续 License 申请会关联到部署信息。</DialogDescription>
      </DialogHeader>

      <form class="deployment-dialog__form" novalidate @submit.prevent="handleSubmit">
        <InputField
          id="deployment-name"
          v-model="form.deploymentName"
          class="deployment-dialog__field"
          label="部署名称"
          required
          placeholder="如：生产环境、测试环境"
          :disabled="submitting"
          :error="errors.deploymentName"
        />

        <InputField
          id="deployment-server"
          v-model="form.serverAddress"
          class="deployment-dialog__field"
          label="服务器地址"
          required
          placeholder="https://crm.example.com:8891"
          :disabled="submitting"
          :error="errors.serverAddress"
        />

        <div class="deployment-dialog__switch-row">
          <Switch
            id="deployment-default"
            v-model="form.isDefault"
            :disabled="submitting"
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

  <AlertDialog :open="showConfirmDialog" @update:open="closeGuard.handleConfirmOpenChange">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>放弃更改？</AlertDialogTitle>
        <AlertDialogDescription>
          已填写部署信息，关闭后这些内容不会保存。
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel @click="continueEditing">继续编辑</AlertDialogCancel>
        <AlertDialogAction @click="confirmCancel">放弃更改</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
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

.deployment-dialog__switch-label {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.deployment-dialog__switch-row {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
}

.deployment-dialog__footer {
  padding-top: $wolf-space-sm-v2;
}
</style>
