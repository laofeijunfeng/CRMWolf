<script setup lang="ts">
import type { PrimitiveProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import type { ButtonVariants } from "."
import { LoaderCircle } from "lucide-vue-next"
import { Primitive } from "reka-ui"
import { cn, omitUndefined } from "@/lib/utils"
import { buttonVariants } from "."

interface Props extends PrimitiveProps {
  variant?: ButtonVariants["variant"]
  size?: ButtonVariants["size"]
  class?: HTMLAttributes["class"]
  /** 防止重复提交，并向辅助技术暴露忙碌状态 */
  loading?: boolean
  /** 显式禁用按钮；loading 时始终视为禁用 */
  disabled?: boolean | undefined
}

const props = withDefaults(defineProps<Props>(), {
  as: "button",
  loading: false,
  disabled: false,
})

const isDisabled = (): boolean => props.disabled || props.loading
</script>

<template>
  <Primitive
    v-bind="omitUndefined({ as, asChild })"
    :class="cn(buttonVariants({ variant, size }), props.loading && 'relative disabled:opacity-100', props.class)"
    :disabled="isDisabled() ? true : undefined"
    :aria-disabled="isDisabled() ? 'true' : undefined"
    :aria-busy="props.loading ? 'true' : undefined"
  >
    <!-- 处理中不是禁用：保留原底色；内容透明占位，宽度与可读名称不变，旋转图标叠在中央 -->
    <template v-if="props.loading">
      <span class="inline-flex items-center gap-control opacity-0"><slot /></span>
      <LoaderCircle class="button-loading-icon absolute inset-0 m-auto animate-spin" aria-hidden="true" />
    </template>
    <slot v-else />
  </Primitive>
</template>

<style scoped>
@media (prefers-reduced-motion: reduce) {
  .button-loading-icon {
    animation-duration: 0.01ms;
    animation-iteration-count: 1;
  }
}
</style>
