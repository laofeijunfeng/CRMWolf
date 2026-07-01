<template>
  <div class="invoice-form-container">
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="wolf-page-title">{{ isEditing ? '编辑发票申请' : '创建发票申请' }}</h1>
      </div>
    </div>

    <div class="form-content">
      <div class="form-wrapper">
        <el-form :model="formData" :rules="formRules" label-width="140px" ref="formRef">
          <div class="form-section">
            <div class="form-section-title">业务信息</div>
            
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="客户" prop="customer_id" required>
                  <el-select
                    v-model="formData.customer_id"
                    placeholder="请选择客户"
                    :loading="customersLoading"
                    filterable
                    @change="handleCustomerChange"
                    style="width: 100%"
                  >
                    <el-option v-for="customer in customers" :key="customer.id" :value="customer.id" :label="customer.account_name" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="合同" prop="contract_id">
                  <el-select
                    v-model="formData.contract_id"
                    placeholder="请选择合同（可选）"
                    :loading="contractsLoading"
                    filterable
                    @change="handleContractChange"
                    clearable
                    style="width: 100%"
                  >
                    <el-option v-for="contract in contracts" :key="contract.id" :value="contract.id" :label="contract.contract_name" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="回款计划" prop="payment_plan_id">
                  <el-select
                    v-model="formData.payment_plan_id"
                    placeholder="请选择回款计划（可选）"
                    :loading="paymentPlansLoading"
                    filterable
                    :disabled="!formData.contract_id"
                    clearable
                    @change="handlePaymentPlanChange"
                    style="width: 100%"
                  >
                    <el-option
                      v-for="plan in paymentPlans"
                      :key="plan.id"
                      :value="plan.id"
                      :label="`${plan.stage_name} - ¥${formatAmount(String(plan.planned_amount))}`"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <div class="form-section">
            <div class="form-section-title">开票信息</div>
            
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="开票抬头" prop="invoice_title_id" required>
                  <el-select
                    v-model="formData.invoice_title_id"
                    placeholder="请选择开票抬头"
                    :loading="invoiceTitlesLoading"
                    filterable
                    @change="handleTitleChange"
                    style="width: 100%"
                  >
                    <el-option 
                      v-for="title in invoiceTitles" 
                      :key="title.id" 
                      :value="title.id"
                      :label="title.title"
                    >
                      <div style="display: flex; flex-direction: column;">
                        <span>{{ title.title }}</span>
                        <span style="font-size: 12px; color: var(--el-text-color-secondary);">{{ title.taxpayer_id }}</span>
                      </div>
                    </el-option>
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="发票类型" prop="invoice_type" required>
                  <el-select v-model="formData.invoice_type" placeholder="请选择发票类型" style="width: 100%">
                    <el-option label="增值税专用发票" value="VAT_SPECIAL" />
                    <el-option label="增值税普通发票" value="VAT_NORMAL" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <div v-if="selectedInvoiceTitle" class="invoice-title-section">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="抬头类型">
                    <el-input v-model="selectedInvoiceTitle.title_type" disabled />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="纳税人识别号">
                    <el-input v-model="selectedInvoiceTitle.taxpayer_id" disabled />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="开户行">
                    <el-input v-model="selectedInvoiceTitle.bank_name" placeholder="请输入开户行" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="开户账号">
                    <el-input v-model="selectedInvoiceTitle.bank_account" placeholder="请输入开户账号" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="开票地址">
                    <el-input v-model="selectedInvoiceTitle.address" placeholder="请输入开票地址" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="电话">
                    <el-input v-model="selectedInvoiceTitle.phone" placeholder="请输入电话" />
                  </el-form-item>
                </el-col>
              </el-row>
            </div>

            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="开票金额" prop="invoice_amount" required>
                  <el-input-number
                    v-model="formData.invoice_amount"
                    placeholder="请输入开票金额"
                    :min="0"
                    :precision="2"
                    :controls="false"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item label="备注" prop="remark">
              <el-input
                v-model="formData.remark"
                type="textarea"
                placeholder="请输入备注信息（可选）"
                :maxlength="500"
                :rows="3"
                show-word-limit
              />
            </el-form-item>
          </div>
        </el-form>

        <!-- 表单操作 -->
        <div class="form-actions">
          <el-button @click="handleBack">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ isEditing ? '保存' : '创建' }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { showError, showSuccess } from '@/utils/errorMessages'
import { ArrowLeft } from '@element-plus/icons-vue'
import invoiceApi, {
  type InvoiceApplicationCreate,
  type InvoiceApplicationUpdate,
  type InvoiceType,
  type InvoiceApplicationResponse
} from '@/api/invoice'
import customerApi from '@/api/customer'
import contractApi from '@/api/contract'
import paymentApi from '@/api/payment'

const router = useRouter()
const route = useRoute()

const isEditing = computed(() => route.name === 'InvoiceEdit')
const invoiceId = computed(() => route.params.id as string)

const formRef = ref()
const submitting = ref(false)
const customersLoading = ref(false)
const contractsLoading = ref(false)
const paymentPlansLoading = ref(false)
const invoiceTitlesLoading = ref(false)

const customers = ref<any[]>([])
const contracts = ref<any[]>([])
const paymentPlans = ref<any[]>([])
const invoiceTitles = ref<any[]>([])
const selectedInvoiceTitle = ref<any>(null)
const selectedPaymentPlan = ref<any>(null)

const formData = reactive<{
  customer_id: number
  contract_id?: number
  payment_plan_id?: number
  invoice_title_id: number
  invoice_type: 'VAT_SPECIAL' | 'VAT_NORMAL'
  invoice_amount: number
  remark: string
}>({
  customer_id: 0,
  contract_id: undefined,
  payment_plan_id: undefined,
  invoice_title_id: 0,
  invoice_type: 'VAT_NORMAL',
  invoice_amount: 0,
  remark: ''
})

const formRules = {
  customer_id: [{ required: true, message: '请选择客户' }],
  invoice_title_id: [{ required: true, message: '请选择开票抬头' }],
  invoice_type: [{ required: true, message: '请选择发票类型' }],
  invoice_amount: [
    { required: true, message: '请输入开票金额' },
    {
      validator: (rule: unknown, value: number, callback: (error?: string) => void) => {
        if (value <= 0) {
          callback('开票金额必须大于0')
        } else {
          callback()
        }
      }
    }
  ]
}

const fetchCustomers = async () => {
  customersLoading.value = true
  try {
    const response = await customerApi.getCustomers({ skip: 0, limit: 100 })
    customers.value = response || []
  } catch (error) {
    console.error('获取客户列表失败', error)
  } finally {
    customersLoading.value = false
  }
}

const fetchContracts = async (customerId: number) => {
  if (!customerId) {
    contracts.value = []
    return
  }

  contractsLoading.value = true
  try {
    const response = await contractApi.getCustomerContracts(customerId)
    contracts.value = response || []
  } catch (error) {
    console.error('获取合同列表失败', error)
  } finally {
    contractsLoading.value = false
  }
}

const fetchPaymentPlans = async (contractId: number) => {
  if (!contractId) {
    paymentPlans.value = []
    return
  }

  paymentPlansLoading.value = true
  try {
    const response = await paymentApi.getPaymentPlans(contractId)
    paymentPlans.value = response || []
  } catch (error) {
    console.error('获取回款计划失败', error)
  } finally {
    paymentPlansLoading.value = false
  }
}

const fetchInvoiceTitles = async (customerId: number) => {
  if (!customerId) {
    invoiceTitles.value = []
    return
  }

  invoiceTitlesLoading.value = true
  try {
    const response = await invoiceApi.getInvoiceTitles(customerId)
    invoiceTitles.value = response.invoice_titles || []
  } catch (error) {
    console.error('获取开票抬头失败', error)
  } finally {
    invoiceTitlesLoading.value = false
  }
}

const handleCustomerChange = (customerId: number) => {
  formData.contract_id = undefined
  formData.payment_plan_id = undefined
  formData.invoice_title_id = 0
  contracts.value = []
  paymentPlans.value = []
  invoiceTitles.value = []

  fetchContracts(customerId)
  fetchInvoiceTitles(customerId)
}

const handleContractChange = (contractId: number) => {
  formData.payment_plan_id = undefined
  formData.invoice_amount = 0
  paymentPlans.value = []
  selectedPaymentPlan.value = null

  if (contractId) {
    fetchPaymentPlans(contractId)
  }
}

const handlePaymentPlanChange = (planId: number) => {
  const plan = paymentPlans.value.find(p => p.id === planId)
  if (plan) {
    selectedPaymentPlan.value = plan
    formData.invoice_amount = plan.remaining_amount || plan.planned_amount
  } else {
    selectedPaymentPlan.value = null
  }
}

const handleTitleChange = (titleId: number) => {
  const title = invoiceTitles.value.find(t => t.id === titleId)
  if (title) {
    selectedInvoiceTitle.value = {
      ...title,
      title_type: title.title_type === 'COMPANY' ? '单位' : '个人',
      bank_name: title.bank_name || '',
      bank_account: title.bank_account || '',
      address: title.address || '',
      phone: title.phone || ''
    }
  } else {
    selectedInvoiceTitle.value = null
  }
}

const handleSubmit = async () => {
  try {
    await formRef.value.validate()

    submitting.value = true

    const originalTitle = invoiceTitles.value.find(t => t.id === formData.invoice_title_id)
    
    if (originalTitle && selectedInvoiceTitle.value) {
      const needsUpdate = 
        selectedInvoiceTitle.value.bank_name !== (originalTitle.bank_name || '') ||
        selectedInvoiceTitle.value.bank_account !== (originalTitle.bank_account || '') ||
        selectedInvoiceTitle.value.address !== (originalTitle.address || '') ||
        selectedInvoiceTitle.value.phone !== (originalTitle.phone || '')
      
      if (needsUpdate) {
        try {
          await invoiceApi.updateInvoiceTitle(formData.invoice_title_id, {
            bank_name: selectedInvoiceTitle.value.bank_name || null,
            bank_account: selectedInvoiceTitle.value.bank_account || null,
            address: selectedInvoiceTitle.value.address || null,
            phone: selectedInvoiceTitle.value.phone || null
          })
          showSuccess('更新', '抬头信息')
        } catch (error) {
          console.error('更新抬头信息失败', error)
          // 继续创建申请，不阻断流程
        }
      }
    }

    const submitData = {
      payment_plan_id: formData.payment_plan_id!,
      invoice_title_id: formData.invoice_title_id,
      invoice_amount: formData.invoice_amount,
      invoice_type: formData.invoice_type
    }

    if (isEditing.value) {
      await invoiceApi.updateInvoiceApplication(Number(invoiceId.value), submitData)
      showSuccess('更新', '发票申请')
    } else {
      await invoiceApi.createInvoiceApplication(submitData)
      showSuccess('创建', '发票申请')
    }

    router.push('/invoices')
  } catch (error: unknown) {
    showError(error, isEditing.value ? '更新发票申请' : '创建发票申请')
  } finally {
    submitting.value = false
  }
}

const handleBack = () => {
  router.back()
}

const formatAmount = (amount: string) => {
  const num = parseFloat(amount)
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

const loadInvoiceData = async () => {
  if (!isEditing.value) return

  try {
    const response = await invoiceApi.getInvoiceApplication(Number(invoiceId.value))
    const data = response as InvoiceApplicationResponse

    formData.customer_id = data.customer_id
    formData.contract_id = data.contract_id || undefined
    formData.payment_plan_id = data.payment_plan_id || undefined
    formData.invoice_title_id = data.invoice_title_id
    formData.invoice_type = data.invoice_type
    formData.invoice_amount = parseFloat(data.invoice_amount)
    formData.remark = data.remark || ''

    await Promise.all([
      fetchContracts(data.customer_id),
      fetchInvoiceTitles(data.customer_id)
    ])

    if (data.contract_id) {
      await fetchPaymentPlans(data.contract_id)
    }
    
    if (data.payment_plan_id) {
      handlePaymentPlanChange(data.payment_plan_id)
    }
    
    if (data.invoice_title_id) {
      handleTitleChange(data.invoice_title_id)
    }
  } catch (error) {
    console.error('获取发票申请详情失败', error)
    showError(error, '获取发票申请详情')
  }
}

onMounted(async () => {
  await fetchCustomers()

  if (isEditing.value) {
    await loadInvoiceData()
  }

  const customerId = route.query.customer_id as string
  const invoiceTitleId = route.query.invoice_title_id as string
  const contractId = route.query.contract_id as string

  if (customerId) {
    formData.customer_id = Number(customerId)
    await Promise.all([
      fetchContracts(Number(customerId)),
      fetchInvoiceTitles(Number(customerId))
    ])

    if (invoiceTitleId) {
      formData.invoice_title_id = Number(invoiceTitleId)
      await new Promise(resolve => setTimeout(resolve, 100))
      handleTitleChange(Number(invoiceTitleId))
    }
  }

  if (contractId) {
    formData.contract_id = Number(contractId)
    await fetchPaymentPlans(Number(contractId))
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.invoice-form-container {
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

.form-content {
  max-width: 800px;
  margin: 0 auto;
  padding: $wolf-page-padding;
}

.form-wrapper {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  padding: $wolf-card-padding;
  box-shadow: $wolf-shadow-card;
}

.form-section {
  margin-bottom: $wolf-space-lg;

  &:last-child {
    margin-bottom: 0;
  }
}

.form-section-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-md;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-default;
}

:deep(.el-form-item) {
  margin-bottom: $wolf-space-md;
}

:deep(.el-form-item__label) {
  color: $wolf-text-secondary;
  font-weight: $wolf-font-weight-medium;
}

:deep(.el-input__wrapper),
:deep(.el-textarea__inner) {
  border-radius: $wolf-radius-sm;
}

:deep(.el-select .el-input__wrapper) {
  border-radius: $wolf-radius-sm;
}

.invoice-title-section {
  margin-top: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  padding: $wolf-card-padding;
  background: $wolf-bg-page;
  border-radius: $wolf-radius-md;

  :deep(.el-form-item__label) {
    color: $wolf-text-secondary;
    font-weight: $wolf-font-weight-medium;
  }
}

// 表单操作
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
  padding-top: $wolf-space-lg;
  border-top: 1px solid $wolf-border-light;
  margin-top: $wolf-space-lg;
}
</style>
