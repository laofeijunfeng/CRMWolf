<script setup lang="ts">
import { computed, ref } from 'vue'
import type { WorkflowNodeCategory, WorkflowNodeType } from './workflowNodeRegistry'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'

export interface WorkflowNodePickerItem {
  type: WorkflowNodeType
  label: string
  description: string
  category: WorkflowNodeCategory
  icon: unknown
  isTrigger: boolean
  disabledReason?: string
}

const props = defineProps<{ open: boolean; nodeTypes: readonly WorkflowNodePickerItem[]; triggerUsed: boolean }>()
const emit = defineEmits<{ 'update:open': [open: boolean]; select: [type: WorkflowNodeType] }>()
const search = ref('')
const categoryLabels: Record<WorkflowNodeCategory, string> = { trigger: '触发器', control: '控制', action: '动作' }
const categoryOrder: WorkflowNodeCategory[] = ['trigger', 'control', 'action']
const normalizedItems = computed(() => props.nodeTypes.map(item => ({
  ...item,
  disabledReason: item.disabledReason ?? (item.isTrigger && props.triggerUsed ? '工作流只能有一个触发器' : undefined),
})))
const filteredItems = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  if (query === '') return normalizedItems.value
  return normalizedItems.value.filter(item => [item.label, item.description, item.type].some(value => value.toLocaleLowerCase().includes(query)))
})
const groups = computed(() => categoryOrder.map(category => ({
  category,
  label: categoryLabels[category],
  items: filteredItems.value.filter(item => item.category === category),
})).filter(group => group.items.length > 0))

function close(): void { emit('update:open', false) }
function select(item: WorkflowNodePickerItem): void {
  if (item.disabledReason !== undefined) return
  emit('select', item.type)
  close()
}
function handleOpenChange(open: boolean): void {
  emit('update:open', open)
  if (!open) search.value = ''
}
function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') close()
}
</script>

<template>
  <Dialog :open="props.open" @update:open="handleOpenChange">
    <DialogContent class="w-[calc(100vw-2rem)] max-w-2xl overflow-hidden p-0">
      <div @keydown="handleKeydown">
        <DialogHeader class="border-b px-6 py-4">
          <DialogTitle>添加节点</DialogTitle>
          <DialogDescription>选择要插入工作流的节点类型</DialogDescription>
        </DialogHeader>
        <Command class="min-h-0" :should-filter="false">
          <CommandInput v-model="search" data-testid="workflow-node-picker-search" placeholder="搜索节点名称、描述或类型" />
          <CommandList class="max-h-[min(60vh,480px)] overflow-y-auto overscroll-contain p-3">
            <CommandEmpty>没有匹配的节点</CommandEmpty>
            <CommandGroup v-for="group in groups" :key="group.category" :heading="group.label">
              <CommandItem
                v-for="item in group.items"
                :key="item.type"
                :value="item.type"
                :disabled="item.disabledReason !== undefined"
                :aria-disabled="item.disabledReason !== undefined ? 'true' : undefined"
                :data-testid="`workflow-picker-item-${item.type}`"
                class="items-start py-3"
                @select="select(item)"
              >
                <component :is="item.icon" class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <span class="min-w-0">
                  <span class="block font-medium">{{ item.label }}</span>
                  <span class="mt-0.5 block text-xs text-muted-foreground">{{ item.description }}</span>
                  <span v-if="item.disabledReason" class="mt-1 block text-xs text-muted-foreground">{{ item.disabledReason }}</span>
                </span>
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </div>
    </DialogContent>
  </Dialog>
</template>
