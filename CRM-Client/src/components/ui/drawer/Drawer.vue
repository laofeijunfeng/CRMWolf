<script lang="ts" setup>
import type { DrawerRootEmits, DrawerRootProps } from "vaul-vue"
import { computed } from "vue"
import { useForwardPropsEmits } from "reka-ui"
import { DrawerRoot } from "vaul-vue"
import { omitUndefined } from "@/lib/utils"

const props = withDefaults(defineProps<DrawerRootProps>(), {
  shouldScaleBackground: true,
})

const emits = defineEmits<DrawerRootEmits>()

const forwardedProps = computed(() => Object.fromEntries(
  Object.entries(props).filter(([, value]) => value !== undefined)
) as DrawerRootProps)
const forwarded = useForwardPropsEmits(forwardedProps, emits)
</script>

<template>
  <DrawerRoot v-bind="omitUndefined(forwarded)">
    <slot />
  </DrawerRoot>
</template>
