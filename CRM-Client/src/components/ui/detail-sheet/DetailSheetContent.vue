<script setup lang="ts">
/**
 * DetailSheetContent - 业务详情 Sheet 统一布局组件
 *
 * 设计规格来源：docs/superpowers/specs/2026-07-14-contract-payment-invoice-detail-sheet-design.md
 *
 * 宽度契约（§9.1）：
 * - 桌面端：w-3/4（右侧 75%）
 * - 最大宽度：max-w-[1080px]
 * - 窄视口：全宽
 *
 * 约束：
 * - 业务 Sheet 不得自行覆盖宽度
 * - 宽度事实来源为本组件，不在每个 Sheet 规格中重复定义
 *
 * 布局结构：
 * - SheetHeader（固定）
 * - ScrollArea（flex-1，独立滚动）
 * - SheetFooter（固定，可选）
 */
import type { DialogContentEmits, DialogContentProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { X } from 'lucide-vue-next'
import {
  DialogClose,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  useForwardPropsEmits
} from 'reka-ui'
import { cn } from '@/lib/utils'

interface DetailSheetContentProps extends DialogContentProps {
  class?: HTMLAttributes['class']
}

defineOptions({
  inheritAttrs: false
})

const props = defineProps<DetailSheetContentProps>()
const emits = defineEmits<DialogContentEmits>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <DialogPortal>
    <!-- DialogOverlay: 遮罩层 z-[200] -->
    <DialogOverlay
      class="fixed inset-0 z-[200] bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
    />
    <!-- DialogContent: 详情 Sheet 主体 -->
    <DialogContent
      :class="cn(
        // 基础样式
        'fixed z-[201] gap-4 bg-background shadow-lg transition ease-in-out data-[state=open]:animate-in data-[state=closed]:animate-out',
        // 位置：右侧
        'inset-y-0 right-0 h-full',
        // 进入/退出动画
        'data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right',
        // 宽度：桌面 75%，最大 1080px
        'w-full sm:w-3/4 sm:max-w-[1080px]',
        // 布局：垂直 flex
        'flex flex-col',
        props.class
      )"
      v-bind="{ ...forwarded, ...$attrs }"
    >
      <slot />

      <DialogClose
        class="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-secondary"
      >
        <X class="w-4 h-4 text-muted-foreground" />
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>