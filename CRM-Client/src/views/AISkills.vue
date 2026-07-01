<template>
  <div class="ai-skills-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="wolf-page-title">AI Skill 配置</h1>
      </div>
      <div class="page-header-right">
        <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="showGeneratorDialog">
          <el-icon><Plus /></el-icon>
          新建 Skill
        </el-button>
      </div>
    </div>

    <!-- Skill 列表 -->
    <div class="skills-section">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="Skill 管理" name="skills">
          <div class="skills-list" v-loading="loading">
            <el-card v-for="skill in skills" :key="skill.id" class="skill-card" shadow="hover">
              <!-- 卡片头部 -->
              <div class="skill-card-header" @click="toggleExpand(skill)">
                <div class="skill-info">
                  <span class="skill-name">{{ skill.display_name }}</span>
                  <el-tag :type="skill.is_active ? 'success' : 'info'" size="small">
                    {{ skill.is_active ? '启用' : '禁用' }}
                  </el-tag>
                  <span class="action-count-badge">{{ skill.action_count || 0 }} 个 Action</span>
                </div>
                <div class="skill-actions">
                  <el-icon class="expand-icon" :class="{ 'expanded': expandedSkills.has(skill.id) }">
                    <ArrowDown />
                  </el-icon>
                  <el-button size="small" text @click.stop="showEditSkillModal(skill)">
                    <el-icon><Edit /></el-icon>
                  </el-button>
                  <el-button size="small" text type="danger" @click.stop="handleDeleteSkill(skill)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
              </div>

              <!-- 卡片基本信息 -->
              <div class="skill-card-summary">
                <div class="skill-meta">
                  <span class="skill-code">{{ skill.skill_name }}</span>
                  <span class="skill-module">模块: {{ skill.module_type }}</span>
                </div>
                <p class="skill-desc">{{ skill.description }}</p>
              </div>

              <!-- 展开的 Actions 列表 -->
              <div v-if="expandedSkills.has(skill.id)" class="skill-actions-expanded">
                <div class="actions-header">
                  <span class="actions-title">Actions 配置</span>
                </div>

                <div v-if="skill.actions && skill.actions.length > 0" class="actions-list">
                  <div v-for="action in skill.actions" :key="action.id" class="action-item">
                    <div class="action-info">
                      <span class="action-name">{{ action.action_name }}</span>
                      <span class="action-display">{{ action.display_name }}</span>
                      <el-tag type="primary" size="small">{{ action.handler_type }}</el-tag>
                      <el-tag :type="action.is_active ? 'success' : 'info'" size="small">
                        {{ action.is_active ? '启用' : '禁用' }}
                      </el-tag>
                    </div>
                    <div class="action-actions">
                      <el-button size="small" text @click="showEditActionModal(skill, action)">
                        <el-icon><Edit /></el-icon>
                      </el-button>
                      <el-button size="small" text type="danger" @click="handleDeleteAction(skill, action)">
                        <el-icon><Delete /></el-icon>
                      </el-button>
                    </div>
                  </div>
                </div>

                <div v-else-if="!skill.actions" class="actions-loading">
                  <el-skeleton :rows="2" animated />
                </div>

                <div v-else class="actions-empty">
                  <el-empty description="添加 Action，定义 Skill 能力" :image-size="60" />
                </div>
              </div>
            </el-card>

            <!-- 空状态 -->
            <el-empty v-if="!loading && skills.length === 0" description="创建 Skill，扩展 AI 能力" />
          </div>
        </el-tab-pane>

        <el-tab-pane label="CRUD 映射" name="crud">
          <el-table :data="crudMappings" stripe v-loading="loading">
            <el-table-column prop="mapping_name" label="映射名称" width="180" />
            <el-table-column prop="crud_module" label="CRUD 模块" width="180" />
            <el-table-column prop="crud_instance_name" label="实例名" width="150" />
            <el-table-column prop="model_class" label="Model 类" width="120" />
            <el-table-column prop="owner_field" label="负责人字段" width="100" />
            <el-table-column prop="status_field" label="状态字段" width="100" />
            <el-table-column prop="name_field" label="名称字段" width="120" />
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="Enum 映射" name="enum">
          <el-table :data="enumMappings" stripe v-loading="loading">
            <el-table-column prop="enum_name" label="Enum 名称" width="180" />
            <el-table-column prop="display_name" label="显示名称" width="150" />
            <el-table-column prop="enum_class" label="Enum 类路径" width="250" />
            <el-table-column prop="values" label="值映射" min-width="300">
              <template #default="{ row }">
                <div class="enum-values">
                  <el-tag v-for="(value, key) in row.values" :key="key" size="small" class="enum-tag">
                    {{ key }} → {{ value }}
                  </el-tag>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="Handler 类型" name="handlers">
          <div class="handlers-section" v-loading="loading">
            <el-card v-for="handler in handlerTypes" :key="handler" class="handler-card" shadow="hover">
              <div class="handler-name">{{ handler }}</div>
              <p class="handler-desc">{{ getHandlerDescription(handler) }}</p>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 创建/编辑 Action 弹窗 -->
    <el-dialog
      v-model="actionModalVisible"
      :title="editingAction ? '编辑 Action' : '新建 Action'"
      width="800px"
      :close-on-click-modal="false"
    >
      <el-form :model="actionForm" :rules="actionRules" ref="actionFormRef" label-width="120px">
        <el-form-item label="所属 Skill">
          <el-input :value="selectedSkill?.display_name" disabled />
        </el-form-item>
        <el-form-item label="Action 名称" prop="action_name">
          <el-input v-model="actionForm.action_name" placeholder="如 list/detail/create" :disabled="!!editingAction" />
        </el-form-item>
        <el-form-item label="显示名称" prop="display_name">
          <el-input v-model="actionForm.display_name" placeholder="如 查询列表" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="actionForm.description" placeholder="查询产品列表" />
        </el-form-item>
        <el-form-item label="Handler 类型" prop="handler_type">
          <el-select v-model="actionForm.handler_type" placeholder="选择 Handler 类型">
            <el-option v-for="h in handlerTypes" :key="h" :label="h" :value="h" />
          </el-select>
        </el-form-item>
        <el-form-item label="Handler 配置" prop="handler_config">
          <el-input
            v-model="handlerConfigJson"
            type="textarea"
            :rows="8"
            placeholder='{"crud_mapping": "product", "owner_filter": true}'
          />
        </el-form-item>
        <el-form-item label="必填参数">
          <el-select v-model="actionForm.required_params" multiple filterable allow-create placeholder="输入参数名">
            <el-option label="entity_id" value="entity_id" />
            <el-option label="name" value="name" />
            <el-option label="content" value="content" />
            <el-option label="method" value="method" />
          </el-select>
        </el-form-item>
        <el-form-item label="可选参数">
          <el-select v-model="actionForm.optional_params" multiple filterable allow-create placeholder="输入参数名">
            <el-option label="next_follow_time" value="next_follow_time" />
            <el-option label="company_scale" value="company_scale" />
          </el-select>
        </el-form-item>
        <el-form-item label="权限码" prop="permission_code">
          <el-input v-model="actionForm.permission_code" placeholder="如 product:list" />
        </el-form-item>
        <el-form-item label="结果模板">
          <el-input v-model="actionForm.result_template" type="textarea" :rows="3" placeholder="共有 {total} 条数据" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="actionForm.is_active" :active-value="1" :inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actionModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveAction" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- AI 辅助生成对话框 -->
    <SkillGeneratorDialog
      v-model="generatorDialogVisible"
      @success="handleGeneratorSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import type { FormInstance, FormRules } from 'element-plus'
import { ArrowLeft, Plus, Edit, Delete, ArrowDown } from '@element-plus/icons-vue'
import { aiSkillsApi, type Skill, type SkillAction, type CRUDMapping, type EnumMapping } from '@/api/aiSkills'
import SkillGeneratorDialog from '@/components/SkillGeneratorDialog.vue'

const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const activeTab = ref('skills')

// 展开的 Skill ID 集合
const expandedSkills = ref(new Set<number>())

// 数据
const skills = ref<Skill[]>([])
const crudMappings = ref<CRUDMapping[]>([])
const enumMappings = ref<EnumMapping[]>([])
const handlerTypes = ref<string[]>([])

// 弹窗
const actionModalVisible = ref(false)
const generatorDialogVisible = ref(false)
const editingAction = ref<SkillAction | null>(null)
const selectedSkill = ref<Skill | null>(null)

// 表单
const actionFormRef = ref<FormInstance>()

const actionForm = reactive({
  action_name: '',
  display_name: '',
  description: '',
  handler_type: '',
  handler_config: {},
  required_params: [] as string[],
  optional_params: [] as string[],
  permission_code: '',
  result_template: '',
  is_active: 1
})

const handlerConfigJson = ref('')

const actionRules: FormRules = {
  action_name: [{ required: true, message: '请输入 Action 名称', trigger: 'blur' }],
  display_name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  handler_type: [{ required: true, message: '请选择 Handler 类型', trigger: 'change' }],
  permission_code: [{ required: true, message: '请输入权限码', trigger: 'blur' }]
}

// Handler 类型描述
const handlerDescriptions: Record<string, string> = {
  QueryListHandler: '查询列表 - 用于列表查询类操作',
  QueryDetailHandler: '查询详情 - 用于详情查询类操作',
  CreateHandler: '创建记录 - 用于创建新记录类操作',
  FollowUpHandler: '跟进记录 - 用于添加跟进记录类操作',
  StatusChangeHandler: '状态变更 - 用于状态变更类操作',
  AggregateHandler: '统计汇总 - 用于统计汇总类操作'
}

const getHandlerDescription = (handler: string) => {
  return handlerDescriptions[handler] || '通用 Handler'
}

// 展开/收起 Skill
const toggleExpand = async (skill: Skill) => {
  if (expandedSkills.value.has(skill.id)) {
    expandedSkills.value.delete(skill.id)
  } else {
    expandedSkills.value.add(skill.id)
    // 加载 Actions
    if (!skill.actions) {
      try {
        const response = await aiSkillsApi.getSkill(skill.id)
        skill.actions = response.data?.actions || []
      } catch (error: unknown) {
        showError(error, '获取 Actions')
      }
    }
  }
}

// 加载数据
const fetchSkills = async () => {
  loading.value = true
  try {
    const response = await aiSkillsApi.getSkills()
    skills.value = response.data?.items || []
  } catch (error: unknown) {
    showError(error, '获取 Skills')
  } finally {
    loading.value = false
  }
}

const fetchCRUDMappings = async () => {
  try {
    const response = await aiSkillsApi.getCRUDMappings()
    crudMappings.value = response.data?.items || []
  } catch (error: unknown) {
    showError(error, '获取 CRUD 映射')
  }
}

const fetchEnumMappings = async () => {
  try {
    const response = await aiSkillsApi.getEnumMappings()
    enumMappings.value = response.data?.items || []
  } catch (error: unknown) {
    showError(error, '获取 Enum 映射')
  }
}

const fetchHandlerTypes = async () => {
  try {
    const response = await aiSkillsApi.getHandlerTypes()
    handlerTypes.value = response.data?.handler_types || []
  } catch (error: unknown) {
    showError(error, '获取 Handler 类型')
  }
}

// Skill 弹窗
const showEditSkillModal = (_skill: Skill) => {
  // 编辑 Skill 使用 AI 辅助生成入口
  ElMessage.info('Skill 编辑请使用 AI 辅助生成入口')
}

const handleDeleteSkill = async (skill: Skill) => {
  try {
    await ElMessageBox.confirm(
      `确认删除 Skill "${skill.display_name}"？其关联的 ${skill.action_count || 0} 个 Action 也会一并删除。`,
      '确认删除',
      { type: 'warning' }
    )
    await aiSkillsApi.deleteSkill(skill.id)
    showSuccess('删除', 'Skill')
    expandedSkills.value.delete(skill.id)
    await fetchSkills()
  } catch (error: unknown) {
    if (error !== 'cancel') {
      showError(error, '删除 Skill')
    }
  }
}

// Action 弹窗（仅编辑）
const showEditActionModal = (skill: Skill, action: SkillAction) => {
  selectedSkill.value = skill
  editingAction.value = action
  Object.assign(actionForm, {
    action_name: action.action_name,
    display_name: action.display_name,
    description: action.description,
    handler_type: action.handler_type,
    handler_config: action.handler_config,
    required_params: action.required_params || [],
    optional_params: action.optional_params || [],
    permission_code: action.permission_code,
    result_template: action.result_template || '',
    is_active: action.is_active
  })
  handlerConfigJson.value = JSON.stringify(action.handler_config, null, 2)
  actionModalVisible.value = true
}

const handleSaveAction = async () => {
  if (!actionFormRef.value) return
  const valid = await actionFormRef.value.validate().catch(() => false)
  if (!valid) return

  if (!editingAction.value) {
    ElMessage.warning('新增 Action 请使用 AI 辅助生成入口')
    return
  }

  // 解析 handler_config JSON
  try {
    actionForm.handler_config = JSON.parse(handlerConfigJson.value || '{}')
  } catch {
    showError(new Error('Handler 配置 JSON 格式错误'), '保存 Action')
    return
  }

  saving.value = true
  try {
    await aiSkillsApi.updateAction(selectedSkill.value!.id, editingAction.value.id, actionForm)
    showSuccess('更新', 'Action')
    actionModalVisible.value = false
    // 刷新当前 Skill 的 Actions
    if (selectedSkill.value && expandedSkills.value.has(selectedSkill.value.id)) {
      const response = await aiSkillsApi.getSkill(selectedSkill.value.id)
      selectedSkill.value.actions = response.data?.actions || []
    }
    await fetchSkills()
  } catch (error: unknown) {
    showError(error, '保存 Action')
  } finally {
    saving.value = false
  }
}

const handleDeleteAction = async (skill: Skill, action: SkillAction) => {
  try {
    await ElMessageBox.confirm(
      `确认删除 Action "${action.display_name}"？`,
      '确认删除',
      { type: 'warning' }
    )
    await aiSkillsApi.deleteAction(skill.id, action.id)
    showSuccess('删除', 'Action')
    // 刷新当前 Skill 的 Actions
    if (expandedSkills.value.has(skill.id)) {
      const response = await aiSkillsApi.getSkill(skill.id)
      skill.actions = response.data?.actions || []
    }
    await fetchSkills()
  } catch (error: unknown) {
    if (error !== 'cancel') {
      showError(error, '删除 Action')
    }
  }
}

const handleBack = () => {
  router.back()
}

// AI 辅助生成
const showGeneratorDialog = () => {
  generatorDialogVisible.value = true
}

const handleGeneratorSuccess = async () => {
  await fetchSkills()
}

onMounted(async () => {
  await Promise.all([
    fetchSkills(),
    fetchCRUDMappings(),
    fetchEnumMappings(),
    fetchHandlerTypes()
  ])
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.ai-skills-container {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 页面头部
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

.page-header-right {
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

// 内容区
.skills-section {
  padding: $wolf-page-padding;
}

.skills-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm;
}

.skill-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  border: none;
  box-shadow: $wolf-shadow-card;
}

.skill-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: $wolf-space-md;
  cursor: pointer;
  transition: background 0.2s;

  &:hover {
    background: $wolf-bg-hover;
  }
}

.skill-info {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.skill-name {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.action-count-badge {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  background: $wolf-bg-hover;
  padding: 2px 8px;
  border-radius: $wolf-radius-sm;
}

.skill-actions {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
}

.expand-icon {
  font-size: 16px;
  color: $wolf-text-tertiary;
  transition: transform 0.2s;

  &.expanded {
    transform: rotate(180deg);
  }
}

.skill-card-summary {
  padding: 0 $wolf-space-md $wolf-space-md;
}

.skill-meta {
  display: flex;
  gap: $wolf-space-md;
  margin-bottom: $wolf-space-xs;
}

.skill-code {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  font-family: monospace;
}

.skill-module {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.skill-desc {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-secondary;
}

// 展开的 Actions 区域
.skill-actions-expanded {
  border-top: 1px solid $wolf-border-light;
  padding: $wolf-space-md;
  background: $wolf-bg-page;
}

.actions-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-sm;
}

.actions-title {
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-secondary;
}

.actions-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
}

.action-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: $wolf-space-sm;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-sm;
  transition: background 0.2s;

  &:hover {
    background: $wolf-bg-hover;
  }
}

.action-info {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.action-name {
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  font-family: monospace;
}

.action-display {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-secondary;
}

.action-actions {
  display: flex;
  gap: $wolf-space-xs;
}

.actions-loading,
.actions-empty {
  padding: $wolf-space-sm;
}

// Handlers 区
.handlers-section {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: $wolf-space-md;
}

.handler-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  border: none;
}

.handler-name {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  font-family: monospace;
}

.handler-desc {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-secondary;
  margin-top: $wolf-space-xs;
}

// Enum values
.enum-values {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs;
}

.enum-tag {
  margin: 0;
}

// 按钮
.wolf-btn--primary-sm {
  background: $wolf-primary !important;
  border-color: $wolf-primary !important;
  color: $wolf-text-inverse !important;
  font-weight: $wolf-font-weight-medium !important;
}

// 响应式
@media (max-width: 768px) {
  .skills-section {
    padding: $wolf-space-md;
  }

  .action-info {
    flex-wrap: wrap;
  }
}
</style>