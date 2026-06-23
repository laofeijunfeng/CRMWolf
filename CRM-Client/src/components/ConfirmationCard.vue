<template>
  <div class="confirmation-card" :class="`risk-${riskLevel}`">
    <!-- 标题区域 -->
    <div class="card-header">
      <div class="header-icon">
        <el-icon :size="24" :class="riskLevelIconClass">
          <component :is="riskLevelIcon" />
        </el-icon>
      </div>
      <div class="header-title">
        <span class="title-text">{{ title }}</span>
        <el-tag :type="riskLevelTagType" size="small">
          {{ riskLevelLabel }}
        </el-tag>
      </div>
    </div>

    <!-- 实体信息 -->
    <div class="entity-info" v-if="entityInfo">
      <div class="info-label">操作对象：</div>
      <div class="info-content">
        <span class="entity-name">{{ entityInfo.name }}</span>
        <span class="entity-id" v-if="entityInfo.id">(ID: {{ entityInfo.id }})</span>
        <div class="entity-source" v-if="entityInfo.source">
          <el-icon><Location /></el-icon>
          <span>{{ entityInfo.source }}</span>
        </div>
      </div>
    </div>

    <!-- 参数列表 -->
    <div class="params-section">
      <div class="section-header">
        <span class="section-label">操作参数：</span>
        <el-button
          v-if="allowEdit"
          size="small"
          text
          @click="toggleEditMode"
        >
          {{ isEditMode ? '取消修改' : '修改参数' }}
        </el-button>
      </div>

      <!-- 查看模式 -->
      <div class="params-list" v-if="!isEditMode">
        <div v-for="(value, key) in displayParams" :key="key" class="param-item">
          <span class="param-label">{{ getParamLabel(key) }}:</span>
          <span class="param-value">{{ formatParamValue(key, value) }}</span>
        </div>
      </div>

      <!-- 编辑模式 -->
      <div class="params-edit" v-if="isEditMode">
        <el-form :model="editedParams" label-width="100px" size="small">
          <el-form-item
            v-for="field in editableFields"
            :key="field.key"
            :label="field.label"
          >
            <el-input
              v-if="field.type === 'text'"
              v-model="editedParams[field.key]"
              :placeholder="field.placeholder"
            />
            <el-input
              v-if="field.type === 'number'"
              v-model.number="editedParams[field.key]"
              type="number"
              :placeholder="field.placeholder"
            />
            <el-select
              v-if="field.type === 'select'"
              v-model="editedParams[field.key]"
              :placeholder="field.placeholder"
            >
              <el-option
                v-for="option in field.options"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-date-picker
              v-if="field.type === 'date'"
              v-model="editedParams[field.key]"
              type="date"
              :placeholder="field.placeholder"
              value-format="YYYY-MM-DD"
            />
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- 证据链 -->
    <div class="evidence-section" v-if="evidenceChain">
      <div class="section-label">识别依据：</div>
      <div class="evidence-content">
        <div class="evidence-item" v-for="(item, idx) in evidenceChain" :key="idx">
          <el-icon><Document /></el-icon>
          <span>{{ item }}</span>
        </div>
      </div>
    </div>

    <!-- 撤销提示 -->
    <div class="undo-hint" v-if="undoTtl">
      <el-icon><Clock /></el-icon>
      <span>确认后 {{ undoTtl }} 秒内可撤销</span>
    </div>

    <!-- 操作按钮 -->
    <div class="card-actions">
      <el-button size="default" @click="handleCancel">取消</el-button>
      <el-button
        v-if="allowEdit && !isEditMode"
        size="default"
        type="warning"
        @click="toggleEditMode"
      >
        修改参数
      </el-button>
      <el-button
        v-if="isEditMode"
        size="default"
        type="info"
        @click="handleEditConfirm"
      >
        确认修改
      </el-button>
      <el-button
        size="default"
        :type="riskLevelButtonType"
        @click="handleConfirm"
        :loading="isLoading"
      >
        {{ confirmButtonText }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  Warning,
  InfoFilled,
  CircleCheckFilled,
  Location,
  Document,
  Clock
} from '@element-plus/icons-vue'

interface EntityInfo {
  name: string
  id?: number
  source?: string
}

interface EvidenceChain {
  items: string[]
}

interface Props {
  title: string
  riskLevel: 'low' | 'medium' | 'high'
  entityInfo?: EntityInfo
  params: Record<string, any>
  allowEdit?: boolean
  evidenceChain?: string[]
  undoTtl?: number
  isLoading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  riskLevel: 'medium',
  allowEdit: false,
  undoTtl: 10,
  isLoading: false
})

const emit = defineEmits<{
  cancel: []
  confirm: [params?: Record<string, any>]
  editParams: [params: Record<string, any>]
}>()

// 编辑状态
const isEditMode = ref(false)
const editedParams = ref<Record<string, any>>({})

// 初始化编辑参数
watch(() => props.params, (newParams) => {
  editedParams.value = { ...newParams }
}, { immediate: true })

// 风险等级图标
const riskLevelIcon = computed(() => {
  switch (props.riskLevel) {
    case 'high':
      return Warning
    case 'medium':
      return InfoFilled
    default:
      return CircleCheckFilled
  }
})

const riskLevelIconClass = computed(() => {
  return `icon-${props.riskLevel}`
})

const riskLevelLabel = computed(() => {
  switch (props.riskLevel) {
    case 'high':
      return '高风险'
    case 'medium':
      return '中风险'
    default:
      return '低风险'
  }
})

const riskLevelTagType = computed(() => {
  switch (props.riskLevel) {
    case 'high':
      return 'danger'
    case 'medium':
      return 'warning'
    default:
      return 'info'
  }
})

const riskLevelButtonType = computed(() => {
  switch (props.riskLevel) {
    case 'high':
      return 'danger'
    case 'medium':
      return 'warning'
    default:
      return 'primary'
  }
})

const confirmButtonText = computed(() => {
  if (isEditMode.value) {
    return '确认修改后执行'
  }
  switch (props.riskLevel) {
    case 'high':
      return '谨慎确认执行'
    default:
      return '确认执行'
  }
})

// 展示参数（过滤敏感信息）
const displayParams = computed(() => {
  const filtered: Record<string, any> = {}
  for (const [key, value] of Object.entries(props.params)) {
    // 过滤掉 ID 类字段（已在实体信息中展示）
    if (!key.endsWith('_id') && key !== 'id') {
      filtered[key] = value
    }
  }
  return filtered
})

// 可编辑字段配置
const editableFields = computed(() => {
  const fields: Array<{
    key: string
    label: string
    type: string
    placeholder?: string
    options?: Array<{ label: string; value: any }>
  }> = []

  for (const [key, value] of Object.entries(props.params)) {
    // 确定字段类型
    let type = 'text'
    if (typeof value === 'number') {
      type = 'number'
    }
    if (key.includes('date') || key.includes('time')) {
      type = 'date'
    }
    if (key === 'method') {
      type = 'select'
    }

    fields.push({
      key,
      label: getParamLabel(key),
      type,
      placeholder: `请输入${getParamLabel(key)}`,
      options: key === 'method' ? [
        { label: '电话', value: '电话' },
        { label: '微信', value: '微信' },
        { label: '邮件', value: '邮件' },
        { label: '拜访', value: '拜访' },
        { label: '其他', value: '其他' }
      ] : undefined
    })
  }

  return fields
})

// 参数标签映射
const PARAM_LABEL_MAP: Record<string, string> = {
  content: '跟进内容',
  method: '跟进方式',
  next_follow_time: '下次跟进时间',
  next_action: '下一步动作',
  actual_amount: '实际金额',
  actual_closing_date: '成交日期',
  customer_name: '客户名称',
  opportunity_name: '商机名称',
  lead_name: '线索名称'
}

function getParamLabel(key: string): string {
  return PARAM_LABEL_MAP[key] || key
}

function formatParamValue(key: string, value: any): string {
  if (value === null || value === undefined) {
    return '未设置'
  }
  if (typeof value === 'boolean') {
    return value ? '是' : '否'
  }
  if (key.includes('amount') && typeof value === 'number') {
    return `${value}万`
  }
  return String(value)
}

function toggleEditMode() {
  isEditMode.value = !isEditMode.value
  if (isEditMode.value) {
    editedParams.value = { ...props.params }
  }
}

function handleCancel() {
  emit('cancel')
}

function handleConfirm() {
  if (isEditMode.value) {
    emit('confirm', editedParams.value)
  } else {
    emit('confirm')
  }
}

function handleEditConfirm() {
  emit('editParams', editedParams.value)
  isEditMode.value = false
}
</script>

<style scoped lang="scss">
.confirmation-card {
  padding: 20px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);

  // 风险等级样式
  &.risk-low {
    border-left: 4px solid #67c23a;
  }

  &.risk-medium {
    border-left: 4px solid #e6a23c;
  }

  &.risk-high {
    border-left: 4px solid #f56c6c;
    background: #fef0f0;
  }
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;

  .header-icon {
    .icon-low {
      color: #67c23a;
    }
    .icon-medium {
      color: #e6a23c;
    }
    .icon-high {
      color: #f56c6c;
    }
  }

  .header-title {
    display: flex;
    align-items: center;
    gap: 8px;

    .title-text {
      font-size: 18px;
      font-weight: 600;
    }
  }
}

.entity-info {
  margin-bottom: 16px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;

  .info-label {
    font-size: 12px;
    color: #909399;
    margin-bottom: 8px;
  }

  .info-content {
    .entity-name {
      font-size: 16px;
      font-weight: 500;
      color: #303133;
    }

    .entity-id {
      font-size: 12px;
      color: #909399;
      margin-left: 8px;
    }

    .entity-source {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      color: #606266;
      margin-top: 8px;
    }
  }
}

.params-section {
  margin-bottom: 16px;

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;

    .section-label {
      font-size: 14px;
      color: #606266;
    }
  }

  .params-list {
    .param-item {
      display: flex;
      align-items: center;
      padding: 8px 12px;
      background: #f5f7fa;
      border-radius: 6px;
      margin-bottom: 8px;

      .param-label {
        width: 100px;
        font-size: 13px;
        color: #909399;
      }

      .param-value {
        font-size: 14px;
        color: #303133;
        flex: 1;
      }
    }
  }

  .params-edit {
    padding: 12px;
    background: #fafafa;
    border-radius: 8px;
  }
}

.evidence-section {
  margin-bottom: 16px;
  padding: 12px;
  background: #ecf5ff;
  border-radius: 8px;

  .section-label {
    font-size: 12px;
    color: #909399;
    margin-bottom: 8px;
  }

  .evidence-content {
    .evidence-item {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: #409eff;
      margin-bottom: 4px;
    }
  }
}

.undo-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #fdf6ec;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #e6a23c;
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}
</style>