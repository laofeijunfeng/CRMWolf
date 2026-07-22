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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { DatePicker } from '@/components/ui/date-picker'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import SegmentedChoiceControl from '@/components/crmwolf/SegmentedChoiceControl.vue'
import SelectionSummary from '@/components/crmwolf/SelectionSummary.vue'
import licenseApplicationApi, { type LicenseApplicationCreate, type LicenseType } from '@/api/licenseApplication'
import type { ContractListResponse } from '@/api/contract'
import type { DeploymentInfoResponse } from '@/api/deployment'
import { handleApiError } from '@/utils/errorHandler'

const APPROVED_CONTRACT_STATUSES = ['SIGNED', 'EFFECTIVE']

interface Props {
  open: boolean
  customerId: number
  deployments: DeploymentInfoResponse[]
  contracts: ContractListResponse[]
  fixedContractId?: number | null
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'success'): void
}

interface LicenseForm {
  deploymentId: string
  licenseType: LicenseType
  contractId: string
  expiryDate: string
  remark: string
}

interface LicenseFormErrors {
  deploymentId: string
  contractId: string
  expiryDate: string
}

const props = withDefaults(defineProps<Props>(), {
  fixedContractId: null
})
const emit = defineEmits<Emits>()

const submitting = ref(false)

const form = reactive<LicenseForm>({
  deploymentId: '',
  licenseType: 'TRIAL',
  contractId: '',
  expiryDate: '',
  remark: '',
})

const errors = reactive<LicenseFormErrors>({
  deploymentId: '',
  contractId: '',
  expiryDate: '',
})

const visible = computed({
  get: (): boolean => props.open,
  set: (value: boolean): void => emit('update:open', value),
})

const approvedContracts = computed<ContractListResponse[]>(() => {
  return props.contracts
    .filter((contract) => APPROVED_CONTRACT_STATUSES.includes(contract.status))
    .sort((a, b) => new Date(b.created_time).getTime() - new Date(a.created_time).getTime())
})

const selectedContract = computed<ContractListResponse | null>(() => {
  return approvedContracts.value.find((contract) => String(contract.id) === form.contractId) ?? null
})
const selectedDeployment = computed<DeploymentInfoResponse | null>(() => {
  return props.deployments.find((deployment) => String(deployment.id) === form.deploymentId) ?? null
})

const selectedContractLabel = computed<string>(() => {
  return selectedContract.value !== null ? contractOptionLabel(selectedContract.value) : ''
})
const selectedDeploymentSummaryItems = computed(() => {
  if (selectedDeployment.value === null) return []

  return [
    { label: '部署名称', value: selectedDeployment.value.deployment_name },
    { label: '服务器地址', value: selectedDeployment.value.server_address },
    { label: '授权人数', value: `${selectedDeployment.value.authorized_users} 人` },
    { label: '默认部署', value: selectedDeployment.value.is_default ? '是' : '否' },
  ]
})

const hasDeployments = computed<boolean>(() => props.deployments.length > 0)
const hasFixedContract = computed<boolean>(() => props.fixedContractId !== null)
const licenseTypeOptions: { value: LicenseType, label: string, tone: 'success' | 'primary' }[] = [
  { value: 'TRIAL', label: '试用', tone: 'success' },
  { value: 'OFFICIAL', label: '正式', tone: 'primary' },
]

function clearErrors(): void {
  errors.deploymentId = ''
  errors.contractId = ''
  errors.expiryDate = ''
}

function formatLocalDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseLocalDate(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null

  const [year, month, day] = value.split('-').map(Number)
  if (year === undefined || month === undefined || day === undefined) return null
  return new Date(year, month - 1, day)
}

function handleExpiryDateChange(date: Date | null): void {
  form.expiryDate = date !== null ? formatLocalDate(date) : ''
}

function resetForm(): void {
  const defaultDeployment = props.deployments.find((deployment) => deployment.is_default)
  form.deploymentId = defaultDeployment !== undefined
    ? String(defaultDeployment.id)
    : props.deployments[0] !== undefined ? String(props.deployments[0].id) : ''
  form.licenseType = hasFixedContract.value ? 'OFFICIAL' : 'TRIAL'
  form.contractId = props.fixedContractId !== null ? String(props.fixedContractId) : ''
  form.expiryDate = ''
  form.remark = ''
  clearErrors()
}

function validateForm(): boolean {
  clearErrors()

  if (form.deploymentId === '') {
    errors.deploymentId = '请选择部署信息'
  }

  if (form.licenseType === 'OFFICIAL' && form.contractId === '') {
    errors.contractId = '正式 License 必须关联合同'
  }

  if (form.expiryDate === '') {
    errors.expiryDate = '请选择到期日期'
  } else {
    const expiryDate = parseLocalDate(form.expiryDate)
    if (expiryDate === null) {
      errors.expiryDate = '请选择有效日期'
    } else {
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      if (expiryDate <= today) {
        errors.expiryDate = '到期日期必须晚于今天'
      }
    }
  }

  return errors.deploymentId === ''
    && errors.contractId === ''
    && errors.expiryDate === ''
}

async function handleSubmit(): Promise<void> {
  if (submitting.value || !validateForm()) return

  const payload: LicenseApplicationCreate = {
    customer_id: props.customerId,
    deployment_info_id: Number(form.deploymentId),
    license_type: form.licenseType,
    contract_id: form.licenseType === 'OFFICIAL' ? Number(form.contractId) : null,
    expiry_date: form.expiryDate,
    remark: form.remark.trim() === '' ? null : form.remark.trim(),
  }

  submitting.value = true
  try {
    const created = await licenseApplicationApi.create(payload)
    await licenseApplicationApi.submitApplication(created.id)
    toast.success('License 申请已提交')
    visible.value = false
    emit('success')
  } catch (error: unknown) {
    handleApiError(error, '提交 License 申请')
  } finally {
    submitting.value = false
  }
}

function handleCancel(): void {
  if (!submitting.value) {
    visible.value = false
  }
}

function handleLicenseTypeChange(value: string): void {
  if (value !== 'TRIAL' && value !== 'OFFICIAL') return
  form.licenseType = value
}

function contractOptionLabel(contract: ContractListResponse): string {
  return `${contract.contract_name} · ${contract.contract_number}`
}

watch(
  () => form.licenseType,
  (type) => {
    if (hasFixedContract.value) {
      form.licenseType = 'OFFICIAL'
      form.contractId = String(props.fixedContractId)
      return
    }
    if (type === 'OFFICIAL' && form.contractId === '' && approvedContracts.value[0] !== undefined) {
      form.contractId = String(approvedContracts.value[0].id)
    }
    if (type === 'TRIAL') {
      form.contractId = ''
    }
  }
)

watch(
  () => [props.open, props.deployments.length, props.fixedContractId] as const,
  ([open]) => {
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
    <DialogContent class="license-application-dialog">
      <DialogHeader>
        <DialogTitle>申请 License</DialogTitle>
        <DialogDescription>选择部署信息、License 类型和有效期，提交后进入审批流程。</DialogDescription>
      </DialogHeader>

      <form class="license-application-dialog__form" novalidate @submit.prevent="handleSubmit">
        <div class="license-application-dialog__grid">
          <div class="license-application-dialog__field">
            <Label for="license-deployment" class="license-application-dialog__label">
              部署信息
              <span class="license-application-dialog__required" aria-hidden="true">*</span>
            </Label>
            <Select v-model="form.deploymentId" :disabled="submitting || !hasDeployments">
              <SelectTrigger
                id="license-deployment"
                class="license-application-dialog__control h-11 min-h-11"
                :aria-invalid="errors.deploymentId !== ''"
                aria-describedby="license-deployment-error"
              >
                <SelectValue :placeholder="hasDeployments ? '请选择部署信息' : '请先新增部署信息'" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="deployment in deployments"
                  :key="deployment.id"
                  :value="String(deployment.id)"
                >
                  {{ deployment.deployment_name }}{{ deployment.is_default ? ' · 默认' : '' }}
                </SelectItem>
              </SelectContent>
            </Select>
            <p v-if="errors.deploymentId" id="license-deployment-error" class="license-application-dialog__error" role="alert">
              {{ errors.deploymentId }}
            </p>
          </div>

          <div class="license-application-dialog__field">
            <Label id="license-type-label" class="license-application-dialog__label">
              License 类型
              <span class="license-application-dialog__required" aria-hidden="true">*</span>
            </Label>
            <SegmentedChoiceControl
              :model-value="form.licenseType"
              :options="licenseTypeOptions"
              class="license-application-dialog__control h-11 min-h-11"
              :disabled="submitting || hasFixedContract"
              labelled-by="license-type-label"
              @update:model-value="handleLicenseTypeChange"
            />
          </div>
        </div>

        <SelectionSummary
          v-if="selectedDeployment !== null"
          :items="selectedDeploymentSummaryItems"
        />

        <div class="license-application-dialog__grid">
          <div v-if="form.licenseType === 'OFFICIAL'" class="license-application-dialog__field">
            <Label for="license-contract" class="license-application-dialog__label">
              关联合同
              <span class="license-application-dialog__required" aria-hidden="true">*</span>
            </Label>
            <Select v-model="form.contractId" :disabled="submitting || hasFixedContract || approvedContracts.length === 0">
              <SelectTrigger
                id="license-contract"
                class="license-application-dialog__control license-application-dialog__contract-trigger h-11 min-h-11"
                :aria-invalid="errors.contractId !== ''"
                aria-describedby="license-contract-error"
                :title="selectedContractLabel || undefined"
              >
                <SelectValue :placeholder="approvedContracts.length > 0 ? '请选择合同' : '暂无可关联的已签署/已生效合同'" />
              </SelectTrigger>
              <SelectContent class="license-application-dialog__contract-content">
                <SelectItem
                  v-for="contract in approvedContracts"
                  :key="contract.id"
                  class="license-application-dialog__contract-option"
                  :value="String(contract.id)"
                >
                  <span class="license-application-dialog__contract-option-text">
                    <span class="license-application-dialog__contract-option-name">
                      {{ contract.contract_name }}
                    </span>
                    <span class="license-application-dialog__contract-option-number">
                      {{ contract.contract_number }}
                    </span>
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
            <p v-if="errors.contractId" id="license-contract-error" class="license-application-dialog__error" role="alert">
              {{ errors.contractId }}
            </p>
          </div>

          <div class="license-application-dialog__field">
            <Label class="license-application-dialog__label">
              到期日期
              <span class="license-application-dialog__required" aria-hidden="true">*</span>
            </Label>
            <DatePicker
              :model-value="parseLocalDate(form.expiryDate)"
              placeholder="请选择到期日期"
              class="license-application-dialog__control h-11 min-h-11"
              :disabled="submitting"
              @update:model-value="handleExpiryDateChange"
            />
            <p v-if="errors.expiryDate" class="license-application-dialog__error" role="alert">
              {{ errors.expiryDate }}
            </p>
          </div>
        </div>

        <div class="license-application-dialog__field">
          <Label for="license-remark" class="license-application-dialog__label">备注</Label>
          <Textarea
            id="license-remark"
            v-model="form.remark"
            class="license-application-dialog__textarea"
            placeholder="请输入申请备注（可选）"
            :disabled="submitting"
          />
        </div>

        <DialogFooter class="license-application-dialog__footer">
          <Button type="button" variant="outline" :disabled="submitting" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :disabled="submitting || !hasDeployments">
            {{ submitting ? '提交中...' : '提交申请' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.license-application-dialog {
  max-width: 720px;
}

.license-application-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.license-application-dialog__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2;
}

.license-application-dialog__field {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;
}

.license-application-dialog__label {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.license-application-dialog__control,
.license-application-dialog__textarea {
  width: 100%;
}

.license-application-dialog__contract-trigger {
  min-width: 0;
  overflow: hidden;
}

.license-application-dialog__contract-trigger :deep(span) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.license-application-dialog__contract-content {
  width: min(560px, calc(100vw - 32px));
  max-width: min(560px, calc(100vw - 32px));
}

.license-application-dialog__contract-option {
  align-items: flex-start;
  min-width: 0;
  white-space: normal;
}

.license-application-dialog__contract-option-text {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
  line-height: $wolf-line-height-body-v2;
}

.license-application-dialog__contract-option-name {
  overflow-wrap: anywhere;
  color: $wolf-text-primary-v2;
}

.license-application-dialog__contract-option-number {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.license-application-dialog__textarea {
  min-height: 96px;
}

.license-application-dialog__required,
.license-application-dialog__error {
  color: $wolf-danger-v2;
}

.license-application-dialog__error {
  margin: 0;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.license-application-dialog__footer {
  padding-top: $wolf-space-sm-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .license-application-dialog__grid {
    grid-template-columns: 1fr;
  }
}
</style>
