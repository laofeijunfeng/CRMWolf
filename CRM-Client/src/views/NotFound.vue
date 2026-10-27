<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'

usePageTitle()
const headerStore = useHeaderStore()
onMounted(() => headerStore.clear())
onUnmounted(() => headerStore.clear())
</script>

<template>
  <main class="grid min-h-full place-items-center bg-background p-6" aria-label="找不到页面">
    <Card class="w-full max-w-[420px] shadow-none">
      <CardHeader>
        <CardTitle>找不到页面</CardTitle>
        <CardDescription>这页不存在。</CardDescription>
      </CardHeader>
    </Card>
  </main>
</template>
