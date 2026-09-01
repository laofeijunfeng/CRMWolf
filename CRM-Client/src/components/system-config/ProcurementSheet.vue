<script setup lang="ts">
import { Sheet, SheetContent } from '@/components/ui/sheet'
import ProcurementMethodsPanel from './ProcurementMethodsPanel.vue'

interface Props {
  open: boolean
  action?: 'create' | 'edit' | undefined
  recordId?: string | undefined
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()
</script>

<template>
  <Sheet :open="props.open" @update:open="emit('update:open', $event)">
    <SheetContent class="p-0 sm:max-w-2xl">
      <ProcurementMethodsPanel
        :active="props.open"
        :action="props.action"
        :record-id="props.recordId"
      />
    </SheetContent>
  </Sheet>
</template>
