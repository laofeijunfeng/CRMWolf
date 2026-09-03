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
    :class="cn(buttonVariants({ variant, size }), props.class)"
    :disabled="isDisabled() ? true : undefined"
    :aria-disabled="isDisabled() ? 'true' : undefined"
    :aria-busy="props.loading ? 'true' : undefined"
  >
    <LoaderCircle v-if="props.loading" class="button-loading-icon animate-spin" aria-hidden="true" />
    <slot />
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
