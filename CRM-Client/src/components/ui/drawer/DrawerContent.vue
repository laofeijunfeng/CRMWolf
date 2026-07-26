<script lang="ts" setup>
import type { DialogContentEmits, DialogContentProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { useForwardPropsEmits } from "reka-ui"
import { DrawerContent, DrawerPortal } from "vaul-vue"
import { cn } from "@/lib/utils"
import DrawerOverlay from "./DrawerOverlay.vue"

const props = withDefaults(defineProps<DialogContentProps & {
  class?: HTMLAttributes["class"]
  overlayClass?: HTMLAttributes["class"]
  portal?: boolean
  showOverlay?: boolean
}>(), {
  portal: true,
  showOverlay: true,
})
const emits = defineEmits<DialogContentEmits>()

const delegatedProps = reactiveOmit(props, "class", "overlayClass", "portal", "showOverlay")
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <DrawerPortal v-if="props.portal">
    <DrawerOverlay v-if="props.showOverlay" :class="props.overlayClass" />
    <DrawerContent
      v-bind="forwarded" :class="cn(
        'fixed inset-x-0 bottom-0 z-[201] mt-24 flex h-auto flex-col rounded-t-[10px] border bg-background',
        props.class,
      )"
    >
      <div class="mx-auto mt-4 h-2 w-[100px] rounded-full bg-muted" />
      <slot />
    </DrawerContent>
  </DrawerPortal>
  <template v-else>
    <DrawerOverlay v-if="props.showOverlay" :class="props.overlayClass" />
    <DrawerContent
      v-bind="forwarded" :class="cn(
        'absolute inset-x-0 bottom-0 z-[201] mt-24 flex h-auto flex-col rounded-t-[10px] border bg-background',
        props.class,
      )"
    >
      <div class="mx-auto mt-4 h-2 w-[100px] rounded-full bg-muted" />
      <slot />
    </DrawerContent>
  </template>
</template>
