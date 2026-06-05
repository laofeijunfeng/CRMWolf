<template>
  <div class="procurement-methods-page">
    <!-- 搜索/操作区 -->
    <div class="wolf-card search-card">
      <el-form :inline="true">
        <el-form-item>
          <el-input
            v-model="searchText"
            placeholder="搜索方式名称、编码"
            clearable
            style="width: 200px"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-select
            v-model="filterStatus"
            placeholder="筛选状态"
            clearable
            style="width: 120px"
            @change="handleSearch"
          >
            <el-option :value="true" label="启用" />
            <el-option :value="false" label="停用" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="handleCreate">
            <el-icon><Plus /></el-icon>
            新增采购方式
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="wolf-card table-card">
      <div class="wolf-table-wrapper">
        <el-table
          :data="filteredMethods"
          v-loading="loading"
          class="wolf-table"
          style="width: 100%"
        >
          <el-table-column prop="code" label="编码" min-width="150">
            <template #default="{ row }">
              <span class="wolf-link">{{ row.code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="150" />
          <el-table-column prop="sort_order" label="排序" width="100" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag v-if="row.is_active" class="wolf-tag wolf-tag--success" size="small">启用</el-tag>
              <el-tag v-else class="wolf-tag wolf-tag--gray" size="small">停用</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="200">
            <template #default="{ row }">
              {{ row.description || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="创建时间" min-width="160">
            <template #default="{ row }">
              {{ formatDateTime(row.created_time) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <div class="wolf-table-actions">
                <el-button type="primary" size="small" class="wolf-btn wolf-btn--primary-sm" @click="handleEdit(row)">
                  编辑
                </el-button>
                <el-button type="text" size="small" class="wolf-btn wolf-btn--text-danger" @click="handleDelete(row)">
                  删除
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog
      v-model="detailVisible"
      :title="`采购方式详情 - ${currentMethod?.name}`"
      width="900px"
      :close-on-click-modal="false"
      class="wolf-dialog"
    >
      <div v-if="currentMethod" v-loading="detailLoading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="编码">
            {{ currentMethod.code }}
          </el-descriptions-item>
          <el-descriptions-item label="名称">
            {{ currentMethod.name }}
          </el-descriptions-item>
          <el-descriptions-item label="排序">
            {{ currentMethod.sort_order }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <span :class="['status-tag', currentMethod.is_active ? 'status-success' : 'status-default']">
              {{ currentMethod.is_active ? '启用' : '停用' }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">
            {{ currentMethod.description || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <el-divider />

        <div class="stages-section">
          <div class="section-header">
            <h3>采购阶段</h3>
            <el-button type="primary" size="small" @click="handleAddStage">
              <el-icon><Plus /></el-icon>
              新增阶段
            </el-button>
          </div>

          <el-timeline v-if="currentMethodStages.length > 0" class="stages-timeline">
            <el-timeline-item
              v-for="stage in currentMethodStages"
              :key="stage.id"
              :timestamp="stage.sort_order.toString()"
              placement="top"
            >
              <el-card>
                <div class="stage-item">
                  <div class="stage-header">
                    <div class="stage-title">
                      <strong>{{ stage.stage_name }}</strong>
                      <span class="status-tag status-info">{{ stage.stage_code }}</span>
                      <span v-if="stage.is_default" class="status-tag status-success">默认起始</span>
                      <span v-if="stage.can_skip" class="status-tag status-warning">可跳过</span>
                    </div>
                    <div class="stage-actions">
                      <span class="action-link" @click="handleEditStage(stage)">编辑</span>
                      <span class="action-link danger" @click="handleDeleteStage(stage)">删除</span>
                    </div>
                  </div>
                  <div class="stage-body">
                    <p><strong>赢率：</strong>{{ stage.win_probability }}%</p>
                    <p><strong>排序：</strong>{{ stage.sort_order }}</p>
                    <p v-if="stage.description"><strong>描述：</strong>{{ stage.description }}</p>
                  </div>
                </div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无阶段模板" />
        </div>
      </div>
    </el-dialog>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="600px"
      :close-on-click-modal="false"
      class="wolf-dialog"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item label="编码" prop="code" required>
          <el-input
            v-model="formData.code"
            placeholder="请输入编码，如：PUBLIC_BIDDING"
            :disabled="isEditMethod"
          />
        </el-form-item>
        <el-form-item label="名称" prop="name" required>
          <el-input v-model="formData.name" placeholder="请输入采购方式名称" />
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
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="3"
            placeholder="请输入描述"
          />
        </el-form-item>
        <el-form-item v-if="isEditMethod" label="状态">
          <el-switch v-model="formData.is_active" :active-value="1" :inactive-value="0" />
          <span class="switch-label">{{ formData.is_active ? '启用' : '停用' }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button class="default-btn" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" class="primary-btn" :loading="submitting" @click="handleSubmit">
          确定
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="stageDialogVisible"
      :title="stageDialogTitle"
      width="600px"
      :close-on-click-modal="false"
      class="wolf-dialog"
    >
      <el-form
        ref="stageFormRef"
        :model="stageFormData"
        :rules="stageFormRules"
        label-width="140px"
      >
        <el-form-item label="阶段编码" prop="stage_code" required>
          <el-input
            v-model="stageFormData.stage_code"
            placeholder="请输入阶段编码"
            :disabled="isEditStage"
          />
        </el-form-item>
        <el-form-item label="阶段名称" prop="stage_name" required>
          <el-input v-model="stageFormData.stage_name" placeholder="请输入阶段名称" />
        </el-form-item>
        <el-form-item label="赢率（%）" prop="win_probability" required>
          <el-input-number
            v-model="stageFormData.win_probability"
            :min="0"
            :max="100"
            :precision="0"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="排序序号" prop="sort_order" required>
          <el-input-number
            v-model="stageFormData.sort_order"
            :min="0"
            :precision="0"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="stageFormData.description"
            type="textarea"
            :rows="3"
            placeholder="请输入描述"
          />
        </el-form-item>
        <el-form-item label="默认起始">
          <el-switch v-model="stageFormData.is_default" :active-value="1" :inactive-value="0" />
          <span class="switch-label">{{ stageFormData.is_default ? '是' : '否' }}</span>
        </el-form-item>
        <el-form-item label="可跳过">
          <el-switch v-model="stageFormData.can_skip" :active-value="1" :inactive-value="0" />
          <span class="switch-label">{{ stageFormData.can_skip ? '是' : '否' }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button class="default-btn" @click="stageDialogVisible = false">取消</el-button>
        <el-button type="primary" class="primary-btn" :loading="stageSubmitting" @click="handleStageSubmit">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- AI 快速创建对话框 -->
    <ProcurementMethodAIDialog
      v-model="showAIDialog"
      @created="handleAICreated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Plus, Search } from '@element-plus/icons-vue'
import procurementApi, {
  type ProcurementMethod,
  type ProcurementMethodCreate,
  type ProcurementMethodUpdate,
  type ProcurementStageTemplate,
  type ProcurementStageTemplateCreate
} from '@/api/procurement'
import ProcurementMethodAIDialog from '@/components/ProcurementMethodAIDialog.vue'

const router = useRouter()

const loading = ref(false)
const detailLoading = ref(false)
const submitting = ref(false)
const stageSubmitting = ref(false)
const dialogVisible = ref(false)
const stageDialogVisible = ref(false)
const detailVisible = ref(false)
const isEditMethod = ref(false)
const isEditStage = ref(false)
const formRef = ref()
const stageFormRef = ref()
const showAIDialog = ref(false)

const procurementMethods = ref<ProcurementMethod[]>([])
const currentMethodStages = ref<ProcurementStageTemplate[]>([])
const currentMethod = ref<ProcurementMethod | null>(null)
const currentStage = ref<ProcurementStageTemplate | null>(null)

const searchText = ref('')
const filterStatus = ref<boolean | undefined>(undefined)

const formData = reactive<ProcurementMethodCreate & { is_active?: number }>({
  code: '',
  name: '',
  sort_order: 0,
  description: '',
  is_active: 1
})

const stageFormData = reactive<ProcurementStageTemplateCreate & { is_default?: number; can_skip?: number }>({
  procurement_method_id: 0,
  stage_code: '',
  stage_name: '',
  win_probability: 50,
  sort_order: 0,
  description: '',
  is_default: 0,
  can_skip: 0
})

const formRules = {
  code: [
    { required: true, message: '请输入编码' },
    { pattern: /^[A-Z_]+$/, message: '编码只能包含大写字母和下划线' }
  ],
  name: [{ required: true, message: '请输入名称' }],
  sort_order: [
    { required: true, message: '请输入排序序号' },
    { type: 'number', min: 0, message: '排序序号不能小于0' }
  ]
}

const stageFormRules = {
  stage_code: [
    { required: true, message: '请输入阶段编码' },
    { pattern: /^[A-Z_]+$/, message: '编码只能包含大写字母和下划线' }
  ],
  stage_name: [{ required: true, message: '请输入阶段名称' }],
  win_probability: [
    { required: true, message: '请输入赢率' },
    { type: 'number', min: 0, max: 100, message: '赢率范围为0-100' }
  ],
  sort_order: [
    { required: true, message: '请输入排序序号' },
    { type: 'number', min: 0, message: '排序序号不能小于0' }
  ]
}

const dialogTitle = computed(() => isEditMethod.value ? '编辑采购方式' : '新增采购方式')
const stageDialogTitle = computed(() => isEditStage.value ? '编辑采购阶段' : '新增采购阶段')

const filteredMethods = computed(() => {
  let filtered = procurementMethods.value

  if (searchText.value) {
    const keyword = searchText.value.toLowerCase()
    filtered = filtered.filter(method =>
      method.name.toLowerCase().includes(keyword) ||
      method.code.toLowerCase().includes(keyword)
    )
  }

  if (filterStatus.value !== undefined) {
    filtered = filtered.filter(method => method.is_active === (filterStatus.value ? 1 : 0))
  }

  return filtered.sort((a, b) => a.sort_order - b.sort_order)
})

const formatDateTime = (dateStr: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const fetchProcurementMethods = async () => {
  loading.value = true
  try {
    const data = await procurementApi.getProcurementMethods() as any
    procurementMethods.value = data || []
  } catch (error: any) {
    console.error('获取采购方式失败', error)
    ElMessage.error('获取采购方式失败')
  } finally {
    loading.value = false
  }
}

const fetchMethodStages = async (methodId: number) => {
  detailLoading.value = true
  try {
    const data = await procurementApi.getStageTemplates({ procurement_method_id: methodId }) as any
    currentMethodStages.value = data || []
  } catch (error: any) {
    console.error('获取阶段模板失败', error)
    ElMessage.error('获取阶段模板失败')
  } finally {
    detailLoading.value = false
  }
}

const handleSearch = () => {
}

const handleBack = () => {
  router.push({ name: 'Settings' })
}

const handleCreate = () => {
  showAIDialog.value = true
}

const handleAICreated = () => {
  fetchProcurementMethods()
}

const handleEdit = (method: ProcurementMethod) => {
  router.push(`/procurement-methods/${method.id}/edit`)
}

const handleView = async (method: ProcurementMethod) => {
  currentMethod.value = method
  detailVisible.value = true
  await fetchMethodStages(method.id)
}

const handleSubmit = async () => {
  try {
    await formRef.value?.validate()
    submitting.value = true

    if (isEditMethod.value && currentMethod.value) {
      const updateData: ProcurementMethodUpdate = {
        name: formData.name,
        sort_order: formData.sort_order,
        description: formData.description,
        is_active: formData.is_active
      }
      await procurementApi.updateProcurementMethod(currentMethod.value.id, updateData)
      ElMessage.success('更新成功')
    } else {
      const createData: ProcurementMethodCreate = {
        code: formData.code,
        name: formData.name,
        sort_order: formData.sort_order,
        description: formData.description
      }
      await procurementApi.createProcurementMethod(createData)
      ElMessage.success('创建成功')
    }

    dialogVisible.value = false
    await fetchProcurementMethods()
  } catch (error: any) {
    console.error('操作失败', error)
    if (error?.response?.data?.detail) {
      ElMessage.error(error.response.data.detail)
    } else {
      ElMessage.error(isEditMethod.value ? '更新失败' : '创建失败')
    }
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (method: ProcurementMethod) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除采购方式"${method.name}"吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await procurementApi.deleteProcurementMethod(method.id)
    ElMessage.success('删除成功')

    await fetchProcurementMethods()
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('删除失败', error)
      if (error?.response?.data?.detail) {
        ElMessage.error(error.response.data.detail)
      } else {
        ElMessage.error('删除失败')
      }
    }
  }
}

const handleAddStage = () => {
  if (!currentMethod.value) return

  isEditStage.value = false
  currentStage.value = null
  const maxOrder = Math.max(0, ...currentMethodStages.value.map(s => s.sort_order))

  Object.assign(stageFormData, {
    procurement_method_id: currentMethod.value.id,
    stage_code: '',
    stage_name: '',
    win_probability: 50,
    sort_order: maxOrder + 1,
    description: '',
    is_default: 0,
    can_skip: 0
  })
  stageDialogVisible.value = true
}

const handleEditStage = (stage: ProcurementStageTemplate) => {
  isEditStage.value = true
  currentStage.value = stage
  Object.assign(stageFormData, {
    procurement_method_id: stage.procurement_method_id,
    stage_code: stage.stage_code,
    stage_name: stage.stage_name,
    win_probability: stage.win_probability,
    sort_order: stage.sort_order,
    description: stage.description || '',
    is_default: stage.is_default,
    can_skip: stage.can_skip
  })
  stageDialogVisible.value = true
}

const handleStageSubmit = async () => {
  try {
    await stageFormRef.value?.validate()
    stageSubmitting.value = true

    if (isEditStage.value && currentStage.value) {
      await procurementApi.updateStageTemplate(currentStage.value.id, {
        stage_name: stageFormData.stage_name,
        win_probability: stageFormData.win_probability,
        sort_order: stageFormData.sort_order,
        description: stageFormData.description,
        is_default: stageFormData.is_default,
        can_skip: stageFormData.can_skip
      })
      ElMessage.success('更新成功')

      const index = currentMethodStages.value.findIndex(s => s.id === currentStage.value!.id)
      if (index > -1) {
        Object.assign(currentMethodStages.value[index], stageFormData)
      }
    } else {
      const data = await procurementApi.createStageTemplate(stageFormData) as any
      ElMessage.success('创建成功')
      currentMethodStages.value.push({ ...stageFormData, id: data.id } as ProcurementStageTemplate)
    }

    stageDialogVisible.value = false
  } catch (error: any) {
    console.error('操作失败', error)
    if (error?.response?.data?.detail) {
      ElMessage.error(error.response.data.detail)
    } else {
      ElMessage.error(isEditStage.value ? '更新失败' : '创建失败')
    }
  } finally {
    stageSubmitting.value = false
  }
}

const handleDeleteStage = async (stage: ProcurementStageTemplate) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除阶段"${stage.stage_name}"吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await procurementApi.deleteStageTemplate(stage.id)
    ElMessage.success('删除成功')

    const index = currentMethodStages.value.findIndex(s => s.id === stage.id)
    if (index > -1) {
      currentMethodStages.value.splice(index, 1)
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('删除失败', error)
      if (error?.response?.data?.detail) {
        ElMessage.error(error.response.data.detail)
      } else {
        ElMessage.error('删除失败')
      }
    }
  }
}

onMounted(() => {
  fetchProcurementMethods()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.procurement-methods-page {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.wolf-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  padding: 0;
  margin-bottom: $wolf-space-md;
}

.search-card {
  padding: $wolf-space-md;
}

.table-card {
  padding: $wolf-space-md;
  overflow: hidden;
}

.wolf-table-wrapper {
  border-radius: $wolf-radius-md;
  overflow-x: auto;
}

.wolf-table :deep(.el-table__header th) {
  background-color: $wolf-bg-hover !important;
  color: $wolf-text-secondary;
  font-weight: $wolf-font-weight-medium;
  font-size: $wolf-font-size-auxiliary;
  padding: 12px $wolf-space-md;
  border-bottom: 1px solid $wolf-border-light;
}

.wolf-table :deep(.el-table__row td) {
  padding: 12px $wolf-space-md;
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  border-bottom: 1px solid $wolf-border-light;
}

.wolf-table :deep(.el-table__row:hover td) {
  background-color: $wolf-bg-hover !important;
}

.wolf-link {
  color: $wolf-text-link;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium;
}

.wolf-link:hover {
  text-decoration: underline;
}

.wolf-table-actions {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
}

.wolf-btn--text-danger {
  color: $wolf-danger-text !important;
  border: 1px solid $wolf-danger-border !important;
  background-color: $wolf-bg-card !important;
  padding: 8px 12px !important;
}

.wolf-btn--text-danger:hover {
  background-color: $wolf-danger-bg !important;
}

.wolf-tag {
  border-radius: $wolf-radius-sm !important;
  padding: 2px 8px !important;
  font-size: $wolf-font-size-caption !important;
  font-weight: $wolf-font-weight-medium !important;
  height: auto !important;
  line-height: 1.5 !important;
  border-width: 1px !important;
}

.wolf-tag--success {
  background-color: $wolf-success-bg !important;
  border-color: $wolf-success-border !important;
  color: $wolf-success-text !important;
}

.wolf-tag--gray {
  background-color: $wolf-purple-bg !important;
  border-color: $wolf-purple-border !important;
  color: $wolf-purple !important;
}

.wolf-btn--primary-sm {
  background: $wolf-primary !important;
  border-color: $wolf-primary !important;
  color: $wolf-text-inverse !important;
  font-weight: $wolf-font-weight-medium !important;
}

// 阶段展示区
.stages-section {
  margin-top: $wolf-space-lg;

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $wolf-space-md;

    h3 {
      margin: 0;
      font-size: $wolf-font-size-title;
      font-weight: $wolf-font-weight-semibold;
      color: $wolf-text-primary;
    }
  }
}

.stages-timeline {
  margin-top: $wolf-space-md;
}

.stage-item {
  .stage-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $wolf-space-sm;

    .stage-title {
      display: flex;
      align-items: center;
      gap: $wolf-space-xs;

      strong {
        font-size: $wolf-font-size-body;
        font-weight: $wolf-font-weight-medium;
        color: $wolf-text-primary;
      }
    }

    .stage-actions {
      display: flex;
      gap: $wolf-space-sm;
    }
  }

  .stage-body {
    p {
      margin: 0 0 $wolf-space-xs 0;
      font-size: $wolf-font-size-auxiliary;
      color: $wolf-text-secondary;

      strong {
        color: $wolf-text-primary;
      }
    }
  }
}

.switch-label {
  margin-left: $wolf-space-sm;
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-auxiliary;
}

@media (max-width: 768px) {
  .procurement-methods-page {
    padding: $wolf-space-md;
  }
}
</style>
