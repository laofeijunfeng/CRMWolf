<template>
  <el-dialog
    v-model="visible"
    :title="application ? '编辑 License 申请' : '申请 License'"
    width="600px"
    :close-on-click-modal="false"
    destroy-on-close
    @close="handleClose"
  >
    <el-form ref="formRef" :model="formData" :rules="rules" label-width="120px">
      <el-form-item label="部署信息" prop="deployment_info_id">
        <el-select v-model="formData.deployment_info_id" placeholder="选择部署信息" style="width: 100%">
          <el-option
            v-for="d in deployments"
            :key="d.id"
            :label="d.deployment_name"
            :value="d.id"
          >
            <span>{{ d.deployment_name }}</span>
            <el-tag v-if="d.is_default" type="success" size="small" style="margin-left: 8px">默认</el-tag>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="License 类型" prop="license_type">
        <el-radio-group v-model="formData.license_type">
          <el-radio value="TRIAL">试用 License</el-radio>
          <el-radio value="OFFICIAL">正式 License</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="关联合同" prop="contract_id" v-if="formData.license_type === 'OFFICIAL'">
        <el-select
          v-model="formData.contract_id"
          placeholder="选择合同（正式 License 必选）"
          style="width: 100%"
          :loading="loadingContracts"
        >
          <el-option
            v-if="contracts.length === 0 && !loadingContracts"
            label="请在客户合同 Tab 中创建合同后选择"
            value=""
            disabled
          />
          <el-option
            v-for="c in contracts"
            :key="c.id"
            :label="c.contract_name"
            :value="c.id"
          >
            <span>{{ c.contract_name }}</span>
            <el-tag
              :type="c.status === 'EFFECTIVE' ? 'success' : 'primary'"
              size="small"
              style="margin-left: 8px"
            >
              {{ c.status === 'EFFECTIVE' ? '已生效' : '已签署' }}
            </el-tag>
          </el-option>
        </el-select>
        <div class="form-tip" v-if="contracts.length > 0">
          已自动选择最新审批通过的合同
        </div>
        <div class="form-tip" v-else>
          正式 License 必须关联合同
        </div>
      </el-form-item>
      <el-form-item label="到期时间" prop="expiry_date">
        <el-date-picker
          v-model="formData.expiry_date"
          type="date"
          placeholder="选择到期时间"
          style="width: 100%"
          :disabled-date="disabledDate"
        />
      </el-form-item>
      <el-form-item label="备注" prop="remark">
        <el-input v-model="formData.remark" type="textarea" :rows="3" placeholder="申请备注（可选）" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="loading">提交申请</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import licenseApplicationApi from '@/api/licenseApplication'
import contractApi from '@/api/contract'
import type { DeploymentInfo } from '@/schemas/deployment'
import type { LicenseApplication } from '@/schemas/licenseApplication'
import type { ContractListResponse } from '@/api/contract'
import { formatLocalDate } from '@/utils/format'

// Approved contract statuses (SIGNED = approved, EFFECTIVE = in effect)
const APPROVED_STATUSES = ['SIGNED', 'EFFECTIVE']

const props = defineProps<{
  visible: boolean
  customerId: number
  application?: LicenseApplication
  deployments: DeploymentInfo[]
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'success': []
}>()

const visible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
})

const formRef = ref<FormInstance>()
const loading = ref(false)

const formData = ref({
  customer_id: props.customerId,
  deployment_info_id: undefined as number | undefined,
  license_type: 'TRIAL' as 'TRIAL' | 'OFFICIAL',
  contract_id: undefined as number | undefined,
  expiry_date: '',
  remark: ''
})

// Fetch approved contracts for this customer
const contracts = ref<ContractListResponse[]>([])
const loadingContracts = ref(false)

const loadContracts = async (): void => {
  if (!props.customerId) return
  loadingContracts.value = true
  try {
    const allContracts = await contractApi.getCustomerContracts(props.customerId)
    // Filter only approved contracts (SIGNED or EFFECTIVE)
    contracts.value = allContracts.filter(c => APPROVED_STATUSES.includes(c.status))
  } catch {
    // Don't show error to user, just leave contracts empty
    contracts.value = []
  } finally {
    loadingContracts.value = false
  }
}

// Auto-select latest approved contract when switching to OFFICIAL
watch(() => formData.value.license_type, (newType): void => {
  if (newType === 'OFFICIAL' && formData.value.contract_id === undefined && contracts.value.length > 0) {
    // Sort by created_time descending and pick the latest
    const sortedContracts = [...contracts.value].sort((a, b) =>
      new Date(b.created_time).getTime() - new Date(a.created_time).getTime()
    )
    // sortedContracts[0] exists because contracts.value.length > 0
    const latestContract = sortedContracts[0]
    if (latestContract) {
      formData.value.contract_id = latestContract.id
    }
  }
})

// Load contracts when dialog opens
watch(() => props.visible, (visible): void => {
  if (visible) {
    loadContracts()
    // Auto-select default deployment info if exists and not editing
    if (!props.application) {
      const defaultDeployment = props.deployments.find(d => d.is_default)
      if (defaultDeployment !== undefined && formData.value.deployment_info_id === undefined) {
        formData.value.deployment_info_id = defaultDeployment.id
      }
    }
  }
})

const rules: FormRules = {
  deployment_info_id: [
    { required: true, message: '请选择部署信息', trigger: 'change' }
  ],
  license_type: [
    { required: true, message: '请选择 License 类型', trigger: 'change' }
  ],
  contract_id: [
    {
      validator: (_rule, value, callback): void => {
        if (formData.value.license_type === 'OFFICIAL' && value === undefined) {
          callback(new Error('正式 License 必须关联合同'))
        } else {
          callback()
        }
      },
      trigger: 'change'
    }
  ],
  expiry_date: [
    { required: true, message: '请选择到期时间', trigger: 'change' }
  ]
}

const disabledDate = (date: Date): boolean => {
  return date <= new Date()
}

// 格式化日期为 YYYY-MM-DD
const formatDate = (date: Date | string): string => {
  if (typeof date === 'string') {
    const parts = date.split('T')
    return parts[0] ?? ''
  }
  const d = new Date(date)
  return formatLocalDate(d)
}

watch(() => props.application, (val): void => {
  if (val) {
    formData.value = {
      customer_id: props.customerId,
      deployment_info_id: val.deployment_info_id ?? undefined,
      license_type: val.license_type,
      contract_id: val.contract_id ?? undefined,
      expiry_date: val.expiry_date !== null && val.expiry_date !== '' ? formatDate(val.expiry_date) : '',
      remark: val.remark ?? ''
    }
  } else {
    formData.value = {
      customer_id: props.customerId,
      deployment_info_id: undefined,
      license_type: 'TRIAL',
      contract_id: undefined,
      expiry_date: '',
      remark: ''
    }
  }
}, { immediate: true })

const handleSubmit = async (): void => {
  try {
    await formRef.value?.validate()
    loading.value = true

    // 转换日期格式并处理可选字段
    const submitData = {
      customer_id: formData.value.customer_id,
      deployment_info_id: formData.value.deployment_info_id ?? null,
      license_type: formData.value.license_type,
      contract_id: formData.value.contract_id ?? null,
      expiry_date: formData.value.expiry_date !== '' ? formatDate(formData.value.expiry_date) : '',
      remark: formData.value.remark ?? null
    }

    let applicationId: number

    if (props.application) {
      // 编辑模式：更新现有申请
      const updateData = {
        deployment_info_id: submitData.deployment_info_id,
        contract_id: submitData.contract_id,
        expiry_date: submitData.expiry_date,
        remark: submitData.remark
      }
      await licenseApplicationApi.updateApplication(props.application.id, updateData)
      applicationId = props.application.id
    } else {
      // 新建模式：创建申请
      const created = await licenseApplicationApi.create(submitData)
      applicationId = created.id
    }

    // 立即提交审批（一步完成）
    await licenseApplicationApi.submitApplication(applicationId)

    ElMessage.success('License 申请已提交，等待审批')
    emit('success')
  } catch (error) {
    if (error !== false) {
      const err = error as { message?: string }
      ElMessage.error(err.message ?? '操作失败')
    }
  } finally {
    loading.value = false
  }
}

const handleClose = (): void => {
  formRef.value?.resetFields()
}
</script>

<style scoped lang="scss">
.form-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
