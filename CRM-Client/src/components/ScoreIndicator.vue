/**
 * ScoreIndicator — 热力值指示器组件
 *
 * 设计目的：
 * - 统一客户/线索热力值视觉语言
 * - 使用 Lucide SVG 图标替代 emoji
 * - 遵循 V2 设计规范（颜色、圆角、字体）
 *
 * 颜色映射（参考 Leads.vue）：
 * - 高分（≥80）: 危险红色（热）- $wolf-danger-v2
 * - 中高（≥60）: 警告橙色 - $wolf-warning-v2
 * - 中等（≥40）: 成功绿色 - $wolf-success-v2
 * - 低分/未知: 中性灰色 - $wolf-text-tertiary-v2
 *
 * 使用场景：
 * - 客户列表页热力值列
 * - 线索列表页热力值列
 * - 详情页热力值卡片
 *
 * 无障碍：
 * - role="status" 标记状态信息
 * - aria-label 包含分数和级别
 */
<script setup lang="ts">
import { computed } from 'vue'
import { Flame, Zap, CheckCircle, TrendingDown, HelpCircle } from 'lucide-vue-next'

export type ScoreLevel = 'high' | 'medium-high' | 'medium' | 'low' | 'unknown'

export interface ScoreIndicatorProps {
  /** 分数值 (null 表示未知) */
  score: number | null
  /** 显示模式: 'badge' 列表页紧凑模式 | 'card' 详情页卡片模式 */
  mode?: 'badge' | 'card'
  /** 是否显示级别文字标签 */
  showLevel?: boolean
}

const props = withDefaults(defineProps<ScoreIndicatorProps>(), {
  mode: 'badge',
  showLevel: false
})

// 分数级别判定
const level = computed<ScoreLevel>(() => {
  if (props.score === null) return 'unknown'
  if (props.score >= 80) return 'high'
  if (props.score >= 60) return 'medium-high'
  if (props.score >= 40) return 'medium'
  return 'low'
})

// 图标组件映射
const iconComponent = computed(() => {
  const iconMap = {
    high: Flame,
    'medium-high': Zap,
    medium: CheckCircle,
    low: TrendingDown,
    unknown: HelpCircle
  }
  return iconMap[level.value]
})

// 级别文字映射
const levelText = computed(() => {
  const textMap: Record<ScoreLevel, string> = {
    high: '高',
    'medium-high': '中高',
    medium: '中',
    low: '低',
    unknown: '未知'
  }
  return textMap[level.value]
})

// aria-label
const ariaLabel = computed(() => {
  if (props.score === null) return '热力值未知'
  return `热力值 ${props.score} 分，级别: ${levelText.value}`
})

// 样式类
const indicatorClasses = computed(() => [
  'score-indicator',
  `score-indicator--${props.mode}`,
  `score-level--${level.value}`
])
</script>

<template>
  <div
    :class="indicatorClasses"
    role="status"
    :aria-label="ariaLabel"
  >
    <component :is="iconComponent" class="score-icon" />
    <span class="score-value">{{ score ?? '--' }}</span>
    <span v-if="showLevel && mode === 'card'" class="score-level-text">
      {{ levelText }}
    </span>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// ========== 基础样式 ==========
.score-indicator {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: $wolf-font-weight-medium-v2;
}

// ========== 图标样式 ==========
.score-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

// ========== Badge 模式（列表页）- 无背景，参考 Leads.vue ==========
.score-indicator--badge {
  gap: 4px;

  .score-icon {
    width: 16px;
    height: 16px;
  }

  .score-value {
    font-size: $wolf-font-size-auxiliary-v2;
  }
}

// ========== Card 模式（详情页）==========
.score-indicator--card {
  gap: 6px;

  .score-icon {
    width: 20px;
    height: 20px;
  }

  .score-value {
    font-size: 18px;
    font-weight: $wolf-font-weight-semibold-v2;
  }

  .score-level-text {
    font-size: $wolf-font-size-caption-v2;
    padding: 2px 6px;
    border-radius: $wolf-radius-sm-v2;
    background: $wolf-bg-muted-v2;
  }
}

// ========== 级别颜色（V2 设计规范）==========
// 参考 Leads.vue 的颜色映射
// 高分（≥80）: 危险红色（热）
.score-level--high {
  .score-icon {
    color: $wolf-danger-v2;
  }
  .score-value {
    color: $wolf-text-primary-v2;
  }
}

// 中高（≥60）: 警告橙色
.score-level--medium-high {
  .score-icon {
    color: $wolf-warning-v2;
  }
  .score-value {
    color: $wolf-text-primary-v2;
  }
}

// 中等（≥40）: 成功绿色
.score-level--medium {
  .score-icon {
    color: $wolf-success-v2;
  }
  .score-value {
    color: $wolf-text-primary-v2;
  }
}

// 低分（<40）: 中性灰色
.score-level--low {
  .score-icon {
    color: $wolf-text-tertiary-v2;
  }
  .score-value {
    color: $wolf-text-tertiary-v2;
  }
}

// 未知: 中性灰色
.score-level--unknown {
  .score-icon {
    color: $wolf-text-tertiary-v2;
  }
  .score-value {
    color: $wolf-text-tertiary-v2;
  }
}
</style>