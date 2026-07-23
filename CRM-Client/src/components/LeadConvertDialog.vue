<script setup lang="ts">
/**
 * LeadConvertDialog.vue - 线索转化为客户弹窗
 *
 * 设计规范：
 * - 使用 shadcn-vue Dialog + Form
 * - V2 Design Tokens
 * - 替代 LeadConvert.vue 页面跳转
 */
import { ref, reactive, watch, computed } from 'vue'
import { toast } from 'vue-sonner'
import { Building2 } from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  InputField,
  SelectField,
} from '@/components/crmwolf'
import { leadApi, type LeadDetail } from '@/api/lead'
import customerApi from '@/api/customer'
import procurementApi from '@/api/procurement'

interface Props {
  open: boolean
  leadId: number | null
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// ==================== State ====================
const loading = ref(false)
const submitting = ref(false)
const leadData = ref<LeadDetail | null>(null)
const procurementMethodOptions = ref<{ id: number; name: string }[]>([])

// 表单数据
const formValues = reactive({
  account_name: '',
  city: '',
  address: '',
  default_procurement_method_id: '' as string | number
})

// 计算属性
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})
const procurementSelectOptions = computed(() =>
  procurementMethodOptions.value.map((option) => ({
    value: String(option.id),
    label: option.name,
  }))
)

// ==================== Methods ====================

// 加载线索详情
const fetchLeadDetail = async (): Promise<void> => {
  if (props.leadId === undefined || props.leadId === null) return

  loading.value = true
  try {
    const res = await leadApi.getLeadDetail(props.leadId)
    leadData.value = res

    // 预填充表单
    formValues.account_name = res.lead_name ?? ''
    formValues.city = res.city ?? ''
  } catch {
    toast.error('获取线索详情失败')
    visible.value = false
  } finally {
    loading.value = false
  }
}

// 加载采购方式选项
const fetchProcurementMethodOptions = async (): Promise<void> => {
  try {
    const res = await procurementApi.getProcurementMethodOptions()
    procurementMethodOptions.value = res ?? []
  } catch {
    procurementMethodOptions.value = []
  }
}

// 提交转化
const handleSubmit = async (): Promise<void> => {
  if (props.leadId === undefined || props.leadId === null) return

  // 简单校验
  if (!formValues.account_name.trim()) {
    toast.error('请输入客户公司名称')
    return
  }
  if (!formValues.city.trim()) {
    toast.error('请输入所在城市')
    return
  }
  if (formValues.default_procurement_method_id === null || formValues.default_procurement_method_id === undefined) {
    toast.error('请选择默认采购方式')
    return
  }

  submitting.value = true
  try {
    const data = {
      lead_id: props.leadId,
      account_name: formValues.account_name.trim().length > 0 ? formValues.account_name : null,
      address: formValues.address.trim().length > 0 ? formValues.address : null,
      default_procurement_method_id: Number(formValues.default_procurement_method_id)
    }
    await customerApi.convertLeadToCustomer(data)
    toast.success('线索转化成功')
    visible.value = false
    emit('success')
    // 不跳转，留在线索管理页面，通过 emit('success') 触发列表刷新
  } catch {
    toast.error('转化线索失败')
  } finally {
    submitting.value = false
  }
}

// 关闭弹窗
const handleClose = (): void => {
  visible.value = false
}

// ==================== Watch ====================
watch(
  () => props.open,
  (open) => {
    if (open === true && props.leadId !== undefined && props.leadId !== null) {
      fetchProcurementMethodOptions()
      fetchLeadDetail()
    }
  }
)

// 重置状态
watch(visible, (val) => {
  if (!val) {
    formValues.account_name = ''
    formValues.city = ''
    formValues.address = ''
    formValues.default_procurement_method_id = ''
    leadData.value = null
  }
})
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="sm:max-w-[600px]">
      <DialogHeader>
        <DialogTitle>转化为客户</DialogTitle>
        <DialogDescription>
          将线索转化为客户，创建客户档案
        </DialogDescription>
      </DialogHeader>

      <!-- 加载状态 -->
      <div v-if="loading" class="space-y-4 py-4">
        <Skeleton class="h-24 w-full" />
        <Skeleton class="h-48 w-full" />
      </div>

      <div v-else class="space-y-6 py-4">
        <!-- 线索信息卡片 -->
        <div v-if="leadData" class="info-card">
          <div class="info-header">
            <div class="avatar">
              {{ leadData.lead_name?.charAt(0) || '线' }}
            </div>
            <div class="info-content">
              <div class="entity-name">{{ leadData.lead_name }}</div>
              <div class="info-badge">线索信息</div>
            </div>
          </div>

          <div class="info-divider" />

          <div class="attributes-grid">
            <div class="attribute-item">
              <span class="attribute-label">线索来源</span>
              <span class="attribute-value">{{ leadData.source || '-' }}</span>
            </div>
            <div class="attribute-item">
              <span class="attribute-label">所在城市</span>
              <span class="attribute-value">{{ leadData.city || '-' }}</span>
            </div>
            <div class="attribute-item">
              <span class="attribute-label">联系人</span>
              <span class="attribute-value">{{ leadData.contact_name || '-' }}</span>
            </div>
            <div class="attribute-item">
              <span class="attribute-label">联系电话</span>
              <span class="attribute-value">{{ leadData.contact_phone || '-' }}</span>
            </div>
            <div class="attribute-item">
              <span class="attribute-label">公司规模</span>
              <span class="attribute-value">{{ leadData.company_scale || '-' }}</span>
            </div>
            <div class="attribute-item">
              <span class="attribute-label">负责人</span>
              <span class="attribute-value">{{ leadData.owner_info?.name || '-' }}</span>
            </div>
          </div>
        </div>

        <!-- 客户信息表单 -->
        <div class="form-section">
          <h4 class="form-section-title">客户信息</h4>

          <div class="space-y-4">
            <!-- 客户公司名称 -->
            <InputField
              id="lead-convert-account-name"
              v-model="formValues.account_name"
              class="form-item"
              label="客户公司名称"
              required
              placeholder="请输入客户公司名称（默认使用线索名称）"
            />

            <!-- 所在城市 + 默认采购方式 -->
            <div class="form-grid">
              <InputField
                id="lead-convert-city"
                v-model="formValues.city"
                class="form-item"
                label="所在城市"
                required
                placeholder="请输入所在城市"
              />

              <SelectField
                id="lead-convert-procurement-method"
                v-model="formValues.default_procurement_method_id"
                class="form-item"
                label="默认采购方式"
                required
                :options="procurementSelectOptions"
                placeholder="请选择默认采购方式"
              />
            </div>

            <!-- 公司地址 -->
            <InputField
              id="lead-convert-address"
              v-model="formValues.address"
              class="form-item"
              label="公司地址"
              placeholder="请输入公司地址（可选）"
            />
          </div>
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="handleClose">
          取消
        </Button>
        <Button
          :disabled="submitting || loading"
          @click="handleSubmit"
        >
          <Building2 v-if="!submitting" class="w-4 h-4 mr-2" />
          {{ submitting ? '转化中...' : '确认转化' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// ==================== 线索信息卡片 ====================
.info-card {
  background: $wolf-bg-muted-v2;
  border-radius: $wolf-radius-lg-v2;
  padding: $wolf-space-md-v2;
}

.info-header {
  display: flex;
  align-items: center;
  gap: $wolf-space-md-v2;
}

.avatar {
  width: 48px;
  height: 48px;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold-v2;
  flex-shrink: 0;
}

.info-content {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.entity-name {
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
}

.info-badge {
  display: inline-flex;
  padding: 2px 8px;
  font-size: $wolf-font-size-caption-v2;
  border-radius: $wolf-radius-sm-v2;
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.info-divider {
  height: 1px;
  background: $wolf-border-default-v2;
  margin: $wolf-space-md-v2 0;
}

.attributes-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: $wolf-space-md-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: repeat(2, 1fr);
  }
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.attribute-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

.attribute-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

// ==================== 表单区域 ====================
.form-section {
  border-top: 1px solid $wolf-border-light-v2;
  padding-top: $wolf-space-md-v2;
}

.form-section-title {
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  margin-bottom: $wolf-space-md-v2;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $wolf-space-md-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

// ==================== Reduced Motion ====================
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
