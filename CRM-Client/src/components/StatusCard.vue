<template>
  <div class="status-card" :class="statusClass">
    <!-- 卡片头部 -->
    <div class="card-header">
      <el-icon class="status-icon" :size="18">
        <CircleCheckFilled v-if="type === 'success'" />
        <WarningFilled v-if="type === 'warning'" />
        <CircleCloseFilled v-if="type === 'error'" />
        <Loading v-if="type === 'loading'" />
      </el-icon>
      <span class="card-title">{{ title }}</span>
      <!-- 右侧：时间 + 撤销图标 -->
      <div class="card-meta">
        <span class="card-timestamp" v-if="timestamp">
          <el-icon :size="12"><Clock /></el-icon>
          {{ timestamp }}
        </span>
        <!-- 成功卡片：撤销图标（右上角） -->
        <el-icon
          v-if="type === 'success' && showActions"
          class="undo-icon"
          :size="14"
          @click="handleUndo"
        >
          <RefreshLeft />
        </el-icon>
      </div>
    </div>

    <!-- 卡片内容 -->
    <div class="card-content">
      <!-- 成功类型：显示摘要 -->
      <div v-if="type === 'success'" class="success-content">
        <span class="content-summary">{{ summary }}</span>
      </div>

      <!-- 警告/错误类型：显示原因和建议 -->
      <div v-if="type === 'warning' || type === 'error'" class="error-content">
        <div class="error-summary">{{ summary }}</div>
        <!-- 缺失字段列表 -->
        <div v-if="missingFields && missingFields.length > 0" class="missing-fields">
          <div class="fields-header">缺少以下信息：</div>
          <div class="field-list">
            <span v-for="field in missingFields" :key="field" class="field-item">
              <el-icon :size="12"><InfoFilled /></el-icon>
              {{ field }}
            </span>
          </div>
        </div>
        <!-- 原始错误详情（可折叠） -->
        <div v-if="showDetail && originalError" class="error-detail">
          <div class="detail-toggle" @click="detailExpanded = !detailExpanded">
            <el-icon :size="12"><ArrowDown v-if="!detailExpanded" /><ArrowUp v-if="detailExpanded" /></el-icon>
            <span>{{ detailExpanded ? '隐藏详情' : '查看详情' }}</span>
          </div>
          <div v-if="detailExpanded" class="detail-content">
            {{ originalError }}
          </div>
        </div>
      </div>

      <!-- 加载类型：显示进度 -->
      <div v-if="type === 'loading'" class="loading-content">
        <span class="loading-text">{{ summary || '正在执行...' }}</span>
      </div>
    </div>

    <!-- 卡片操作区（仅警告/错误卡片显示） -->
    <div class="card-actions" v-if="showActions && (type === 'warning' || type === 'error')">
      <el-button size="small" type="primary" @click="handleRetry">
        补充信息
      </el-button>
      <el-button size="small" text @click="handleIgnore">
        忽略此项
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
  Loading,
  Clock,
  InfoFilled,
  ArrowDown,
  ArrowUp,
  RefreshLeft
} from '@element-plus/icons-vue'

interface Props {
  type: 'success' | 'warning' | 'error' | 'loading'
  title: string
  summary?: string
  timestamp?: string
  missingFields?: string[]
  originalError?: string
  showDetail?: boolean
  showActions?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  type: 'success',
  showDetail: false,
  showActions: true
})

const emit = defineEmits<{
  (e: 'undo'): void
  (e: 'retry'): void
  (e: 'ignore'): void
}>()

const detailExpanded = ref(false)

const statusClass = computed(() => {
  return {
    'card-success': props.type === 'success',
    'card-warning': props.type === 'warning',
    'card-error': props.type === 'error',
    'card-loading': props.type === 'loading'
  }
})

const handleUndo = () => {
  emit('undo')
}

const handleRetry = () => {
  emit('retry')
}

const handleIgnore = () => {
  emit('ignore')
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.status-card {
  padding: $wolf-space-md;
  border-radius: $wolf-radius-lg;  // 12px 圆角
  background: $wolf-bg-card;       // 白色背景
  box-shadow: $wolf-shadow-card;   // 轻阴影
  margin-bottom: $wolf-card-gap;   // 16px 间距
  transition: all 0.2s ease;

  // 成功卡片样式 - 使用灰色背景区分层级
  &.card-success {
    background: $wolf-bg-hover;    // 灰色背景（与白色抽屉区分）

    .status-icon {
      color: $wolf-success-text;  // 绿色图标
    }

    .card-title {
      color: $wolf-text-primary;  // 标题保持黑色
    }
  }

  // 警告卡片样式
  &.card-warning {
    .status-icon {
      color: $wolf-warning-text;  // 橙色图标
    }

    .card-title {
      color: $wolf-text-primary;
    }
  }

  // 错误卡片样式
  &.card-error {
    .status-icon {
      color: $wolf-danger-text;   // 红色图标
    }

    .card-title {
      color: $wolf-text-primary;
    }
  }

  // 加载卡片样式
  &.card-loading {
    .status-icon {
      color: $wolf-primary;       // 蓝色图标
    }

    .card-title {
      color: $wolf-text-primary;
    }
  }

  // 头部
  .card-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    margin-bottom: $wolf-space-xs;

    .status-icon {
      flex-shrink: 0;
    }

    .card-title {
      font-size: $wolf-font-size-body;
      font-weight: $wolf-font-weight-medium;
      flex: 1;
      color: $wolf-text-primary;
    }

    // 右侧元信息（时间 + 撤销图标）
    .card-meta {
      display: flex;
      align-items: center;
      gap: $wolf-space-sm;

      .card-timestamp {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: $wolf-font-size-caption;
        color: $wolf-text-tertiary;
      }

      .undo-icon {
        color: $wolf-text-tertiary;
        cursor: pointer;
        transition: color 0.2s;

        &:hover {
          color: $wolf-primary;
        }
      }
    }
  }

  // 内容区
  .card-content {
    .success-content {
      .content-summary {
        font-size: $wolf-font-size-auxiliary;  // 13px
        color: $wolf-text-secondary;
        line-height: $wolf-line-height-body;
        word-wrap: break-word;      // 允许换行
        word-break: break-all;      // 长单词可断行
        max-width: 100%;            // 限制宽度
      }
    }

    .error-content {
      .error-summary {
        font-size: $wolf-font-size-auxiliary;
        color: $wolf-text-secondary;
        margin-bottom: $wolf-space-sm;
        line-height: $wolf-line-height-body;
        word-wrap: break-word;
        word-break: break-all;
      }

      .missing-fields {
        padding: $wolf-space-sm;
        background: $wolf-bg-hover;
        border-radius: $wolf-radius-sm;
        margin-bottom: $wolf-space-sm;

        .fields-header {
          font-size: $wolf-font-size-caption;
          color: $wolf-text-tertiary;
          margin-bottom: $wolf-space-xs;
        }

        .field-list {
          display: flex;
          flex-direction: column;
          gap: 4px;

          .field-item {
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: $wolf-font-size-caption;
            color: $wolf-text-primary;
          }
        }
      }

      .error-detail {
        .detail-toggle {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: $wolf-font-size-caption;
          color: $wolf-primary;
          cursor: pointer;
          padding: $wolf-space-xs 0;

          &:hover {
            opacity: 0.8;
          }
        }

        .detail-content {
          font-size: $wolf-font-size-caption;
          color: $wolf-text-tertiary;
          padding: $wolf-space-sm;
          background: rgba(0, 0, 0, 0.03);
          border-radius: $wolf-radius-sm;
          margin-top: $wolf-space-xs;
          word-break: break-all;
        }
      }
    }

    .loading-content {
      .loading-text {
        font-size: $wolf-font-size-auxiliary;
        color: $wolf-text-secondary;
        line-height: $wolf-line-height-body;
      }
    }
  }

  // 操作区
  .card-actions {
    display: flex;
    justify-content: flex-end;
    gap: $wolf-space-sm;  // 8px 按钮间距
    margin-top: $wolf-space-sm;
    padding-top: $wolf-space-sm;
    border-top: 1px solid $wolf-border-light;

    :deep(.el-button) {
      font-size: $wolf-font-size-caption;
    }
  }
}
</style>