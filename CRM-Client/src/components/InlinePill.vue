<template>
  <div class="inline-pill" :class="{ 'expanded': isExpanded, [`risk-${riskLevel}`]: true }">
    <!-- 默认态（一行） -->
    <div class="pill-collapsed" v-if="!isExpanded">
      <div class="pill-content">
        <span class="pill-icon">📄</span>
        <span class="pill-summary">{{ actionDisplayName }}: {{ summaryText }}</span>
      </div>
      <div class="pill-actions">
        <el-button size="small" text @click="handleExpand">
          查看详情
        </el-button>
        <el-button size="small" type="primary" @click="handleConfirm">
          ✓ 确认
        </el-button>
        <el-button size="small" text @click="handleCancel">
          ↩ 取消
        </el-button>
      </div>
    </div>

    <!-- 展开态（多行） -->
    <div class="pill-expanded" v-if="isExpanded">
      <div class="pill-header">
        <span class="pill-title">{{ actionDisplayName }}</span>
        <el-tag :type="riskLevelTagType" size="small">
          {{ riskLevelLabel }}
        </el-tag>
      </div>

      <div class="pill-details">
        <div v-for="(value, key) in detailedParams" :key="key" class="detail-item">
          <span class="detail-label">{{ getParamLabel(key) }}:</span>
          <span class="detail-value">{{ formatParamValue(key, value) }}</span>
        </div>
      </div>

      <!-- 推荐选项（多歧义时） -->
      <div v-if="recommendation" class="pill-recommendation">
        <div class="recommendation-header">
          <el-icon><StarFilled /></el-icon>
          <span>推荐选项</span>
        </div>
        <div class="recommendation-option">
          <span class="option-name">{{ recommendation.option.name }}</span>
          <span class="option-details">{{ recommendation.option.details }}</span>
          <span class="option-reason">{{ recommendation.reason }}</span>
        </div>

        <!-- 切换下拉 -->
        <el-dropdown v-if="recommendation.alternatives?.length > 0">
          <el-button size="small" text>
            切换其他 <el-icon><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="alt in recommendation.alternatives"
                :key="alt.id"
                @click="handleSelectAlternative(alt.id)"
              >
                {{ alt.name }} - {{ alt.details }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <!-- 撤销提示 -->
      <div class="pill-undo-hint">
        <el-icon><Clock /></el-icon>
        <span>确认后 {{ undoTtl }} 秒内可撤销</span>
      </div>

      <div class="pill-actions-expanded">
        <el-button type="primary" size="default" @click="handleConfirm">
          ✓ 确认执行
        </el-button>
        <el-button size="default" @click="handleCancel">
          ↩ 取消
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { StarFilled, ArrowDown, Clock } from '@element-plus/icons-vue'

interface RecommendationOption {
  id: number
  name: string
  details: string
}

interface Recommendation {
  option: RecommendationOption
  reason: string
  alternatives: RecommendationOption[]
}

interface Props {
  actionType: string
  actionDisplayName: string
  params: Record<string, any>
  riskLevel: 'low' | 'medium' | 'high'
  summaryText: string
  detailedParams: Record<string, any>
  recommendation?: Recommendation
  undoTtl: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  confirm: [params?: Record<string, any>]
  cancel: []
  expand: []
  selectAlternative: [id: number]
}>()

const isExpanded = ref(false)

// 风险等级映射
const riskLevelTagType = computed(() => {
  switch (props.riskLevel) {
    case 'high': return 'danger'
    case 'medium': return 'warning'
    default: return 'info'
  }
})

const riskLevelLabel = computed(() => {
  switch (props.riskLevel) {
    case 'high': return '高风险'
    case 'medium': return '中风险'
    default: return '低风险'
  }
})

// 参数标签映射
const PARAM_LABEL_MAP: Record<string, string> = {
  content: '跟进内容',
  method: '跟进方式',
  next_follow_time: '下次跟进时间',
  opportunity_name: '商机名称',
  customer_name: '客户名称',
  lead_name: '线索名称',
  actual_amount: '实际金额',
  actual_closing_date: '成交日期',
  stage_name: '阶段',
  win_probability: '赢率'
}

function getParamLabel(key: string): string {
  return PARAM_LABEL_MAP[key] || key
}

function formatParamValue(key: string, value: any): string {
  if (value === null || value === undefined) return '未设置'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') {
    if (key.includes('amount')) return `${value}万`
    if (key.includes('probability')) return `${value}%`
    return String(value)
  }
  return String(value)
}

function handleExpand() {
  isExpanded.value = !isExpanded.value
  emit('expand')
}

function handleConfirm() {
  emit('confirm')
}

function handleCancel() {
  emit('cancel')
}

function handleSelectAlternative(id: number) {
  emit('selectAlternative', id)
}
</script>

<style scoped lang="scss">
.inline-pill {
  margin: 12px 0;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 8px;

  // 风险等级边框
  &.risk-low {
    border-left: 3px solid #67c23a;
  }
  &.risk-medium {
    border-left: 3px solid #e6a23c;
  }
  &.risk-high {
    border-left: 3px solid #f56c6c;
    background: #fef0f0;
  }

  &.expanded {
    padding: 16px;
    background: #fff;
  }
}

.pill-collapsed {
  display: flex;
  align-items: center;
  justify-content: space-between;

  .pill-content {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;

    .pill-icon {
      font-size: 16px;
    }

    .pill-summary {
      font-size: 14px;
      color: #303133;
    }
  }

  .pill-actions {
    display: flex;
    align-items: center;
    gap: 4px;
  }
}

.pill-expanded {
  .pill-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;

    .pill-title {
      font-size: 16px;
      font-weight: 500;
    }
  }

  .pill-details {
    margin-bottom: 12px;

    .detail-item {
      display: flex;
      align-items: center;
      padding: 4px 0;

      .detail-label {
        width: 100px;
        font-size: 13px;
        color: #909399;
      }

      .detail-value {
        font-size: 14px;
        color: #303133;
      }
    }
  }

  .pill-recommendation {
    padding: 12px;
    background: #ecf5ff;
    border-radius: 6px;
    margin-bottom: 12px;

    .recommendation-header {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      color: #409eff;
      margin-bottom: 8px;
    }

    .recommendation-option {
      .option-name {
        font-size: 14px;
        font-weight: 500;
        color: #303133;
      }

      .option-details {
        font-size: 12px;
        color: #606266;
        margin-left: 8px;
      }

      .option-reason {
        font-size: 12px;
        color: #409eff;
        margin-left: 8px;
      }
    }
  }

  .pill-undo-hint {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: #e6a23c;
    margin-bottom: 12px;
  }

  .pill-actions-expanded {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding-top: 12px;
    border-top: 1px solid #ebeef5;
  }
}
</style>