<script setup lang="ts">
import type { WithClassAsProps } from "./interface"
import { ArrowLeft } from "lucide-vue-next"
import { cn } from "@/lib/utils"
import { Button } from '@/components/ui/button'
import { useCarousel } from "./useCarousel"

const props = defineProps<WithClassAsProps>()

const { orientation, canScrollPrev, scrollPrev } = useCarousel()
</script>

<template>
  <Button
    :disabled="!canScrollPrev"
    size="icon"
    aria-label="上一张"
    :class="cn(
      'touch-manipulation absolute size-11 rounded-full p-0',
      orientation === 'horizontal'
        ? '-left-[54px] top-1/2 -translate-y-1/2'
        : '-top-[54px] left-1/2 -translate-x-1/2 rotate-90',
      props.class,
    )"
    variant="outline"
    @click="scrollPrev"
  >
    <slot>
      <ArrowLeft class="h-4 w-4 text-current" aria-hidden="true" />
    </slot>
  </Button>
</template>
