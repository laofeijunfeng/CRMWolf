<template>
  <div class="lead-convert">
    <!-- 页面标题栏 -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleGoBack" aria-label="返回">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
      </div>
      <div class="page-header-right">
        <el-button @click="handleGoBack">取消</el-button>
      </div>
    </div>

    <!-- 内容区 -->
    <div class="convert-content">
      <template v-if="leadData">
        <!-- 线索信息卡片 -->
        <div class="info-card" v-loading="loading">
          <!-- 标题区 -->
          <div class="info-header">
            <div class="info-left">
              <div class="avatar">{{ leadData?.lead_name?.charAt(0) || '线' }}</div>
              <div class="title-section">
                <h2 class="entity-name">{{ leadData?.lead_name }}</h2>
                <span class="info-tag">线索信息</span>
              </div>
            </div>
            <div class="info-right">
              <div class="stat-item">
                <div class="stat-label">转化来源</div>
                <div class="stat-value">线索</div>
              </div>
            </div>
          </div>

          <!-- 分隔线 -->
          <div class="info-divider"></div>

          <!-- 属性网格 -->
          <div class="attributes-grid">
            <div class="attribute-item">
              <div class="attribute-label">线索来源</div>
              <div class="attribute-value">{{ leadData.source || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">所在城市</div>
              <div class="attribute-value">{{ leadData.city || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">联系人</div>
              <div class="attribute-value">{{ leadData.contact_name || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">联系电话</div>
              <div class="attribute-value">{{ leadData.contact_phone || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">公司规模</div>
              <div class="attribute-value">{{ leadData.company_scale || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">负责人</div>
              <div class="attribute-value">{{ leadData.owner_info?.name || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">创建时间</div>
              <div class="attribute-value">{{ formatDate(leadData.created_time) }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">创建人</div>
              <div class="attribute-value">{{ leadData.creator_info?.name || '-' }}</div>
            </div>
          </div>
        </div>

        <!-- 客户信息表单卡片 -->
        <div class="form-card">
          <div class="card-title">客户信息</div>

          <el-form :model="convertForm" :rules="convertFormRules" label-position="top" ref="convertFormRef">
            <el-row :gutter="24">
              <el-col :span="24">
                <el-form-item label="客户公司名称" prop="account_name" required>
                  <el-input v-model="convertForm.account_name" placeholder="请输入客户公司名称（默认使用线索名称）" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="24">
              <el-col :span="12">
                <el-form-item label="所在城市" prop="city" required>
                  <el-input v-model="convertForm.city" placeholder="请输入所在城市" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="默认采购方式" prop="default_procurement_method_id" required>
                  <el-select
                    v-model="convertForm.default_procurement_method_id"
                    placeholder="请选择默认采购方式"
                    style="width: 100%"
                    clearable
                  >
                    <el-option
                      v-for="option in procurementMethodOptions"
                      :key="option.id"
                      :label="option.name"
                      :value="option.id"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="24">
              <el-col :span="24">
                <el-form-item label="公司地址" prop="address">
                  <el-input v-model="convertForm.address" placeholder="请输入公司地址" />
                </el-form-item>
              </el-col>
            </el-row>

            <!-- 操作按钮 -->
            <div class="form-actions">
              <el-button @click="handleGoBack">取消</el-button>
              <el-button type="primary" @click="handleSubmit">
                <el-icon><CircleCheck /></el-icon>
                确认转化
              </el-button>
            </div>
          </el-form>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { showError, showSuccess } from '@/utils/errorMessages'
import {
  ArrowLeft,
  CircleCheck
} from '@element-plus/icons-vue'
import { leadApi, type LeadDetail } from '@/api/lead'
import customerApi from '@/api/customer'
import procurementApi from '@/api/procurement'
import { usePageTitle } from '@/composables/usePageTitle'

usePageTitle()

const router = useRouter()
const route = useRoute()
const leadId = Number(route.params.id || route.query.lead_id)

const loading = ref(false)
const leadData = ref<LeadDetail | null>(null)
const procurementMethodOptions = ref<any[]>([])
const convertFormRef = ref()

const convertForm = reactive({
  account_name: '',
  city: '',
  address: '',
  default_procurement_method_id: undefined as number | undefined
})

const convertFormRules = {
  account_name: [{ required: true, message: '请输入客户公司名称', trigger: 'blur' }],
  city: [{ required: true, message: '请输入所在城市', trigger: 'blur' }],
  default_procurement_method_id: [{ required: true, message: '请选择默认采购方式', trigger: 'change' }]
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const fetchLeadDetail = async () => {
  loading.value = true
  try {
    const res = await leadApi.getLeadDetail(leadId)
    leadData.value = res

    convertForm.account_name = res.lead_name || ''
    convertForm.city = res.city || ''
  } catch (error: unknown) {
    showError(error, '获取线索详情')
    router.back()
  } finally {
    loading.value = false
  }
}

const fetchProcurementMethodOptions = async () => {
  try {
    const res = await procurementApi.getProcurementMethodOptions()
    procurementMethodOptions.value = res || []
  } catch (error) {
    console.error('获取采购方式选项失败:', error)
  }
}

const handleSubmit = async () => {
  try {
    await convertFormRef.value?.validate()
  } catch {
    return
  }

  loading.value = true
  try {
    const data = {
      lead_id: leadId,
      account_name: convertForm.account_name || undefined,
      address: convertForm.address || undefined,
      default_procurement_method_id: convertForm.default_procurement_method_id || undefined
    }
    const result = await customerApi.convertLeadToCustomer(data)
    showSuccess('转化', '线索')
    router.push(`/customers/${result.customer_id}`)
  } catch (error: unknown) {
    showError(error, '转化线索')
  } finally {
    loading.value = false
  }
}

const handleGoBack = () => {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/leads')
  }
}

onMounted(async () => {
  if (!leadId) {
    showError(new Error('缺少线索ID参数'), '转化线索')
    router.push('/leads')
    return
  }

  await fetchProcurementMethodOptions()
  await fetchLeadDetail()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.lead-convert {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

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

.page-header-left,
.page-header-right {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.page-header-left {
  flex: 1;
  min-width: 0;
}

.page-header-right {
  flex-shrink: 0;
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
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.convert-content {
  padding: $wolf-page-padding;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

// 信息卡片
.info-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.info-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: $wolf-space-md;
}

.info-left {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.avatar {
  width: 48px;
  height: 48px;
  border-radius: $wolf-radius-full;
  background: $wolf-primary-light;
  color: $wolf-primary;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold;
  flex-shrink: 0;
}

.title-section {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
}

.entity-name {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
}

.info-tag {
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  border-radius: $wolf-radius-sm;
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.info-right {
  flex-shrink: 0;
}

.stat-item {
  text-align: right;
}

.stat-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-bottom: $wolf-space-xs;
}

.stat-value {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.info-divider {
  height: 1px;
  background: $wolf-border-light;
  margin: $wolf-space-md 0;
}

// 属性网格
.attributes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: $wolf-space-md;
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
}

.attribute-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.attribute-value {
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
}

// 表单卡片
.form-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-md;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;
}

.form-actions {
  display: flex;
  justify-content: center;
  gap: $wolf-space-sm;
  margin-top: $wolf-space-lg;
  padding-top: $wolf-space-md;
  border-top: 1px solid $wolf-border-light;
}

// 表单标签样式
:deep(.el-form-item__label) {
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-secondary;
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
  .convert-content {
    padding: $wolf-space-md;
  }

  .info-card,
  .form-card {
    padding: $wolf-space-md;
  }

  .info-header {
    flex-direction: column;
    gap: $wolf-space-md;
  }

  .info-right {
    align-self: flex-start;
  }

  .attributes-grid {
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