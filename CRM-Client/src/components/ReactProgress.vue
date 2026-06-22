<template>
  <div class="react-progress">
    <!-- 轮数进度条 -->
    <div class="round-indicator">
      <span class="round-label">Round {{ currentRound }}/{{ maxRounds }}</span>
      <el-progress
        :percentage="(currentRound / maxRounds) * 100"
        :show-text="false"
        :stroke-width="4"
      />
    </div>

    <!-- 已完成轮数展示 -->
    <div v-if="previousResults.length > 0" class="previous-rounds">
      <div class="round-header">
        <el-icon><Check /></el-icon>
        <span>已完成 Round {{ currentRound - 1 }}</span>
      </div>
      <div class="round-tools">
        <div
          v-for="result in previousResults"
          :key="`${result.tool}-${result.message}`"
          class="tool-result"
        >
          <span class="tool-name">{{ getToolDisplayName(result.tool) }}</span>
          <el-tag :type="result.success ? 'success' : 'danger'" size="small">
            {{ result.success ? '成功' : result.message === '用户跳过' ? '跳过' : '失败' }}
          </el-tag>
        </div>
      </div>
    </div>

    <!-- 当前轮结果展示 -->
    <div v-if="currentRoundResults && currentRoundResults.length > 0" class="current-round">
      <div class="round-header">
        <el-icon><Loading /></el-icon>
        <span>Round {{ currentRound }} 执行中</span>
      </div>
      <div class="round-tools">
        <div
          v-for="result in currentRoundResults"
          :key="`${result.tool}-${result.message}`"
          class="tool-result"
        >
          <span class="tool-name">{{ getToolDisplayName(result.tool) }}</span>
          <el-tag :type="result.success ? 'success' : 'info'" size="small">
            {{ result.success ? '成功' : '跳过' }}
          </el-tag>
        </div>
      </div>
    </div>

    <!-- 当前轮加载状态 -->
    <div v-if="isLoading" class="current-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>AI 正在分析下一步操作...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Check, Loading } from '@element-plus/icons-vue'
import type { ExecutedResult } from '@/api/aiAssistant'

interface Props {
  currentRound: number
  maxRounds: number
  previousResults: ExecutedResult[]
  currentRoundResults?: ExecutedResult[]
  isLoading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  previousResults: () => [],
  currentRoundResults: () => [],
  isLoading: false
})

// 使用 props 避免 TS6133 错误
console.assert(props.currentRound > 0, 'currentRound should be positive')

/**
 * 获取工具显示名称
 */
function getToolDisplayName(toolName: string): string {
  const toolNames: Record<string, string> = {
    follow_up_customer: '创建跟进记录',
    win_opportunity: '标记商机赢单',
    lose_opportunity: '标记商机输单',
    create_opportunity: '创建商机',
    update_opportunity_stage: '推进商机阶段',
    create_contract: '创建合同',
    query_contracts: '查询合同',
    get_contract_detail: '获取合同详情',
    update_contract_status: '更新合同状态',
    create_payment_plan: '创建回款计划',
    create_payment_record: '登记回款',
    query_payment_records: '查询回款记录',
    confirm_payment: '确认回款',
    create_invoice_application: '申请开票',
    query_invoice_applications: '查询开票申请',
    get_invoice_application_detail: '获取开票申请详情'
  }
  return toolNames[toolName] || toolName
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.react-progress {
  padding: $wolf-space-md;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-md;
  margin-bottom: $wolf-space-md;

  .round-indicator {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    margin-bottom: $wolf-space-md;

    .round-label {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      min-width: 80px;
    }

    .el-progress {
      flex: 1;
    }
  }

  .previous-rounds,
  .current-round {
    margin-bottom: $wolf-space-sm;

    .round-header {
      display: flex;
      align-items: center;
      gap: $wolf-space-xs;
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      margin-bottom: $wolf-space-xs;

      .el-icon {
        font-size: 14px;
      }
    }

    .round-tools {
      padding-left: $wolf-space-md;

      .tool-result {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: $wolf-space-xs 0;

        .tool-name {
          font-size: $wolf-font-size-caption;
          color: $wolf-text-primary;
        }
      }
    }
  }

  .previous-rounds {
    .round-header {
      color: $wolf-success;

      .el-icon {
        color: $wolf-success;
      }
    }
  }

  .current-round {
    .round-header {
      color: $wolf-primary;

      .el-icon {
        color: $wolf-primary;
      }
    }
  }

  .current-loading {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-md;
    background: $wolf-primary-light;
    border-radius: $wolf-radius-sm;

    .el-icon {
      font-size: 16px;
      color: $wolf-primary;
    }

    span {
      font-size: $wolf-font-size-caption;
      color: $wolf-primary;
    }
  }
}
</style>