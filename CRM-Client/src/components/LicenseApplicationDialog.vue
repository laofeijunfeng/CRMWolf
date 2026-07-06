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
      <el-form-item label="部署信息" prop="deployment_id">
        <el-select v-model="formData.deployment_id" placeholder="选择部署信息" style="width: 100%">
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
          <el-radio value="trial">试用 License</el-radio>
          <el-radio value="formal">正式 License</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="关联合同" prop="contract_id" v-if="formData.license_type === 'formal'">
        <el-select v-model="formData.contract_id" placeholder="选择合同（正式 License 必选）" style="width: 100%">
          <el-option label="请在客户合同 Tab 中创建合同后选择" value="" disabled />
          <!-- TODO: 需要从 API 加载客户合同列表 -->
        </el-select>
        <div class="form-tip">正式 License 必须关联合同</div>
      </el-form-item>
      <el-form-item label="到期时间" prop="license_expiry_date">
        <el-date-picker
          v-model="formData.license_expiry_date"
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
      <el-button type="primary" @click="handleSubmit" :loading="loading">保存草稿</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import licenseApplicationApi from '@/api/licenseApplication'
import type { DeploymentInfo, LicenseApplication, LicenseApplicationCreate } from '@/schemas/deployment'

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

const formData = ref<LicenseApplicationCreate>({
  customer_id: props.customerId,
  deployment_id: undefined as unknown as number,
  license_type: 'trial',
  contract_id: undefined,
  license_expiry_date: '',
  remark: ''
})

const rules: FormRules<LicenseApplicationCreate> = {
  deployment_id: [
    { required: true, message: '请选择部署信息', trigger: 'change' }
  ],
  license_type: [
    { required: true, message: '请选择 License 类型', trigger: 'change' }
  ],
  contract_id: [
    {
      validator: (rule, value, callback) => {
        if (formData.value.license_type === 'formal' && !value) {
          callback(new Error('正式 License 必须关联合同'))
        } else {
          callback()
        }
      },
      trigger: 'change'
    }
  ],
  license_expiry_date: [
    { required: true, message: '请选择到期时间', trigger: 'change' }
  ]
}

const disabledDate = (date: Date) => {
  return date <= new Date()
}

watch(() => props.application, (val) => {
  if (val) {
    formData.value = {
      customer_id: props.customerId,
      deployment_id: val.deployment_id,
      license_type: val.license_type,
      contract_id: val.contract_id,
      license_expiry_date: val.license_expiry_date,
      remark: val.remark || ''
    }
  } else {
    formData.value = {
      customer_id: props.customerId,
      deployment_id: undefined as unknown as number,
      license_type: 'trial',
      contract_id: undefined,
      license_expiry_date: '',
      remark: ''
    }
  }
}, { immediate: true })

const handleSubmit = async () => {
  try {
    await formRef.value?.validate()
    loading.value = true
    if (props.application) {
      await licenseApplicationApi.update(props.application.id, formData.value)
      ElMessage.success('编辑成功')
    } else {
      await licenseApplicationApi.create(formData.value)
      ElMessage.success('创建成功')
    }
    emit('success')
  } catch (error: any) {
    if (error !== false) {
      ElMessage.error(error.message || '操作失败')
    }
  } finally {
    loading.value = false
  }
}

const handleClose = () => {
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