<script setup lang="ts">
/**
 * FollowUpPanel.vue - 跟进记录面板组件
 *
 * 用于 CustomerDetailSheet 中的跟进记录面板
 * 包装 FollowUpList 组件，提供标题和添加按钮
 *
 * 技术栈：shadcn-vue + variables-v2.scss
 */
import { Plus } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
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
}

interface Props {
  followUps: FollowUp[]
  loading?: boolean
  currentUserId?: string
}

withDefaults(defineProps<Props>(), {
  loading: false,
  currentUserId: undefined
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
    <div class="panel-header">
      <h3 class="panel-title">跟进记录</h3>
      <Button size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        添加跟进
      </Button>
    </div>

    <!-- Panel Content -->
    <div class="panel-content">
      <FollowUpList
        :follow-ups="followUps"
        :loading="loading"
        :current-user-id="currentUserId"
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

.panel-title {
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
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