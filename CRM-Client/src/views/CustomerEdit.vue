<template>
  <div class="customer-edit-page">
    <!-- 表单内容 -->
    <div class="form-container" v-loading="loading">
      <!-- 基本信息卡片 -->
      <div class="form-card">
        <div class="card-title">基本信息</div>
        <el-form
          :model="form"
          :rules="formRules"
          label-position="top"
          ref="formRef"
        >
          <div class="form-grid">
            <el-form-item label="客户名称" prop="account_name" required>
              <el-input
                v-model="form.account_name"
                placeholder="请输入客户公司名称"
              />
            </el-form-item>

            <el-form-item label="所在城市" prop="city" required>
              <el-input
                v-model="form.city"
                placeholder="请输入所在城市"
              />
            </el-form-item>
          </div>

          <div class="form-grid">
            <el-form-item label="客户来源" prop="source">
              <el-select
                v-model="form.source"
                placeholder="请选择客户来源"
                clearable
                style="width: 100%"
              >
                <el-option label="线上注册" value="线上注册" />
                <el-option label="市场活动" value="市场活动" />
                <el-option label="客户推荐" value="客户推荐" />
                <el-option label="电话营销" value="电话营销" />
                <el-option label="网站咨询" value="网站咨询" />
                <el-option label="展会" value="展会" />
                <el-option label="其他" value="其他" />
                <el-option label="线索转化" value="线索转化" />
              </el-select>
            </el-form-item>

            <el-form-item label="公司规模" prop="company_scale">
              <el-select
                v-model="form.company_scale"
                placeholder="请选择公司规模"
                clearable
                style="width: 100%"
              >
                <el-option label="1-50人" value="1-50人" />
                <el-option label="51-200人" value="51-200人" />
                <el-option label="201-500人" value="201-500人" />
                <el-option label="501-1000人" value="501-1000人" />
                <el-option label="1000人以上" value="1000人以上" />
              </el-select>
            </el-form-item>
          </div>

          <div class="form-grid">
            <el-form-item label="默认采购方式" prop="default_procurement_method_id">
              <el-select
                v-model="form.default_procurement_method_id"
                placeholder="请选择默认采购方式"
                clearable
                style="width: 100%"
              >
                <el-option
                  v-for="option in procurementMethodOptions"
                  :key="option.id"
                  :label="option.name"
                  :value="option.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="公司地址" prop="address">
              <el-input
                v-model="form.address"
                placeholder="请输入公司地址"
              />
            </el-form-item>
          </div>
        </el-form>
      </div>

      <!-- 客户档案卡片（仅编辑模式显示） -->
      <div v-if="isEdit && hasProfile" class="form-card">
        <div class="card-title">
          <span>客户档案</span>
          <el-tag size="small" :type="profileStatusType">{{ profileStatusText }}</el-tag>
        </div>

        <el-form label-position="top">
          <div class="form-grid">
            <el-form-item label="公司官网">
              <el-input
                v-model="form.company_website"
                placeholder="请输入公司官网地址"
              />
            </el-form-item>
          </div>

          <div class="form-section">
            <el-form-item label="企业背景">
              <el-input
                v-model="form.company_background"
                type="textarea"
                :rows="4"
                placeholder="请输入企业背景介绍"
              />
            </el-form-item>
          </div>

          <div class="form-section">
            <el-form-item label="主营业务">
              <el-input
                v-model="form.main_business"
                type="textarea"
                :rows="4"
                placeholder="请输入主营业务描述"
              />
            </el-form-item>
          </div>

          <div class="form-section">
            <el-form-item label="项目需求背景">
              <el-input
                v-model="form.project_background"
                type="textarea"
                :rows="4"
                placeholder="请输入项目需求背景"
              />
            </el-form-item>
          </div>
        </el-form>
      </div>

      <!-- 表单操作 -->
      <div class="form-actions-card">
        <el-button @click="handleGoBack">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { showError, showSuccess } from '@/utils/errorMessages'
import customerApi, { type CustomerCreate, type CustomerUpdate } from '@/api/customer'
import procurementApi, { type ProcurementMethodOption } from '@/api/procurement'
import { usePageTitle } from '@/composables/usePageTitle'
import { useHeaderStore } from '@/stores/header'

usePageTitle()

const router = useRouter()
const route = useRoute()
const headerStore = useHeaderStore()

onMounted(() => {
  headerStore.setBack(true)
})

onUnmounted(() => {
  headerStore.clear()
})

const loading = ref(false)
const submitting = ref(false)
const formRef = ref()
const procurementMethodOptions = ref<ProcurementMethodOption[]>([])

const customerId = computed(() => Number(route.params.id))
const isEdit = computed(() => !!customerId.value)

// 档案状态相关
const profileStatus = ref<string | null>(null)
const hasProfile = computed(() => profileStatus.value === 'COMPLETED')
const profileStatusType = computed(() => {
  switch (profileStatus.value) {
    case 'COMPLETED': return 'success'
    case 'GENERATING': return 'warning'
    case 'PENDING': return 'info'
    case 'FAILED': return 'danger'
    default: return 'info'
  }
})
const profileStatusText = computed(() => {
  switch (profileStatus.value) {
    case 'COMPLETED': return '已生成'
    case 'GENERATING': return '生成中'
    case 'PENDING': return '待生成'
    case 'FAILED': return '生成失败'
    default: return '未生成'
  }
})

const form = reactive({
  account_name: '',
  city: '',
  address: '',
  company_scale: '',
  source: '',
  default_procurement_method_id: undefined as number | undefined,
  // 档案字段
  company_background: '',
  company_website: '',
  main_business: '',
  project_background: ''
})

const formRules = {
  account_name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }],
  city: [{ required: true, message: '请输入所在城市', trigger: 'blur' }]
}

const fetchCustomerDetail = async () => {
  if (!isEdit.value) return

  loading.value = true
  try {
    const res = await customerApi.getCustomerDetail(customerId.value)
    Object.assign(form, {
      account_name: res.account_name || '',
      city: res.city || '',
      address: res.address || '',
      company_scale: res.company_scale || '',
      source: res.source || '',
      default_procurement_method_id: res.default_procurement_method_id || undefined,
      // 档案字段
      company_background: res.company_background || '',
      company_website: res.company_website || '',
      main_business: res.main_business || '',
      project_background: res.project_background || ''
    })
    profileStatus.value = res.profile_status
  } catch (error: unknown) {
    showError(error, '获取客户详情')
    router.back()
  } finally {
    loading.value = false
  }
}

const fetchOptions = async () => {
  try {
    const procurementRes = await procurementApi.getProcurementMethodOptions()
    procurementMethodOptions.value = procurementRes || []
  } catch (error) {
    console.error('获取选项失败:', error)
  }
}

const handleSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    if (isEdit.value) {
      const updateData: CustomerUpdate = {
        account_name: form.account_name || undefined,
        city: form.city || undefined,
        address: form.address || undefined,
        company_scale: form.company_scale || undefined,
        source: form.source || undefined,
        default_procurement_method_id: form.default_procurement_method_id || undefined,
        // 档案字段
        company_background: form.company_background || undefined,
        company_website: form.company_website || undefined,
        main_business: form.main_business || undefined,
        project_background: form.project_background || undefined
      }
      await customerApi.updateCustomer(customerId.value, updateData)
      showSuccess('更新', '客户')
    } else {
      const createData: CustomerCreate = {
        account_name: form.account_name,
        city: form.city,
        address: form.address || undefined,
        company_scale: form.company_scale || undefined,
        source: form.source || undefined,
        default_procurement_method_id: form.default_procurement_method_id || undefined
      }
      await customerApi.createCustomer(createData)
      showSuccess('创建', '客户')
    }
    router.back()
  } catch (error: unknown) {
    showError(error, isEdit.value ? '更新客户' : '创建客户')
  } finally {
    submitting.value = false
  }
}

const handleGoBack = () => {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/customers')
  }
}

onMounted(async () => {
  await fetchOptions()
  if (isEdit.value) {
    await fetchCustomerDetail()
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.customer-edit-page {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 表单容器（撑满页面宽度）
.form-container {
  padding: $wolf-page-padding;
}

// 表单卡片（撑满页面宽度）
.form-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-md;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;
}

// 表单网格（两列布局）
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $wolf-space-md;
}

.form-section {
  margin-bottom: $wolf-space-md;
}

// 表单操作卡片
.form-actions-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
}

// 表单标签样式
:deep(.el-form-item__label) {
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-body;
  padding-bottom: $wolf-space-xs;
}

// 输入框样式
:deep(.el-input__wrapper),
:deep(.el-textarea__inner) {
  border-radius: $wolf-radius-md;
  transition: all 0.2s ease;

  &:hover {
    border-color: $wolf-border-hover;
  }

  &.is-focus,
  &:focus {
    border-color: $wolf-primary;
    box-shadow: 0 0 0 2px rgba($wolf-primary, 0.1);
  }
}

// 响应式
@media (max-width: 768px) {
  .form-container {
    padding: $wolf-space-md;
  }

  .form-card {
    padding: $wolf-space-md;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-actions-card {
    flex-direction: column-reverse;

    .el-button {
      width: 100%;
    }
  }
}
</style>