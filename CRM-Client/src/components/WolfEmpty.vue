/**
 * CRMWolf 统一空状态组件
 *
 * 设计原则（符合 frontend-design skill）：
 * - Invitation to act（不是 mood）
 * - 明确的下一步行为建议
 * - 统一的品牌风格
 */
<template>
  <el-empty :image-size="imageSize">
    <template #description>
      <div class="wolf-empty-content">
        <span class="wolf-empty-title">{{ title }}</span>
        <span class="wolf-empty-desc">{{ description }}</span>
      </div>
    </template>

    <!-- 行动按钮插槽 -->
    <slot name="action" />
  </el-empty>
</template>

<script setup lang="ts">
import { computed } from 'vue'

// ========== Props ==========

const props = defineProps({
  /** Invitation 标题（"设置审批流程"、"添加客户"等） */
  title: {
    type: String,
    required: true
  },
  /** 行为建议（"点击添加审批节点，配置审批权限"等） */
  description: {
    type: String,
    default: ''
  },
  /** 图标大小 */
  imageSize: {
    type: Number,
    default: 120
  }
})

// ========== Computed ==========

/** 是否显示描述（如果有描述才显示） */
const hasDescription = computed(() => {
  return props.description && props.description.trim().length > 0
})
</script>

<style scoped lang="scss">
@import '@/styles/variables.scss';

// ==================== Wolf Empty Content ====================

.wolf-empty-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $wolf-space-xs;
  text-align: center;
}

// Invitation 标题（明确的行为建议）
.wolf-empty-title {
  // ← Signature: IBM Plex Sans（性格化字体）
  font-family: $wolf-font-display;
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-secondary;
}

// 行为建议（具体的下一步）
.wolf-empty-desc {
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  color: $wolf-text-tertiary;
}
</style>