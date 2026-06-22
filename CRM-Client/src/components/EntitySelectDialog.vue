<template>
  <el-dialog
    v-model="visible"
    title="请选择实体"
    width="500px"
    :close-on-click-modal="false"
    @close="handleCancel"
  >
    <div class="entity-select">
      <!-- 提示信息 -->
      <div class="select-message">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ message }}</span>
      </div>

      <!-- 实体类型说明 -->
      <div class="entity-type-label">
        {{ getEntityTypeText(entityType) }}候选列表：
      </div>

      <!-- 候选列表 -->
      <div class="candidate-list">
        <div
          v-for="candidate in candidates"
          :key="candidate.id"
          class="candidate-item"
          :class="{ 'selected': selectedId === candidate.id }"
          @click="selectedId = candidate.id"
        >
          <el-radio
            :value="candidate.id"
            :label="candidate.id"
            v-model="selectedId"
          >
            <div class="candidate-content">
              <span class="candidate-name">{{ candidate.name }}</span>
              <span class="candidate-info">{{ candidate.display_info }}</span>
            </div>
          </el-radio>
        </div>
      </div>

      <!-- 无候选提示 -->
      <div v-if="candidates.length === 0" class="no-candidates">
        <span>没有找到匹配的{{ getEntityTypeText(entityType) }}</span>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button
        type="primary"
        :disabled="!selectedId"
        @click="handleConfirm"
      >
        确认选择
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import type { EntityCandidate } from '@/api/aiAssistant'

interface Props {
  visible: boolean
  entityType: 'opportunity' | 'contact' | 'contract'
  candidates: EntityCandidate[]
  message: string
}

interface Emits {
  (e: 'update:visible', value: boolean): void
  (e: 'select', candidate: EntityCandidate): void
  (e: 'cancel'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const visible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
})

const selectedId = ref<number | null>(null)

/**
 * 获取实体类型文本
 */
function getEntityTypeText(type: string): string {
  const map: Record<string, string> = {
    opportunity: '商机',
    contact: '联系人',
    contract: '合同'
  }
  return map[type] || type
}

/**
 * 确认选择
 */
function handleConfirm() {
  if (!selectedId.value) return

  // 找到选中的候选
  const selectedCandidate = props.candidates.find(c => c.id === selectedId.value)
  if (selectedCandidate) {
    emit('select', selectedCandidate)
  }
}

/**
 * 取消选择
 */
function handleCancel() {
  emit('cancel')
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.entity-select {
  .select-message {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-md;
    background: $wolf-warning-bg;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;
    color: $wolf-warning-text;

    .el-icon {
      color: $wolf-warning;
      font-size: 18px;
    }

    span {
      font-size: $wolf-font-size-body;
    }
  }

  .entity-type-label {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
    margin-bottom: $wolf-space-sm;
  }

  .candidate-list {
    max-height: 300px;
    overflow-y: auto;

    .candidate-item {
      padding: $wolf-space-md;
      margin-bottom: $wolf-space-xs;
      border-radius: $wolf-radius-md;
      background: $wolf-bg-card;
      cursor: pointer;
      transition: all 0.2s ease;

      &:hover {
        background: $wolf-bg-hover;
      }

      &.selected {
        background: $wolf-primary-light;
        border: 1px solid $wolf-primary;
      }

      .candidate-content {
        display: flex;
        flex-direction: column;
        gap: $wolf-space-xs;

        .candidate-name {
          font-size: $wolf-font-size-body;
          color: $wolf-text-primary;
          font-weight: $wolf-font-weight-medium;
        }

        .candidate-info {
          font-size: $wolf-font-size-caption;
          color: $wolf-text-tertiary;
        }
      }
    }
  }

  .no-candidates {
    padding: $wolf-space-lg;
    text-align: center;
    color: $wolf-text-tertiary;
    font-size: $wolf-font-size-body;
  }
}
</style>