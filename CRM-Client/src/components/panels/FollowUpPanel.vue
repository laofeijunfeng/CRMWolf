<script setup lang="ts">
/**
 * FollowUpPanel.vue - 客户活动面板组件
 *
 * 用于 CustomerDetailSheet 中的客户活动面板
 * 包装 FollowUpList 组件，提供标题和添加按钮
 *
 * 技术栈：shadcn-vue + variables-v2.scss
 */
import { CircleHelp, Plus } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { HoverInfo } from '@/components/crmwolf'
import FollowUpList from '@/components/FollowUpList.vue'

// ==================== Props & Emits ====================
interface FollowUp {
  id: number
  customer_id?: number | null
  original_lead_id?: number | null
  content: string
  method: string
  next_follow_time?: string | null
  next_action?: string | null
  creator_id: string
  creator_info?: { id: string; name: string; avatar_url?: string | null }
  customer_info?: { id: number; account_name: string }
  created_time: string
  effectiveness_score?: number | null
  effectiveness_is_valid?: boolean | null
  effectiveness_reason?: string | null
  effectiveness_detail_json?: string | null
  effectiveness_status?: string | null
  effectiveness_evaluated_time?: string | null
  effectiveness_error_message?: string | null
}

interface Props {
  followUps: FollowUp[]
  loading?: boolean | undefined
  currentUserId?: string | undefined
  showHeader?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  currentUserId: undefined,
  showHeader: true
})

const emit = defineEmits<{
  'add': []
  'delete': [followUp: FollowUp]
}>()

// ==================== Methods ====================
const handleAdd = (): void => {
  emit('add')
}

const handleDelete = (followUp: FollowUp): void => {
  emit('delete', followUp)
}
</script>

<template>
  <div class="follow-up-panel">
    <!-- Panel Header -->
    <div v-if="showHeader" class="panel-header">
      <div class="panel-title-group">
        <h3 class="panel-title">客户活动</h3>
        <HoverInfo side="bottom" align="start" content-class="principle-hover-card">
          <template #trigger>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              class="principle-trigger"
              aria-label="有效跟进评估原则"
            >
              <CircleHelp class="principle-icon" />
            </Button>
          </template>
          <div class="principle-tooltip">
            <div class="principle-tooltip-title">有效跟进评估 6 大原则</div>
            <div>事实优先：记录客观事实，避免主观感受。</div>
            <div>动作闭环：明确时间、责任人和下一步。</div>
            <div>决策穿透：识别决策链和关键角色。</div>
            <div>阶段推进：体现销售阶段或关键节点变化。</div>
            <div>异议具象：写清异议原因和影响。</div>
            <div>信息可接力：他人可直接接手跟进。</div>
          </div>
        </HoverInfo>
      </div>
      <Button size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        添加活动
      </Button>
    </div>

    <!-- Panel Content -->
    <div class="panel-content">
      <FollowUpList
        :follow-ups="props.followUps"
        :loading="props.loading"
        :current-user-id="props.currentUserId"
        @delete="handleDelete"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.follow-up-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: $wolf-space-md-v2 $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
}

.panel-title-group {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  min-width: 0;
}

.panel-title {
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
}

.principle-trigger {
  width: 24px !important;
  height: 24px !important;
  min-width: 24px !important;
  color: $wolf-text-tertiary-v2;
}

.principle-icon {
  width: 14px;
  height: 14px;
}

:global(.principle-hover-card) {
  width: 300px;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
}

.principle-tooltip {
  max-width: 300px;
  display: grid;
  gap: $wolf-space-xs-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 18px;
}

.principle-tooltip-title {
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.panel-content {
  flex: 1;
  overflow: auto;
  padding: $wolf-space-md-v2;
}

// Override FollowUpList container styles to fit panel layout
:deep(.follow-up-list-container) {
  padding: 0;
  background: transparent;
}
</style>
