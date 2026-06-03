<template>
  <el-drawer
    v-model="visible"
    :title="drawerTitle"
    direction="rtl"
    size="400px"
  >
    <div class="todo-list">
      <!-- 线索跟进 -->
      <div v-if="todos.lead_follow_ups?.length" class="todo-group">
        <div class="group-header">
          <span class="group-icon lead"></span>
          <span class="group-title">线索跟进</span>
          <span class="group-count">{{ todos.lead_follow_ups.length }}</span>
        </div>
        <div class="todo-items">
          <div
            v-for="item in todos.lead_follow_ups"
            :key="item.id"
            class="todo-item"
            :class="{ overdue: item.is_overdue }"
          >
            <div class="item-content" @click="handleNavigate('lead', item.lead_id)">
              <div class="item-name">{{ item.lead_name }}</div>
              <div class="item-meta">{{ item.next_action || '暂无下一步动作' }}</div>
            </div>
            <el-button class="follow-btn" size="small" text type="primary" @click="handleFollowUp('lead_follow_up', item.id, item.lead_name)">
              跟进
            </el-button>
          </div>
        </div>
      </div>

      <!-- 客户跟进 -->
      <div v-if="todos.customer_follow_ups?.length" class="todo-group">
        <div class="group-header">
          <span class="group-icon customer"></span>
          <span class="group-title">客户跟进</span>
          <span class="group-count">{{ todos.customer_follow_ups.length }}</span>
        </div>
        <div class="todo-items">
          <div
            v-for="item in todos.customer_follow_ups"
            :key="item.id"
            class="todo-item"
            :class="{ overdue: item.is_overdue }"
          >
            <div class="item-content" @click="handleNavigate('customer', item.customer_id)">
              <div class="item-name">{{ item.account_name }}</div>
              <div class="item-meta">{{ item.next_action || '暂无下一步动作' }}</div>
            </div>
            <el-button class="follow-btn" size="small" text type="primary" @click="handleFollowUp('customer_follow_up', item.id, item.account_name)">
              跟进
            </el-button>
          </div>
        </div>
      </div>

      <!-- 商机跟进 -->
      <div v-if="todos.opportunities?.length" class="todo-group">
        <div class="group-header">
          <span class="group-icon opportunity"></span>
          <span class="group-title">商机跟进</span>
          <span class="group-count">{{ todos.opportunities.length }}</span>
        </div>
        <div class="todo-items">
          <div
            v-for="item in todos.opportunities"
            :key="item.id"
            class="todo-item"
            :class="{ overdue: item.is_overdue }"
            @click="handleNavigate('opportunity', item.id)"
          >
            <div class="item-name">{{ item.opportunity_name }}</div>
            <div class="item-meta">
              {{ item.customer_name }}
              <span class="amount-tag">¥{{ formatAmount(item.total_amount) }}</span>
              <span v-if="item.current_stage_name" class="stage-tag">{{ item.current_stage_name }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 回款计划 -->
      <div v-if="todos.payment_plans?.length" class="todo-group">
        <div class="group-header">
          <span class="group-icon payment"></span>
          <span class="group-title">回款计划</span>
          <span class="group-count">{{ todos.payment_plans.length }}</span>
        </div>
        <div class="todo-items">
          <div
            v-for="item in todos.payment_plans"
            :key="item.id"
            class="todo-item"
            :class="{ overdue: item.is_overdue }"
            @click="handleNavigate('contract', item.contract_id)"
          >
            <div class="item-name">{{ item.contract_name }}</div>
            <div class="item-meta">
              {{ item.customer_name }}
              <span class="amount-tag">¥{{ formatAmount(item.planned_amount) }}</span>
              <span class="stage-tag">{{ item.stage_name }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 无待办 -->
      <el-empty v-if="todos.total_count === 0" description="当日暂无待办事项" />
    </div>
  </el-drawer>

  <!-- 跟进弹窗 -->
  <FollowUpDialog
    v-model="followUpDialogVisible"
    :todo-type="followUpTodoType"
    :todo-id="followUpTodoId"
    :entity-name="followUpEntityName"
    @refresh="handleRefresh"
  />
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import type { CalendarDateDetailResponse } from '@/api/calendar'
import FollowUpDialog from '@/components/FollowUpDialog.vue'

interface Props {
  visible: boolean
  date: string
  todos: CalendarDateDetailResponse
}

interface Emits {
  (e: 'update:visible', value: boolean): void
  (e: 'refresh'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const router = useRouter()

const visible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value)
})

const drawerTitle = computed(() => {
  const dateParts = props.date.split('-')
  return `${dateParts[0]}年${dateParts[1]}月${dateParts[2]}日 待办事项`
})

const formatAmount = (amount: number) => {
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const handleNavigate = (type: string, id: number) => {
  const routeMap: Record<string, string> = {
    lead: `/leads/${id}`,
    customer: `/customers/${id}`,
    opportunity: `/opportunities/${id}`,
    contract: `/contracts/${id}`
  }
  const route = routeMap[type]
  if (route) {
    router.push(route)
    visible.value = false
  }
}

// 跟进弹窗相关
const followUpDialogVisible = ref(false)
const followUpTodoType = ref('')
const followUpTodoId = ref(0)
const followUpEntityName = ref('')

const handleFollowUp = (todoType: string, todoId: number, entityName: string) => {
  followUpTodoType.value = todoType
  followUpTodoId.value = todoId
  followUpEntityName.value = entityName
  followUpDialogVisible.value = true
}

const handleRefresh = () => {
  emit('refresh')
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.todo-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

.todo-group {
  .group-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-sm $wolf-space-md;
    background: $wolf-bg-elevated;
    border-radius: $wolf-radius-sm;

    .group-icon {
      width: 8px;
      height: 8px;
      border-radius: $wolf-radius-full;

      &.lead { background: $wolf-primary; }
      &.customer { background: #67C23A; }
      &.opportunity { background: #E6A23C; }
      &.payment { background: #909399; }
    }

    .group-title {
      font-size: $wolf-font-size-body;
      font-weight: $wolf-font-weight-medium;
      color: $wolf-text-secondary;
    }

    .group-count {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      padding: 2px 8px;
      background: $wolf-bg-hover;
      border-radius: $wolf-radius-sm;
    }
  }

  .todo-items {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .todo-item {
    padding: $wolf-space-md;
    border-radius: $wolf-radius-sm;
    transition: background 0.2s;
    border-bottom: 1px solid $wolf-border-light;
    display: flex;
    align-items: center;
    justify-content: space-between;

    &:last-child {
      border-bottom: none;
    }

    &:hover {
      background: $wolf-bg-hover;
    }

    &.overdue {
      .item-name {
        color: $wolf-danger-text;
      }
      background: $wolf-danger-bg;
    }

    .item-content {
      flex: 1;
      cursor: pointer;
      min-width: 0;
    }

    .follow-btn {
      flex-shrink: 0;
      margin-left: $wolf-space-sm;
    }

    .item-name {
      font-size: $wolf-font-size-body;
      color: $wolf-text-primary;
      margin-bottom: 4px;
      font-weight: $wolf-font-weight-medium;
    }

    .item-meta {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      display: flex;
      align-items: center;
      gap: 8px;

      .amount-tag {
        color: $wolf-primary;
        font-weight: $wolf-font-weight-medium;
      }

      .stage-tag {
        padding: 2px 6px;
        background: $wolf-primary-light;
        color: $wolf-primary;
        border-radius: $wolf-radius-sm;
        font-size: 12px;
      }
    }
  }
}
</style>