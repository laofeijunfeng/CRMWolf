<script setup lang="ts">
/**
 * DialogContent - Modal Dialog Component
 *
 * z-index: z-[1000] (Modal 层，最高层级)
 *
 * 层级关系（详见 docs/LAYOUT.md）：
 * - Dialog (z-1000) > Sheet (z-200) > TopBar (z-90)
 * - Modal 层遮挡一切，包括 Drawer 和 Navigation
 *
 * Portal: 通过 DialogPortal 渲染到 <body>，避免 stacking context 冲突
 *
 * 规范依据：
 * - docs/LAYOUT.md - z-index 层级管理
 * - UI/UX Pro Max §5: z-index-management
 * - AppLayout.vue $z-index-modal: 1000
 */
import type { DialogContentEmits, DialogContentProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { X } from "lucide-vue-next"
import {
  DialogClose,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  useForwardPropsEmits,
} from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps<DialogContentProps & { class?: HTMLAttributes["class"] }>()
const emits = defineEmits<DialogContentEmits>()

const delegatedProps = reactiveOmit(props, "class")

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <!-- DialogPortal: 渲染到 <body>，避免 stacking context -->
  <DialogPortal>
    <!-- DialogOverlay: Scrim (遮罩层) z-[1000] -->
    <DialogOverlay
      class="fixed inset-0 z-[1000] bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
    />
    <!-- DialogContent: Modal 主体 z-[1000]（最高层级） -->
    <DialogContent
      v-bind="forwarded"
      :class="
        cn(
          'fixed left-1/2 top-1/2 z-[1000] grid w-full max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg',
          props.class,
        )"
    >
      <slot />

      <DialogClose
        aria-label="关闭"
        class="absolute right-2 top-2 inline-flex size-11 items-center justify-center rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground"
      >
        <X class="w-4 h-4" aria-hidden="true" />
        <span class="sr-only">关闭</span>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
