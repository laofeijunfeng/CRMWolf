<template>
  <div class="opportunity-edit-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="wolf-page-title">{{ isEdit ? '编辑商机' : '新建商机' }}</h1>
      </div>
    </div>

    <!-- 表单内容 -->
    <div class="form-container">
      <div class="form-card">
        <div class="card-title">基本信息</div>
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          v-loading="loading"
        >
          <div class="form-grid">
            <!-- 从客户创建：显示 disabled 输入框 -->
            <el-form-item v-if="fromCustomer" label="客户">
              <el-input
                :model-value="customerInfo?.account_name || ''"
                disabled
              />
            </el-form-item>

            <!-- 独立创建：显示客户搜索下拉 -->
            <el-form-item v-else prop="customer_id" label="客户" required>
              <el-select
                v-model="form.customer_id"
                filterable
                remote
                placeholder="搜索或选择客户"
                :remote-method="searchCustomers"
                :loading="customerLoading"
                style="width: 100%"
              >
                <el-option
                  v-for="item in customerOptions"
                  :key="item.id"
                  :label="item.account_name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item prop="opportunity_name" label="商机名称" required>
              <el-input
                v-model="form.opportunity_name"
                placeholder="请输入商机名称"
              />
            </el-form-item>
          </div>

          <div class="form-grid">
            <el-form-item prop="total_amount" label="预计总金额" required>
              <el-input-number
                v-model="form.total_amount"
                placeholder="请输入预计总金额"
                :min="0"
                :precision="2"
                :controls="false"
                style="width: 100%"
              >
                <template #prefix>¥</template>
              </el-input-number>
            </el-form-item>

            <el-form-item prop="user_count" label="采购用户数" required>
              <el-input-number
                v-model="form.user_count"
                placeholder="请输入采购用户数"
                :min="1"
                :precision="0"
                :controls="false"
                style="width: 100%"
              />
            </el-form-item>
          </div>

          <div class="form-grid">
            <el-form-item prop="license_type" label="授权模式" required>
              <el-select v-model="form.license_type" placeholder="请选择授权模式" style="width: 100%">
                <el-option value="SUBSCRIPTION" label="订阅制" />
                <el-option value="PERPETUAL" label="买断制" />
              </el-select>
            </el-form-item>

            <el-form-item v-if="form.license_type === 'SUBSCRIPTION'" prop="subscription_years" label="订阅年限" required>
              <el-input-number
                v-model="form.subscription_years"
                placeholder="请输入订阅年限"
                :min="1"
                :max="10"
                :precision="0"
                :controls="false"
                style="width: 100%"
              >
                <template #append>年</template>
              </el-input-number>
            </el-form-item>
          </div>

          <div class="form-grid">
            <el-form-item prop="purchase_type" label="采购类型" required>
              <el-select v-model="form.purchase_type" placeholder="请选择采购类型" style="width: 100%">
                <el-option value="NEW" label="新购" />
                <el-option value="RENEWAL" label="续购" />
                <el-option value="EXPANSION" label="增购" />
              </el-select>
            </el-form-item>

            <el-form-item prop="expected_closing_date" label="预计成交日期" required>
              <el-date-picker
                v-model="form.expected_closing_date"
                style="width: 100%"
                placeholder="请选择预计成交日期"
              />
            </el-form-item>
          </div>

          <div class="form-grid">
            <el-form-item label="采购方式">
              <el-select
                v-model="form.procurement_method_id"
                placeholder="请选择采购方式"
                clearable
                style="width: 100%"
                @change="handleProcurementMethodChange"
              >
                <el-option
                  v-for="method in procurementMethods"
                  :key="method.id"
                  :value="method.id"
                  :label="method.name"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="负责人">
              <el-input :model-value="userStore.userInfo?.name || ''" placeholder="当前登录用户" disabled />
              <div class="form-tip">默认为当前登录用户</div>
            </el-form-item>
          </div>
        </el-form>
      </div>

      <!-- 表单操作 -->
      <div class="form-actions-card">
        <el-button @click="handleBack">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { showError, showSuccess } from '@/utils/errorMessages'
import { ArrowLeft } from '@element-plus/icons-vue'
import { opportunityApi, PurchaseType, LicenseType, type Opportunity } from '@/api/opportunity'
import customerApi from '@/api/customer'
import procurementApi, { type ProcurementMethod } from '@/api/procurement'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref()
const loading = ref(false)
const submitting = ref(false)
const customerLoading = ref(false)
const customerOptions = ref<any[]>([])
const customerInfo = ref<any>(null)
const procurementMethods = ref<ProcurementMethod[]>([])

const fromCustomer = computed(() => !!route.params.customerId)
const customerId = computed(() => route.params.customerId as string | undefined)
const opportunityId = computed(() => route.params.id as string | undefined)
const isEdit = computed(() => !!opportunityId.value)

const form = reactive({
  opportunity_name: '',
  customer_id: 0,
  total_amount: undefined as number | undefined,
  user_count: undefined as number | undefined,
  license_type: 'SUBSCRIPTION' as LicenseType,
  subscription_years: undefined as number | undefined,
  purchase_type: 'NEW' as PurchaseType,
  expected_closing_date: '',
  procurement_method_id: undefined as number | undefined,
  owner_id: userStore.userInfo?.id ? String(userStore.userInfo.id) : ''
})

const handleProcurementMethodChange = async (methodId: number | undefined) => {
  // 可以在这里添加其他逻辑，例如记录用户选择等
}

const rules = {
  customer_id: [{ required: true, message: '请选择客户', trigger: 'change' }],
  opportunity_name: [{ required: true, message: '请输入商机名称', trigger: 'blur' }],
  total_amount: [{ required: true, message: '请输入预计总金额', trigger: 'blur' }],
  user_count: [{ required: true, message: '请输入采购用户数', trigger: 'blur' }],
  license_type: [{ required: true, message: '请选择授权模式', trigger: 'change' }],
  subscription_years: [
    {
      required: true,
      validator: (rule: unknown, value: unknown, callback: (error?: Error) => void) => {
        if (form.license_type === 'SUBSCRIPTION' && !value) {
          callback(new Error('订阅制时必须填写订阅年限'))
        } else {
          callback()
        }
      }
    }
  ],
  purchase_type: [{ required: true, message: '请选择采购类型', trigger: 'change' }],
  expected_closing_date: [{ required: true, message: '请选择预计成交日期', trigger: 'change' }]
}

const fetchProcurementMethods = async () => {
  try {
    const data = await procurementApi.getProcurementMethods({ is_active: 1 })
    procurementMethods.value = data.filter((m: ProcurementMethod) => m.is_active === 1)
      .sort((a: ProcurementMethod, b: ProcurementMethod) => a.sort_order - b.sort_order)
  } catch (error) {
    console.error('获取采购方式失败', error)
  }
}

const fetchCustomerOptions = async () => {
  try {
    const data = await customerApi.getCustomers({ limit: 100 })
    customerOptions.value = data || []
  } catch (error) {
    console.error('获取客户列表失败', error)
  }
}

const searchCustomers = async (query: string) => {
  if (!query) {
    customerOptions.value = []
    return
  }
  customerLoading.value = true
  try {
    const data = await customerApi.getCustomers({ keyword: query, limit: 20 })
    customerOptions.value = data || []
  } catch (error) {
    console.error('搜索客户失败', error)
    customerOptions.value = []
  } finally {
    customerLoading.value = false
  }
}

const fetchCustomerInfo = async (id: string, setDefaults: boolean = false) => {
  loading.value = true
  try {
    const data = await customerApi.getCustomerDetail(Number(id))
    customerInfo.value = data

    if (setDefaults) {
      form.customer_id = data.id
      form.opportunity_name = `${data.account_name}项目`
      form.total_amount = data.default_opportunity?.total_amount || undefined
      form.user_count = data.default_opportunity?.user_count || undefined
      form.license_type = data.default_opportunity?.license_type || 'SUBSCRIPTION'
      form.subscription_years = data.default_opportunity?.subscription_years || undefined
      form.purchase_type = data.default_opportunity?.purchase_type || 'NEW'
      form.expected_closing_date = data.default_opportunity?.expected_closing_date || ''

      // 使用客户的默认采购方式
      if (data.default_procurement_method_id) {
        form.procurement_method_id = data.default_procurement_method_id
        await handleProcurementMethodChange(data.default_procurement_method_id)
      } else if (data.default_opportunity?.procurement_method_id) {
        form.procurement_method_id = data.default_opportunity.procurement_method_id
        await handleProcurementMethodChange(data.default_opportunity.procurement_method_id)
      }
    }
  } catch (error) {
    console.error('获取客户信息失败', error)
    showError(error, '获取客户信息')
  } finally {
    loading.value = false
  }
}

const fetchOpportunityDetail = async (id: string) => {
  loading.value = true
  try {
    const data = await opportunityApi.getOpportunityDetail(Number(id))
    Object.assign(form, {
      opportunity_name: data.opportunity_name,
      customer_id: data.customer_id || 0,
      total_amount: data.total_amount,
      user_count: data.user_count,
      license_type: data.license_type,
      subscription_years: data.subscription_years,
      purchase_type: data.purchase_type,
      expected_closing_date: data.expected_closing_date,
      procurement_method_id: data.procurement_method_id
    })

    if (data.customer_id) {
      await fetchCustomerInfo(data.customer_id)
    }

    if (data.procurement_method_id) {
      await handleProcurementMethodChange(data.procurement_method_id)
    }
  } catch (error) {
    console.error('获取商机详情失败', error)
    showError(error, '获取商机详情')
    router.back()
  } finally {
    loading.value = false
  }
}

const handleBack = () => {
  if (fromCustomer.value && customerId.value) {
    router.push(`/customers/${customerId.value}`)
  } else if (isEdit.value && opportunityId.value) {
    router.push(`/opportunities/${opportunityId.value}`)
  } else {
    router.push('/opportunities')
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
    const data = {
      opportunity_name: form.opportunity_name,
      customer_id: fromCustomer.value ? Number(customerId.value) : form.customer_id,
      total_amount: form.total_amount!,
      user_count: form.user_count!,
      license_type: form.license_type,
      subscription_years: form.license_type === 'SUBSCRIPTION' ? form.subscription_years : null,
      purchase_type: form.purchase_type,
      expected_closing_date: new Date(form.expected_closing_date).toISOString().split('T')[0],
      procurement_method_id: form.procurement_method_id,
      owner_id: form.owner_id
    }

    let result
    if (isEdit.value && opportunityId.value) {
      result = await opportunityApi.updateOpportunity(Number(opportunityId.value), data)
      showSuccess('更新', '商机')
    } else {
      result = await opportunityApi.createOpportunity(data)
      showSuccess('创建', '商机')
    }

    router.push(`/opportunities/${result.id}`)
  } catch (error: unknown) {
    console.error('提交失败', error)

    if (error.errors) {
      ElMessage.warning('请检查表单填写是否完整')
      return
    }

    showError(error, isEdit.value ? '更新商机' : '创建商机')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    fetchProcurementMethods()
  ])

  if (isEdit.value && opportunityId.value) {
    await fetchOpportunityDetail(opportunityId.value)
  } else if (fromCustomer.value && customerId.value) {
    await fetchCustomerInfo(customerId.value, true)
  } else {
    await fetchCustomerOptions()
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.opportunity-edit-page {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 页面标题（sticky）
.page-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: $wolf-bg-card;
  border-bottom: 1px solid $wolf-border-default;
  height: $wolf-header-height;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 $wolf-page-padding;
}

.page-header-left {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.back-btn {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: $wolf-radius-md !important;
  background: transparent !important;
  border: none !important;

  &:hover {
    background: $wolf-bg-hover !important;
  }
}

.page-title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
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

.section-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-md;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-md;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;
}

// 表单网格
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $wolf-space-md;
}

.form-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-top: $wolf-space-xs;
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