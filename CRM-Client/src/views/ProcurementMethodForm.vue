<template>
  <div class="procurement-method-form-page">
    <!-- 页面标题栏 -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="wolf-page-title">{{ isEdit ? '编辑采购方式' : '新增采购方式' }}</h1>
      </div>
    </div>

    <!-- 表单内容 -->
    <div class="form-content">
      <el-row :gutter="16">
        <el-col :span="14">
          <!-- 基本信息卡片 -->
          <div class="form-card">
            <div class="card-header">
              <span class="card-title">基本信息</span>
            </div>
            <el-form
              ref="formRef"
              :model="form"
              :rules="rules"
              label-position="top"
              @submit.prevent="handleSubmit"
            >
              <el-row :gutter="16">
                <el-col :span="24">
                  <el-form-item label="方式名称" prop="name" required>
                    <el-input
                      v-model="form.name"
                      placeholder="请输入采购方式名称"
                      maxlength="100"
                      show-word-limit
                    />
                  </el-form-item>
                </el-col>
              </el-row>

              <el-row :gutter="16">
                <el-col :span="8">
                  <el-form-item label="方式编码" prop="code" required>
                    <el-input
                      v-model="form.code"
                      placeholder="请输入方式编码，如：STANDARD_BIDDING"
                      maxlength="50"
                      show-word-limit
                      :disabled="isEdit"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item label="排序" prop="sort_order">
                    <el-input-number
                      v-model="form.sort_order"
                      :min="0"
                      :max="9999"
                      placeholder="请输入排序"
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item v-if="isEdit" label="状态" prop="is_active">
                    <el-switch
                      v-model="isActiveSwitch"
                      active-text="启用"
                      inactive-text="禁用"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item label="描述" prop="description">
                <el-input
                  v-model="form.description"
                  type="textarea"
                  placeholder="请输入描述"
                  maxlength="500"
                  show-word-limit
                  :autosize="{ minRows: 3, maxRows: 6 }"
                />
              </el-form-item>
            </el-form>
          </div>

          <!-- 采购阶段卡片 -->
          <div class="form-card">
            <div class="card-header">
              <span class="card-title">采购阶段</span>
              <el-button type="primary" size="small" @click="handleAddStage">
                <el-icon><Plus /></el-icon>
                添加阶段
              </el-button>
            </div>

            <div v-if="form.stages.length === 0" class="empty-stages">
              <el-empty description="设置采购阶段，点击添加按钮定义流程">
                <el-button type="primary" @click="handleAddStage">
                  添加第一阶段
                </el-button>
              </el-empty>
            </div>

            <div v-else class="stages-list">
              <transition-group name="list">
                <div
                  v-for="(stage, index) in form.stages"
                  :key="index"
                  :class="['stage-card', { 'is-deleting': stage.mark_delete }]"
                >
                  <div class="stage-card-inner">
                    <div class="stage-card-header">
                      <div class="stage-card-title">
                        <span class="stage-order-tag">第 {{ stage.sort_order }} 阶段</span>
                        <strong>{{ stage.stage_name || '未命名阶段' }}</strong>
                      </div>
                      <div class="stage-actions">
                        <el-button
                          v-if="index > 0"
                          link
                          size="small"
                          @click="handleMoveStage(index, 'up')"
                        >
                          <el-icon><ArrowUp /></el-icon>
                        </el-button>
                        <el-button
                          v-if="index < form.stages.length - 1"
                          link
                          size="small"
                          @click="handleMoveStage(index, 'down')"
                        >
                          <el-icon><ArrowDown /></el-icon>
                        </el-button>
                        <el-button
                          v-if="stage.mark_delete"
                          size="small"
                          @click="handleRestoreStage(index)"
                        >
                          <el-icon><RefreshLeft /></el-icon>
                          恢复
                        </el-button>
                        <el-popconfirm
                          v-else
                          title="确定要删除这个阶段吗？"
                          @confirm="handleDeleteStage(index)"
                        >
                          <template #reference>
                            <el-button size="small" class="danger-btn">
                              删除
                            </el-button>
                          </template>
                        </el-popconfirm>
                      </div>
                    </div>

                    <el-form :model="stage" label-position="top">
                      <el-row :gutter="16">
                        <el-col :span="12">
                          <el-form-item label="阶段名称" required>
                            <el-input
                              v-model="stage.stage_name"
                              placeholder="如：需求确认"
                              maxlength="100"
                            />
                          </el-form-item>
                        </el-col>
                        <el-col :span="12">
                          <el-form-item label="阶段编码" required>
                            <el-input
                              v-model="stage.template_code"
                              placeholder="如：REQUIREMENT_CONFIRM"
                              maxlength="50"
                            />
                          </el-form-item>
                        </el-col>
                      </el-row>

                      <el-row :gutter="16">
                        <el-col :span="6">
                          <el-form-item label="赢率（%）" required>
                            <el-input-number
                              v-model="stage.win_probability"
                              :min="0"
                              :max="100"
                              :precision="0"
                              placeholder="赢率"
                              style="width: 100%"
                            />
                          </el-form-item>
                        </el-col>
                        <el-col :span="6">
                          <el-form-item label="排序" required>
                            <el-input-number
                              v-model="stage.sort_order"
                              :min="1"
                              :max="99"
                              placeholder="排序"
                              style="width: 100%"
                            />
                          </el-form-item>
                        </el-col>
                        <el-col :span="6">
                          <el-form-item label="默认起始">
                            <el-switch
                              v-model="stage.is_default_start"
                              :active-value="1"
                              :inactive-value="0"
                              active-text="是"
                              inactive-text="否"
                            />
                          </el-form-item>
                        </el-col>
                        <el-col :span="6">
                          <el-form-item label="可跳过">
                            <el-switch
                              v-model="stage.can_skip"
                              :active-value="1"
                              :inactive-value="0"
                              active-text="是"
                              inactive-text="否"
                            />
                          </el-form-item>
                        </el-col>
                      </el-row>

                      <el-form-item label="描述">
                        <el-input
                          v-model="stage.description"
                          type="textarea"
                          placeholder="请输入阶段描述"
                          maxlength="200"
                          show-word-limit
                          :autosize="{ minRows: 2, maxRows: 4 }"
                        />
                      </el-form-item>
                    </el-form>
                  </div>
                </div>
              </transition-group>
            </div>
          </div>
        </el-col>

        <!-- 流程预览 -->
        <el-col :span="10">
          <div class="preview-card">
            <div class="card-header">
              <span class="card-title">流程预览</span>
            </div>
            <el-timeline v-if="form.stages.length > 0">
              <el-timeline-item
                v-for="stage in sortedStages"
                :key="stage.sort_order"
                :timestamp="`第 ${stage.sort_order} 阶段`"
                placement="top"
              >
                <div class="preview-stage">
                  <div class="preview-stage-title">
                    <strong>{{ stage.stage_name }}</strong>
                    <div class="preview-stage-tags">
                      <span class="status-tag status-info">{{ stage.template_code }}</span>
                      <span v-if="stage.is_default_start" class="status-tag status-success">默认起始</span>
                      <span v-if="stage.can_skip" class="status-tag status-warning">可跳过</span>
                    </div>
                  </div>
                  <div class="preview-stage-body">
                    <p>赢率：{{ stage.win_probability }}%</p>
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="添加采购阶段，定义采购流程" />
          </div>
        </el-col>
      </el-row>

      <!-- 表单操作 -->
      <div class="form-actions">
        <el-button @click="handleBack">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Plus, ArrowUp, ArrowDown, Delete, RefreshLeft } from '@element-plus/icons-vue'
import procurementApi from '../api/procurement'

const route = useRoute()
const router = useRouter()

const formRef = ref()
const submitting = ref(false)
const isEdit = computed(() => !!route.params.id)

const isActiveSwitch = computed({
  get: () => form.value.is_active === 1,
  set: (val) => {
    form.value.is_active = val ? 1 : 0
  }
})

const form = ref({
  id: undefined as number | undefined,
  name: '',
  code: '',
  sort_order: 0,
  description: '',
  is_active: 1,
  stages: []
})

const rules = {
  name: [{ required: true, message: '请输入采购方式名称', trigger: 'blur' }],
  code: [{ required: true, message: '请输入方式编码', trigger: 'blur' }]
}

const sortedStages = computed(() => {
  return [...form.value.stages].sort((a, b) => a.sort_order - b.sort_order)
})

const fetchMethodDetail = async (id: string) => {
  try {
    const method = await procurementApi.getProcurementMethod(Number(id))

    if (method) {
      form.value = {
        ...method,
        stages: []
      }

      // 直接使用 method 中已包含的 stage_templates，不再调用单独的 API
      const stages = method.stage_templates || []

      form.value.stages = stages.map((stage: { stage_name: string; stage_order: number }) => ({
        id: stage.id,
        stage_name: stage.stage_name,
        template_code: stage.template_code || stage.stage_code || '',
        win_probability: stage.win_probability,
        sort_order: stage.sort_order,
        is_default_start: stage.is_default_start || stage.is_default || 0,
        can_skip: stage.can_skip || 0,
        description: stage.description || '',
        mark_delete: false
      }))
    }
  } catch (error: unknown) {
    console.error('获取采购方式详情失败', error)
    ElMessage.error('获取采购方式详情失败，请刷新页面或稍后重试')
  }
}

const handleAddStage = () => {
  const nextOrder = form.value.stages.filter(s => !s.mark_delete).length + 1
  form.value.stages.push({
    stage_name: '',
    template_code: '',
    win_probability: 50,
    sort_order: nextOrder,
    is_default_start: form.value.stages.length === 0 ? 1 : 0,
    can_skip: 0,
    description: ''
  })
}

const handleMoveStage = (index: number, direction: 'up' | 'down') => {
  const stages = form.value.stages
  if (direction === 'up' && index > 0) {
    ;[stages[index - 1], stages[index]] = [stages[index], stages[index - 1]]
    stages[index - 1].sort_order = index
    stages[index].sort_order = index + 1
  } else if (direction === 'down' && index < stages.length - 1) {
    ;[stages[index], stages[index + 1]] = [stages[index + 1], stages[index]]
    stages[index].sort_order = index + 1
    stages[index + 1].sort_order = index + 2
  }
}

const handleDeleteStage = (index: number) => {
  const stage = form.value.stages[index]
  if (stage.id) {
    stage.mark_delete = true
    stage._deleting = true
  } else {
    form.value.stages.splice(index, 1)
  }
  form.value.stages.forEach((s, i) => {
    if (!s.mark_delete) {
      s.sort_order = i + 1
    }
  })
}

const handleRestoreStage = (index: number) => {
  const stage = form.value.stages[index]
  if (stage.mark_delete) {
    stage.mark_delete = false
    delete stage._deleting
  }
}

const handleSubmit = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true

  try {
    if (isEdit.value) {
      const methodData = {
        name: form.value.name,
        sort_order: form.value.sort_order,
        description: form.value.description,
        is_active: form.value.is_active ? 1 : 0
      }

      const stagesData = form.value.stages
        .filter(s => !s.mark_delete)
        .map(s => ({
          id: s.id || undefined,
          template_code: s.template_code,
          stage_name: s.stage_name,
          win_probability: s.win_probability,
          sort_order: s.sort_order,
          is_default_start: s.is_default_start,
          can_skip: s.can_skip,
          description: s.description
        }))

      await procurementApi.fullUpdateProcurementMethod(form.value.id!, {
        method: methodData,
        stages: stagesData
      })
    } else {
      const methodData = {
        code: form.value.code,
        name: form.value.name,
        sort_order: form.value.sort_order,
        description: form.value.description
      }

      const stagesData = form.value.stages.map(s => ({
        template_code: s.template_code,
        stage_name: s.stage_name,
        win_probability: s.win_probability,
        sort_order: s.sort_order,
        is_default_start: s.is_default_start,
        can_skip: s.can_skip,
        description: s.description
      }))

      await procurementApi.fullUpdateProcurementMethod(form.value.id!, {
        method: methodData,
        stages: stagesData
      })
    }

    ElMessage.success(isEdit.value ? '已保存，可以继续下一步操作' : '已创建，可以继续下一步操作')
    router.push('/procurement-methods')
  } catch (error: unknown) {
    console.error('提交失败', error)
    ElMessage.error(error.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

const handleBack = () => {
  router.push('/procurement-methods')
}

onMounted(() => {
  if (isEdit.value) {
    fetchMethodDetail(route.params.id as string)
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.procurement-method-form-page {
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

// 表单内容
.form-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: $wolf-page-padding;
}

// 表单卡片
.form-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-md;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

// 空状态
.empty-stages {
  padding: 40px 0;
}

// 阶段列表
.stages-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

.stage-card {
  transition: all 0.3s;
}

.stage-card.is-deleting {
  opacity: 0.6;
  background: $wolf-bg-hover;
}

.stage-card.is-deleting .stage-card-title {
  text-decoration: line-through;
  color: $wolf-text-tertiary;
}

.stage-card-inner {
  background: $wolf-bg-elevated;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
}

.stage-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: $wolf-space-sm;
  margin-bottom: $wolf-space-md;
}

.stage-card-title {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;

  strong {
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-medium;
    color: $wolf-text-primary;
  }
}

.stage-order-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  color: $wolf-primary;
  background: $wolf-primary-light;
  border-radius: $wolf-radius-sm;
}

.stage-actions {
  display: flex;
  gap: $wolf-space-xs;
}

.danger-btn {
  color: $wolf-danger-text !important;
  background: transparent !important;
  border: none !important;

  &:hover {
    background: $wolf-danger-bg !important;
  }
}

// 流程预览卡片
.preview-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
  position: sticky;
  top: 100px;
}

.preview-stage {
  background: $wolf-bg-elevated;
  border-radius: $wolf-radius-sm;
  padding: $wolf-space-sm;
}

.preview-stage-title {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: $wolf-space-xs;

  strong {
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-medium;
    color: $wolf-text-primary;
  }
}

.preview-stage-tags {
  display: flex;
  gap: $wolf-space-xs;
  flex-wrap: wrap;
}

.preview-stage-body {
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-auxiliary;
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

// 动画
.list-enter-active,
.list-leave-active {
  transition: all 0.3s ease;
}

.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: translateX(-30px);
}

// 响应式
@media (max-width: 1200px) {
  .form-card .el-col { span: 24 !important; }
}

@media (max-width: 768px) {
  .form-content {
    padding: $wolf-space-md;
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
  padding: $wolf-space-md;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
}
</style>