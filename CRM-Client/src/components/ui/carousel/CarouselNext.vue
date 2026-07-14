<script setup lang="ts">
import type { WithClassAsProps } from "./interface"
import { ArrowRight } from "lucide-vue-next"
import { cn } from "@/lib/utils"
import { Button } from '@/components/ui/button'
import { useCarousel } from "./useCarousel"

const props = defineProps<WithClassAsProps>()

const { orientation, canScrollNext, scrollNext } = useCarousel()
</script>

<template>
  <Button
    :disabled="!canScrollNext"
    size="icon"
    aria-label="下一张"
    :class="cn(
      'touch-manipulation absolute size-11 rounded-full p-0',
      orientation === 'horizontal'
        ? '-right-[54px] top-1/2 -translate-y-1/2'
        : '-bottom-[54px] left-1/2 -translate-x-1/2 rotate-90',
      props.class,
    )"
    variant="outline"
    @click="scrollNext"
  >
    <slot>
      <ArrowRight class="h-4 w-4 text-current" aria-hidden="true" />
    </slot>
  </Button>
</template>
