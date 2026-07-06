<!-- PaymentRecordView.vue - Placeholder for Task 1.7 -->
<template>
  <div class="payment-record-view">
    <!-- Task 1.7 will implement: record list table with filters -->
    <div class="placeholder-content">
      <el-empty description="回款记录视图开发中 - Task 1.7">
        <el-button type="primary" @click="goToPlans">返回回款计划</el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

const goToPlans = (): void => {
  router.push({ path: '/payments', query: { nav: 'plans' } })
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.payment-record-view {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.placeholder-content {
  text-align: center;
  color: $wolf-text-tertiary;
}
</style>