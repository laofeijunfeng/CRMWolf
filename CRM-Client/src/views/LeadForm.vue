<template>
  <div class="lead-form">
    <!-- 表单内容 -->
    <div class="form-content">
      <div class="form-card">
        <el-form
          :model="formData"
          :rules="formRules"
          label-position="top"
          ref="formRef"
        >
          <!-- 基本信息 -->
          <div class="form-section">
            <div class="section-title">基本信息</div>

            <div class="form-grid">
              <el-form-item label="线索名称" prop="lead_name" required>
                <el-input
                  v-model="formData.lead_name"
                  placeholder="请输入线索名称"
                />
              </el-form-item>

              <el-form-item label="线索来源" prop="source" required>
                <el-select
                  v-model="formData.source"
                  placeholder="请选择线索来源"
                  style="width: 100%"
                >
                  <el-option value="线上注册" label="线上注册" />
                  <el-option value="市场活动" label="市场活动" />
                  <el-option value="客户推荐" label="客户推荐" />
                  <el-option value="电话营销" label="电话营销" />
                  <el-option value="网站咨询" label="网站咨询" />
                  <el-option value="展会" label="展会" />
                  <el-option value="其他" label="其他" />
                </el-select>
              </el-form-item>
            </div>

            <div class="form-grid">
              <el-form-item label="所在城市" prop="city" required>
                <el-input
                  v-model="formData.city"
                  placeholder="请输入所在城市"
                />
              </el-form-item>

              <el-form-item label="公司规模" prop="company_scale">
                <el-select
                  v-model="formData.company_scale"
                  placeholder="请选择公司规模"
                  clearable
                  style="width: 100%"
                >
                  <el-option value="1-50人" label="1-50人" />
                  <el-option value="51-200人" label="51-200人" />
                  <el-option value="201-500人" label="201-500人" />
                  <el-option value="501-1000人" label="501-1000人" />
                  <el-option value="1000人以上" label="1000人以上" />
                </el-select>
              </el-form-item>
            </div>
          </div>

          <!-- 分隔线 -->
          <div class="section-divider"></div>

          <!-- 联系人信息 -->
          <div class="form-section">
            <div class="section-title">联系人信息</div>

            <div class="form-grid">
              <el-form-item label="联系人姓名" prop="contact_name" required>
                <el-input
                  v-model="formData.contact_name"
                  placeholder="请输入联系人姓名"
                />
              </el-form-item>

              <el-form-item label="联系电话" prop="contact_phone" required>
                <el-input
                  v-model="formData.contact_phone"
                  placeholder="请输入联系电话"
                />
              </el-form-item>
            </div>

            <div class="form-grid form-grid--single">
              <el-form-item label="备注" prop="remark">
                <el-input
                  v-model="formData.remark"
                  type="textarea"
                  :rows="4"
                  placeholder="请输入备注信息（可选）"
                />
              </el-form-item>
            </div>
          </div>
        </el-form>

        <!-- 操作按钮 -->
        <div class="form-actions">
          <el-button @click="handleBack">取消</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="submitting">
            {{ isEdit ? '保存' : '创建' }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { showError, showSuccess } from '@/utils/errorMessages'
import { leadApi } from '@/api/lead'
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

const isEdit = ref(false)
const leadId = ref<string>('')
const submitting = ref(false)
const formRef = ref()

const formData = reactive({
  lead_name: '',
  source: '',
  city: '',
  contact_name: '',
  contact_phone: '',
  company_scale: '',
  remark: ''
})

const formRules = {
  lead_name: [
    { required: true, message: '请输入线索名称', trigger: 'blur' }
  ],
  source: [
    { required: true, message: '请选择线索来源', trigger: 'change' }
  ],
  city: [
    { required: true, message: '请输入所在城市', trigger: 'blur' }
  ],
  contact_name: [
    { required: true, message: '请输入联系人姓名', trigger: 'blur' }
  ],
  contact_phone: [
    { required: true, message: '请输入联系电话', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号码', trigger: 'blur' }
  ]
}

onMounted(async () => {
  if (route.params.id) {
    isEdit.value = true
    leadId.value = route.params.id as string
    await fetchLeadDetail()
  }
})

const fetchLeadDetail = async () => {
  try {
    const response = await leadApi.getLeadDetail(parseInt(leadId.value))
    Object.assign(formData, {
      lead_name: response.lead_name || '',
      source: response.source || '',
      city: response.city || '',
      contact_name: response.contact_name || '',
      contact_phone: response.contact_phone || '',
      company_scale: response.company_scale || '',
      remark: response.remark || ''
    })
  } catch (error) {
    console.error('获取线索详情失败', error)
    showError(error, '获取线索详情')
  }
}

const handleSubmit = async () => {
  if (!formRef.value) return

  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return

    submitting.value = true
    try {
      const submitData = {
        ...formData,
        company_scale: formData.company_scale || undefined
      }

      if (isEdit.value) {
        await leadApi.updateLead(parseInt(leadId.value), submitData)
        showSuccess('更新', '线索')
      } else {
        await leadApi.createLead(submitData)
        showSuccess('创建', '线索')
      }
      router.push('/leads')
    } catch (error) {
      console.error('提交失败', error)
      showError(error, isEdit.value ? '更新线索' : '创建线索')
    } finally {
      submitting.value = false
    }
  })
}

const handleBack = () => {
  router.push('/leads')
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.lead-form {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
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

.form-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  padding: $wolf-card-padding;
  box-shadow: $wolf-shadow-card;
}

.form-section {
  margin-bottom: $wolf-space-lg;
}

.section-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-md;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;
}

.section-divider {
  height: 1px;
  background: $wolf-border-light;
  margin: $wolf-space-lg 0;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $wolf-space-md;
  margin-bottom: $wolf-space-md;
}

.form-grid--single {
  grid-template-columns: 1fr;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
  padding-top: $wolf-space-lg;
  border-top: 1px solid $wolf-border-light;
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
  .form-content {
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