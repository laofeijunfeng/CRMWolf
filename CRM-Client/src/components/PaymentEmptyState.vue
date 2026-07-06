<script setup lang="ts">
/**
 * PaymentEmptyState.vue - Task 7.4
 *
 * Unified empty state component for payment module.
 * Supports 3 variations: no plans, no records, no approval config.
 *
 * Design: Uses $wolf-* design tokens, Calendar/Wallet icons,
 * provides clear action suggestions.
 */

import { useRouter } from 'vue-router'
import { Calendar, Wallet, Document } from '@element-plus/icons-vue'

const router = useRouter()

type EmptyType = 'no-plans' | 'no-records' | 'no-approval-config'

interface Props {
  type: EmptyType
  showAction?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showAction: true
})

const emptyConfig = computed(() => {
  switch (props.type) {
    case 'no-plans':
      return {
        icon: Calendar,
        description: '还没有回款计划',
        actionLabel: '创建回款计划',
        actionPath: '/contracts'
      }
    case 'no-records':
      return {
        icon: Wallet,
        description: '还没有登记回款',
        actionLabel: '前往回款计划',
        actionPath: '/payments'
      }
    case 'no-approval-config':
      return {
        icon: Document,
        description: '未配置审批流程',
        actionLabel: '联系管理员',
        actionPath: ''
      }
    default:
      return {
        icon: Calendar,
        description: '暂无数据',
        actionLabel: '',
        actionPath: ''
      }
  }
})

const handleAction = (): void => {
  if (emptyConfig.value.actionPath.length > 0) {
    router.push(emptyConfig.value.actionPath)
  }
}

import { computed } from 'vue'
</script>

<template>
  <div class="payment-empty-state">
    <el-empty :description="emptyConfig.description">
      <template #image>
        <el-icon class="empty-icon" :size="60">
          <component :is="emptyConfig.icon" />
        </el-icon>
      </template>

      <el-button
        v-if="showAction && emptyConfig.actionLabel.length > 0"
        type="primary"
        size="default"
        @click="handleAction"
      >
        {{ emptyConfig.actionLabel }}
      </el-button>

      <template #footer>
        <p v-if="type === 'no-plans'" class="empty-hint">
          回款计划可在合同详情页中创建
        </p>
        <p v-if="type === 'no-records'" class="empty-hint">
          找到回款计划后点击"登记回款"开始记录
        </p>
        <p v-if="type === 'no-approval-config'" class="empty-hint">
          回款审批流程需要管理员在系统设置中配置
        </p>
      </template>
    </el-empty>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.payment-empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: $wolf-space-lg * 2;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  min-height: 300px;

  .el-empty {
    padding: $wolf-space-lg;
  }

  .empty-icon {
    color: $wolf-text-placeholder;
    opacity: 0.6;
  }

  .empty-hint {
    margin-top: $wolf-space-sm;
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
    line-height: $wolf-line-height-normal;
  }
}

// Reduced motion support
@media (prefers-reduced-motion: reduce) {
  .payment-empty-state {
    transition: none;
  }
}
</style>