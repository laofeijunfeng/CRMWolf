<script setup lang="ts">
import { Sheet } from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'

withDefaults(defineProps<{
  open: boolean
  embedded?: boolean | undefined
  elevated?: boolean | undefined
}>(), { embedded: false, elevated: false })

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()
</script>

<template>
  <div v-if="embedded" class="flex flex-1 flex-col min-h-0 min-w-0 overflow-hidden">
    <slot />
  </div>
  <Sheet v-else :open="open" @update:open="emit('update:open', $event)">
    <DetailSheetContent v-bind="elevated ? { elevated: true } : {}">
      <slot />
    </DetailSheetContent>
  </Sheet>
</template>
