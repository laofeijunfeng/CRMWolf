/**
 * ErrorState — 项目首统一错误态组件（C-DSG-4 Error / C-DSG-7 条12 403 兜底）
 *
 * 设计目的：项目此前无统一错误态，散落各处用 el-empty / 自写 div 表达。
 * Phase C 引入审批后必须覆盖 5 态（Loading/Empty/Error/Success/Conflict），
 * Error 态为本组件。支持 `variant: 'error'|'forbidden'`：
 * - 'error'    通用加载失败 / 服务器错误（默认）
 * - 'forbidden' 403 权限态（C-DSG-7 条12），用 Lock 图标，文案"你没有该操作权限"
 *
 * 信息层级：图标 → 标题 → 描述 → 行动按钮（slot#action）。文案不道歉、不模糊。
 */
<script setup lang="ts">
import { computed } from 'vue'
import type { PropType, Component } from 'vue'
import { WarningFilled, Lock } from '@element-plus/icons-vue'

interface VariantConfig {
  icon: Component
  iconVar: string
  bgVar: string
}

const VARIANT_MAP: Record<'error' | 'forbidden', VariantConfig> = {
  error: {
    icon: WarningFilled,
    iconVar: '--wolf-danger-text',
    bgVar: '--wolf-danger-bg'
  },
  forbidden: {
    icon: Lock,
    iconVar: '--wolf-danger-text',
    bgVar: '--wolf-danger-bg'
  }
}

const props = defineProps({
  variant: {
    type: String as PropType<'error' | 'forbidden'>,
    default: 'error'
  },
  title: {
    type: String,
    required: true
  },
  description: {
    type: String,
    default: ''
  }
})

const config = computed<VariantConfig>(() => VARIANT_MAP[props.variant])

const iconStyle = computed<Record<string, string>>(() => ({
  color: `var(${config.value.iconVar})`,
  backgroundColor: `var(${config.value.bgVar})`
}))
</script>

<template>
  <div class="error-state" role="alert" :aria-label="title">
    <div class="error-state__icon" :style="iconStyle">
      <el-icon :size="32">
        <component :is="config.icon" />
      </el-icon>
    </div>
    <div class="error-state__content">
      <span class="error-state__title">{{ title }}</span>
      <span v-if="description" class="error-state__description">{{ description }}</span>
    </div>
    <div v-if="$slots['action']" class="error-state__action">
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped lang="scss">
@import '@/styles/variables.scss';

.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-md;
  padding: $wolf-space-lg;
  min-height: 200px;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  text-align: center;
}

.error-state__icon {
  width: 56px;
  height: 56px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: $wolf-radius-full;
}

.error-state__content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $wolf-space-sm;
  max-width: 360px;
}

.error-state__title {
  font-family: $wolf-font-display;
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.error-state__description {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
  line-height: $wolf-line-height-body;
}

.error-state__action {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}
</style>