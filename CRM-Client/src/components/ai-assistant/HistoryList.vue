/**
 * AI 助手 - 历史对话列表组件
 *
 * 按日期分组展示对话历史（今天、昨天、更早）
 */
<template>
  <div class="history-list">
    <!-- 今天 -->
    <div
      v-if="groups.today.length > 0"
      class="history-list__group"
    >
      <div class="history-list__group-title">
        今天
      </div>
      <HistoryItem
        v-for="item in groups.today"
        :key="item.id"
        :id="item.id"
        :title="item.title"
        :entity-type="item.entityType"
        :created-at="item.createdAt"
        :active="item.id === activeId"
        @select="handleSelect"
        @delete="handleDelete"
      />
    </div>

    <!-- 昨天 -->
    <div
      v-if="groups.yesterday.length > 0"
      class="history-list__group"
    >
      <div class="history-list__group-title">
        昨天
      </div>
      <HistoryItem
        v-for="item in groups.yesterday"
        :key="item.id"
        :id="item.id"
        :title="item.title"
        :entity-type="item.entityType"
        :created-at="item.createdAt"
        :active="item.id === activeId"
        @select="handleSelect"
      />
    </div>

    <!-- 更早 -->
    <div
      v-if="groups.earlier.length > 0"
      class="history-list__group"
    >
      <div class="history-list__group-title">
        更早
      </div>
      <HistoryItem
        v-for="item in groups.earlier"
        :key="item.id"
        :id="item.id"
        :title="item.title"
        :entity-type="item.entityType"
        :created-at="item.createdAt"
        :active="item.id === activeId"
        @select="handleSelect"
      />
    </div>

    <!-- 空状态 -->
    <div
      v-if="isEmpty"
      class="history-list__empty"
    >
      <!-- ✅ Copywriting: Invitation to act（不是 mood） -->
      <div class="history-list__empty-content">
        <span class="history-list__empty-title">开始你的第一个对话</span>
        <span class="history-list__empty-desc">AI 会帮你管理客户、商机和合同</span>
      </div>
    </div>

    <!-- 加载状态 -->
    <div
      v-if="loading"
      class="history-list__loading"
    >
      <span class="history-list__loading-text">加载中...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import HistoryItem from './HistoryItem.vue'
import type { ConversationGroup } from '@/api/aiConversation'

// ========== Props ==========

const props = defineProps({
  /** 按日期分组的对话列表 */
  groups: {
    type: Object as PropType<ConversationGroup>,
    required: true
  },
  /** 当前选中的对话 ID */
  activeId: {
    type: Number as PropType<number | null>,
    default: null
  },
  /** 加载状态 */
  loading: {
    type: Boolean,
    default: false
  }
})

// ========== Emits ==========

const emit = defineEmits<{
  (e: 'select', id: number): void
  (e: 'delete', id: number): void
}>()

// ========== Computed ==========

/** 是否所有分组都为空 */
const isEmpty = computed(() => {
  return (
    !props.loading &&
    props.groups.today.length === 0 &&
    props.groups.yesterday.length === 0 &&
    props.groups.earlier.length === 0
  )
})

// ========== Methods ==========

function handleSelect(id: number): void {
  emit('select', id)
}

function handleDelete(id: number): void {
  emit('delete', id)
}
</script>

<style scoped lang="scss">
@import '@/styles/variables.scss';

.history-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
  height: 100%;
  overflow-y: auto;
  padding: $wolf-space-md;

  // 分组
  .history-list__group {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-xs;
  }

  // 分组标题
  .history-list__group-title {
    font-size: $wolf-font-size-caption;
    font-weight: $wolf-font-weight-medium;
    color: $wolf-text-tertiary;
    padding: $wolf-space-sm 0 $wolf-space-xs;
    text-transform: uppercase;
  }

  // 空状态
  .history-list__empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 200px;
  }

  // ✅ Copywriting: Invitation to act（引导行动）
  .history-list__empty-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: $wolf-space-xs;
    text-align: center;
  }

  .history-list__empty-title {
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-medium;
    color: $wolf-text-secondary;
  }

  .history-list__empty-desc {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
  }

  // 加载状态
  .history-list__loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 200px;
  }

  .history-list__loading-text {
    font-size: $wolf-font-size-auxiliary;
    color: $wolf-text-tertiary;
  }
}
</style>