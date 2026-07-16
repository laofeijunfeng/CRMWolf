<script setup lang="ts">
/**
 * OpportunityStageStepper - 商机采购阶段步骤器
 *
 * 基于 shadcn-vue Stepper 组件封装：
 * - 仅自定义主题色（使用 variables-v2.scss）
 * - 保留 Stepper 原生动画和交互
 * - 官方样式：icon + 名称竖向分布，step之间有横线连接
 *
 * 功能：
 * - 显示采购阶段流程
 * - 点击阶段推进商机状态
 *
 * 规范依据：
 * - MASTER.md §3.5 组件封装原则
 * - UI/UX Pro Max §7: Animation duration 150-300ms
 */
import { ref, computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import {
  Stepper,
  StepperItem,
  StepperIndicator,
  StepperTitle,
  StepperSeparator
} from '@/components/ui/stepper'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { confirmDialog } from '@/utils/confirmDialog'
import procurementApi, {
  type OpportunityProcurementStageInfo
} from '@/api/procurement'

interface Props {
  opportunityId: number
}

const props = defineProps<Props>()

const loading = ref(false)
const allStages = ref<OpportunityProcurementStageInfo[]>([])

// 当前阶段索引（用于 Stepper 的 modelValue）
const currentStep = computed(() => {
  const current = allStages.value.find(stage => stage.is_current)
  if (!current) return 0
  return allStages.value.findIndex(s => s.id === current.id)
})

// 获取采购阶段数据
const fetchStages = async () => {
  loading.value = true
  try {
    const data = await procurementApi.getOpportunityProcurementStages(props.opportunityId)
    allStages.value = data || []
  } catch (error) {
    handleApiError(error, '获取采购阶段')
  } finally {
    loading.value = false
  }
}

// 点击阶段推进
const handleStageClick = async (stage: OpportunityProcurementStageInfo, index: number) => {
  if (loading.value) return

  const current = allStages.value.find(s => s.is_current)
  const currentStepIndex = current ? allStages.value.findIndex(s => s.id === current.id) : -1

  // 只能点击未完成阶段
  if (index <= currentStepIndex) return

  const isNewOpportunity = !current
  const confirmMessage = isNewOpportunity
    ? `确定将商机的起始阶段设置为「${stage.stage_name}」？赢率将从 0% 变为 ${stage.win_probability}%。`
    : `确定将商机推进到「${stage.stage_name}」？赢率将从 ${current?.win_probability}% 变为 ${stage.win_probability}%。`

  const confirmed = await confirmDialog(confirmMessage, isNewOpportunity ? '设置起始阶段' : '推进阶段')
  if (!confirmed) return

  loading.value = true
  try {
    await procurementApi.moveOpportunityStage(props.opportunityId, {
      stage_template_id: stage.id
    })
    toast.success(`阶段已推进至「${stage.stage_name}」`)
    await fetchStages()
  } catch (error) {
    handleApiError(error, '推进阶段')
  } finally {
    loading.value = false
  }
}

onMounted(fetchStages)
</script>

<template>
  <Card v-if="!loading && allStages.length > 0" class="stage-card">
    <CardHeader class="p-4 border-b border-wolf-border-light-v2">
      <h3 class="text-sm font-semibold text-wolf-text-primary-v2">采购阶段</h3>
    </CardHeader>
    <CardContent class="p-4">
      <Stepper
        :model-value="currentStep + 1"
        class="flex w-full gap-2"
        orientation="horizontal"
      >
        <StepperItem
          v-for="(stage, index) in allStages"
          :key="stage.id"
          :step="index + 1"
          class="flex-1 cursor-pointer"
          @click="handleStageClick(stage, index)"
        >
          <!-- 官方样式：竖向分布 -->
          <div class="flex flex-col items-center gap-2">
            <!-- StepperIndicator：显示百分比 -->
            <StepperIndicator
              class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold data-[state=active]:bg-wolf-primary-v2 data-[state=completed]:bg-wolf-success-v2 data-[state=inactive]:bg-muted"
            >
              {{ stage.win_probability }}%
            </StepperIndicator>

            <!-- StepperTitle：显示步骤名称 -->
            <StepperTitle class="text-xs font-medium text-center text-wolf-text-primary-v2">
              {{ stage.stage_name }}
            </StepperTitle>
          </div>

          <!-- StepperSeparator：横线连接 -->
          <StepperSeparator
            v-if="index < allStages.length - 1"
            class="h-0.5 flex-1 mt-5 data-[state=active]:bg-wolf-primary-v2 data-[state=completed]:bg-wolf-success-v2 data-[state=inactive]:bg-muted"
          />
        </StepperItem>
      </Stepper>

      <!-- 帮助提示 -->
      <p class="mt-4 text-xs text-wolf-text-tertiary-v2 text-center">
        点击未完成阶段可推进商机状态
      </p>
    </CardContent>
  </Card>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.stage-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  box-shadow: $wolf-shadow-card-v2;
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>