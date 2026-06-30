<template>
  <div v-loading="loading" class="procurement-stage-flow">
    <el-card shadow="never" class="stage-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">采购阶段</span>
          <div v-if="currentStage" class="current-stage-info">
            <span class="current-stage-name">{{ currentStage.stage_name }}</span>
            <el-tag type="primary" size="small">
              赢率 {{ currentStage.win_probability }}%
            </el-tag>
          </div>
        </div>
      </template>

      <div class="stage-content">
        <!-- 进度条背景 -->
        <div class="progress-track">
          <div
            class="progress-fill"
            :style="{ width: progressWidth }"
          ></div>
        </div>

        <!-- 阶段节点 -->
        <div class="stage-nodes">
          <div
            v-for="(stage, index) in allStages"
            :key="stage.id"
            class="stage-node"
            :class="{
              'is-completed': isCompleted(stage),
              'is-current': isCurrent(stage),
              'is-clickable': canClickStage(stage),
              'is-skippable': stage.can_skip
            }"
            :aria-label="`阶段: ${stage.stage_name}, 赢率: ${stage.win_probability}%${isCurrent(stage) ? ', 当前阶段' : ''}${canClickStage(stage) ? ', 可点击推进' : ''}`"
            :tabindex="canClickStage(stage) ? 0 : -1"
            @click="handleStageClick(stage)"
            @keydown.enter="handleStageClick(stage)"
            @keydown.space.prevent="handleStageClick(stage)"
          >
            <!-- 节点图标 -->
            <div class="node-icon">
              <!-- 完成状态：勾选图标 -->
              <svg v-if="isCompleted(stage)" class="node-check" viewBox="0 0 24 24" fill="none">
                <path d="M5 13l4 4L19 7" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <!-- 当前状态：脉冲动画 -->
              <div v-else-if="isCurrent(stage)" class="node-pulse">
                <span class="pulse-ring"></span>
                <span class="pulse-dot"></span>
              </div>
              <!-- 等待状态：序号 -->
              <span v-else class="node-number">{{ index + 1 }}</span>
            </div>

            <!-- 节点信息 -->
            <div class="node-info">
              <span class="node-name">{{ stage.stage_name }}</span>
              <div class="node-meta">
                <el-tag
                  :type="isCompleted(stage) ? 'success' : isCurrent(stage) ? '' : 'info'"
                  size="small"
                  effect="plain"
                >
                  {{ stage.win_probability }}%
                </el-tag>
                <el-tag v-if="stage.can_skip" type="warning" size="small" effect="plain">
                  可跳过
                </el-tag>
              </div>
            </div>

            <!-- 可点击提示箭头 -->
            <svg
              v-if="canClickStage(stage) && !isCurrent(stage)"
              class="click-hint"
              viewBox="0 0 24 24"
            >
              <path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
        </div>

        <!-- 帮助提示 -->
        <div class="stage-hint">
          <svg class="hint-icon" viewBox="0 0 24 24">
            <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>点击未完成阶段可推进商机状态</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import procurementApi, {
  type OpportunityProcurementStageInfo
} from '@/api/procurement'

interface Props {
  opportunityId: number
}

const props = defineProps<Props>()

const loading = ref(false)
const isAdvancing = ref(false)

const allStages = ref<OpportunityProcurementStageInfo[]>([])

const currentStage = computed(() => {
  return allStages.value.find(stage => stage.is_current) || null
})

const progressWidth = computed(() => {
  if (!currentStage.value || allStages.value.length === 0) return '0%'
  const currentIndex = allStages.value.findIndex(s => s.id === currentStage.value?.id)
  const percentage = ((currentIndex + 1) / allStages.value.length) * 100
  return `${percentage}%`
})

const isCompleted = (stage: OpportunityProcurementStageInfo): boolean => {
  if (!currentStage.value) return false
  return stage.sort_order < currentStage.value.sort_order
}

const isCurrent = (stage: OpportunityProcurementStageInfo): boolean => {
  if (!currentStage.value) return false
  return stage.id === currentStage.value.id
}

const canClickStage = (stage: OpportunityProcurementStageInfo): boolean => {
  if (!currentStage.value) return true
  if (stage.id === currentStage.value.id) return false
  return stage.sort_order > currentStage.value.sort_order
}

const handleStageClick = async (stage: OpportunityProcurementStageInfo) => {
  if (!canClickStage(stage) || isAdvancing.value) return

  const isNewOpportunity = !currentStage.value
  const confirmMessage = isNewOpportunity
    ? `确定将商机的起始阶段设置为「${stage.stage_name}」？赢率将从 0% 变为 ${stage.win_probability}%。`
    : `确定将商机推进到「${stage.stage_name}」？赢率将从 ${currentStage.value?.win_probability}% 变为 ${stage.win_probability}%。`

  const confirmTitle = isNewOpportunity ? '设置起始阶段' : '推进阶段'

  try {
    await ElMessageBox.confirm(confirmMessage, confirmTitle, {
      confirmButtonText: '确认推进',
      cancelButtonText: '取消',
      type: 'info',
      customClass: 'stage-confirm-dialog'
    })

    isAdvancing.value = true
    loading.value = true

    try {
      await procurementApi.moveOpportunityStage(props.opportunityId, {
        stage_template_id: stage.id
      })
      ElMessage.success({
        message: `阶段已推进至「${stage.stage_name}」`,
        duration: 2000
      })
      await fetchOpportunityStages()
    } catch (error: any) {
      console.error('推进阶段失败', error)
      if (error?.response?.data?.detail) {
        ElMessage.error(error.response.data.detail)
      } else {
        ElMessage.error('阶段推进失败，请稍后重试')
      }
    } finally {
      loading.value = false
      isAdvancing.value = false
    }
  } catch {
    // 用户取消操作
  }
}

const fetchOpportunityStages = async () => {
  loading.value = true
  try {
    const stagesData = await procurementApi.getOpportunityProcurementStages(props.opportunityId) as any
    allStages.value = stagesData || []
  } catch (error) {
    console.error('获取采购阶段失败', error)
    ElMessage.error('获取采购阶段失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await fetchOpportunityStages()
})
</script>

<style scoped lang="scss">
.procurement-stage-flow {
  margin-bottom: var(--wolf-card-gap);
}

.stage-card {
  background: var(--wolf-bg-card);
  border-radius: var(--wolf-radius-lg);
  box-shadow: var(--wolf-shadow-card);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: var(--wolf-font-size-card-title);
  font-weight: var(--wolf-font-weight-semibold);
  color: var(--wolf-text-primary);
}

.current-stage-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.current-stage-name {
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
  color: var(--wolf-primary);
}

.stage-content {
  padding: var(--wolf-card-padding);
}

/* === 进度条 === */
.progress-track {
  height: 4px;
  background: var(--wolf-border-light);
  border-radius: 2px;
  margin-bottom: 24px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--wolf-success) 0%, var(--wolf-primary) 100%);
  border-radius: 2px;
  transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

/* === 阶段节点 === */
.stage-nodes {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  justify-content: stretch;
}

.stage-node {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 12px;
  border-radius: var(--wolf-radius-md);
  background: var(--wolf-bg-hover);
  border: 1px solid var(--wolf-border-light);
  transition: border-color 0.2s, box-shadow 0.2s, background-color 0.2s;
  min-width: 100px;
  flex-grow: 1;
  flex-basis: 0;
  cursor: default;
}

/* 可点击状态：初始视觉提示 */
.stage-node.is-clickable:not(.is-current) {
  cursor: pointer;
  border-color: var(--wolf-primary-lighter);
  background: var(--wolf-bg-hover);
  box-shadow: 0 2px 8px rgba(22, 93, 255, 0.06);
}

.stage-node.is-clickable:not(.is-current):hover {
  border-color: var(--wolf-primary);
  background: var(--wolf-primary-light);
  box-shadow: 0 4px 16px rgba(22, 93, 255, 0.15);
}

.stage-node.is-clickable:not(.is-current):focus-visible {
  outline: 2px solid var(--wolf-primary);
  outline-offset: 2px;
  border-color: var(--wolf-primary);
}

/* 当前状态 */
.stage-node.is-current {
  border-color: var(--wolf-primary);
  background: var(--wolf-primary-light);
  box-shadow: 0 4px 16px rgba(22, 93, 255, 0.2);
}

/* 完成状态 - 优雅的绿色点缀 */
.stage-node.is-completed {
  border-color: var(--wolf-success);
  background: transparent;
  box-shadow: none;
}

.stage-node.is-completed::before {
  content: '';
  position: absolute;
  top: 8px;
  left: 8px;
  right: 8px;
  bottom: 8px;
  border-radius: calc(var(--wolf-radius-md) - 4px);
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.05) 0%, rgba(34, 197, 94, 0.02) 100%);
  pointer-events: none;
}

/* === 节点图标 === */
.node-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  transition: all 0.2s;
}

.stage-node.is-completed .node-icon {
  background: var(--wolf-success);
  color: white;
  box-shadow: 0 2px 8px rgba(34, 197, 94, 0.3);
}

.stage-node.is-current .node-icon {
  background: var(--wolf-primary);
  color: white;
}

.stage-node:not(.is-completed):not(.is-current) .node-icon {
  background: var(--wolf-border-light);
  color: var(--wolf-text-tertiary);
}

.stage-node.is-clickable:not(.is-current):hover .node-icon {
  background: var(--wolf-primary);
  color: white;
}

.node-check {
  width: 20px;
  height: 20px;
}

.node-number {
  line-height: 1;
}

/* 脉冲动画 */
.node-pulse {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pulse-ring {
  position: absolute;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--wolf-primary);
  opacity: 0.3;
  animation: pulse 2s ease-out infinite;
}

.pulse-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: white;
}

@keyframes pulse {
  0% {
    transform: scale(1);
    opacity: 0.3;
  }
  100% {
    transform: scale(1.5);
    opacity: 0;
  }
}

/* === 节点信息 === */
.node-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.node-name {
  font-size: 14px;
  font-weight: var(--wolf-font-weight-medium);
  color: var(--wolf-text-primary);
  text-align: center;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stage-node.is-completed .node-name {
  color: var(--wolf-success);
  position: relative;
}

.stage-node.is-completed .node-name::after {
  content: '';
  position: absolute;
  bottom: -2px;
  left: 50%;
  transform: translateX(-50%);
  width: 60%;
  height: 2px;
  background: var(--wolf-success);
  border-radius: 1px;
  opacity: 0.5;
}

.stage-node.is-current .node-name {
  color: var(--wolf-primary);
  font-weight: var(--wolf-font-weight-semibold);
}

/* 阶段少时居中显示 */
.stage-nodes:has(.stage-node:nth-child(1):last-child),
.stage-nodes:has(.stage-node:nth-child(2):last-child),
.stage-nodes:has(.stage-node:nth-child(3):last-child) {
  justify-content: center;
}

.stage-nodes:has(.stage-node:nth-child(1):last-child) .stage-node,
.stage-nodes:has(.stage-node:nth-child(2):last-child) .stage-node,
.stage-nodes:has(.stage-node:nth-child(3):last-child) .stage-node {
  flex-grow: 0;
  min-width: 120px;
}

.node-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
}

/* === 点击提示箭头 === */
.click-hint {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 16px;
  height: 16px;
  color: var(--wolf-primary);
  opacity: 0;
  transition: opacity 0.2s;
}

.stage-node.is-clickable:not(.is-current):hover .click-hint {
  opacity: 1;
}

/* === 帮助提示 === */
.stage-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 16px;
  padding: 8px 12px;
  background: var(--wolf-bg-hover);
  border-radius: var(--wolf-radius-sm);
  color: var(--wolf-text-tertiary);
  font-size: 13px;
}

.hint-icon {
  width: 16px;
  height: 16px;
  color: var(--wolf-text-secondary);
}

/* === 响应式 === */
@media (max-width: 768px) {
  .stage-nodes {
    gap: 12px;
  }

  .stage-node {
    min-width: 80px;
    padding: 12px 8px;
  }

  .node-icon {
    width: 32px;
    height: 32px;
  }

  .node-name {
    font-size: 12px;
    max-width: 80px;
  }

  /* 移动端阶段少时居中 */
  .stage-nodes:has(.stage-node:nth-child(1):last-child) {
    justify-content: center;
  }

  .stage-nodes:has(.stage-node:nth-child(2):last-child) {
    justify-content: center;
  }

  .stage-nodes:has(.stage-node:nth-child(3):last-child) {
    justify-content: center;
  }
}

/* === 无障碍：减少动画 === */
@media (prefers-reduced-motion: reduce) {
  .progress-fill {
    transition: none;
  }

  .pulse-ring {
    animation: none;
  }

  .stage-node {
    transition: none;
  }
}
</style>