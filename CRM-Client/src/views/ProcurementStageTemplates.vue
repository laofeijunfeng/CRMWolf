<template>
  <div class="stage-templates-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button type="text" class="back-btn" @click="handleBack" aria-label="返回">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
      </div>
      <el-button type="primary" class="primary-btn" @click="handleCreate">
        <el-icon><Plus /></el-icon>
        新增阶段模板
      </el-button>
    </div>

    <!-- 表格区 -->
    <div class="table-card">
      <el-table
        :data="stageTemplates"
        :loading="loading"
        stripe
      >
        <el-table-column prop="sort_order" label="排序" width="80" />
        <el-table-column prop="stage_code" label="阶段编码" min-width="150">
          <template #default="{ row }">
            <span class="link-text">{{ row.stage_code }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="stage_name" label="阶段名称" min-width="150" />
        <el-table-column prop="win_probability" label="赢率" min-width="100" align="right">
          <template #default="{ row }">
            {{ row.win_probability }}%
          </template>
        </el-table-column>
        <el-table-column label="默认起始" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.is_default" class="status-tag status-success">是</span>
            <span v-else class="text-muted">否</span>
          </template>
        </el-table-column>
        <el-table-column label="可跳过" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.can_skip" class="status-tag status-warning">是</span>
            <span v-else class="text-muted">否</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="120">
          <template #default="{ row }">
            <span :class="['status-tag', row.is_active ? 'status-success' : 'status-default']">
              {{ row.is_active ? '启用' : '停用' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <span class="action-link" @click="handleEdit(row)">编辑</span>
              <span class="action-link danger" @click="handleDelete(row)">删除</span>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 编辑抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :title="isEdit ? '编辑阶段模板' : '新增阶段模板'"
      direction="rtl"
      size="500px"
      class="wolf-drawer"
      @close="handleDrawerClose"
    >
      <!-- 影响评估 -->
      <div v-if="isEdit && impactAssessment" class="impact-assessment">
        <el-alert
          title="影响评估"
          type="warning"
          :closable="false"
          show-icon
        >
          <template #default>
            <p>此模板已被 <strong>{{ impactAssessment.opportunity_count }}</strong> 个商机使用</p>
            <p>其中活跃商机：<strong>{{ impactAssessment.active_opportunity_count }}</strong> 个</p>
            <el-button
              type="text"
              size="small"
              @click="handleViewActiveOpportunities"
            >
              查看详情
            </el-button>
          </template>
        </el-alert>
      </div>

      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item label="阶段编码" prop="stage_code" required>
          <el-input
            v-model="formData.stage_code"
            placeholder="请输入阶段编码，如：LEAD, QUALIFIED等"
            :disabled="isEdit"
          />
        </el-form-item>
        <el-form-item label="阶段名称" prop="stage_name" required>
          <el-input v-model="formData.stage_name" placeholder="请输入阶段名称" />
        </el-form-item>
        <el-form-item label="赢率(%)" prop="win_probability" required>
          <el-input-number
            v-model="formData.win_probability"
            placeholder="请输入赢率"
            :min="0"
            :max="100"
            :precision="0"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="排序序号" prop="sort_order" required>
          <el-input-number
            v-model="formData.sort_order"
            placeholder="请输入排序序号"
            :min="0"
            :precision="0"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="默认起始" prop="is_default">
          <el-switch v-model="formData.is_default" :active-value="1" :inactive-value="0" />
          <span class="switch-label">
            {{ formData.is_default ? '是' : '否' }}
          </span>
        </el-form-item>
        <el-form-item label="可跳过" prop="can_skip">
          <el-switch v-model="formData.can_skip" :active-value="1" :inactive-value="0" />
          <span class="switch-label">
            {{ formData.can_skip ? '是' : '否' }}
          </span>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="3"
            placeholder="请输入描述"
          />
        </el-form-item>
        <el-form-item v-if="isEdit" label="状态">
          <el-switch v-model="formData.is_active" :active-value="1" :inactive-value="0" />
          <span class="switch-label">{{ formData.is_active ? '启用' : '停用' }}</span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button class="default-btn" @click="drawerVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          class="primary-btn"
          :loading="submitting"
          @click="handleSubmit"
        >
          确定
        </el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Plus } from '@element-plus/icons-vue'
import procurementApi, {
  type ProcurementStageTemplate,
  type ProcurementStageTemplateCreate,
  type ProcurementStageTemplateUpdate
} from '@/api/procurement'
import { usePageTitle } from '@/composables/usePageTitle'

usePageTitle()

const router = useRouter()
const route = useRoute()

const methodId = computed(() => Number(route.params.methodId))
const methodName = computed(() => (route.query.methodName as string) || '采购方式')

const loading = ref(false)
const submitting = ref(false)
const drawerVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()

const stageTemplates = ref<ProcurementStageTemplate[]>([])
const impactAssessment = ref<{ opportunity_count: number; active_opportunity_count: number } | null>(null)
const selectedTemplate = ref<ProcurementStageTemplate | null>(null)

const formData = reactive<ProcurementStageTemplateCreate & {
  is_active?: number
  description?: string
}>({
  procurement_method_id: methodId.value,
  stage_code: '',
  stage_name: '',
  win_probability: 0,
  sort_order: 0,
  is_default: 0,
  can_skip: 0,
  description: '',
  is_active: 1
})

const formRules = {
  stage_code: [
    { required: true, message: '请输入阶段编码' },
    { pattern: /^[A-Z_]+$/, message: '阶段编码只能包含大写字母和下划线' }
  ],
  stage_name: [{ required: true, message: '请输入阶段名称' }],
  win_probability: [
    { required: true, message: '请输入赢率' },
    { type: 'number', min: 0, max: 100, message: '赢率必须在0-100之间' }
  ],
  sort_order: [
    { required: true, message: '请输入排序序号' },
    { type: 'number', min: 0, message: '排序序号不能小于0' }
  ]
}

const fetchStageTemplates = async () => {
  loading.value = true
  try {
    const data = await procurementApi.getStageTemplates({
      procurement_method_id: methodId.value
    })
    stageTemplates.value = (data || []).sort((a: ProcurementStageTemplate, b: ProcurementStageTemplate) =>
      a.sort_order - b.sort_order
    )
  } catch (error: unknown) {
    console.error('获取阶段模板失败', error)
    ElMessage.error('获取阶段模板失败，请刷新页面或稍后重试')
  } finally {
    loading.value = false
  }
}

const fetchImpactAssessment = async (templateId: number) => {
  try {
    const data = await procurementApi.assessTemplateChange(templateId)
    impactAssessment.value = data
  } catch (error: unknown) {
    console.error('获取影响评估失败', error)
  }
}

const handleCreate = () => {
  isEdit.value = false
  selectedTemplate.value = null
  impactAssessment.value = null
  Object.assign(formData, {
    procurement_method_id: methodId.value,
    stage_code: '',
    stage_name: '',
    win_probability: 0,
    sort_order: stageTemplates.value.length,
    is_default: 0,
    can_skip: 0,
    description: '',
    is_active: 1
  })
  drawerVisible.value = true
}

const handleEdit = async (row: ProcurementStageTemplate) => {
  isEdit.value = true
  selectedTemplate.value = row
  Object.assign(formData, {
    procurement_method_id: row.procurement_method_id,
    stage_code: row.stage_code,
    stage_name: row.stage_name,
    win_probability: row.win_probability,
    sort_order: row.sort_order,
    is_default: row.is_default,
    can_skip: row.can_skip,
    description: '',
    is_active: row.is_active
  })

  await fetchImpactAssessment(row.id)
  drawerVisible.value = true
}

const handleSubmit = async () => {
  try {
    await formRef.value?.validate()
    submitting.value = true

    if (isEdit.value && selectedTemplate.value) {
      const updateData: ProcurementStageTemplateUpdate = {
        stage_name: formData.stage_name,
        win_probability: formData.win_probability,
        sort_order: formData.sort_order,
        is_default: formData.is_default,
        can_skip: formData.can_skip,
        is_active: formData.is_active
      }
      await procurementApi.updateStageTemplate(selectedTemplate.value.id, updateData)
      ElMessage.success('已更新，可以继续下一步操作')
    } else {
      const createData: ProcurementStageTemplateCreate = {
        procurement_method_id: formData.procurement_method_id,
        stage_code: formData.stage_code,
        stage_name: formData.stage_name,
        win_probability: formData.win_probability,
        sort_order: formData.sort_order,
        is_default: formData.is_default,
        can_skip: formData.can_skip,
        description: formData.description
      }
      await procurementApi.createStageTemplate(createData)
      ElMessage.success('已创建，可以继续下一步操作')
    }

    drawerVisible.value = false
    await fetchStageTemplates()
  } catch (error: unknown) {
    console.error('操作失败', error)
    if (error?.response?.data?.detail) {
      ElMessage.error(error.response.data.detail)
    } else {
      ElMessage.error('更新失败，请确认数据状态或联系管理员')
    }
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (row: ProcurementStageTemplate) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除阶段模板"${row.stage_name}"吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await procurementApi.deleteStageTemplate(row.id)
    ElMessage.success('已删除，可以继续下一步操作')
    await fetchStageTemplates()
  } catch (error: unknown) {
    if (error !== 'cancel') {
      console.error('删除失败', error)
      if (error?.response?.data?.detail) {
        ElMessage.error(error.response.data.detail)
      } else {
        ElMessage.error('删除失败，请确认数据状态或联系管理员')
      }
    }
  }
}

const handleViewActiveOpportunities = () => {
  if (selectedTemplate.value) {
    ElMessage.info('查看活跃商机功能待实现')
  }
}

const handleDrawerClose = () => {
  formRef.value?.resetFields()
  impactAssessment.value = null
}

const handleBack = () => {
  router.push({ name: 'ProcurementMethods' })
}

onMounted(() => {
  fetchStageTemplates()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.stage-templates-page {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 页面标题区
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-lg;
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
  color: $wolf-text-secondary !important;

  &:hover {
    background: $wolf-bg-hover !important;
    color: $wolf-text-primary !important;
  }
}

.page-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
}

.page-desc {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
  margin: 0;
}

.primary-btn {
  height: $wolf-button-height-md;
  padding: 0 $wolf-space-md;
}

// 表格样式由全局 wolf-design.scss 统一控制
.table-card {
  background: transparent;
}

// 链接样式
.link-text {
  color: $wolf-text-link;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium;

  &:hover {
    color: $wolf-text-link-hover;
  }
}

// 状态标签（浅底色 + 同色系文字）
.status-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  border-radius: $wolf-radius-sm;
}

.status-success {
  background: $wolf-success-bg;
  color: $wolf-success-text;
}

.status-warning {
  background: $wolf-warning-bg;
  color: $wolf-warning-text;
}

.status-info {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-default {
  background: $wolf-bg-hover;
  color: $wolf-text-placeholder;
}

.text-muted {
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-auxiliary;
}

// 操作区
.action-cell {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.action-link {
  color: $wolf-text-link;
  font-size: $wolf-font-size-auxiliary;
  cursor: pointer;

  &:hover { color: $wolf-text-link-hover; }

  &.danger {
    color: $wolf-danger-text;

    &:hover { color: $wolf-danger-text; }
  }
}

// 影响评估
.impact-assessment {
  margin-bottom: $wolf-space-md;

  p {
    margin: $wolf-space-xs 0;
    font-size: $wolf-font-size-auxiliary;
    color: $wolf-text-secondary;
  }

  strong {
    color: $wolf-warning-text;
  }
}

.switch-label {
  margin-left: $wolf-space-sm;
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-auxiliary;
}

.default-btn {
  height: $wolf-button-height-md;
  padding: 0 $wolf-space-md;
  background: $wolf-bg-hover;
  color: $wolf-text-secondary;
  border: none;

  &:hover {
    background: $wolf-bg-active;
    color: $wolf-text-primary;
  }
}

// 抽屉样式
:deep(.el-drawer__header) {
  margin-bottom: $wolf-space-md;
  padding: $wolf-space-md;
  border-bottom: 1px solid $wolf-border-light;
}

:deep(.el-drawer__body) {
  padding: $wolf-space-md;
  background: $wolf-bg-elevated;
}

:deep(.el-drawer__footer) {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
  padding: $wolf-space-md;
  border-top: 1px solid $wolf-border-light;
}

// 响应式
@media (max-width: 768px) {
  .stage-templates-page { padding: $wolf-space-md; }
}
</style>