<template>
  <div class="workflow-mini-map">
    <div class="mini-map-header">
      <el-icon><Location /></el-icon>
      <span>流程进度</span>
    </div>

    <div class="mini-map-steps">
      <div
        v-for="(step, index) in steps"
        :key="step.id"
        class="mini-map-step"
        :class="`step-${step.status}`"
      >
        <!-- 步骤图标 -->
        <div class="step-icon">
          <el-icon v-if="step.status === 'completed'" class="icon-completed">
            <CircleCheckFilled />
          </el-icon>
          <el-icon v-else-if="step.status === 'running'" class="is-loading">
            <Loading />
          </el-icon>
          <el-icon v-else class="icon-pending">
            <Clock />
          </el-icon>
        </div>

        <!-- 步骤内容 -->
        <div class="step-content">
          <div class="step-name">{{ step.name }}</div>

          <!-- 步骤结果 -->
          <div v-if="step.result" class="step-result">
            <span :class="step.result.success ? 'success' : 'failed'">
              {{ step.result.message }}
            </span>
          </div>

          <!-- 当前步骤的 Inline Pill -->
          <InlinePill
            v-if="step.status === 'running' && step.inlinePill"
            :action-type="step.inlinePill.actionType"
            :action-display-name="step.inlinePill.actionDisplayName"
            :params="step.inlinePill.params"
            :risk-level="step.inlinePill.riskLevel"
            :summary-text="step.inlinePill.summaryText"
            :detailed-params="step.inlinePill.detailedParams"
            :recommendation="step.inlinePill.recommendation"
            :undo-ttl="step.inlinePill.undoTtl"
            @confirm="handleConfirm"
            @cancel="handleCancel"
            @select-alternative="handleSelectAlternative"
          />
        </div>

        <!-- 连接线 -->
        <div v-if="index < steps.length - 1" class="step-connector">
          <div class="connector-line" :class="connectorClass(step.status)"></div>
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="mini-map-actions">
      <el-button size="small" @click="handleUndoLast">
        撤销上一步
      </el-button>
      <el-button size="small" type="warning" @click="handlePause">
        暂停流程
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Location, CircleCheckFilled, Loading, Clock } from '@element-plus/icons-vue'
import InlinePill from './InlinePill.vue'

interface StepResult {
  success: boolean
  message: string
}

interface InlinePillData {
  actionType: string
  actionDisplayName: string
  params: Record<string, unknown>
  riskLevel: 'low' | 'medium' | 'high'
  summaryText: string
  detailedParams: Record<string, unknown>
  recommendation?: unknown
  undoTtl: number
}

interface Step {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  result?: StepResult
  inlinePill?: InlinePillData
}

interface Props {
  steps: Step[]
  currentStep: number
}

defineProps<Props>()

const emit = defineEmits<{
  confirm: [params?: unknown]
  cancel: []
  selectAlternative: [id: number]
  undoLast: []
  pause: []
}>()

function connectorClass(status: string): string {
  if (status === 'completed') return 'completed'
  return 'pending'
}

function handleConfirm(params?: unknown) {
  emit('confirm', params)
}

function handleCancel() {
  emit('cancel')
}

function handleSelectAlternative(id: number) {
  emit('selectAlternative', id)
}

function handleUndoLast() {
  emit('undoLast')
}

function handlePause() {
  emit('pause')
}
</script>

<style scoped lang="scss">
.workflow-mini-map {
  margin: 16px 0;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;

  .mini-map-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    font-weight: 500;
    color: #303133;
    margin-bottom: 16px;
  }

  .mini-map-steps {
    .mini-map-step {
      position: relative;
      padding: 8px 0;

      .step-icon {
        position: absolute;
        left: 0;
        top: 8px;
        width: 24px;
        height: 24px;

        .icon-completed {
          color: #67c23a;
        }

        .icon-pending {
          color: #c0c4cc;
        }
      }

      .step-content {
        margin-left: 32px;

        .step-name {
          font-size: 14px;
          color: #303133;
          margin-bottom: 4px;
        }

        .step-result {
          font-size: 12px;

          .success {
            color: #67c23a;
          }

          .failed {
            color: #f56c6c;
          }
        }
      }

      &.step-running {
        .step-content {
          .step-name {
            color: #e6a23c;
            font-weight: 500;
          }
        }
      }

      &.step-failed {
        .step-content {
          .step-name {
            color: #f56c6c;
          }
        }
      }

      .step-connector {
        position: absolute;
        left: 11px;
        top: 32px;
        height: 24px;
        width: 2px;

        .connector-line {
          width: 2px;
          height: 100%;
          background: #c0c4cc;

          &.completed {
            background: #67c23a;
          }
        }
      }
    }
  }

  .mini-map-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid #ebeef5;
  }
}
</style>