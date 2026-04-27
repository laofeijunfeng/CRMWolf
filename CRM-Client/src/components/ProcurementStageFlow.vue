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
        <el-steps 
          :active="currentStepIndex" 
          align-center
          finish-status="success"
          process-status="process"
          class="stage-steps"
        >
          <el-step
            v-for="stage in allStages"
            :key="stage.id"
            :status="getStepStatus(stage)"
            :class="{
              'is-finish': getStepStatus(stage) === 'success',
              'is-process': getStepStatus(stage) === 'process',
              'is-wait': getStepStatus(stage) === 'wait'
            }"
            class="stage-step"
          >
            <template #icon>
              <div 
                class="step-icon-wrapper"
                :class="{ 'is-clickable': canClickStage(stage) }"
                @click.stop="handleStageClick(stage)"
              >
                <span class="step-win-rate">{{ stage.win_probability }}%</span>
              </div>
            </template>

            <template #title>
              <div 
                class="step-title"
                :class="{ 'is-clickable': canClickStage(stage) }"
                @click.stop="handleStageClick(stage)"
              >{{ stage.stage_name }}</div>
            </template>
            
            <template #description>
              <div class="step-description">
                <div class="step-meta">
                  <el-tag v-if="stage.can_skip" size="small" type="warning">可跳过</el-tag>
                </div>
              </div>
            </template>
          </el-step>
        </el-steps>
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

const allStages = ref<OpportunityProcurementStageInfo[]>([])

const currentStage = computed(() => {
  return allStages.value.find(stage => stage.is_current) || null
})

const currentStepIndex = computed(() => {
  if (!currentStage.value) return 0
  return allStages.value.findIndex(s => s.id === currentStage.value?.id)
})

const getStepStatus = (stage: OpportunityProcurementStageInfo): 'success' | 'process' | 'wait' => {
  if (!currentStage.value) return 'wait'
  if (stage.id === currentStage.value.id) return 'process'
  if (stage.sort_order < currentStage.value.sort_order) return 'success'
  return 'wait'
}

onMounted(async () => {
  await fetchOpportunityStages()
})

const canClickStage = (stage: OpportunityProcurementStageInfo) => {
  if (!currentStage.value) {
    return true
  }
  if (stage.id === currentStage.value.id) {
    return false
  }
  return stage.sort_order > currentStage.value.sort_order
}

const handleStageClick = async (stage: OpportunityProcurementStageInfo) => {
  if (!canClickStage(stage)) return
  
  const isNewOpportunity = !currentStage.value
  const confirmMessage = isNewOpportunity
    ? `确定要将商机的起始阶段设置为"${stage.stage_name}"吗？赢率将为 ${stage.win_probability}%。`
    : `确定要将商机阶段推进到"${stage.stage_name}"吗？当前赢率将从 ${currentStage.value?.win_probability}% 变为 ${stage.win_probability}%。`
  
  const confirmTitle = isNewOpportunity ? '设置起始阶段' : '确认推进阶段'
  
  try {
    await ElMessageBox.confirm(
      confirmMessage,
      confirmTitle,
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    loading.value = true
    try {
      await procurementApi.moveOpportunityStage(props.opportunityId, {
        stage_template_id: stage.id
      })
      ElMessage.success('阶段推进成功')
      await fetchOpportunityStages()
    } catch (error: any) {
      console.error('推进阶段失败', error)
      if (error?.response?.data?.detail) {
        ElMessage.error(error.response.data.detail)
      } else {
        ElMessage.error('推进阶段失败')
      }
    } finally {
      loading.value = false
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
  gap: 8px;
}

.current-stage-name {
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
  color: var(--wolf-text-primary);
}

.stage-content {
  padding: var(--wolf-card-padding) 0;
}

.stage-steps {
  margin-bottom: var(--wolf-spacing-lg);
  
  :deep(.el-step__head) {
    padding-bottom: 16px;
  }
  
  :deep(.el-step__head.is-process) {
    color: var(--wolf-primary);
  }
  
  :deep(.el-step__head.is-finish) {
    color: var(--wolf-success) !important;
  }
  
  :deep(.el-step__head.is-wait) {
    color: var(--wolf-text-tertiary);
  }
  
  :deep(.el-step__line) {
    background-color: var(--wolf-border-light);
  }
  
  :deep(.el-step__line.is-finish) {
    background-color: var(--wolf-success) !important;
  }
  
  :deep(.el-step__icon) {
    width: auto;
    height: auto;
    border: none;
    background: transparent;
  }
}

.step-icon-wrapper {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: var(--wolf-font-weight-semibold);
  border: 2px solid var(--wolf-border-color);
  background: var(--wolf-bg-hover);
  color: var(--wolf-text-tertiary);
  transition: all 0.3s ease;
  cursor: default;
}

.step-icon-wrapper.is-clickable {
  cursor: pointer;
}

.step-icon-wrapper.is-clickable:hover {
  border-color: var(--wolf-primary) !important;
  background: var(--wolf-primary-light) !important;
  color: var(--wolf-primary) !important;
  transform: scale(1.1);
  box-shadow: 0 2px 8px rgba(22, 93, 255, 0.2);
}

:deep(.el-step.is-process .step-icon-wrapper) {
  border-color: var(--wolf-primary);
  background: var(--wolf-primary);
  color: white;
  box-shadow: 0 2px 8px rgba(22, 93, 255, 0.2);
}

:deep(.el-step.is-finish .el-step__head) {
  color: var(--wolf-success) !important;
}

:deep(.el-step.is-finish .el-step__head.is-process) {
  color: var(--wolf-success) !important;
}

:deep(.el-step.is-finish .el-step__line-inner) {
  background-color: var(--wolf-success) !important;
  border-color: var(--wolf-success) !important;
}

:deep(.el-step.is-finish .el-step-icon) {
  color: var(--wolf-success) !important;
  border-color: var(--wolf-success-border) !important;
}

:deep(.el-step.is-finish .el-step-icon.is-icon) {
  color: var(--wolf-success) !important;
}

:deep(.el-step.is-finish .step-icon-wrapper) {
  border-color: var(--wolf-success-border) !important;
  background: var(--wolf-success-bg) !important;
  color: var(--wolf-success) !important;
}

:deep(.el-step.is-finish .step-title) {
  color: var(--wolf-success) !important;
}

:deep(.el-step.is-finish .el-step__line),
:deep(.el-step__line.is-finish) {
  background-color: var(--wolf-success) !important;
}

.step-win-rate {
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
}

.step-title {
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
  color: var(--wolf-text-primary);
  cursor: default;
  transition: all 0.3s ease;
}

.step-title.is-clickable {
  cursor: pointer;
}

.step-title.is-clickable:hover {
  color: var(--wolf-primary) !important;
}

.step-description {
  padding: 8px 0 0 0;
}

.step-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.win-rate {
  font-size: var(--wolf-font-size-small);
  font-weight: var(--wolf-font-weight-medium);
  color: var(--wolf-text-secondary);
}
</style>
