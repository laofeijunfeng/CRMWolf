<template>
  <el-dialog
    v-model="visible"
    :title="deployment ? '编辑部署信息' : '新增部署信息'"
    width="500px"
    :close-on-click-modal="false"
    destroy-on-close
    @close="handleClose"
  >
    <el-form ref="formRef" :model="formData" :rules="rules" label-width="120px">
      <el-form-item label="部署名称" prop="deployment_name">
        <el-input v-model="formData.deployment_name" placeholder="如：生产环境、测试环境" maxlength="100" />
      </el-form-item>
      <el-form-item label="服务器地址" prop="server_address">
        <el-input v-model="formData.server_address" placeholder="https://crm.example.com:8891" maxlength="500" />
        <div class="form-tip">服务器地址必须以 http:// 或 https:// 开头</div>
      </el-form-item>
      <el-form-item label="授权人数" prop="authorized_users">
        <el-input-number v-model="formData.authorized_users" :min="1" :max="9999" placeholder="授权用户数量" />
      </el-form-item>
      <el-form-item label="是否默认">
        <el-switch v-model="formData.is_default" />
      </el-form-item>
      <el-form-item label="描述" prop="description">
        <el-input v-model="formData.description" type="textarea" :rows="3" placeholder="部署信息描述（可选）" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="loading">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import deploymentApi from '@/api/deployment'
import type { DeploymentInfo, DeploymentInfoCreate } from '@/schemas/deployment'

const props = defineProps<{
  visible: boolean
  customerId: number
  deployment?: DeploymentInfo
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

const formData = ref<DeploymentInfoCreate>({
  deployment_name: '',
  server_address: '',
  authorized_users: 1,
  is_default: false,
  description: '',
  customer_id: props.customerId
})

const rules: FormRules<DeploymentInfoCreate> = {
  deployment_name: [
    { required: true, message: '请输入部署名称', trigger: 'blur' },
    { max: 100, message: '部署名称不能超过 100 个字符', trigger: 'blur' }
  ],
  server_address: [
    { required: true, message: '请输入服务器地址', trigger: 'blur' },
    { pattern: /^https?:\/\/.+/, message: '服务器地址必须以 http:// 或 https:// 开头', trigger: 'blur' },
    { max: 500, message: '服务器地址不能超过 500 个字符', trigger: 'blur' }
  ],
  authorized_users: [
    { required: true, message: '请输入授权人数', trigger: 'blur' },
    { type: 'number', min: 1, message: '授权人数必须大于 0', trigger: 'blur' }
  ]
}

watch(() => props.deployment, (val) => {
  if (val) {
    formData.value = {
      deployment_name: val.deployment_name,
      server_address: val.server_address,
      authorized_users: val.authorized_users,
      is_default: val.is_default,
      description: val.description || '',
      customer_id: props.customerId
    }
  } else {
    formData.value = {
      deployment_name: '',
      server_address: '',
      authorized_users: 1,
      is_default: false,
      description: '',
      customer_id: props.customerId
    }
  }
}, { immediate: true })

const handleSubmit = async () => {
  try {
    await formRef.value?.validate()
    loading.value = true
    if (props.deployment) {
      await deploymentApi.update(props.deployment.id, formData.value)
      ElMessage.success('编辑成功')
    } else {
      await deploymentApi.create(formData.value)
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