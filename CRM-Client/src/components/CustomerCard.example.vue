/**
 * Vue 组件示例 - 类型安全实现
 *
 * @description 展示如何按照规范实现类型安全的 Vue 组件
 */

<script setup lang="ts">
// ===== 1. 导入区（按字母排序） =====
import { computed, onMounted, ref } from 'vue'
import type { PropType } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'

// ===== 2. 类型导入（从 schemas/） =====
import type { CustomerResponse, CustomerCreate } from '@/schemas/customer'
import { CustomerStatusMap } from '@/schemas/common'

// ===== 3. Store 导入 =====
import { useCustomerStore } from '@/stores/example-customer'
import { usePermissionStore } from '@/stores/permissions'

// ===== 4. Props 定义（必须类型化） =====
const props = defineProps({
  /** 客户数据 */
  customer: {
    type: Object as PropType<CustomerResponse>,
    required: true
  },
  /** 显示模式 */
  mode: {
    type: String as PropType<'view' | 'edit'>,
    default: 'view'
  }
})

// ===== 5. Emits 定义（必须类型化） =====
const emit = defineEmits<{
  /** 更新客户 */
  (e: 'update', value: CustomerCreate): void
  /** 删除客户 */
  (e: 'delete', id: number): void
  /** 关闭 */
  (e: 'close'): void
}>()

// ===== 6. Store 使用 =====
const customerStore = useCustomerStore()
const permissionStore = usePermissionStore()

// 正确解构：State 用 storeToRefs，Actions 直接解构
const { loading, error } = storeToRefs(customerStore)
const { fetchList, create } = customerStore

// ===== 7. 本地状态（必须类型化） =====
const isEditing = ref<boolean>(false)
const formData = ref<CustomerCreate>({
  account_name: '',
  city: ''
})

// ===== 8. 计算属性（必须返回类型） =====
/** 显示名称 */
const displayName = computed<string>(() => {
  return props.customer.account_name || '未命名客户'
})

/** 状态文本 */
const statusText = computed<string>(() => {
  return CustomerStatusMap[props.customer.status] || '未知'
})

/** 是否有编辑权限 */
const canEdit = computed<boolean>(() => {
  return permissionStore.hasPermission('customer:edit:own') || permissionStore.hasPermission('customer:edit:all')
})

/** 是否可以删除 */
const canDelete = computed<boolean>(() => {
  return permissionStore.hasPermission('customer:delete:own') || permissionStore.hasPermission('customer:delete:all')
})

// ===== 9. 方法（必须参数和返回类型） =====
/**
 * 处理编辑
 */
const handleEdit = (): void => {
  isEditing.value = true
  formData.value = {
    account_name: props.customer.account_name,
    city: props.customer.city,
    industry: props.customer.industry ?? undefined
  }
}

/**
 * 处理保存
 */
const handleSave = async (): Promise<void> => {
  emit('update', formData.value)
  isEditing.value = false
}

/**
 * 处理删除
 */
const handleDelete = (): void => {
  emit('delete', props.customer.id)
}

/**
 * 处理关闭
 */
const handleClose = (): void => {
  emit('close')
}

// ===== 10. 生命周期 =====
onMounted(() => {
  // 初始化逻辑
})
</script>

<template>
  <div class="customer-card">
    <!-- 加载状态 -->
    <div v-if="loading" class="wolf-loading">
      加载中...
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="wolf-error">
      {{ error }}
    </div>

    <!-- 正常显示 -->
    <div v-else>
      <h3 class="wolf-title">{{ displayName }}</h3>
      <p class="wolf-text">状态: {{ statusText }}</p>
      <p class="wolf-text">城市: {{ customer.city }}</p>

      <!-- 编辑模式 -->
      <div v-if="isEditing" class="wolf-form">
        <input
          v-model="formData.account_name"
          type="text"
          placeholder="客户名称"
        />
        <input
          v-model="formData.city"
          type="text"
          placeholder="城市"
        />
        <button class="wolf-btn-primary" @click="handleSave">
          保存
        </button>
      </div>

      <!-- 查看模式 -->
      <div v-else class="wolf-actions">
        <!-- 权限控制 -->
        <button
          v-if="canEdit"
          class="wolf-btn-secondary"
          @click="handleEdit"
        >
          编辑
        </button>
        <button
          v-if="canDelete"
          class="wolf-btn-danger"
          @click="handleDelete"
        >
          删除
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.customer-card {
  padding: var(--wolf-spacing-md);
  border-radius: var(--wolf-radius-md);
}

.wolf-title {
  font-size: var(--wolf-font-lg);
  color: var(--wolf-text-primary);
}

.wolf-loading,
.wolf-error {
  text-align: center;
  padding: var(--wolf-spacing-lg);
}
</style>