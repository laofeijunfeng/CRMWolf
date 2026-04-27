<template>
  <div class="callback-container">
    <el-icon class="is-loading" :size="40"><Loading /></el-icon>
    <p>正在登录中...</p>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

onMounted(async () => {
  const code = route.query.code as string

  if (!code) {
    ElMessage.error('未获取到授权码')
    router.push('/login')
    return
  }

  try {
    await userStore.login({ code })
    ElMessage.success('登录成功')
    router.push('/customers')
  } catch (error: any) {
    ElMessage.error(error.message || '登录失败')
    router.push('/login')
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.callback-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-lg;
  background: $wolf-bg-page;
}

p {
  font-size: $wolf-font-size-body;
  color: $wolf-text-secondary;
}
</style>
