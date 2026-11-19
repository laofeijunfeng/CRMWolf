<script setup lang="ts">
import type { AlertDialogContentEmits, AlertDialogContentProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { computed } from "vue"
import { reactiveOmit } from "@vueuse/core"
import {
  AlertDialogContent,
  AlertDialogOverlay,
  AlertDialogPortal,
  useForwardPropsEmits,
} from "reka-ui"
import { cn, omitUndefined } from "@/lib/utils"

// topmost：全局确认层，必须压过任何（含 elevated）Dialog / Sheet，不依赖 DOM 顺序。
const props = defineProps<AlertDialogContentProps & { class?: HTMLAttributes["class"], elevated?: boolean, topmost?: boolean }>()
const emits = defineEmits<AlertDialogContentEmits>()

const delegatedProps = reactiveOmit(props, "class", "elevated", "topmost")
const overlayZ = computed(() => props.topmost ? "z-[1300]" : props.elevated ? "z-[1200]" : "z-[1000]")
const contentZ = computed(() => props.topmost ? "z-[1301]" : props.elevated ? "z-[1201]" : "z-[1000]")

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <AlertDialogPortal>
    <AlertDialogOverlay
      :class="cn('fixed inset-0 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0', overlayZ)"
    />
    <AlertDialogContent
      v-bind="omitUndefined(forwarded)"
      :class="
        cn(
          contentZ,
          'fixed left-1/2 top-1/2 grid w-[calc(100vw-2rem)] max-w-[var(--dialog-w-sm)] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-xl border bg-background p-6 shadow-3 duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]',
          props.class,
        )
      "
    >
      <slot />
    </AlertDialogContent>
  </AlertDialogPortal>
</template>
