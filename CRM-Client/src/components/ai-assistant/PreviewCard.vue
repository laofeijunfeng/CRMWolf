/**
 * AI 助手 - 内嵌预览卡片组件
 *
 * 展示操作预览：标题 + 风险标签 + 参数字段 + 操作按钮
 */
<template>
  <div class="preview-card">
    <!-- Header: 标题 + 风险标签 -->
    <div class="preview-card__header">
      <div class="preview-card__title-row">
        <el-icon class="preview-card__icon">
          <component :is="actionIconComponent" />
        </el-icon>
        <span class="preview-card__title">
          {{ title }}
        </span>
      </div>
      <span
        class="preview-card__tag"
        :class="tagClass"
      >
        {{ riskLabel }}
      </span>
    </div>

    <!-- Body: 参数字段 -->
    <div class="preview-card__body">
      <PreviewField
        v-for="field in displayFields"
        :key="field.key"
        :label="field.label"
        :value="field.displayValue"
        :type="field.type"
        :is-empty="field.isEmpty"
        :entity-type="field.entityType"
      />
    </div>

    <!-- Footer: 操作按钮 -->
    <div class="preview-card__footer">
      <button
        class="preview-card__btn preview-card__btn--confirm"
        :disabled="loading"
        @click="handleConfirm"
      >
        {{ loading ? '执行中...' : '确认执行' }}
      </button>
      <button
        class="preview-card__btn preview-card__btn--cancel"
        :disabled="loading"
        @click="handleCancel"
      >
        取消
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import type { Component } from 'vue'
import { Plus, Document, Trophy, Refresh, Delete, Search } from '@element-plus/icons-vue'
import PreviewField from './PreviewField.vue'
import {
  getActionConfig,
  formatFieldValue,
  type FieldConfig
} from '@/config/previewFieldConfig'

// ========== Props ==========

const props = defineProps({
  /** 操作类型 */
  actionType: {
    type: String,
    required: true
  },
  /** 参数数据 */
  params: {
    type: Object as PropType<Record<string, unknown>>,
    required: true
  },
  /** 风险等级（Task 5.9: 从后端传入） */
  riskLevel: {
    type: String as PropType<'LOW' | 'MEDIUM' | 'HIGH'>,
    default: 'LOW'
  },
  /** 加载状态 */
  loading: {
    type: Boolean,
    default: false
  }
})

// ========== Emits ==========

const emit = defineEmits<{
  (e: 'confirm', actionType: string, params: Record<string, unknown>): void
  (e: 'cancel'): void
}>()

// ========== Computed ==========

/** 操作配置 */
const actionConfig = computed(() => {
  return getActionConfig(props.actionType)
})

/** 标题 */
const title = computed(() => {
  if (!actionConfig.value) {
    return props.actionType
  }
  // 模板替换：如果有 name 字段，替换标题
  let titleText = actionConfig.value.titleTemplate
  const name = props.params['name'] || props.params['customer_name'] || props.params['opportunity_name']
  if (name) {
    titleText = `${titleText}: ${name}`
  }
  return titleText
})

/** 风险标签样式（Task 5.9: 简化映射） */
const tagClass = computed(() => {
  switch (props.riskLevel) {
    case 'HIGH': return 'preview-card__tag--danger'
    case 'MEDIUM': return 'preview-card__tag--warning'
    default: return 'preview-card__tag--success'
  }
})

/** 风险标签文本 */
const riskLabel = computed(() => {
  switch (props.riskLevel) {
    case 'HIGH': return '高风险'
    case 'MEDIUM': return '中风险'
    default: return '低风险'
  }
})

/** 操作图标组件 */
const actionIconComponent = computed(() => {
  // 根据操作类型返回 Element Plus 图标组件
  const iconMap: Record<string, Component> = {
    create_customer: Plus,
    create_follow_up: Document,
    win_opportunity: Trophy,
    update_customer_status: Refresh,
    delete_customer: Delete,
    query_customer: Search
  }
  return iconMap[props.actionType] || Plus
})

/** 展示字段列表 */
const displayFields = computed(() => {
  if (!actionConfig.value) {
    return []
  }

  return actionConfig.value.fields.map((field: FieldConfig) => {
    const rawValue = props.params[field.key]
    const isEmpty = rawValue === null || rawValue === undefined || rawValue === ''
    const displayValue = formatFieldValue(field, rawValue)

    return {
      key: field.key,
      label: field.label,
      type: field.type,
      entityType: field.entityType || '',
      isEmpty,
      displayValue
    }
  })
})

// ========== Methods ==========

function handleConfirm(): void {
  emit('confirm', props.actionType, props.params)
}

function handleCancel(): void {
  emit('cancel')
}
</script>

<style scoped lang="scss">
@import '@/styles/variables.scss';

.preview-card {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm;
  padding: $wolf-space-md;
  margin-top: $wolf-space-sm;
  background-color: $wolf-bg-card;
  border: 1px solid $wolf-border-light;
  border-radius: $wolf-radius-lg;

  // ========== Header ==========

  .preview-card__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: $wolf-space-sm;
  }

  .preview-card__title-row {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs;
  }

  .preview-card__icon {
    font-size: 16px;
    color: $wolf-primary;
  }

  .preview-card__title {
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-primary;
  }

  // 风险标签
  .preview-card__tag {
    display: inline-flex;
    align-items: center;
    padding: 0 $wolf-space-xs;
    height: $wolf-tag-height;
    font-size: $wolf-tag-font-size;
    font-weight: $wolf-font-weight-normal;
    border-radius: $wolf-tag-radius;

    // 低风险 - 成功色
    &--success {
      background-color: $wolf-tag-success-bg;
      color: $wolf-tag-success-text;
    }

    // 中风险 - 警告色
    &--warning {
      background-color: $wolf-tag-warning-bg;
      color: $wolf-tag-warning-text;
    }

    // 高风险 - 危险色
    &--danger {
      background-color: $wolf-tag-danger-bg;
      color: $wolf-tag-danger-text;
    }
  }

  // ========== Body ==========

  .preview-card__body {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-xs;
    padding: $wolf-space-sm 0;
  }

  // ========== Footer ==========

  .preview-card__footer {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding-top: $wolf-space-sm;
    border-top: 1px solid $wolf-border-light;
  }

  .preview-card__btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: $wolf-button-height-md;
    padding: $wolf-button-padding-md;
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-normal;
    border-radius: $wolf-radius-sm;
    cursor: pointer;
    transition: all 0.2s ease;

    // 确认按钮
    &--confirm {
      color: $wolf-text-inverse;
      background-color: $wolf-primary;
      border: none;

      &:hover:not(:disabled) {
        background-color: $wolf-primary-hover;
      }

      &:active:not(:disabled) {
        background-color: $wolf-primary-active;
      }

      &:disabled {
        background-color: $wolf-primary-disabled;
        cursor: not-allowed;
      }
    }

    // 取消按钮
    &--cancel {
      color: $wolf-btn-text;
      background-color: $wolf-btn-bg;
      border: 1px solid $wolf-border-default;

      &:hover:not(:disabled) {
        background-color: $wolf-btn-bg-hover;
        color: $wolf-btn-text-hover;
      }

      &:active:not(:disabled) {
        background-color: $wolf-btn-bg-active;
      }

      &:disabled {
        background-color: $wolf-bg-disabled;
        color: $wolf-text-disabled;
        cursor: not-allowed;
      }
    }
  }
}
</style>