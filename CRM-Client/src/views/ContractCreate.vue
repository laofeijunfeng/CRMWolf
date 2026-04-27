<template>
  <div class="contract-create-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="page-title">{{ pageTitle }}</h1>
      </div>
    </div>

    <!-- 表单区 -->
    <div class="form-container">
      <div class="form-card">
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <div class="form-grid">
            <el-form-item prop="contract_name" label="合同名称">
              <el-input v-model="form.contract_name" placeholder="请输入合同名称" />
            </el-form-item>

            <el-form-item v-if="!isFromOpportunity && !isFromCustomer" prop="customer_id" label="关联客户">
              <el-select v-model="form.customer_id" placeholder="请选择客户" filterable>
                <el-option v-for="customer in customerList" :key="customer.id" :value="customer.id" :label="customer.account_name" />
              </el-select>
            </el-form-item>
            <el-form-item v-else label="关联客户">
              <el-input :model-value="opportunityInfo?.customer_info?.account_name || customerInfo?.account_name" disabled />
            </el-form-item>
          </div>

          <div class="form-grid">
            <el-form-item v-if="!isFromOpportunity" prop="opportunity_id" label="关联商机">
              <el-select v-model="form.opportunity_id" placeholder="请选择商机" filterable>
                <el-option v-for="opp in opportunityList" :key="opp.id" :value="opp.id" :label="opp.opportunity_name" />
              </el-select>
              <div v-if="isFromCustomer" class="form-extra">
                <el-icon><InfoFilled /></el-icon>
                只显示跟进中且未创建合同的商机
              </div>
            </el-form-item>
            <el-form-item v-else label="关联商机">
              <el-input :model-value="opportunityInfo?.opportunity_name" disabled />
            </el-form-item>

            <el-form-item prop="signing_contact_id" label="签约人">
              <el-select v-model="form.signing_contact_id" placeholder="请选择签约人" filterable>
                <el-option v-for="contact in contactList" :key="contact.id" :value="contact.id" :label="`${contact.name} (${contact.mobile})`" />
              </el-select>
            </el-form-item>
          </div>

          <div class="form-grid">
            <el-form-item prop="user_count" label="采购用户数">
              <el-input-number
                v-model="form.user_count"
                :min="1"
                placeholder="请输入用户数"
                style="width: 100%"
              />
              <template v-if="isFromOpportunity">
                <div class="form-extra form-extra--success">
                  <el-icon><CircleCheckFilled /></el-icon>
                  从商机自动填充，可修改
                </div>
              </template>
            </el-form-item>

            <el-form-item prop="total_amount" label="合同总金额（元）">
              <el-input-number
                v-model="form.total_amount"
                :min="0"
                :precision="2"
                placeholder="请输入总金额"
                style="width: 100%"
              >
                <template #prefix>¥</template>
              </el-input-number>
              <template v-if="isFromOpportunity">
                <div class="form-extra form-extra--success">
                  <el-icon><CircleCheckFilled /></el-icon>
                  从商机自动填充，可修改
                </div>
              </template>
            </el-form-item>
          </div>

          <div class="form-grid">
            <el-form-item prop="license_type" label="授权模式">
              <el-select v-model="form.license_type" placeholder="请选择授权模式">
                <el-option value="SUBSCRIPTION" label="订阅" />
                <el-option value="PERPETUAL" label="买断" />
              </el-select>
              <template v-if="isFromOpportunity">
                <div class="form-extra form-extra--success">
                  <el-icon><CircleCheckFilled /></el-icon>
                  从商机自动填充，可修改
                </div>
              </template>
            </el-form-item>

            <el-form-item v-if="form.license_type === 'SUBSCRIPTION'" prop="subscription_years" label="订阅年限">
              <el-input-number
                v-model="form.subscription_years"
                :min="1"
                placeholder="请输入订阅年限"
                style="width: 100%"
              />
              <template v-if="isFromOpportunity">
                <div class="form-extra form-extra--success">
                  <el-icon><CircleCheckFilled /></el-icon>
                  从商机自动填充，可修改
                </div>
              </template>
            </el-form-item>
          </div>

          <div class="form-grid">
            <el-form-item prop="signing_date" label="签署日期">
              <el-date-picker
                v-model="form.signing_date"
                type="date"
                style="width: 100%"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                placeholder="请选择签署日期"
              />
              <template v-if="isFromOpportunity && opportunityInfo?.actual_closing_date">
                <div class="form-extra form-extra--success">
                  <el-icon><CircleCheckFilled /></el-icon>
                  从商机的实际成交日期自动填充
                </div>
              </template>
              <template v-else-if="isFromOpportunity && opportunityInfo?.expected_closing_date">
                <div class="form-extra form-extra--success">
                  <el-icon><CircleCheckFilled /></el-icon>
                  从商机的预计成交日期自动填充
                </div>
              </template>
            </el-form-item>

            <el-form-item prop="effective_date" label="生效日期">
              <el-date-picker
                v-model="form.effective_date"
                type="date"
                style="width: 100%"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                placeholder="请选择生效日期"
              />
              <div class="form-extra">
                <el-icon><InfoFilled /></el-icon>
                通常为签署日期当天或之后
              </div>
            </el-form-item>
          </div>
        </el-form>

        <div class="form-actions">
          <el-button @click="handleBack">取消</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="submitting">
            提交
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { ArrowLeft, CircleCheckFilled, InfoFilled } from '@element-plus/icons-vue'
import contractApi, { type ContractCreate } from '@/api/contract'
import customerApi from '@/api/customer'
import { opportunityApi, type Opportunity } from '@/api/opportunity'

const router = useRouter()
const route = useRoute()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const customerList = ref<any[]>([])
const opportunityList = ref<any[]>([])
const contactList = ref<any[]>([])
const opportunityInfo = ref<Opportunity | null>(null)
const customerInfo = ref<any>(null)

const isFromOpportunity = computed(() => {
  return !!route.query.opportunityId
})

const isFromCustomer = computed(() => {
  return !!route.query.customerId
})

const pageTitle = computed(() => {
  if (isFromOpportunity.value) {
    return '从商机创建合同'
  } else if (isFromCustomer.value && customerInfo.value) {
    return `为 ${customerInfo.value.account_name} 创建合同`
  } else if (isFromCustomer.value) {
    return '为客户创建合同'
  } else {
    return '新建合同'
  }
})

const form = reactive<ContractCreate>({
  contract_name: '',
  customer_id: 0,
  opportunity_id: undefined as any,
  signing_contact_id: undefined as any,
  user_count: 0,
  total_amount: 0,
  license_type: 'SUBSCRIPTION',
  subscription_years: null,
  signing_date: '',
  effective_date: ''
})

const rules: FormRules<ContractCreate> = {
  contract_name: [{ required: true, message: '请输入合同名称' }],
  customer_id: [{ required: true, message: '请选择客户' }],
  opportunity_id: [{ required: true, message: '请选择商机' }],
  signing_contact_id: [{ required: true, message: '请选择签约人' }],
  user_count: [{ required: true, message: '请输入采购用户数' }],
  total_amount: [{ required: true, message: '请输入合同总金额' }],
  license_type: [{ required: true, message: '请选择授权模式' }],
  subscription_years: [
    {
      validator: (rule, value, callback) => {
        if (form.license_type === 'SUBSCRIPTION' && !value) {
          callback(new Error('订阅制时必须填写订阅年限'))
        } else {
          callback()
        }
      },
      trigger: 'change'
    }
  ]
}

const fetchCustomerList = async () => {
  try {
    const data = await customerApi.getCustomers({ limit: 100 }) as unknown as any[]
    customerList.value = data
  } catch (error) {
    console.error('获取客户列表失败', error)
  }
}

const fetchOpportunityList = async () => {
  try {
    const data = await opportunityApi.getOpportunities({ limit: 100 }) as unknown as Opportunity[]
    opportunityList.value = data
  } catch (error) {
    console.error('获取商机列表失败', error)
  }
}

const fetchOpportunityListForCustomer = async (customerId: number) => {
  try {
    const data = await opportunityApi.getAvailableForContract(customerId)
    opportunityList.value = data as unknown as Opportunity[]
  } catch (error) {
    console.error('获取客户商机列表失败', error)
  }
}

const fetchOpportunityInfo = async (opportunityId: string) => {
  try {
    const data = await opportunityApi.getOpportunity(Number(opportunityId)) as unknown as Opportunity
    opportunityInfo.value = data
    
    form.customer_id = data.customer_id
    form.opportunity_id = data.id
    form.total_amount = Number(data.total_amount)
    form.license_type = data.license_type as any
    form.subscription_years = data.subscription_years
    
    form.user_count = data.user_count || 0
    
    if (data.opportunity_name) {
      form.contract_name = `${data.opportunity_name}-合同`
    }
    
    if (data.actual_closing_date) {
      form.signing_date = data.actual_closing_date
    } else if (data.expected_closing_date) {
      form.signing_date = data.expected_closing_date
    }
    
    await fetchContacts(data.customer_id)
  } catch (error) {
    console.error('获取商机信息失败', error)
    ElMessage.error('获取商机信息失败')
  }
}

const fetchContacts = async (customerId: number) => {
  try {
    const data = await customerApi.getContacts(customerId) as unknown as any[]
    contactList.value = data.filter(contact => contact && contact.id > 0)
  } catch (error) {
    console.error('获取联系人列表失败', error)
  }
}

const handleSubmit = async () => {
  if (!formRef.value) return
  
  try {
    await formRef.value.validate()
    
    submitting.value = true
    
    const submitData: any = {
      contract_name: form.contract_name,
      customer_id: form.customer_id,
      signing_contact_id: form.signing_contact_id,
      user_count: form.user_count,
      total_amount: form.total_amount,
      license_type: form.license_type
    }

    if (form.opportunity_id) {
      submitData.opportunity_id = form.opportunity_id
    }
    
    if (form.license_type === 'SUBSCRIPTION') {
      submitData.subscription_years = form.subscription_years
    }
    
    if (form.signing_date) {
      submitData.signing_date = form.signing_date
    }
    
    if (form.effective_date) {
      submitData.effective_date = form.effective_date
    }
    
    if (isFromOpportunity.value) {
      await contractApi.createContractFromOpportunity(form.opportunity_id, {
        contract_name: form.contract_name,
        signing_contact_id: form.signing_contact_id
      })
    } else {
      await contractApi.createContract(submitData)
    }
    
    ElMessage.success('创建成功')
    router.push('/contracts')
  } catch (error: any) {
    console.error('创建合同失败', error)
    if (error.errors) {
      return
    }
    ElMessage.error(error.response?.data?.detail || error.message || '创建失败')
  } finally {
    submitting.value = false
  }
}

const fetchCustomerInfo = async (customerId: string) => {
  try {
    const data = await customerApi.getCustomerDetail(Number(customerId)) as any
    customerInfo.value = data
    form.customer_id = data.id
  } catch (error) {
    console.error('获取客户信息失败', error)
  }
}

const handleBack = () => {
  router.back()
}

watch(() => form.opportunity_id, async (newOpportunityId: number) => {
  if (newOpportunityId && !isFromOpportunity.value) {
    const opportunity = opportunityList.value.find(opp => opp.id === newOpportunityId)
    if (opportunity) {
      form.total_amount = Number(opportunity.total_amount || 0)
      form.user_count = opportunity.user_count || 0
      form.license_type = opportunity.license_type as any
      form.subscription_years = opportunity.subscription_years

      if (opportunity.customer_id) {
        form.customer_id = opportunity.customer_id
        await fetchContacts(opportunity.customer_id)
      }
    }
  }
})

onMounted(async () => {
  if (isFromOpportunity.value) {
    const opportunityId = route.query.opportunityId as string
    await fetchOpportunityInfo(opportunityId)
  } else if (isFromCustomer.value) {
    const customerId = route.query.customerId as string
    await fetchCustomerInfo(customerId)
    await fetchOpportunityListForCustomer(Number(customerId))
    await fetchContacts(Number(customerId))
  } else {
    fetchCustomerList()
    fetchOpportunityList()
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.contract-create-page {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 页面头部（sticky）
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

// 表单容器
.form-container {
  max-width: 800px;
  margin: 0 auto;
  padding: $wolf-page-padding;
}

.form-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  padding: $wolf-card-padding;
  box-shadow: $wolf-shadow-card;
}

// 表单网格
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $wolf-space-md;
  margin-bottom: $wolf-space-md;
}

.form-card :deep(.el-form-item__label) {
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-body;
  padding-bottom: $wolf-space-xs;
}

.form-card :deep(.el-input__wrapper),
.form-card :deep(.el-select .el-input__wrapper),
.form-card :deep(.el-date-picker.el-input__wrapper) {
  border-radius: $wolf-radius-sm;
  transition: all 0.2s ease;
}

.form-card :deep(.el-input__wrapper:hover),
.form-card :deep(.el-select .el-input__wrapper:hover) {
  border-color: $wolf-border-hover;
}

.form-card :deep(.el-input__wrapper.is-focus),
.form-card :deep(.el-select .el-input__wrapper.is-focus) {
  border-color: $wolf-primary;
  box-shadow: 0 0 0 2px rgba($wolf-primary, 0.1);
}

// 表单提示
.form-extra {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-caption;
  margin-top: $wolf-space-xs;

  &.form-extra--success {
    color: $wolf-success-text;
  }
}

// 操作按钮
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
  padding-top: $wolf-space-lg;
  border-top: 1px solid $wolf-border-light;
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

  .form-actions {
    flex-direction: column-reverse;

    .el-button {
      width: 100%;
    }
  }
}
</style>
