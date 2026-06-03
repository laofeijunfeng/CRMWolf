<template>
  <div class="payment-plan-create-container">
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="page-title">创建回款计划</h1>
      </div>
    </div>

    <div class="form-container">
      <div class="info-card">
        <div class="card-header">
          <span class="card-title">合同信息</span>
        </div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="合同名称">{{ contractInfo?.contract_name }}</el-descriptions-item>
          <el-descriptions-item label="合同编号">{{ contractInfo?.contract_number }}</el-descriptions-item>
          <el-descriptions-item label="合同金额">¥{{ formatAmount(contractInfo?.total_amount || 0) }}</el-descriptions-item>
          <el-descriptions-item label="客户名称">{{ contractInfo?.customer_info?.account_name }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="plans-card">
        <div class="card-header">
          <span class="card-title">回款计划明细</span>
          <el-button class="wolf-btn wolf-btn--default-sm" @click="addPlan">
            <el-icon><Plus /></el-icon>
            添加阶段
          </el-button>
        </div>

        <div class="plans-form">
          <div v-if="form.plans.length === 0" class="empty-plans">
            <el-empty description="暂无计划，请点击上方按钮添加">
              <el-button type="primary" @click="addPlan">
                添加第一个阶段
              </el-button>
            </el-empty>
          </div>

          <div v-else class="plans-list">
            <div
              v-for="(plan, index) in form.plans"
              :key="index"
              class="plan-form-item"
            >
              <div class="plan-header">
                <span class="plan-index">第 {{ index + 1 }} 阶段</span>
                <el-button
                  v-if="form.plans.length > 1"
                  class="wolf-btn wolf-btn--danger-sm"
                  @click="removePlan(index)"
                >
                  <el-icon><Delete /></el-icon>
                  删除
                </el-button>
              </div>

              <el-form :model="plan" label-width="140px">
                <el-row :gutter="24">
                  <el-col :span="8">
                    <el-form-item label="阶段名称" required>
                      <el-input
                        v-model="plan.stage_name"
                        placeholder="如：首付款、进度款等"
                        maxlength="50"
                      />
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="计划金额（元）" required>
                      <el-input-number
                        v-model="plan.planned_amount"
                        :min="0"
                        :precision="2"
                        :step="1000"
                        placeholder="请输入金额"
                        style="width: 100%"
                      />
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="计划日期" required>
                      <el-date-picker
                        v-model="plan.due_date"
                        type="date"
                        placeholder="选择日期"
                        style="width: 100%"
                        value-format="YYYY-MM-DD"
                      />
                    </el-form-item>
                  </el-col>
                </el-row>
              </el-form>
            </div>
          </div>

          <div v-if="form.plans.length > 0" class="summary-section">
            <div class="summary-info">
              <span>计划总金额：<strong>¥{{ formatAmount(totalPlannedAmount) }}</strong></span>
              <span>合同金额：<strong>¥{{ formatAmount(contractInfo?.total_amount || 0) }}</strong></span>
              <span v-if="totalPlannedAmount !== contractInfo?.total_amount">
                差额：<strong class="summary-diff">
                  ¥{{ formatAmount(Math.abs((contractInfo?.total_amount || 0) - totalPlannedAmount)) }}
                </strong>
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 表单操作 -->
      <div class="form-actions">
        <el-button @click="handleBack">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          保存
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Plus, Delete } from '@element-plus/icons-vue'
import contractApi from '@/api/contract'
import paymentApi from '@/api/payment'

const route = useRoute()
const router = useRouter()

const contractId = computed(() => Number(route.params.contractId))
const contractInfo = ref<any>(null)
const loading = ref(false)
const submitting = ref(false)

const form = ref({
  plans: [] as Array<{
    stage_name: string
    planned_amount: number
    due_date: string
  }>
})

const totalPlannedAmount = computed(() => {
  return form.value.plans.reduce((sum, plan) => sum + (plan.planned_amount || 0), 0)
})

const formatAmount = (amount: number | string) => {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const fetchContractInfo = async () => {
  loading.value = true
  try {
    const data = await contractApi.getContract(contractId.value)
    contractInfo.value = data
  } catch (error: any) {
    console.error('获取合同信息失败', error)
    ElMessage.error('获取合同信息失败')
  } finally {
    loading.value = false
  }
}

const addPlan = () => {
  form.value.plans.push({
    stage_name: '',
    planned_amount: 0,
    due_date: ''
  })
}

const removePlan = (index: number) => {
  form.value.plans.splice(index, 1)
}

const validatePlans = () => {
  if (form.value.plans.length === 0) {
    ElMessage.error('请至少添加一个回款计划')
    return false
  }

  for (let i = 0; i < form.value.plans.length; i++) {
    const plan = form.value.plans[i]
    if (!plan.stage_name) {
      ElMessage.error(`请填写第 ${i + 1} 阶段的阶段名称`)
      return false
    }
    if (!plan.planned_amount || plan.planned_amount <= 0) {
      ElMessage.error(`请填写第 ${i + 1} 阶段的计划金额`)
      return false
    }
    if (!plan.due_date) {
      ElMessage.error(`请填写第 ${i + 1} 阶段的计划日期`)
      return false
    }
  }

  return true
}

const handleSubmit = async () => {
  if (!validatePlans()) {
    return
  }

  submitting.value = true
  try {
    await paymentApi.createPaymentPlans(contractId.value, form.value)
    ElMessage.success('创建成功')
    router.back()
  } catch (error: any) {
    console.error('创建回款计划失败', error)
    ElMessage.error(error.response?.data?.detail || '创建失败')
  } finally {
    submitting.value = false
  }
}

const handleBack = () => {
  router.back()
}

onMounted(() => {
  if (contractId.value) {
    fetchContractInfo()
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.payment-plan-create-container {
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

.form-container {
  max-width: 800px;
  margin: 0 auto;
  padding: $wolf-page-padding;
}

.info-card,
.plans-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-md;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.plans-form {
  .empty-plans {
    padding: $wolf-space-lg 0;
  }

  .plans-list {
    display: flex;
    flex-direction: column;
    gap: $wolf-card-gap;
  }

  .plan-form-item {
    padding: $wolf-card-padding;
    background: $wolf-bg-page;
    border-radius: $wolf-radius-md;
    border: 1px solid $wolf-border-default;

    .plan-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: $wolf-space-md;
      padding-bottom: $wolf-space-sm;
      border-bottom: 1px solid $wolf-border-light;

      .plan-index {
        font-size: $wolf-font-size-body;
        font-weight: $wolf-font-weight-semibold;
        color: $wolf-text-primary;
      }
    }
  }

  .summary-section {
    margin-top: $wolf-space-lg;
    padding: $wolf-card-padding;
    background: $wolf-info-bg;
    border-radius: $wolf-radius-md;

    .summary-info {
      display: flex;
      gap: $wolf-space-lg;
      font-size: $wolf-font-size-body;
      color: $wolf-text-secondary;

      strong {
        font-weight: $wolf-font-weight-semibold;
      }

      .summary-diff {
        color: $wolf-warning-text;
      }
    }
  }
}

@media (max-width: 768px) {
  .form-container {
    padding: $wolf-space-md;
  }

  .plan-form-item {
    padding: $wolf-space-sm;
  }

  .form-actions {
    flex-direction: column-reverse;

    .el-button {
      width: 100%;
    }
  }
}

// 表单操作
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
  padding-top: $wolf-space-lg;
  margin-top: $wolf-space-lg;
  border-top: 1px solid $wolf-border-light;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}
</style>
