/**
 * CRMWolf 统一空状态组件
 *
 * 设计原则（符合 frontend-design skill + UX-OPTIMIZATION-MOCKUP）：
 * - Invitation to act（不是 mood）
 * - 明确的下一步行为建议
 * - 品牌风格插图（低饱和蓝建筑）
 * - 业务化引导文案，有温度
 * - 信息层级：插图 → 标题 → 文案 → 按钮
 */
<template>
  <div class="wolf-empty">
    <!-- 品牌风格插图（SVG 内联） -->
    <div class="empty-illustration">
      <svg viewBox="0 0 120 120" class="brand-icon">
        <!-- 背景 -->
        <ellipse cx="60" cy="100" rx="40" ry="8" fill="#F5F5F3"/>
        <!-- 主体 - 简化建筑 -->
        <rect x="30" y="40" width="60" height="50" rx="6" fill="#4A6FA5" opacity="0.15"/>
        <rect x="35" y="45" width="50" height="40" rx="4" fill="#F8F6F2" stroke="#4A6FA5" stroke-width="1.5"/>
        <!-- 窗户 -->
        <rect x="42" y="55" width="10" height="12" rx="2" fill="#4A6FA5" opacity="0.3"/>
        <rect x="58" y="55" width="10" height="12" rx="2" fill="#4A6FA5" opacity="0.3"/>
        <rect x="50" y="72" width="12" height="13" rx="2" fill="#4A6FA5" opacity="0.2"/>
        <!-- 加号提示 -->
        <circle cx="90" cy="30" r="12" fill="#4A6FA5"/>
        <line x1="90" y1="24" x2="90" y2="36" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
        <line x1="84" y1="30" x2="96" y2="30" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
      </svg>
    </div>

    <!-- 业务化文案 -->
    <div class="empty-content">
      <span class="empty-title">{{ title }}</span>
      <span v-if="description" class="empty-hint">{{ description }}</span>
    </div>

    <!-- 行动按钮插槽 -->
    <slot name="action" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

// ========== Props ==========

const props = defineProps({
  /** Invitation 标题（"还没有客户记录"、"设置审批流程"等） */
  title: {
    type: String,
    required: true
  },
  /** 行为建议（"点击下方按钮添加第一个客户"等） */
  description: {
    type: String,
    default: ''
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

// ==================== Wolf Empty Container ====================

.wolf-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: $wolf-space-lg;
  min-height: 200px;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-sm;
}

// 品牌风格插图
.empty-illustration {
  margin-bottom: $wolf-space-md;
}

.brand-icon {
  width: 120px;
  height: 120px;
}

// 内容区域
.empty-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $wolf-space-sm;
  text-align: center;
  max-width: 300px;
}

// Invitation 标题（明确的行为建议）- Signature: IBM Plex Sans
.empty-title {
  font-family: $wolf-font-display;
  font-size: $wolf-font-size-body; // 16px
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

// 行为建议（具体的下一步）
.empty-hint {
  font-size: $wolf-font-size-body; // 14px
  font-weight: $wolf-font-weight-normal;
  color: $wolf-text-tertiary;
  line-height: $wolf-line-height-body; // 1.5
}

// 行动按钮样式（通过插槽传入）
// 使用示例：
// <WolfEmpty title="还没有客户记录" description="点击下方按钮添加第一个客户">
//   <template #action>
//     <el-button type="primary">+ 新建客户</el-button>
//   </template>
// </WolfEmpty>
</style>