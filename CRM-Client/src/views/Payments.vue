<!-- eslint-disable vue/multi-word-component-names -- 路由页面以资源名单词命名，重命名将破坏 router 注册与既有深链 -->
<template>
  <div class="payments-page">
    <!-- Left sidebar: PaymentSidebar component -->
    <PaymentSidebar
      :active-nav="activeNav"
      @nav-change="handleNavChange"
      @create-action="handleQuickAction"
    />

    <!-- Right content area: Dynamic view switching with keep-alive -->
    <div class="content-area">
      <transition name="slide-fade" mode="out-in">
        <keep-alive>
          <PaymentPlanView v-if="activeNav === 'plans'" key="plans" />
          <PaymentRecordView v-else key="records" />
        </keep-alive>
      </transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import PaymentSidebar from '@/components/PaymentSidebar.vue'
import PaymentPlanView from '@/views/PaymentPlanView.vue'
import PaymentRecordView from '@/views/PaymentRecordView.vue'
import { usePermissionStore } from '@/stores/permissions'
import { logger } from '@/utils/logger'

const router = useRouter()
const route = useRoute()
const permissionStore = usePermissionStore()

// Active navigation state: 'plans' or 'records'
const activeNav = ref<'plans' | 'records'>('plans')

// Deep link URL param parsing on mount
onMounted(() => {
  const navParam = route.query['nav'] as string | undefined
  if (navParam === 'plans' || navParam === 'records') {
    activeNav.value = navParam
  }
})

// Handle navigation change from sidebar
function handleNavChange(key: 'plans' | 'records'): void {
  activeNav.value = key
  // Update URL query param for deep linking
  router.replace({ query: { ...route.query, nav: key } })
}

// Handle quick actions from sidebar
function handleQuickAction(action: { key: string; label: string }): void {
  logger.info('[Payments]', 'Quick action triggered', { action })

  switch (action.key) {
    case 'create-plan':
      // Check permission for creating payment plan
      if (permissionStore.hasPermission('payment:create')) {
        router.push('/payments/create')
      } else {
        ElMessage.warning('您没有创建回款计划的权限')
      }
      break
    case 'register-payment':
      // This action requires selecting a plan first
      // Switch to plans view and show a hint
      if (activeNav.value !== 'plans') {
        activeNav.value = 'plans'
        router.replace({ query: { ...route.query, nav: 'plans' } })
      }
      ElMessage.info('请在回款计划列表中选择要登记的计划')
      break
    default:
      logger.warn('[Payments]', 'Unknown quick action', { action })
  }
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.payments-page {
  display: flex;
  height: calc(100vh - 48px); // Subtract header height
  background: $wolf-bg-page;
}

.content-area {
  flex: 1;
  overflow: hidden;
  padding: $wolf-page-padding;
  min-width: 0; // Prevent flex item overflow
}

// Slide-fade transition for view switching
.slide-fade-enter-active {
  transition: all 0.2s ease-out;
}

.slide-fade-leave-active {
  transition: all 0.15s ease-in;
}

.slide-fade-enter-from {
  opacity: 0;
  transform: translateX(10px);
}

.slide-fade-leave-to {
  opacity: 0;
  transform: translateX(-10px);
}

// Responsive adjustments
@media (max-width: 768px) {
  .payments-page {
    flex-direction: column;
    height: auto;
    min-height: calc(100vh - 48px);
  }

  .content-area {
    padding: $wolf-space-md;
  }
}
</style>