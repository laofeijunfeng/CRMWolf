/**
 * AI 助手 - 预览字段组件
 *
 * 展示单个参数字段：标签 + 值
 */
<template>
  <div class="preview-field">
    <span class="preview-field__label">
      {{ label }}
    </span>
    <span
      class="preview-field__value"
      :class="valueClass"
    >
      <template v-if="isEntity">
        <!-- 实体类型：显示为链接样式 -->
        <span class="preview-field__entity">
          {{ displayValue }}
        </span>
      </template>
      <template v-else>
        {{ displayValue }}
      </template>
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import type { FieldType } from '@/config/previewFieldConfig'

// ========== Props ==========

const props = defineProps({
  /** 字段标签 */
  label: {
    type: String,
    required: true
  },
  /** 字段值 */
  value: {
    type: [String, Number, null] as PropType<string | number | null>,
    default: null
  },
  /** 字段类型 */
  type: {
    type: String as PropType<FieldType>,
    default: 'text'
  },
  /** 是否为空值 */
  isEmpty: {
    type: Boolean,
    default: false
  },
  /** 实体类型（用于 entity 类型） */
  entityType: {
    type: String,
    default: ''
  }
})

// ========== Computed ==========

/** 是否为实体类型 */
const isEntity = computed(() => {
  return props.type === 'entity' && !props.isEmpty
})

/** 显示值 */
const displayValue = computed(() => {
  if (props.isEmpty) {
    return '-'
  }
  return String(props.value)
})

/** 值样式类 */
const valueClass = computed(() => {
  if (props.isEmpty) {
    return 'preview-field__value--empty'
  }
  if (props.type === 'entity') {
    return 'preview-field__value--entity'
  }
  return ''
})
</script>

<style scoped lang="scss">
@import '@/styles/variables.scss';

.preview-field {
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-md;
  padding: $wolf-space-xs 0;

  // 标签
  .preview-field__label {
    flex-shrink: 0;
    width: 80px;
    font-size: $wolf-font-size-caption;
    font-weight: $wolf-font-weight-normal;
    color: $wolf-text-tertiary;
    line-height: $wolf-line-height-body;
  }

  // 值
  .preview-field__value {
    flex: 1;
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-normal;
    color: $wolf-text-primary;
    line-height: $wolf-line-height-body;
    word-break: break-word;

    // 空值样式
    &--empty {
      color: $wolf-text-placeholder;
    }

    // 实体链接样式
    &--entity {
      color: $wolf-primary;
      cursor: pointer;

      &:hover {
        color: $wolf-primary-hover;
      }
    }
  }

  // 实体内容
  .preview-field__entity {
    display: inline;
  }
}
</style>