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
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  DateField,
  InputField,
  SelectField,
  SegmentedChoiceControl,
  TextareaField,
} from '@/components/crmwolf'
import SelectionSummary from '@/components/crmwolf/SelectionSummary.vue'
import ProductIntentPicker from '@/components/crmwolf/ProductIntentPicker.vue'
import FieldHelpTip from '@/components/crmwolf/FieldHelpTip.vue'
import DeploymentInfoFormDialog from '@/components/dialogs/DeploymentInfoFormDialog.vue'
import licenseApplicationApi, { type LicenseType } from '@/api/licenseApplication'
import { TRIAL_EXPIRY_REQUIRED_ERROR, type LicenseApplicationCreate } from '@/schemas/licenseApplication'
import type { ContractListResponse } from '@/api/contract'
import type { DeploymentInfoResponse } from '@/api/deployment'
import { handleApiError } from '@/utils/errorHandler'
import { useDialogCloseGuard } from '@/composables/useDialogCloseGuard'
import { useProductCatalog } from '@/composables/useProductCatalog'

const APPROVED_CONTRACT_STATUSES = ['SIGNED']
const LOCKED_PRODUCT_HINT = '产品跟随关联合同对应的商机，不可修改'

interface Props {
  elevated?: boolean
  open: boolean
  customerId: string
  deployments: DeploymentInfoResponse[]
  contracts: ContractListResponse[]
  defaultLicenseType?: LicenseType | null
  defaultContractId?: number | null
  fixedContractId?: number | null
  canCreateDeployment?: boolean
  /** 当前商机的产品，作为默认产品；正式版关联合同时锁定为该产品 */
  opportunityProductPublicId?: string | null
  opportunityProductName?: string | null
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'success'): void
  (event: 'deployment-created', deployment: DeploymentInfoResponse): void
}

interface LicenseForm {
  deploymentId: string
  licenseType: LicenseType
  contractId: string
  productPublicId: string
  authorizedUsers: string
  expiryDate: string
  isPermanent: boolean
  remark: string
}

interface LicenseFormErrors {
  deploymentId: string
  contractId: string
  productPublicId: string
  authorizedUsers: string
  expiryDate: string
}

const props = withDefaults(defineProps<Props>(), {
  defaultLicenseType: null,
  defaultContractId: null,
  fixedContractId: null,
  canCreateDeployment: false,
  opportunityProductPublicId: null,
  opportunityProductName: null,
})
const emit = defineEmits<Emits>()

const submitting = ref(false)
const deploymentDialogOpen = ref(false)
const locallyCreatedDeployments = ref<DeploymentInfoResponse[]>([])
const productCatalog = useProductCatalog()

const form = reactive<LicenseForm>({
  deploymentId: '',
  licenseType: 'TRIAL',
  contractId: '',
  productPublicId: '',
  authorizedUsers: '1',
  expiryDate: '',
  isPermanent: false,
  remark: '',
})

const initialForm = ref<LicenseForm>({ ...form })

const errors = reactive<LicenseFormErrors>({
  deploymentId: '',
  contractId: '',
  productPublicId: '',
  authorizedUsers: '',
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
const availableDeployments = computed<DeploymentInfoResponse[]>(() => {
  const propDeploymentIds = new Set(props.deployments.map((deployment) => deployment.id))
  return [
    ...props.deployments,
    ...locallyCreatedDeployments.value.filter((deployment) => !propDeploymentIds.has(deployment.id)),
  ]
})
const selectedDeployment = computed<DeploymentInfoResponse | null>(() => {
  return availableDeployments.value.find((deployment) => String(deployment.id) === form.deploymentId) ?? null
})
const deploymentOptions = computed(() =>
  availableDeployments.value.map((deployment) => ({
    value: String(deployment.id),
    label: `${deployment.deployment_name}${deployment.is_default ? ' · 默认' : ''}`,
  }))
)
const contractOptions = computed(() =>
  approvedContracts.value.map((contract) => ({
    value: String(contract.id),
    label: contractOptionLabel(contract),
  }))
)

const selectedContractLabel = computed<string>(() => {
  return selectedContract.value !== null ? contractOptionLabel(selectedContract.value) : ''
})
const selectedDeploymentSummaryItems = computed(() => {
  if (selectedDeployment.value === null) return []

  return [
    { label: '部署名称', value: selectedDeployment.value.deployment_name },
    { label: '服务器地址', value: selectedDeployment.value.server_address },
    { label: '默认部署', value: selectedDeployment.value.is_default ? '是' : '否' },
  ]
})

const hasDeployments = computed<boolean>(() => availableDeployments.value.length > 0)
const hasFixedContract = computed<boolean>(() => props.fixedContractId !== null)
const productLocked = computed<boolean>(() =>
  form.licenseType === 'OFFICIAL'
  && form.contractId !== ''
  && (props.opportunityProductPublicId ?? '') !== ''
)
const productFallbackName = computed<string>(() =>
  form.productPublicId !== '' && form.productPublicId === props.opportunityProductPublicId
    ? (props.opportunityProductName ?? '').trim()
    : ''
)
const productBlocked = computed<boolean>(() => {
  if (productCatalog.loading.value) return true
  if (productCatalog.forbidden.value) return productFallbackName.value === ''
  return productCatalog.empty.value && !productLocked.value
})
const hasFormChanges = computed<boolean>(() => {
  return Object.keys(form).some((key) => {
    const field = key as keyof LicenseForm
    return form[field] !== initialForm.value[field]
  })
})
const closeGuard = useDialogCloseGuard({
  isDirty: hasFormChanges,
  submitting,
  emitOpen: (open) => emit('update:open', open),
})
const defaultApprovedContract = computed<ContractListResponse | null>(() => {
  if (props.defaultContractId === null) return null
  return approvedContracts.value.find((contract) => contract.id === props.defaultContractId) ?? null
})
const licenseTypeOptions: { value: LicenseType, label: string, tone: 'success' | 'primary' }[] = [
  { value: 'TRIAL', label: '试用', tone: 'success' },
  { value: 'OFFICIAL', label: '正式', tone: 'primary' },
]

function clearErrors(): void {
  errors.deploymentId = ''
  errors.contractId = ''
  errors.productPublicId = ''
  errors.authorizedUsers = ''
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

// 永久与到期日期互斥：切换任一方向都清空日期，关闭永久后需重新选择。
function handlePermanentChange(value: boolean): void {
  form.isPermanent = value
  form.expiryDate = ''
  errors.expiryDate = ''
}

function getInitialLicenseType(): LicenseType {
  if (hasFixedContract.value) return 'OFFICIAL'
  if (props.defaultLicenseType === 'OFFICIAL' && defaultApprovedContract.value !== null) return 'OFFICIAL'
  if (props.defaultLicenseType === 'TRIAL') return 'TRIAL'
  return defaultApprovedContract.value !== null ? 'OFFICIAL' : 'TRIAL'
}

function getInitialContractId(licenseType: LicenseType): string {
  if (props.fixedContractId !== null) return String(props.fixedContractId)
  if (licenseType !== 'OFFICIAL') return ''
  if (defaultApprovedContract.value !== null) return String(defaultApprovedContract.value.id)
  return approvedContracts.value[0] !== undefined ? String(approvedContracts.value[0].id) : ''
}

function getInitialAuthorizedUsers(contractId: string): string {
  const contract = approvedContracts.value.find((item) => String(item.id) === contractId)
  if (contract !== undefined && Number.isInteger(contract.user_count) && contract.user_count > 0) {
    return String(contract.user_count)
  }

  const deployment = availableDeployments.value.find((item) => String(item.id) === form.deploymentId)
  if (deployment?.authorized_users !== null && deployment?.authorized_users !== undefined && deployment.authorized_users > 0) {
    return String(deployment.authorized_users)
  }

  return '1'
}

function resetForm(): void {
  const defaultDeployment = availableDeployments.value.find((deployment) => deployment.is_default)
  const initialLicenseType = getInitialLicenseType()
  const initialContractId = getInitialContractId(initialLicenseType)
  form.deploymentId = defaultDeployment !== undefined
    ? String(defaultDeployment.id)
    : availableDeployments.value[0] !== undefined ? String(availableDeployments.value[0].id) : ''
  form.licenseType = initialLicenseType
  form.contractId = initialContractId
  form.productPublicId = props.opportunityProductPublicId ?? ''
  form.authorizedUsers = getInitialAuthorizedUsers(initialContractId)
  form.expiryDate = ''
  form.isPermanent = false
  form.remark = ''
  clearErrors()
  initialForm.value = { ...form }
}

function validateForm(): boolean {
  clearErrors()

  if (form.deploymentId === '') {
    errors.deploymentId = '请选择部署信息'
  }

  if (form.licenseType === 'OFFICIAL' && form.contractId === '') {
    errors.contractId = '正式 License 必须关联合同'
  }

  if (form.productPublicId === '' && !productBlocked.value) {
    errors.productPublicId = '请选择产品'
  }

  const authorizedUsers = Number(form.authorizedUsers)
  if (form.authorizedUsers.trim() === '' || !Number.isInteger(authorizedUsers) || authorizedUsers < 1) {
    errors.authorizedUsers = '请输入大于 0 的整数'
  }

  if (!form.isPermanent) {
    const expiryDate = form.expiryDate === '' ? null : parseLocalDate(form.expiryDate)
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    if (form.licenseType === 'TRIAL' && (expiryDate === null || expiryDate <= today)) {
      errors.expiryDate = TRIAL_EXPIRY_REQUIRED_ERROR
    } else if (form.expiryDate === '') {
      errors.expiryDate = '请选择到期日期'
    } else if (expiryDate === null) {
      errors.expiryDate = '请选择有效日期'
    } else if (expiryDate <= today) {
      errors.expiryDate = '到期日期必须晚于今天'
    }
  }

  return errors.deploymentId === ''
    && errors.contractId === ''
    && errors.productPublicId === ''
    && errors.expiryDate === ''
}

async function handleSubmit(): Promise<void> {
  if (submitting.value || productBlocked.value || !validateForm()) return

  const payload: LicenseApplicationCreate = {
    customer_id: props.customerId,
    deployment_info_id: Number(form.deploymentId),
    license_type: form.licenseType,
    contract_id: form.licenseType === 'OFFICIAL' ? Number(form.contractId) : null,
    product_public_id: form.productPublicId,
    authorized_users: Number(form.authorizedUsers),
    is_permanent: form.isPermanent,
    expiry_date: form.isPermanent ? null : form.expiryDate,
    remark: form.remark.trim() === '' ? null : form.remark.trim(),
  }

  submitting.value = true
  try {
    const created = await licenseApplicationApi.create(payload)
    await licenseApplicationApi.submitApplication(created.id)
    toast.success('License 申请已提交')
    closeGuard.approveClose()
    visible.value = false
    emit('success')
  } catch (error: unknown) {
    handleApiError(error, '提交 License 申请')
  } finally {
    submitting.value = false
  }
}

function handleOpenChange(open: boolean): void {
  closeGuard.handleOpenChange(open)
}

function handleCancel(): void {
  closeGuard.requestClose()
}

function handleAddDeployment(): void {
  if (!props.canCreateDeployment || submitting.value) return
  deploymentDialogOpen.value = true
}

function handleDeploymentSuccess(deployment: DeploymentInfoResponse): void {
  locallyCreatedDeployments.value = [
    ...locallyCreatedDeployments.value.filter((item) => item.id !== deployment.id),
    deployment,
  ]
  form.deploymentId = String(deployment.id)
  errors.deploymentId = ''
  deploymentDialogOpen.value = false
  emit('deployment-created', deployment)
}

function handleLicenseTypeChange(value: string): void {
  if (value !== 'TRIAL' && value !== 'OFFICIAL') return
  form.licenseType = value
}

function contractOptionLabel(contract: ContractListResponse): string {
  return `${contract.contract_name} · ${contract.contract_number}`
}

/** 可编辑时不保留已停用或不在目录中的产品，避免提交后才被后端拒绝 */
function clearUnselectableProduct(): void {
  if (productLocked.value || form.productPublicId === '') return
  if (productCatalog.loading.value || productCatalog.forbidden.value) return
  const selected = productCatalog.products.value.find(product => product.public_id === form.productPublicId)
  if (selected?.is_active === true) return
  if (initialForm.value.productPublicId === form.productPublicId) {
    initialForm.value = { ...initialForm.value, productPublicId: '' }
  }
  form.productPublicId = ''
}

watch(
  productLocked,
  (locked) => {
    if (locked) {
      form.productPublicId = props.opportunityProductPublicId ?? ''
    } else {
      clearUnselectableProduct()
    }
  }
)

watch(
  () => productCatalog.loading.value,
  (loading) => {
    if (!loading) clearUnselectableProduct()
  }
)

watch(
  () => form.productPublicId,
  () => {
    errors.productPublicId = ''
  }
)

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
      form.authorizedUsers = getInitialAuthorizedUsers(form.contractId)
    }
    if (type === 'TRIAL') {
      form.contractId = ''
      form.isPermanent = false
    }
  }
)

watch(
  () => form.contractId,
  (contractId) => {
    if (form.licenseType === 'OFFICIAL' && contractId !== '') {
      form.authorizedUsers = getInitialAuthorizedUsers(contractId)
    }
  }
)

watch(
  () => [
    props.open,
    props.deployments.length,
    props.fixedContractId,
    props.defaultContractId,
    props.defaultLicenseType,
    props.opportunityProductPublicId,
    props.opportunityProductName,
  ] as const,
  ([open]) => {
    if (open) {
      closeGuard.reset()
      resetForm()
      void productCatalog.load()
    } else {
      if (closeGuard.handleParentClose()) return
      deploymentDialogOpen.value = false
      locallyCreatedDeployments.value = []
      clearErrors()
    }
  },
  { immediate: true }
)
</script>

<template>
  <Dialog :open="props.open" @update:open="handleOpenChange">
    <DialogContent size="lg" v-bind="elevated ? { elevated: true } : {}" class="license-application-form-dialog license-application-dialog">
      <DialogHeader>
        <DialogTitle>申请 License</DialogTitle>
        <DialogDescription>选择部署信息、License 类型和有效期，提交后进入审批流程。</DialogDescription>
      </DialogHeader>

      <div class="license-application-form-dialog__body">

      <form id="license-application-form" class="license-application-dialog__form" novalidate @submit.prevent="handleSubmit">
        <div class="license-application-dialog__grid">
          <SelectField
            id="license-deployment"
            v-model="form.deploymentId"
            class="license-application-dialog__field"
            label="部署信息"
            required
            :options="deploymentOptions"
            :placeholder="hasDeployments ? '请选择部署信息' : '请新增部署信息'"
            :disabled="submitting"
            :add-action-label="canCreateDeployment ? '新增部署信息' : ''"
            :add-action-disabled="submitting"
            :error="errors.deploymentId"
            @add="handleAddDeployment"
          />

          <div class="license-application-dialog__field">
            <p id="license-type-label" class="license-application-dialog__label license-application-dialog__label-row">
              License 类型
              <span class="license-application-dialog__required" aria-hidden="true">*</span>
            </p>
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

        <SelectField
          v-if="form.licenseType === 'OFFICIAL'"
          id="license-contract"
          v-model="form.contractId"
          class="license-application-dialog__field"
          label="关联合同"
          required
          :options="contractOptions"
          :placeholder="approvedContracts.length > 0 ? '请选择合同' : '暂无可关联的已签署合同'"
          :disabled="submitting || hasFixedContract || approvedContracts.length === 0"
          :error="errors.contractId"
          :title="selectedContractLabel || undefined"
          trigger-class="license-application-dialog__contract-trigger"
          content-class="license-application-dialog__contract-content"
        />

        <div class="license-application-dialog__field">
          <ProductIntentPicker
            v-model="form.productPublicId"
            id-prefix="license-product"
            :catalog="productCatalog"
            :locked="productLocked"
            :fallback-name="productFallbackName"
            :hint="productLocked ? LOCKED_PRODUCT_HINT : ''"
            :disabled="submitting"
            :invalid="errors.productPublicId !== ''"
          />
          <p
            v-if="errors.productPublicId !== ''"
            id="license-product-error"
            class="text-caption text-danger"
            role="alert"
          >
            {{ errors.productPublicId }}
          </p>
        </div>

        <div class="license-application-dialog__grid">
          <DateField
            id="license-expiry-date"
            class="license-application-dialog__field"
            label="到期日期"
            required
            :model-value="form.isPermanent ? null : parseLocalDate(form.expiryDate)"
            :placeholder="form.isPermanent ? '永久有效' : '请选择到期日期'"
            :disabled="submitting || form.isPermanent"
            :error="errors.expiryDate"
            @update:model-value="handleExpiryDateChange"
          >
            <template #label-action>
              <div v-if="form.licenseType === 'OFFICIAL'" class="license-application-dialog__permanent">
                <Switch
                  id="license-permanent"
                  size="sm"
                  :model-value="form.isPermanent"
                  :disabled="submitting"
                  @update:model-value="handlePermanentChange"
                />
                <Label for="license-permanent" class="license-application-dialog__label">永久</Label>
              </div>
              <FieldHelpTip v-else label="试用到期日期规则">{{ TRIAL_EXPIRY_REQUIRED_ERROR }}</FieldHelpTip>
            </template>
          </DateField>

          <InputField
            id="license-authorized-users"
            v-model="form.authorizedUsers"
            class="license-application-dialog__field"
            label="使用人数"
            required
            type="number"
            inputmode="numeric"
            min="1"
            step="1"
            placeholder="请输入使用人数"
            :disabled="submitting"
            :error="errors.authorizedUsers"
          />
        </div>

        <TextareaField
          id="license-remark"
          v-model="form.remark"
          class="license-application-dialog__field"
          label="备注"
          placeholder="请输入申请备注（可选）"
          :disabled="submitting"
        />

        </form>
      </div>


        <DialogFooter class="license-application-form-dialog__footer">
          <Button type="button" variant="outline" :disabled="submitting" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" form="license-application-form" :disabled="submitting || !hasDeployments || productBlocked">
            {{ submitting ? '提交中...' : '提交申请' }}
          </Button>
        </DialogFooter>
    </DialogContent>
  </Dialog>

  <DeploymentInfoFormDialog
    :customer-id="customerId"
    :open="deploymentDialogOpen"
    @update:open="deploymentDialogOpen = $event"
    @success="handleDeploymentSuccess"
  />
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.license-application-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $space-4;
}

.license-application-dialog__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $space-3;
}

.license-application-dialog__field {
  display: flex;
  flex-direction: column;
  gap: $space-1;
  min-width: 0;
}

.license-application-dialog__label {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.license-application-dialog__label-row {
  display: flex;
  align-items: center;
  height: 1.25rem;
}

.license-application-dialog__permanent {
  display: flex;
  align-items: center;
  gap: $space-1;
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

.license-application-dialog__required {
  color: hsl(var(--status-danger));
}

.license-application-dialog__footer {
  padding-top: $space-2;
}

@media (max-width: $bp-sm) {
  .license-application-dialog__grid {
    grid-template-columns: 1fr;
  }
}
</style>

<style lang="scss">
@use '@/styles/tokens.scss' as *;

/* 非 scoped：DialogContent 经 Portal 渲染，scoped data 属性不随 class 传递 */
.license-application-form-dialog {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  max-height: min(90vh, 90dvh);
  overflow: hidden;
}

.license-application-form-dialog__body {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: $space-4;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-inline: calc(2px + 2px);
  scroll-padding-bottom: calc($space-6 + var(--safe-bottom));
}
</style>
