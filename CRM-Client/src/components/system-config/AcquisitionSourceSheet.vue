<script setup lang="ts">
import {
  Sheet,
  SheetContent,
} from '@/components/ui/sheet'
import AcquisitionSourcePanel from './AcquisitionSourcePanel.vue'

interface Props {
  open: boolean
  action?: 'create' | 'edit' | undefined
  recordId?: string | undefined
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()
</script>

<template>
  <Sheet :open="open" @update:open="emit('update:open', $event)">
    <SheetContent class="p-0 sm:max-w-2xl">
      <AcquisitionSourcePanel :active="open" :action="props.action" :record-id="props.recordId" />
    </SheetContent>
  </Sheet>
</template>
