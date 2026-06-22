<template>
  <Teleport to="body">
    <Transition name="snackbar-slide-up">
      <div class="undo-snackbar-container" v-if="visible">
        <div class="undo-snackbar">
          <!-- 进度条 -->
          <div class="snackbar-progress">
            <el-progress
              :percentage="progressPercentage"
              :show-text="false"
              :stroke-width="6"
              :color="progressColor"
            />
          </div>

          <!-- 内容区 -->
          <div class="snackbar-content">
            <!-- 左侧：结果图标 + 描述 -->
            <div class="snackbar-left">
              <el-icon :size="24" class="snackbar-icon">
                <CircleCheckFilled />
              </el-icon>
              <span class="snackbar-message">{{ message }}</span>
            </div>

            <!-- 右侧：操作按钮 -->
            <div class="snackbar-right">
              <el-button
                size="small"
                type="warning"
                :disabled="!canUndo"
                :loading="isUndoing"
                @click="handleUndo"
              >
                撤销
              </el-button>
              <el-button size="small" text @click="handleDismiss">
                关闭
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { CircleCheckFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

interface Props {
  operationId: number
  undoEndpoint: string
  ttl: number
  message?: string
  visible?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  ttl: 10,
  message: '操作已执行',
  visible: true
})

const emit = defineEmits<{
  'undo-success': []
  'undo-failed': [reason: string]
  'expired': []
  'dismiss': []
}>()

const remainingSeconds = ref(props.ttl)
const isUndoing = ref(false)
const canUndo = ref(true)
const localVisible = ref(props.visible)

// 进度条
const progressPercentage = computed(() => {
  return (remainingSeconds.value / props.ttl) * 100
})

// 进度条颜色（动态变化）
const progressColor = computed(() => {
  if (remainingSeconds.value > props.ttl * 0.5) {
    return '#e6a23c'  // 橙色（活跃）
  } else if (remainingSeconds.value > props.ttl * 0.2) {
    return '#909399'  // 灰色（即将过期）
  } else {
    return '#c0c4cc'  // 更浅灰色（快过期）
  }
})

// 倒计时
let countdownTimer: ReturnType<typeof setInterval> | null = null

const startCountdown = () => {
  countdownTimer = setInterval(() => {
    remainingSeconds.value -= 1
    if (remainingSeconds.value <= 0) {
      stopCountdown()
      canUndo.value = false
      localVisible.value = false
      emit('expired')
    }
  }, 1000)
}

const stopCountdown = () => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

watch(() => props.visible, (newVal) => {
  localVisible.value = newVal
  if (newVal) {
    remainingSeconds.value = props.ttl
    canUndo.value = true
    startCountdown()
  } else {
    stopCountdown()
  }
}, { immediate: true })

onUnmounted(() => {
  stopCountdown()
})

// 撤销
const handleUndo = async () => {
  if (!canUndo.value) return

  isUndoing.value = true
  stopCountdown()

  try {
    const response = await fetch(props.undoEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })

    const result = await response.json()

    if (result.success) {
      localVisible.value = false
      emit('undo-success')
      ElMessage.success({
        message: result.message || '操作已撤销',
        duration: 2000
      })
    } else {
      emit('undo-failed', result.reason || '撤销失败')
      ElMessage.error({
        message: result.reason || '撤销失败',
        duration: 3000
      })
      if (remainingSeconds.value > 0) {
        startCountdown()
      }
    }
  } catch (error) {
    console.error('Undo failed:', error)
    emit('undo-failed', '撤销请求失败')
    ElMessage.error('撤销请求失败')
    if (remainingSeconds.value > 0) {
      startCountdown()
    }
  } finally {
    isUndoing.value = false
  }
}

const handleDismiss = () => {
  stopCountdown()
  localVisible.value = false
  emit('dismiss')
}

defineExpose({
  visible: localVisible
})
</script>

<style scoped lang="scss">
.undo-snackbar-container {
  position: fixed;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  width: 100%;
  max-width: 800px;
}

.undo-snackbar {
  background: #fff;
  border-top: 1px solid #ebeef5;
  box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.1);

  .snackbar-progress {
    padding: 4px 16px 0;
  }

  .snackbar-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;

    .snackbar-left {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 1;

      .snackbar-icon {
        color: #67c23a;
      }

      .snackbar-message {
        font-size: 14px;
        color: #303133;
      }
    }

    .snackbar-right {
      display: flex;
      align-items: center;
      gap: 8px;
    }
  }
}

.snackbar-slide-up-enter-active {
  animation: slideUp 0.3s ease-out;
}

.snackbar-slide-up-leave-active {
  animation: slideDown 0.3s ease-in;
}

@keyframes slideUp {
  from {
    transform: translateX(-50%) translateY(100%);
    opacity: 0;
  }
  to {
    transform: translateX(-50%) translateY(0);
    opacity: 1;
  }
}

@keyframes slideDown {
  from {
    transform: translateX(-50%) translateY(0);
    opacity: 1;
  }
  to {
    transform: translateX(-50%) translateY(100%);
    opacity: 0;
  }
}
</style>