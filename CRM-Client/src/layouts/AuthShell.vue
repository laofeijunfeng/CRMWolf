<script setup lang="ts">
import { LogOut } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'

interface Props {
  title: string
  description?: string
  /** 已登录但未进入团队的引导页显示右上角退出登录 */
  showLogout?: boolean
}

withDefaults(defineProps<Props>(), {
  description: '',
  showLogout: false,
})

const emit = defineEmits<{
  logout: []
}>()
</script>

<template>
  <main class="auth-shell relative flex min-h-dvh items-center justify-center bg-card sm:bg-background">
    <Button
      v-if="showLogout"
      variant="ghost"
      size="sm"
      class="auth-shell__logout absolute text-muted-foreground"
      @click="emit('logout')"
    >
      <LogOut class="size-icon-sm" aria-hidden="true" />
      退出登录
    </Button>

    <div
      class="grid w-full max-w-[var(--dialog-w-sm)] gap-space-6 sm:rounded-lg sm:border sm:border-border sm:bg-card sm:p-space-8 sm:shadow-1"
    >
      <div class="grid justify-items-center gap-space-2">
        <img src="/logo.png" alt="CRM Logo" class="size-12 object-contain" />
        <span class="text-body-strong text-foreground">智能客户关系管理系统</span>
      </div>

      <header class="grid gap-space-1 text-center">
        <h1 class="m-0 text-title text-foreground">{{ title }}</h1>
        <p v-if="description" class="m-0 text-body text-muted-foreground">{{ description }}</p>
      </header>

      <slot />

      <div v-if="$slots['footer']" class="grid justify-items-center gap-space-2 text-center text-body text-muted-foreground">
        <slot name="footer" />
      </div>
    </div>
  </main>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.auth-shell {
  padding: calc(var(--page-padding) + var(--safe-top)) var(--page-padding)
    calc(var(--page-padding) + var(--safe-bottom));
}

.auth-shell__logout {
  top: calc($space-4 + var(--safe-top));
  right: $space-4;
}
</style>
